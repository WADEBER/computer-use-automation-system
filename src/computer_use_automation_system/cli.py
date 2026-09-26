"""CLI entry point: the `discover` subcommand (Phase 5, HU-1).

argparse (stdlib) only, no extra dependencies. Exit codes map the final
`RunStatus`: 0 goal_reached, 10 blocked, 11 needs_approval, 12 max_steps,
13 timeout, 14 dead_end, 15 llm_error; argparse usage errors exit 2.
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


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "discover" not in args:
        print("Hello from computer-use-automation-system!")
        return 0

    from dotenv import load_dotenv

    load_dotenv()
    parser = build_parser()
    namespace = parser.parse_args(args)
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
