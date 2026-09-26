import io
import json

from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import RunStatus, StepRecord
from computer_use_automation_system.safety.models import RedactionConfig, RedactionPattern

STEP_KEYS = {
    "step_index",
    "action",
    "element_ref",
    "value_preview",
    "reason",
    "policy_decision",
    "outcome",
    "snapshot_hash",
    "elapsed_ms",
    "max_steps",
}


def _redaction() -> RedactionConfig:
    return RedactionConfig(
        patterns=[
            RedactionPattern(
                name="card", regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b", replacement="[REDACTED_CARD]"
            )
        ],
        literals=["Alice Smith"],
        field_keys=["snapshot_hash"],
    )


def _record(step_index: int = 1, value_preview: str | None = "M-1001") -> StepRecord:
    return StepRecord(
        step_index=step_index,
        action="type",
        element_ref=step_index,
        value_preview=value_preview,
        reason="enter the member id",
        outcome="ok",
        snapshot_hash="deadbeef",
        elapsed_ms=12,
        max_steps=15,
    )


def test_file_has_one_parseable_json_line_per_step(tmp_path) -> None:
    log_path = tmp_path / "steps.jsonl"
    out = io.StringIO()
    logger = StepLogger(log_path, _redaction(), stdout=out)
    for index in range(1, 4):
        logger.write_step(_record(index))
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for index, line in enumerate(lines, start=1):
        payload = json.loads(line)
        assert payload["step_index"] == index
        assert set(payload) == STEP_KEYS


def test_stdout_gets_one_json_line_per_step(tmp_path) -> None:
    out = io.StringIO()
    logger = StepLogger(tmp_path / "s.jsonl", _redaction(), stdout=out)
    logger.write_step(_record(1))
    logger.write_step(_record(2))
    stdout_lines = out.getvalue().splitlines()
    assert len(stdout_lines) == 2
    assert json.loads(stdout_lines[1])["step_index"] == 2


def test_written_lines_are_redacted(tmp_path) -> None:
    log_path = tmp_path / "steps.jsonl"
    out = io.StringIO()
    logger = StepLogger(log_path, _redaction(), stdout=out)
    logger.write_step(_record(1, value_preview="4111-1111-1111-1111 for Alice Smith"))
    content = log_path.read_text(encoding="utf-8")
    assert "4111-1111-1111-1111" not in content
    assert "Alice Smith" not in content
    assert "[REDACTED_CARD]" in content
    payload = json.loads(content.strip())
    assert payload["snapshot_hash"] == "[REDACTED_SNAPSHOT_HASH]"


def test_summary_line_reports_status(tmp_path) -> None:
    out = io.StringIO()
    logger = StepLogger(tmp_path / "s.jsonl", _redaction(), stdout=out)
    logger.write_summary(RunStatus.GOAL_REACHED, steps=3)
    payload = json.loads(out.getvalue().strip())
    assert payload["status"] == "goal_reached"
    assert payload["steps"] == 3


def test_creates_parent_directories(tmp_path) -> None:
    log_path = tmp_path / "nested" / "deep" / "steps.jsonl"
    logger = StepLogger(log_path, _redaction(), stdout=io.StringIO())
    logger.write_step(_record())
    assert log_path.exists()
