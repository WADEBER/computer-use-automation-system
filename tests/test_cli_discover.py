import json

import pytest

from computer_use_automation_system import cli
from computer_use_automation_system.artifact.models import Artifact
from computer_use_automation_system.discovery.artifact_builder import StepSource, build_artifact
from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    RunStatus,
    StepRecord,
)
from computer_use_automation_system.safety.models import PolicyConfig

EXIT_BY_STATUS = {
    RunStatus.GOAL_REACHED: 0,
    RunStatus.BLOCKED: 10,
    RunStatus.NEEDS_APPROVAL: 11,
    RunStatus.MAX_STEPS: 12,
    RunStatus.TIMEOUT: 13,
    RunStatus.DEAD_END: 14,
    RunStatus.LLM_ERROR: 15,
}


def _minimal_artifact() -> Artifact:
    record = StepRecord(
        step_index=1,
        action="navigate",
        value_preview="http://127.0.0.1:5000/",
        reason="open the app",
        outcome="ok",
        snapshot_hash="abc",
        elapsed_ms=0,
        max_steps=15,
    )
    return build_artifact("open the app", "http://127.0.0.1:5000/", [StepSource(record=record)])


def test_discover_without_flags_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["discover"])
    assert exc.value.code == 2


def test_empty_goal_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["discover", "--goal", "   ", "--entry", "http://127.0.0.1:5000/"])
    assert exc.value.code == 2


def test_invalid_entry_url_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["discover", "--goal", "g", "--entry", "ftp://example/x"])
    assert exc.value.code == 2


def test_non_positive_max_steps_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["discover", "--goal", "g", "--entry", "http://127.0.0.1:5000/", "--max-steps", "0"]
        )
    assert exc.value.code == 2


def test_non_positive_total_timeout_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "discover",
                "--goal",
                "g",
                "--entry",
                "http://127.0.0.1:5000/",
                "--total-timeout-ms",
                "0",
            ]
        )
    assert exc.value.code == 2


def test_total_timeout_flag_reaches_the_discovery_config(monkeypatch, tmp_path) -> None:
    captured: dict[str, DiscoveryConfig] = {}

    def fake_execute(config, policy, logger):
        captured["config"] = config
        return DiscoveryResult(status=RunStatus.TIMEOUT, steps=[])

    monkeypatch.setattr(cli, "_execute", fake_execute)
    # --artifact-out must resolve inside the working directory (SEC-505).
    monkeypatch.chdir(tmp_path)
    code = cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--total-timeout-ms",
            "600000",
            "--artifact-out",
            str(tmp_path / "a.json"),
            "--log-out",
            str(tmp_path / "s.jsonl"),
        ]
    )
    assert code == 13
    assert captured["config"].total_timeout_ms == 600000


def test_each_status_maps_to_its_exit_code(monkeypatch, tmp_path) -> None:
    for status, expected in EXIT_BY_STATUS.items():
        artifact = _minimal_artifact() if status is RunStatus.GOAL_REACHED else None

        def fake_execute(config, policy, logger, *, status=status, artifact=artifact):
            return DiscoveryResult(status=status, steps=[], artifact=artifact)

        monkeypatch.setattr(cli, "_execute", fake_execute)
        # --artifact-out must resolve inside the working directory (SEC-505).
        monkeypatch.chdir(tmp_path)
        code = cli.main(
            [
                "discover",
                "--goal",
                "open the app",
                "--entry",
                "http://127.0.0.1:5000/",
                "--artifact-out",
                str(tmp_path / "a.json"),
                "--log-out",
                str(tmp_path / "s.jsonl"),
            ]
        )
        assert code == expected, f"{status} -> {code}, expected {expected}"


def test_stdout_receives_one_json_line_per_step(monkeypatch, tmp_path, capsys) -> None:
    def fake_execute(config, policy, logger):
        record = StepRecord(
            step_index=1,
            action="click",
            element_ref=1,
            reason="open detail",
            outcome="ok",
            snapshot_hash="abc",
            elapsed_ms=5,
            max_steps=config.max_steps,
            policy_decision={"decision": "allow", "reason": "in perimeter"},
        )
        logger.write_step(record)
        logger.write_summary(RunStatus.MAX_STEPS, steps=1)
        return DiscoveryResult(status=RunStatus.MAX_STEPS, steps=[record])

    monkeypatch.setattr(cli, "_execute", fake_execute)
    code = cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--log-out",
            str(tmp_path / "s.jsonl"),
        ]
    )
    assert code == 12
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    step_payload = json.loads(lines[0])
    assert step_payload["step_index"] == 1
    assert step_payload["action"] == "click"
    summary_payload = json.loads(lines[1])
    assert summary_payload["status"] == "max_steps"


def test_flags_reach_the_discovery_config(monkeypatch, tmp_path) -> None:
    captured: dict[str, DiscoveryConfig] = {}

    def fake_execute(config, policy, logger):
        captured["config"] = config
        return DiscoveryResult(status=RunStatus.TIMEOUT, steps=[])

    monkeypatch.setattr(cli, "_execute", fake_execute)
    # --artifact-out must resolve inside the working directory (SEC-505).
    monkeypatch.chdir(tmp_path)
    cli.main(
        [
            "discover",
            "--goal",
            "find the balance",
            "--entry",
            "http://127.0.0.1:5000/",
            "--max-steps",
            "3",
            "--artifact-out",
            str(tmp_path / "art.json"),
            "--log-out",
            str(tmp_path / "log.jsonl"),
        ]
    )
    config = captured["config"]
    assert config.goal == "find the balance"
    assert config.max_steps == 3
    assert config.artifact_out == tmp_path / "art.json"
    assert config.log_out == tmp_path / "log.jsonl"


def test_artifact_out_outside_the_working_tree_exits_2(monkeypatch, tmp_path, capsys) -> None:
    """SEC-505: the CLI refuses to write the artifact outside the working
    tree before any browser or LLM work starts."""

    def must_not_run(config, policy, logger):
        raise AssertionError("the run must never start")

    monkeypatch.setattr(cli, "_execute", must_not_run)
    code = cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--artifact-out",
            str(tmp_path / "outside.json"),
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "--artifact-out must stay inside the working directory" in captured.err
    assert "Traceback" not in captured.err


def test_policy_comes_from_the_single_config_file(monkeypatch, tmp_path) -> None:
    captured: dict[str, PolicyConfig] = {}

    def fake_execute(config, policy, logger):
        captured["policy"] = policy
        return DiscoveryResult(status=RunStatus.TIMEOUT, steps=[])

    monkeypatch.setattr(cli, "_execute", fake_execute)
    cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--log-out",
            str(tmp_path / "s.jsonl"),
        ]
    )
    assert captured["policy"].allowed_origins == ["http://127.0.0.1:5000/"]
    assert captured["policy"].redaction.patterns


def test_no_args_prints_help_instead_of_running(capsys) -> None:
    code = cli.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "computer-use-automation-system" in out
    assert "{discover,replay}" in out


def test_help_flag_prints_help(capsys) -> None:
    code = cli.main(["--help"])
    assert code == 0
    out = capsys.readouterr().out
    assert "discover" in out
    assert "replay" in out


def test_unknown_command_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2


def test_policy_read_error_exits_2_without_traceback(monkeypatch, tmp_path, capsys) -> None:
    def broken_policy():
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(cli, "load_policy", broken_policy)
    code = cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--log-out",
            str(tmp_path / "s.jsonl"),
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "discover: invalid policy config" in captured.err
    assert "Traceback" not in captured.err


def test_runtime_error_exits_1_with_single_redacted_line(monkeypatch, tmp_path, capsys) -> None:
    def exploding_execute(config, policy, logger):
        raise RuntimeError("chrome went away\nsecond line of noise")

    monkeypatch.setattr(cli, "_execute", exploding_execute)
    code = cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--log-out",
            str(tmp_path / "s.jsonl"),
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert "discover: run failed: RuntimeError: chrome went away" in captured.err
    assert "second line of noise" not in captured.err
    assert "Traceback" not in captured.err


def test_step_logger_used_by_cli_writes_to_log_path(monkeypatch, tmp_path) -> None:
    def fake_execute(config, policy, logger):
        assert isinstance(logger, StepLogger)
        assert logger.log_path == config.log_out
        return DiscoveryResult(status=RunStatus.TIMEOUT, steps=[])

    monkeypatch.setattr(cli, "_execute", fake_execute)
    cli.main(
        [
            "discover",
            "--goal",
            "g",
            "--entry",
            "http://127.0.0.1:5000/",
            "--log-out",
            str(tmp_path / "nested" / "s.jsonl"),
        ]
    )
