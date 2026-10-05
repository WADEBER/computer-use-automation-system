"""CLI entry point: `discover` (Phase 5, HU-1) and `replay` (Phase 6, HU-5).

argparse (stdlib) only, no extra dependencies. Exit codes:
- discover: 0 goal_reached, 10 blocked, 11 needs_approval, 12 max_steps,
  13 timeout, 14 dead_end, 15 llm_error, 1 unexpected runtime error
  (browser/LLM infrastructure), 2 usage or config error.
- replay: 0 success, 10 blocked, 11 needs_approval, 1 other failure,
  2 usage error / unreadable or invalid artifact.
argparse usage errors always exit 2. No args or --help prints the help.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from computer_use_automation_system.discovery.llm_client import OllamaClient
from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    RunStatus,
)
from computer_use_automation_system.discovery.runner import run_discovery
from computer_use_automation_system.replay.engine import replay as run_replay
from computer_use_automation_system.replay.handoff import Operator
from computer_use_automation_system.replay.logging_runner import ReplayLogger
from computer_use_automation_system.replay.models import (
    HandoffDecision,
    HandoffRequest,
    OperatorResponse,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)
from computer_use_automation_system.replay.taxonomy import load_taxonomy
from computer_use_automation_system.safety.models import PolicyConfig, RedactionConfig
from computer_use_automation_system.safety.policy import load_policy
from computer_use_automation_system.safety.redaction import redact_text

EXIT_BY_STATUS: dict[RunStatus, int] = {
    RunStatus.GOAL_REACHED: 0,
    RunStatus.BLOCKED: 10,
    RunStatus.NEEDS_APPROVAL: 11,
    RunStatus.MAX_STEPS: 12,
    RunStatus.TIMEOUT: 13,
    RunStatus.DEAD_END: 14,
    RunStatus.LLM_ERROR: 15,
}

REPLAY_EXIT_BY_STAGE: dict[ReplayStage, int] = {
    ReplayStage.POLICY: 10,  # refined per policy_kind below
    ReplayStage.INPUT_VALIDATION: 1,
    ReplayStage.STEP: 1,
    ReplayStage.CHECKPOINT: 1,
    ReplayStage.OUTPUT_VALIDATION: 1,
}


def _non_empty(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def _http_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise argparse.ArgumentTypeError("must be an http(s) URL")
    return value


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _key_value(value: str) -> tuple[str, str]:
    key, sep, val = value.partition("=")
    if not sep or not key.strip():
        raise argparse.ArgumentTypeError("must be in the form key=value")
    return key.strip(), val


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="computer-use-automation-system")
    subparsers = parser.add_subparsers(dest="command")
    discover = subparsers.add_parser(
        "discover", help="run the discovery loop and emit a typed artifact"
    )
    discover.add_argument("--goal", required=True, type=_non_empty)
    discover.add_argument("--entry", required=True, type=_http_url)
    discover.add_argument("--max-steps", type=_positive_int, default=15)
    discover.add_argument(
        "--total-timeout-ms",
        type=_positive_int,
        default=None,
        help="global budget for the whole discovery run (default 300000)",
    )
    discover.add_argument("--artifact-out", default=None)
    discover.add_argument("--log-out", default=None)
    replay_cmd = subparsers.add_parser(
        "replay", help="deterministically replay a typed artifact (no LLM)"
    )
    replay_cmd.add_argument("--artifact", required=True, type=_non_empty)
    replay_cmd.add_argument(
        "--input", required=True, action="append", type=_key_value, dest="inputs"
    )
    replay_cmd.add_argument("--approved", action="store_true")
    replay_cmd.add_argument("--max-timeout-ms", type=_positive_int, default=None)
    replay_cmd.add_argument(
        "--log-out",
        default=None,
        help="write a redacted JSONL event log of this run (Phase 9 evidence)",
    )
    replay_cmd.add_argument(
        "--interactive",
        action="store_true",
        help="pause on handoff triggers and prompt an operator on stdin",
    )
    return parser


class PromptOperator:
    """Interactive operator for `replay --interactive` (Phase 8, HU-6).

    Prints the handoff package summary to stdout and reads one decision from
    stdin (case-insensitive: resume / finish / abort). Invalid input or EOF
    falls back to abort, which never assumes approval.
    """

    def intervene(self, request: HandoffRequest) -> OperatorResponse:
        print(f"handoff pause: trigger={request.trigger} stage={request.stage.value}")
        step = f" step={request.step_id}" if request.step_id is not None else ""
        action = f" action={request.action}" if request.action is not None else ""
        print(f"capability={request.capability}{step}{action}")
        safe_reason = request.reason.replace("\r", "\\r").replace("\n", "\\n")
        print(f"reason={safe_reason}")
        print(f"observed elements={len(request.snapshot)}")
        try:
            raw = input("decision [resume|finish|abort]: ")
        except (EOFError, KeyboardInterrupt, UnicodeDecodeError, OSError):
            print("handoff: no input available; aborting")
            return OperatorResponse(decision="abort")
        choices: dict[str, HandoffDecision] = {
            "resume": "resume",
            "finish": "finish",
            "abort": "abort",
        }
        picked = choices.get(raw.strip().lower())
        if picked is None:
            print("handoff: invalid decision; aborting")
            return OperatorResponse(decision="abort")
        return OperatorResponse(decision=picked)


def _execute(config: DiscoveryConfig, policy: PolicyConfig, logger: StepLogger) -> DiscoveryResult:
    """Wire the real dependencies (Chrome + Ollama). Tests monkeypatch this."""
    from computer_use_automation_system.discovery.selenium_driver import build_webdriver

    driver = build_webdriver(timeout_s=max(1.0, config.step_timeout_ms / 1000))
    client = OllamaClient(model=config.ollama_model, base_url=config.ollama_base_url)
    try:
        return run_discovery(config, driver, client, policy, logger=logger)
    finally:
        driver.quit()


def _execute_replay(
    artifact,
    inputs: dict[str, object],
    policy: PolicyConfig,
    *,
    approved: bool,
    max_timeout_ms: int | None,
    operator: Operator | None = None,
    events: Callable[[dict[str, object]], None] | None = None,
) -> ReplayResult:
    """Wire the real browser (Chrome, no LLM). Tests monkeypatch this."""
    from computer_use_automation_system.discovery.selenium_driver import build_webdriver

    driver = build_webdriver()
    try:
        return run_replay(
            artifact,
            inputs,
            driver,
            policy,
            approved=approved,
            step_timeout_ms=max_timeout_ms,
            operator=operator,
            events=events,
        )
    finally:
        driver.quit()


def _replay_exit_code(result: ReplayResult) -> int:
    if result.status is ReplayStatus.SUCCESS:
        return 0
    error = result.error
    if error is None:  # pragma: no cover - model invariants forbid this
        return 1
    if error.stage is ReplayStage.POLICY:
        return 11 if error.policy_kind == "needs_approval" else 10
    return REPLAY_EXIT_BY_STAGE[error.stage]


def _print_replay_result(result: ReplayResult, redaction: RedactionConfig) -> None:
    if result.status is ReplayStatus.SUCCESS:
        print(f"replay success: {result.capability_id} v{result.version}")
        print(f"steps_executed={result.steps_executed} elapsed_ms={result.elapsed_ms}")
        for key in sorted(result.outputs or {}):
            value = redact_text(str(result.outputs[key]), redaction)  # type: ignore[index]
            print(f"output {key}={value}")
        return
    error = result.error
    if error is None:  # pragma: no cover - model invariants forbid this
        print("replay failure: unknown error")
        return
    step = f" step={error.step_id}" if error.step_id is not None else ""
    kind = f" {error.policy_kind}" if error.policy_kind else ""
    category = f" {error.failure_category}" if error.failure_category else ""
    print(f"replay failure: stage={error.stage.value}{step}{kind}{category} {error.message}")


def _run_replay_command(namespace: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from computer_use_automation_system.artifact.models import Artifact

    try:
        load_taxonomy()  # eager validation: bad config -> exit 2, no hot crash
    except OSError as exc:
        detail = exc.strerror or "read error"
        print(f"replay: invalid taxonomy config: {detail}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        # Never echo config values back (CWE-209): only field names.
        fields = ", ".join(".".join(str(part) for part in err["loc"]) for err in exc.errors())
        print(f"replay: invalid taxonomy config (fields: {fields})", file=sys.stderr)
        return 2

    artifact_path = Path(namespace.artifact)
    try:
        artifact = Artifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        print(f"replay: unreadable or invalid artifact: {exc}", file=sys.stderr)
        return 2

    inputs = dict(namespace.inputs)
    try:
        policy = load_policy()
    except OSError as exc:
        detail = exc.strerror or "read error"
        print(f"replay: invalid policy config: {detail}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        # Never echo config values back (CWE-209): only field names.
        fields = ", ".join(".".join(str(part) for part in err["loc"]) for err in exc.errors())
        print(f"replay: invalid policy config (fields: {fields})", file=sys.stderr)
        return 2
    operator: Operator | None = PromptOperator() if namespace.interactive else None
    logger: ReplayLogger | None = None
    if namespace.log_out:
        logger = ReplayLogger(namespace.log_out, policy.redaction)
        logger.write(
            {
                "event": "start",
                "capability_id": artifact.capability_id,
                "version": artifact.version,
                "input_keys": sorted(inputs),
            }
        )
    if operator is None and logger is None:
        # Keep the legacy call shape byte-for-byte when --interactive and
        # --log-out are off.
        result = _execute_replay(
            artifact,
            inputs,
            policy,
            approved=namespace.approved,
            max_timeout_ms=namespace.max_timeout_ms,
        )
    else:
        extras: dict[str, Any] = {}
        if operator is not None:
            extras["operator"] = operator
        if logger is not None:
            extras["events"] = logger.write
        result = _execute_replay(
            artifact,
            inputs,
            policy,
            approved=namespace.approved,
            max_timeout_ms=namespace.max_timeout_ms,
            **extras,
        )
    if logger is not None:
        logger.write({"event": "result", **result.model_dump(mode="json")})
    _print_replay_result(result, policy.redaction)
    return _replay_exit_code(result)


def _run_discover_command(namespace: argparse.Namespace) -> int:
    """Build the config/policy, run the loop and map status to an exit code.

    Config problems exit 2 (like replay); unexpected infrastructure errors
    (browser, Ollama connection) exit 1 with a single redacted line instead
    of a raw traceback.
    """
    from pydantic import ValidationError

    overrides: dict = {}
    if namespace.artifact_out:
        overrides["artifact_out"] = Path(namespace.artifact_out)
    if namespace.log_out:
        overrides["log_out"] = Path(namespace.log_out)
    if namespace.total_timeout_ms:
        overrides["total_timeout_ms"] = namespace.total_timeout_ms
    try:
        config = DiscoveryConfig(
            goal=namespace.goal,
            entry_url=namespace.entry,
            max_steps=namespace.max_steps,
            **overrides,
        )
    except ValidationError as exc:
        # Never echo config values back (CWE-209): only field names.
        fields = ", ".join(".".join(str(part) for part in err["loc"]) for err in exc.errors())
        print(f"discover: invalid configuration (fields: {fields})", file=sys.stderr)
        return 2

    try:
        policy = load_policy()
    except OSError as exc:
        detail = exc.strerror or "read error"
        print(f"discover: invalid policy config: {detail}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        # Never echo config values back (CWE-209): only field names.
        fields = ", ".join(".".join(str(part) for part in err["loc"]) for err in exc.errors())
        print(f"discover: invalid policy config (fields: {fields})", file=sys.stderr)
        return 2

    logger = StepLogger(config.log_out, policy.redaction)
    try:
        result = _execute(config, policy, logger)
    except Exception as exc:  # noqa: BLE001 - boundary: one clean line, no traceback
        first_line = str(exc).replace("\r", " ").split("\n", 1)[0]
        detail = f"{type(exc).__name__}: {first_line}"[:500]
        message = redact_text(detail, policy.redaction)
        print(f"discover: run failed: {message}", file=sys.stderr)
        return 1
    return EXIT_BY_STATUS[result.status]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    parser = build_parser()
    if not args or args[0] in ("--help", "-h"):
        parser.print_help()
        return 0

    from dotenv import load_dotenv

    load_dotenv()
    namespace = parser.parse_args(args)
    try:
        if namespace.command == "replay":
            return _run_replay_command(namespace)
        if namespace.command != "discover":
            parser.error("the following arguments are required: discover")
        return _run_discover_command(namespace)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
