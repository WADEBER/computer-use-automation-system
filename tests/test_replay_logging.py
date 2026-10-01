"""Phase 9, HU-1: structured replay logging -- engine event emission via the
`events` callback and the redacting `ReplayLogger` writer (evidence contract).

CI never opens network, Ollama or Chrome: the timeline comes from the fake
driver and operator used by the Phase 6/8 suites.
"""

import json
from pathlib import Path

from computer_use_automation_system.artifact.models import (
    ActionType,
    Artifact,
    Checkpoint,
    Locator,
    LocatorType,
    Step,
)
from computer_use_automation_system.replay import ReplayStage, ReplayStatus
from computer_use_automation_system.replay.engine import replay
from computer_use_automation_system.replay.logging_runner import ReplayLogger
from computer_use_automation_system.replay.models import OperatorResponse
from computer_use_automation_system.safety.models import (
    PolicyConfig,
    RedactionConfig,
    RedactionPattern,
)
from fakes import FakeOperator, ReplayFakeDriver

ENTRY = "http://127.0.0.1:5000/"
DONE = "http://127.0.0.1:5000/done"

OK_PAGES: dict[str, list[dict]] = {
    ENTRY: [
        {"tag": "div", "id": "main", "selectors": ["#main"], "text": "MemberServ"},
        {
            "tag": "button",
            "id": "go",
            "text": "Go",
            "selectors": ["#go"],
            "role": "button",
            "href": "/done",
        },
    ],
    DONE: [{"tag": "div", "id": "ok", "selectors": ["#ok"], "text": "done"}],
}

NOT_FOUND_PAGES: dict[str, list[dict]] = {
    ENTRY: [
        {"tag": "div", "id": "main", "selectors": ["#main"], "text": "MemberServ"},
        {"tag": "p", "id": "flash", "text": "Member not found"},
    ],
}

DENIED_PAGES: dict[str, list[dict]] = {
    ENTRY: [
        {"tag": "div", "id": "main", "selectors": ["#main"], "text": "MemberServ"},
        {"tag": "p", "id": "flash", "text": "Access denied"},
    ],
}


def _artifact() -> Artifact:
    return Artifact(
        capability_id="open_done_page",
        version="1.0.0",
        description="Opens the console home page and follows the link to the done page.",
        target_app={"name": "MemberServ", "entry_url": ENTRY},
        input_schema={
            "type": "object",
            "properties": {"region": {"type": "string"}},
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": [],
        },
        steps=[
            Step(
                step_id=1,
                action_type=ActionType.NAVIGATE,
                description="Open the console home page",
                locators=[Locator(type=LocatorType.ID, value="main")],
                value=ENTRY,
            ),
            Step(
                step_id=2,
                action_type=ActionType.CLICK,
                description="Follow the link to the done page",
                locators=[Locator(type=LocatorType.ID, value="go")],
            ),
        ],
        checkpoint=Checkpoint(
            description="Done marker is visible",
            locators=[Locator(type=LocatorType.CSS, value="#ok")],
            expected_condition="visible",
        ),
    )


def _policy() -> PolicyConfig:
    return PolicyConfig(
        allowed_origins=["http://127.0.0.1:5000"],
        allowed_routes=["/"],
        allowed_action_types=list(ActionType),
        rules=[],
        redaction=RedactionConfig(
            patterns=[
                RedactionPattern(
                    name="card",
                    regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",
                    replacement="[REDACTED_CARD]",
                )
            ],
            literals=["dummy-999"],
            field_keys=["password"],
        ),
    )


def _driver(pages: dict[str, list[dict]]) -> ReplayFakeDriver:
    return ReplayFakeDriver(pages, start_url=ENTRY)


# --- Engine event emission ---------------------------------------------------


def test_happy_path_emits_timeline_in_order() -> None:
    events: list[dict] = []
    result = replay(_artifact(), {}, _driver(OK_PAGES), _policy(), events=events.append)
    assert result.status is ReplayStatus.SUCCESS
    kinds = [event["event"] for event in events]
    assert kinds == [
        "policy_decision",
        "step",
        "policy_decision",
        "step",
        "checkpoint",
    ]
    assert events[-1] == {"event": "checkpoint", "passed": True}


def test_policy_decision_event_carries_audit_fields() -> None:
    events: list[dict] = []
    replay(_artifact(), {}, _driver(OK_PAGES), _policy(), events=events.append)
    first = events[0]
    assert first["action_type"] == "navigate"
    assert first["decision"] == "allow"
    assert first["url"] == ENTRY
    assert isinstance(first["reason"], str) and first["reason"]
    step_events = [event for event in events if event["event"] == "step"]
    assert [event["step_id"] for event in step_events] == [1, 2]
    assert all(event["action_type"] for event in step_events)


def test_business_outcome_failure_emits_typed_failure_event() -> None:
    events: list[dict] = []
    result = replay(_artifact(), {}, _driver(NOT_FOUND_PAGES), _policy(), events=events.append)
    assert result.status is ReplayStatus.FAILURE
    failures = [event for event in events if event["event"] == "failure"]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["stage"] == ReplayStage.STEP.value
    assert failure["step_id"] == 2
    assert failure["failure_category"] == "business_outcome"
    assert "checkpoint" not in [event["event"] for event in events]


def test_handoff_pause_emits_event_with_decision() -> None:
    driver = _driver(DENIED_PAGES)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    events: list[dict] = []
    result = replay(_artifact(), {}, driver, _policy(), operator=operator, events=events.append)
    assert result.status is ReplayStatus.FAILURE
    handoffs = [event for event in events if event["event"] == "handoff"]
    assert handoffs == [
        {
            "event": "handoff",
            "index": 0,
            "trigger": "hard_failure",
            "stage": ReplayStage.STEP.value,
            "step_id": 2,
            "decision": "resume",
        }
    ]
    failures = [event for event in events if event["event"] == "failure"]
    assert len(failures) == 1
    assert failures[0]["failure_category"] == "hard"


def test_events_default_keeps_legacy_behavior() -> None:
    result = replay(_artifact(), {}, _driver(OK_PAGES), _policy())
    assert result.status is ReplayStatus.SUCCESS


# --- ReplayLogger writer -----------------------------------------------------


def _redaction() -> RedactionConfig:
    return RedactionConfig(
        patterns=[
            RedactionPattern(
                name="card",
                regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",
                replacement="[REDACTED_CARD]",
            )
        ],
        literals=["hunter2"],
        field_keys=["password"],
    )


def test_replay_logger_writes_redacted_jsonl_and_creates_parents(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "replay.log"
    logger = ReplayLogger(log_path, _redaction())
    logger.write({"event": "start", "note": "card 1111-2222-3333-4444"})
    logger.write({"event": "result", "status": "success", "password": "hunter2"})
    raw = log_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["start", "result"]
    first = json.loads(lines[0])
    assert first["note"] == "card [REDACTED_CARD]"
    assert "1111-2222-3333-4444" not in raw
    assert "hunter2" not in raw


def test_replay_logger_appends_one_valid_json_line_per_event(tmp_path: Path) -> None:
    log_path = tmp_path / "replay.log"
    logger = ReplayLogger(log_path, _redaction())
    for index in range(3):
        logger.write({"event": "step", "step_id": index})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [event["step_id"] for event in parsed] == [0, 1, 2]
