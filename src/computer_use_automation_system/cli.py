"""CLI entry point: `discover` (Phase 5, HU-1) and `replay` (Phase 6, HU-5).

argparse (stdlib) only, no extra dependencies. Exit codes:
- discover: 0 goal_reached, 10 blocked, 11 needs_approval, 12 max_steps,
  13 timeout, 14 dead_end, 15 llm_error.
- replay: 0 success, 10 blocked, 11 needs_approval, 1 other failure,
  2 usage error / unreadable or invalid artifact.
argparse usage errors always exit 2.
"""

import argparse
import sys
from pathlib import Path

from computer_use_automation_system.discovery.llm_client import OllamaClient
from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    RunStatus,
)
from computer_use_automation_system.discovery.runner import run_discovery
from computer_use_automation_system.replay.engine import replay as run_replay
from computer_use_automation_system.replay.models import ReplayResult, ReplayStage, ReplayStatus
from computer_use_automation_system.safety.models import PolicyConfig
from computer_use_automation_system.safety.policy import load_policy

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
    return parser


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


def _print_replay_result(result: ReplayResult) -> None:
    if result.status is ReplayStatus.SUCCESS:
        print(f"replay success: {result.capability_id} v{result.version}")
        print(f"steps_executed={result.steps_executed} elapsed_ms={result.elapsed_ms}")
        for key in sorted(result.outputs or {}):
            print(f"output {key}={result.outputs[key]}")  # type: ignore[index]
        return
    error = result.error
    if error is None:  # pragma: no cover - model invariants forbid this
        print("replay failure: unknown error")
        return
    step = f" step={error.step_id}" if error.step_id is not None else ""
    kind = f" {error.policy_kind}" if error.policy_kind else ""
    print(f"replay failure: stage={error.stage.value}{step}{kind} {error.message}")


def _run_replay_command(namespace: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from computer_use_automation_system.artifact.models import Artifact

    artifact_path = Path(namespace.artifact)
    try:
        artifact = Artifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        print(f"replay: unreadable or invalid artifact: {exc}", file=sys.stderr)
        return 2

    inputs = dict(namespace.inputs)
    policy = load_policy()
    result = _execute_replay(
        artifact,
        inputs,
        policy,
        approved=namespace.approved,
        max_timeout_ms=namespace.max_timeout_ms,
    )
    _print_replay_result(result)
    return _replay_exit_code(result)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] not in ("discover", "replay"):
        print("Hello from computer-use-automation-system!")
        return 0

    from dotenv import load_dotenv

    load_dotenv()
    parser = build_parser()
    namespace = parser.parse_args(args)
    if namespace.command == "replay":
        return _run_replay_command(namespace)
    if namespace.command != "discover":
        parser.error("the following arguments are required: discover")

    overrides: dict = {}
    if namespace.artifact_out:
        overrides["artifact_out"] = Path(namespace.artifact_out)
    if namespace.log_out:
        overrides["log_out"] = Path(namespace.log_out)
    config = DiscoveryConfig(
        goal=namespace.goal,
        entry_url=namespace.entry,
        max_steps=namespace.max_steps,
        **overrides,
    )
    policy = load_policy()
    logger = StepLogger(config.log_out, policy.redaction)
    result = _execute(config, policy, logger)
    return EXIT_BY_STATUS[result.status]
