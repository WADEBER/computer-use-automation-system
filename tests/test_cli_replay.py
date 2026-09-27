"""Phase 6, HU-5: the `replay` subcommand — flags, exit codes, stderr
diagnostics, monkeypatched execution seam, and the untouched placeholder."""

import pytest

from computer_use_automation_system import cli
from computer_use_automation_system.replay.models import (
    ReplayError,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)

FIXTURE = "tests/fixtures/valid_artifact.json"


def _success() -> ReplayResult:
    return ReplayResult(
        status=ReplayStatus.SUCCESS,
        capability_id="lookup_member_balance",
        version="1.0.0",
        outputs={"savings_balance": "15200.00"},
        steps_executed=6,
        elapsed_ms=42,
    )


def _failure(stage: ReplayStage, *, step_id: int | None = None, policy_kind=None) -> ReplayResult:
    return ReplayResult(
        status=ReplayStatus.FAILURE,
        capability_id="lookup_member_balance",
        version="1.0.0",
        steps_executed=0,
        error=ReplayError(stage=stage, step_id=step_id, policy_kind=policy_kind, message="boom"),
    )


def _run(args: list[str]) -> int:
    return cli.main(["replay", *args])


def test_missing_artifact_flag_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["--input", "member_id=M-1001"])
    assert exc.value.code == 2


def test_missing_input_flag_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["--artifact", FIXTURE])
    assert exc.value.code == 2


def test_malformed_input_pair_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["--artifact", FIXTURE, "--input", "member_id"])
    assert exc.value.code == 2


def test_unreadable_artifact_exits_2_with_stderr_message(tmp_path, capsys) -> None:
    code = _run(["--artifact", str(tmp_path / "missing.json"), "--input", "member_id=M-1"])
    assert code == 2
    captured = capsys.readouterr()
    assert "artifact" in captured.err.lower()
    assert "Traceback" not in captured.err


def test_invalid_artifact_exits_2_with_stderr_message(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"capability_id": ""}', encoding="utf-8")
    code = _run(["--artifact", str(bad), "--input", "member_id=M-1"])
    assert code == 2
    captured = capsys.readouterr()
    assert "artifact" in captured.err.lower()
    assert "Traceback" not in captured.err


def test_success_exits_0_and_prints_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_execute_replay", lambda *a, **k: _success())
    code = _run(["--artifact", FIXTURE, "--input", "member_id=M-1001"])
    assert code == 0
    out = capsys.readouterr().out
    assert "lookup_member_balance" in out
    assert "1.0.0" in out
    assert "savings_balance" in out


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_failure(ReplayStage.POLICY, step_id=1, policy_kind="blocked"), 10),
        (_failure(ReplayStage.POLICY, step_id=1, policy_kind="needs_approval"), 11),
        (_failure(ReplayStage.STEP, step_id=2), 1),
        (_failure(ReplayStage.CHECKPOINT, step_id=6), 1),
        (_failure(ReplayStage.INPUT_VALIDATION), 1),
        (_failure(ReplayStage.OUTPUT_VALIDATION), 1),
    ],
)
def test_failure_stages_map_to_exit_codes(monkeypatch, capsys, result, expected) -> None:
    monkeypatch.setattr(cli, "_execute_replay", lambda *a, **k: result)
    code = _run(["--artifact", FIXTURE, "--input", "member_id=M-1001"])
    assert code == expected
    out = capsys.readouterr().out
    assert result.error.stage.value in out
    assert "boom" in out


def test_flags_reach_the_execution_seam(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute(artifact, inputs, policy, *, approved, max_timeout_ms):
        captured.update(
            artifact=artifact,
            inputs=inputs,
            policy=policy,
            approved=approved,
            max_timeout_ms=max_timeout_ms,
        )
        return _success()

    monkeypatch.setattr(cli, "_execute_replay", fake_execute)
    code = _run(
        [
            "--artifact",
            FIXTURE,
            "--input",
            "member_id=M-1001",
            "--approved",
            "--max-timeout-ms",
            "30000",
        ]
    )
    assert code == 0
    assert captured["artifact"].capability_id == "lookup_member_balance"
    assert captured["inputs"] == {"member_id": "M-1001"}
    assert captured["approved"] is True
    assert captured["max_timeout_ms"] == 30000
    assert captured["policy"].allowed_origins


def test_defaults_leave_approval_off_and_no_timeout(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute(artifact, inputs, policy, *, approved, max_timeout_ms):
        captured.update(approved=approved, max_timeout_ms=max_timeout_ms)
        return _success()

    monkeypatch.setattr(cli, "_execute_replay", fake_execute)
    assert _run(["--artifact", FIXTURE, "--input", "member_id=M-1"]) == 0
    assert captured == {"approved": False, "max_timeout_ms": None}


def test_repeatable_inputs_merge(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute(artifact, inputs, policy, *, approved, max_timeout_ms):
        captured["inputs"] = inputs
        return _success()

    monkeypatch.setattr(cli, "_execute_replay", fake_execute)
    _run(
        [
            "--artifact",
            FIXTURE,
            "--input",
            "member_id=M-1001",
            "--input",
            "region=eu",
        ]
    )
    assert captured["inputs"] == {"member_id": "M-1001", "region": "eu"}


def test_placeholder_still_prints_without_replay_args(capsys) -> None:
    assert cli.main([]) == 0
    assert "computer-use-automation-system" in capsys.readouterr().out
