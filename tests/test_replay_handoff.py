"""Phase 8 (steps 1-6): handoff contracts and engine pause mechanism.

Covers strict `HandoffRequest` / `HandoffRecord`, closed trigger/decision
types, the additive `ReplayResult.handoff` field, the injectable `Operator`
seam with its fake, the four pause triggers, the control transfer over the
same live session and the three operator decisions (spec HU-1..HU-6)."""

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from computer_use_automation_system.artifact.models import (
    ActionType,
    Artifact,
    Locator,
    LocatorType,
    Step,
)
from computer_use_automation_system.discovery.act import DriverActionError
from computer_use_automation_system.discovery.models import ObservedElement
from computer_use_automation_system.replay.engine import replay
from computer_use_automation_system.replay.handoff import Operator
from computer_use_automation_system.replay.models import (
    MAX_HANDOFF_TEXT,
    MAX_SNAPSHOT_ELEMENTS,
    ControlState,
    HandoffDecision,
    HandoffRecord,
    HandoffRequest,
    HandoffTrigger,
    OperatorResponse,
    ReplayError,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)
from computer_use_automation_system.replay.taxonomy import TaxonomyConfig
from computer_use_automation_system.safety.models import (
    PolicyConfig,
    PolicyRule,
    RedactionConfig,
    RedactionPattern,
)
from fakes import FakeOperator, ReplayFakeDriver


def _request_payload() -> dict[str, object]:
    return {
        "trigger": "hard_failure",
        "stage": ReplayStage.STEP,
        "step_id": 3,
        "action": "click",
        "reason": "step 3 (click) failed: element_not_found; classified hard",
        "capability": "lookup_member_balance v1.0.0",
        "description": "MemberServ console flow",
        "snapshot": [{"tag": "div", "id": "main", "text": "MemberServ"}],
        "screenshot": None,
    }


def _record_payload(index: int, decision: str = "resume") -> dict[str, object]:
    return {
        "index": index,
        "request": _request_payload(),
        "decision": decision,
        "note": "checked the live page",
        "resumed_snapshot": (
            None if decision == "abort" else [{"tag": "div", "id": "main", "text": "MemberServ"}]
        ),
    }


def _success(handoff: list[HandoffRecord] | None = None) -> ReplayResult:
    return ReplayResult(
        status=ReplayStatus.SUCCESS,
        capability_id="lookup_member_balance",
        version="1.0.0",
        outputs={"member_name": "Alice Hartwell"},
        steps_executed=6,
        elapsed_ms=12,
        decisions=[],
        handoff=handoff or [],
    )


def test_handoff_types_are_closed_literals() -> None:
    assert get_args(HandoffTrigger) == (
        "hard_failure",
        "retries_exhausted",
        "needs_approval",
        "risky_step",
    )
    assert get_args(HandoffDecision) == ("resume", "finish", "abort")
    assert get_args(ControlState) == ("automation", "human")


def test_handoff_request_is_strict_and_round_trips() -> None:
    payload = _request_payload()
    payload["surprise"] = True
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(payload)

    request = HandoffRequest.model_validate(_request_payload())
    restored = HandoffRequest.model_validate_json(request.model_dump_json())
    assert restored == request
    assert set(request.model_dump()) == {
        "trigger",
        "stage",
        "step_id",
        "action",
        "reason",
        "capability",
        "description",
        "snapshot",
        "screenshot",
    }


def test_handoff_request_rejects_unknown_trigger_and_non_pausable_stages() -> None:
    for stage in (ReplayStage.INPUT_VALIDATION, ReplayStage.OUTPUT_VALIDATION):
        payload = _request_payload()
        payload["stage"] = stage
        with pytest.raises(ValidationError):
            HandoffRequest.model_validate(payload)

    payload = _request_payload()
    payload["trigger"] = "blocked"
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(payload)


def test_confirm_triggers_pause_at_the_policy_stage() -> None:
    for trigger in ("needs_approval", "risky_step"):
        payload = _request_payload()
        payload.update({"trigger": trigger, "stage": ReplayStage.STEP})
        with pytest.raises(ValidationError):
            HandoffRequest.model_validate(payload)

    payload = _request_payload()
    payload.update({"trigger": "needs_approval", "stage": ReplayStage.POLICY, "action": "click"})
    request = HandoffRequest.model_validate(payload)
    assert request.stage is ReplayStage.POLICY


def test_failure_triggers_never_pause_at_the_policy_stage() -> None:
    payload = _request_payload()
    payload["stage"] = ReplayStage.POLICY
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(payload)

    payload = _request_payload()
    payload.update({"trigger": "retries_exhausted", "stage": ReplayStage.CHECKPOINT})
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(payload)

    payload = _request_payload()
    payload.update({"trigger": "retries_exhausted", "stage": ReplayStage.STEP})
    assert HandoffRequest.model_validate(payload).stage is ReplayStage.STEP

    payload = _request_payload()
    payload.update({"trigger": "hard_failure", "stage": ReplayStage.CHECKPOINT, "step_id": None})
    assert HandoffRequest.model_validate(payload).stage is ReplayStage.CHECKPOINT


def test_step_id_is_required_on_step_and_policy_stages() -> None:
    for stage in (ReplayStage.STEP, ReplayStage.POLICY):
        payload = _request_payload()
        payload.update({"stage": stage, "step_id": None})
        with pytest.raises(ValidationError):
            HandoffRequest.model_validate(payload)

    payload = _request_payload()
    payload.update({"stage": ReplayStage.CHECKPOINT, "step_id": None})
    assert HandoffRequest.model_validate(payload).step_id is None


def test_handoff_record_is_strict_and_round_trips() -> None:
    payload = _record_payload(0)
    payload["surprise"] = True
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)

    record = HandoffRecord.model_validate(_record_payload(1))
    restored = HandoffRecord.model_validate_json(record.model_dump_json())
    assert restored == record
    assert set(record.model_dump()) == {
        "index",
        "request",
        "decision",
        "note",
        "resumed_snapshot",
    }


def test_handoff_record_decision_invariants() -> None:
    aborted = HandoffRecord.model_validate(_record_payload(0, decision="abort"))
    assert aborted.resumed_snapshot is None

    payload = _record_payload(0, decision="abort")
    payload["resumed_snapshot"] = [{"tag": "div"}]
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)

    payload = _record_payload(0, decision="resume")
    payload["resumed_snapshot"] = None
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)

    payload = _record_payload(0, decision="finish")
    assert HandoffRecord.model_validate(payload).decision == "finish"

    payload = _record_payload(0, decision="escalate")
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)

    payload = _record_payload(0)
    payload["note"] = ""
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)

    payload = _record_payload(-1)
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate(payload)


def test_replay_result_handoff_defaults_to_empty_for_phase6_payload() -> None:
    payload: dict[str, object] = {
        "status": "success",
        "capability_id": "lookup_member_balance",
        "version": "1.0.0",
        "outputs": {"member_name": "Alice Hartwell"},
        "steps_executed": 6,
        "elapsed_ms": 12,
        "decisions": [],
        "error": None,
    }
    restored = ReplayResult.model_validate_json(json.dumps(payload))
    assert restored.handoff == []
    dumped = json.loads(_success().model_dump_json())
    assert dumped["handoff"] == []


def test_replay_result_handoff_round_trip_with_records() -> None:
    records = [
        HandoffRecord.model_validate(_record_payload(0)),
        HandoffRecord.model_validate(_record_payload(1, decision="finish")),
    ]
    result = _success(handoff=records)
    restored = ReplayResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert [record.index for record in restored.handoff] == [0, 1]
    assert [record.decision for record in restored.handoff] == ["resume", "finish"]


def test_replay_result_rejects_uncorrelated_handoff_indexes() -> None:
    records = [
        HandoffRecord.model_validate(_record_payload(0)),
        HandoffRecord.model_validate(_record_payload(2)),
    ]
    with pytest.raises(ValidationError):
        _success(handoff=records)


def test_abort_failure_result_carries_the_policy_error_and_record() -> None:
    record = HandoffRecord.model_validate(_record_payload(0, decision="abort"))
    result = ReplayResult(
        status=ReplayStatus.FAILURE,
        capability_id="lookup_member_balance",
        version="1.0.0",
        outputs=None,
        steps_executed=2,
        elapsed_ms=8,
        decisions=[],
        error=ReplayError(
            stage=ReplayStage.POLICY,
            step_id=3,
            policy_kind="needs_approval",
            message="policy confirm: manual transfer requires approval",
        ),
        handoff=[record],
    )
    restored = ReplayResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.error is not None
    assert restored.error.policy_kind == "needs_approval"


START = "http://127.0.0.1:5000/"


def test_operator_response_is_strict() -> None:
    with pytest.raises(ValidationError):
        OperatorResponse.model_validate({"decision": "resume", "surprise": True})
    with pytest.raises(ValidationError):
        OperatorResponse(decision="resume", note="")
    with pytest.raises(ValidationError):
        OperatorResponse(decision="escalate")
    response = OperatorResponse(decision="finish", note="handled manually")
    assert response.decision == "finish"


def test_pause_package_enforces_text_and_snapshot_caps() -> None:
    """SEC-805: the pause package and its evidence record are bounded, so a
    hostile page or an oversized note can not flood the operator prompt or
    the persisted handoff log (fail closed at model level)."""
    oversized_snapshot = [{"tag": "div", "id": "main"}] * (MAX_SNAPSHOT_ELEMENTS + 1)
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate({**_request_payload(), "snapshot": oversized_snapshot})
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(
            {**_request_payload(), "reason": "r" * (MAX_HANDOFF_TEXT + 1)}
        )
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(
            {**_request_payload(), "description": "d" * (MAX_HANDOFF_TEXT + 1)}
        )
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate({**_record_payload(0), "note": "n" * (MAX_HANDOFF_TEXT + 1)})
    with pytest.raises(ValidationError):
        HandoffRecord.model_validate({**_record_payload(0), "resumed_snapshot": oversized_snapshot})
    ok = HandoffRequest.model_validate(
        {
            **_request_payload(),
            "snapshot": [{"tag": "div"}] * MAX_SNAPSHOT_ELEMENTS,
            "reason": "r" * MAX_HANDOFF_TEXT,
        }
    )
    assert len(ok.snapshot) == MAX_SNAPSHOT_ELEMENTS


def test_fake_operator_satisfies_the_operator_protocol_and_collects_requests() -> None:
    operator: Operator = FakeOperator(
        ReplayFakeDriver({}, START),
        responses=[OperatorResponse(decision="resume")],
    )
    assert isinstance(operator, Operator)
    assert not isinstance(object(), Operator)

    response = operator.intervene(
        HandoffRequest.model_validate(_request_payload()),
    )
    assert response.decision == "resume"
    assert [request.trigger for request in operator.requests] == ["hard_failure"]


def test_fake_operator_mirrors_control_and_driver_rejects_calls_while_human() -> None:
    driver = ReplayFakeDriver({}, START)
    seen: list[bool] = []

    def handler(request: HandoffRequest) -> OperatorResponse:
        seen.append(driver.human_control)
        with pytest.raises(AssertionError):
            driver.current_url()
        with pytest.raises(AssertionError):
            driver.observe_raw()
        return OperatorResponse(decision="resume", note="carry on")

    operator = FakeOperator(driver, handler=handler)
    response = operator.intervene(
        HandoffRequest.model_validate(_request_payload()),
    )
    assert seen == [True]
    assert driver.human_control is False
    assert operator.calls_during_wait == [(0, 0)]
    assert response.note == "carry on"


def test_driver_calls_work_again_once_the_operator_releases_control() -> None:
    driver = ReplayFakeDriver({}, START)
    driver.human_control = True
    with pytest.raises(AssertionError):
        driver.navigate(START)
    driver.human_control = False
    driver.navigate(START)
    assert driver.calls == [("navigate", START)]


def test_fake_operator_fails_loudly_when_it_runs_out_of_responses() -> None:
    operator = FakeOperator(ReplayFakeDriver({}, START))
    with pytest.raises(AssertionError):
        operator.intervene(HandoffRequest.model_validate(_request_payload()))


# --- Engine pause mechanism (steps 3-6) ------------------------------------

EXECUTE_URL = "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute"


def _policy(rules: list[PolicyRule] | None = None) -> PolicyConfig:
    return PolicyConfig(
        allowed_origins=["http://127.0.0.1:5000"],
        allowed_routes=["/", "/members"],
        allowed_action_types=list(ActionType),
        rules=rules or [],
        redaction=RedactionConfig(
            patterns=[
                RedactionPattern(
                    name="card",
                    regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",
                    replacement="[REDACTED_CARD]",
                )
            ],
            literals=["dummy-999"],
            field_keys=["password", "pin"],
        ),
    )


def _taxonomy(**overrides: object) -> TaxonomyConfig:
    payload: dict[str, object] = {
        "version": "1.0.0",
        "max_recoverable_attempts": 3,
        "patterns": {
            "business_outcome": ["No records found"],
            "recoverable": ["Loading, please wait"],
            "hard": ["Permission denied"],
        },
        "recoverable_driver_codes": ["stale", "timeout"],
        "known_dialogs": [],
    }
    payload.update(overrides)
    return TaxonomyConfig.model_validate(payload)


def _mini(
    steps: list[Step],
    *,
    checkpoint_locators: list[Locator] | None = None,
    output_properties: dict | None = None,
    output_required: list[str] | None = None,
) -> Artifact:
    return Artifact(
        capability_id="mini_capability",
        version="1.0.0",
        description="mini flow for handoff tests",
        target_app={"name": "MemberServ", "entry_url": START},
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": output_properties or {"value": {"type": "string"}},
            "required": output_required or [],
        },
        steps=steps,
        checkpoint={
            "description": "target state visible",
            "locators": checkpoint_locators or [{"type": "css", "value": "#memberName"}],
            "expected_condition": "visible",
        },
    )


def _navigate_step(url: str) -> Step:
    return Step(
        step_id=1,
        action_type=ActionType.NAVIGATE,
        description="open the target page",
        locators=[Locator(type=LocatorType.ID, value="main")],
        value=url,
    )


def _pages() -> dict[str, list[dict]]:
    return {
        START: [
            {
                "tag": "input",
                "id": "q",
                "type": "text",
                "value": "",
                "name": "q",
                "selectors": ["#q", "input[name='q']"],
                "role": "textbox",
            },
        ],
        EXECUTE_URL: [
            {
                "tag": "button",
                "id": "confirmBtn",
                "text": "Confirm",
                "role": "button",
                "selectors": ["#confirmBtn"],
            },
            {
                "tag": "h2",
                "id": "memberName",
                "text": "Alice Hartwell",
                "selectors": ["#memberName"],
            },
            {"tag": "td", "id": "pan", "text": "4111-1111-1111-1111", "selectors": ["#pan"]},
        ],
    }


def _dismiss_pages() -> dict[str, list[dict]]:
    return {
        START: [
            {
                "tag": "input",
                "id": "q",
                "type": "text",
                "value": "",
                "name": "q",
                "selectors": ["#q"],
                "role": "textbox",
            },
            {
                "tag": "div",
                "id": "sessDlg",
                "role": "dialog",
                "name": "session warning",
                "text": "Session will expire soon",
                "selectors": ["#sessDlg"],
            },
            {
                "tag": "button",
                "id": "closeDlg",
                "role": "button",
                "text": "Continue",
                "selectors": ["#closeDlg"],
            },
        ],
    }


def _confirm_rules() -> list[PolicyRule]:
    return [
        PolicyRule(
            match_action_type=ActionType.CLICK,
            match_url_pattern="*/execute",
            decision="confirm",
            reason="irreversible execution",
        )
    ]


def _confirm_any_click_rules() -> list[PolicyRule]:
    return [
        PolicyRule(
            match_action_type=ActionType.CLICK,
            decision="confirm",
            reason="manual confirmation required",
        )
    ]


def _risky_artifact(
    *,
    checkpoint_locators: list[Locator] | None = None,
    output_required: list[str] | None = None,
) -> Artifact:
    return _mini(
        [
            _navigate_step(EXECUTE_URL),
            Step(
                step_id=2,
                action_type=ActionType.CLICK,
                description="confirm the disbursement",
                locators=[Locator(type=LocatorType.ID, value="confirmBtn")],
            ),
        ],
        checkpoint_locators=checkpoint_locators,
        output_required=output_required,
    )


def _type_step() -> Step:
    return Step(
        step_id=2,
        action_type=ActionType.TYPE,
        description="type the query",
        locators=[Locator(type=LocatorType.ID, value="q")],
        value="{{input.q}}",
    )


def _type_artifact(
    *,
    checkpoint_locators: list[Locator] | None = None,
    output_required: list[str] | None = None,
) -> Artifact:
    return _mini(
        [_navigate_step(START), _type_step()],
        checkpoint_locators=checkpoint_locators or [Locator(type=LocatorType.CSS, value="#q")],
        output_required=output_required,
    )


class _FlakyTypeDriver(ReplayFakeDriver):
    """ReplayFakeDriver whose `type_text` raises `code` for the first
    `failures` attempts (then behaves normally)."""

    def __init__(
        self,
        pages: dict[str, list[dict]],
        start_url: str,
        code: str = "timeout",
        failures: int = 1,
    ) -> None:
        super().__init__(pages, start_url)
        self._code = code
        self._failures = failures
        self.type_attempts = 0

    def type_text(self, element: ObservedElement, text: str) -> None:
        self.type_attempts += 1
        if self.type_attempts <= self._failures:
            raise DriverActionError(self._code)
        super().type_text(element, text)


def test_risky_step_trigger_pauses_before_the_action_and_resume_approves() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert len(result.handoff) == 1
    record = result.handoff[0]
    request = record.request
    assert request.trigger == "risky_step"
    assert request.stage is ReplayStage.POLICY
    assert request.step_id == 2
    assert request.action is ActionType.CLICK
    assert request.capability == "mini_capability v1.0.0"
    assert request.description == "mini flow for handoff tests"
    assert request.screenshot is None
    assert request.snapshot
    assert record.decision == "resume"
    assert record.resumed_snapshot is not None
    assert record.note is None
    assert operator.requests == [request]
    assert driver.calls[0] == ("navigate", EXECUTE_URL)
    assert ("click", "confirmBtn", EXECUTE_URL) in driver.calls
    assert driver.human_control is False
    assert not any(call[0] == "quit" for call in driver.calls)
    entered, exited = operator.calls_during_wait[0]
    assert entered == exited


def test_pause_package_is_truncated_at_capture_and_broken_evidence_helpers() -> None:
    """SEC-805 + DEF-803: the engine bounds what it captures (snapshot and
    operator note) and treats a broken optional evidence helper as "absent"
    instead of crashing the pause."""

    class HugeDriver(ReplayFakeDriver):
        def observe_raw(self) -> list[dict]:
            self._guard()
            return [{"tag": "div", "id": f"n{i}"} for i in range(MAX_SNAPSHOT_ELEMENTS + 80)]

        @property
        def screenshot_b64(self) -> str:
            raise TypeError("screenshot backend exploded")

    driver = HugeDriver(_pages(), START)
    operator = FakeOperator(
        driver,
        responses=[OperatorResponse(decision="resume", note="n" * (MAX_HANDOFF_TEXT + 500))],
    )
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    record = result.handoff[0]
    assert len(record.request.snapshot) == MAX_SNAPSHOT_ELEMENTS
    assert record.request.screenshot is None
    assert record.resumed_snapshot is not None
    assert len(record.resumed_snapshot) == MAX_SNAPSHOT_ELEMENTS
    assert record.note is not None
    assert len(record.note) == MAX_HANDOFF_TEXT


def test_needs_approval_trigger_pauses_on_the_enforce_dismiss_path() -> None:
    driver = _FlakyTypeDriver(_dismiss_pages(), START, code="timeout", failures=1)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(_confirm_any_click_rules()),
        taxonomy=_taxonomy(
            known_dialogs=[
                {
                    "pattern": "Session will expire soon",
                    "dismiss_locator": {"type": "css", "value": "#closeDlg"},
                }
            ]
        ),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert len(result.handoff) == 1
    request = result.handoff[0].request
    assert request.trigger == "needs_approval"
    assert request.stage is ReplayStage.POLICY
    assert request.step_id == 2
    assert request.action is ActionType.CLICK
    assert result.handoff[0].decision == "resume"
    assert driver.type_attempts == 2
    dismiss_clicks = [call for call in driver.calls if call[0] == "click"]
    assert dismiss_clicks and dismiss_clicks[0][1] == "closeDlg"


def test_hard_failure_trigger_pauses_once_and_retries_the_step() -> None:
    driver = _FlakyTypeDriver(_pages(), START, code="element_not_found", failures=1)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert len(result.handoff) == 1
    request = result.handoff[0].request
    assert request.trigger == "hard_failure"
    assert request.stage is ReplayStage.STEP
    assert request.step_id == 2
    assert request.action is ActionType.TYPE
    assert result.handoff[0].decision == "resume"


def test_retries_exhausted_trigger_pauses_once_then_fails_without_loops() -> None:
    driver = _FlakyTypeDriver(_pages(), START, code="timeout", failures=99)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.STEP
    assert result.error.failure_category == "recoverable"
    assert "attempts exhausted" in result.error.message
    assert len(operator.requests) == 1
    request = operator.requests[0]
    assert request.trigger == "retries_exhausted"
    assert request.stage is ReplayStage.STEP
    assert request.step_id == 2
    assert len(result.handoff) == 1
    assert result.handoff[0].decision == "resume"


def test_block_verdict_never_escalates_to_a_handoff() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver)
    result = replay(
        _mini([_navigate_step("http://evil.example/")]),
        {},
        driver,
        _policy(),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "blocked"
    assert operator.requests == []
    assert result.handoff == []


def test_business_outcome_failure_never_escalates_to_a_handoff() -> None:
    pages = {START: [{"tag": "div", "id": "flash", "text": 'No records found for "zzz"'}]}
    driver = _FlakyTypeDriver(pages, START, code="element_not_found", failures=1)
    operator = FakeOperator(driver)
    result = replay(
        _type_artifact(),
        {"q": "zzz"},
        driver,
        _policy(),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"
    assert operator.requests == []
    assert result.handoff == []


def test_without_operator_the_phase6_failure_paths_are_unchanged() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "needs_approval"
    assert result.error.message == "irreversible execution"
    assert result.handoff == []
    assert not any(call[0] == "click" for call in driver.calls)


def test_operator_attached_but_never_triggered_leaves_the_run_untouched() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver)
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert result.handoff == []
    assert operator.requests == []


def test_abort_returns_the_failure_in_the_trigger_stage_and_records_it() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(
        driver,
        responses=[OperatorResponse(decision="abort", note="not safe right now")],
    )
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "needs_approval"
    assert result.error.step_id == 2
    assert result.error.message == "irreversible execution"
    assert result.error.failure_category is None
    assert len(result.handoff) == 1
    record = result.handoff[0]
    assert record.decision == "abort"
    assert record.note == "not safe right now"
    assert record.resumed_snapshot is None
    assert not any(call[0] == "click" for call in driver.calls)


def test_finish_skips_remaining_steps_and_validates_only_the_checkpoint() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="finish")])
    result = replay(
        _risky_artifact(output_required=["value"]),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert result.outputs == {}
    assert result.steps_executed == 1
    assert len(result.handoff) == 1
    assert result.handoff[0].decision == "finish"
    assert result.handoff[0].resumed_snapshot is not None
    assert not any(call[0] == "click" for call in driver.calls)


def test_resume_still_gates_success_through_output_validation() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _risky_artifact(output_required=["value"]),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.OUTPUT_VALIDATION
    assert len(result.handoff) == 1
    assert result.handoff[0].decision == "resume"


def test_finish_with_a_broken_checkpoint_fails_at_the_checkpoint_stage() -> None:
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(
        driver,
        responses=[
            OperatorResponse(decision="finish"),
            OperatorResponse(decision="abort", note="cannot fix it"),
        ],
    )
    result = replay(
        _risky_artifact(checkpoint_locators=[Locator(type=LocatorType.CSS, value="#ghost")]),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.CHECKPOINT
    assert result.error.failure_category == "hard"
    assert [record.index for record in result.handoff] == [0, 1]
    first, second = result.handoff
    assert first.request.trigger == "risky_step"
    assert first.decision == "finish"
    assert second.request.trigger == "hard_failure"
    assert second.request.stage is ReplayStage.CHECKPOINT
    assert second.decision == "abort"
    assert second.resumed_snapshot is None


def test_handoff_package_redacts_snapshot_and_operator_note() -> None:
    driver = ReplayFakeDriver(_pages(), START)

    def handler(request: HandoffRequest) -> OperatorResponse:
        return OperatorResponse(decision="resume", note="literal dummy-999 approved")

    operator = FakeOperator(driver, handler=handler)
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    request = result.handoff[0].request
    snapshot_text = json.dumps(request.model_dump()["snapshot"])
    assert "4111-1111-1111-1111" not in snapshot_text
    assert "[REDACTED_CARD]" in snapshot_text
    assert "4111" not in request.model_dump_json()
    assert result.handoff[0].note == "literal [REDACTED_NAME] approved"


def test_execute_replay_seam_forwards_the_operator_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import computer_use_automation_system.cli as cli
    from computer_use_automation_system.discovery import selenium_driver

    class _StubDriver:
        def quit(self) -> None:
            return None

    seen: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> ReplayResult:
        seen.clear()
        seen.update(kwargs)
        return ReplayResult(
            status=ReplayStatus.SUCCESS,
            capability_id="stub_capability",
            version="1.0.0",
            outputs={},
            steps_executed=0,
            elapsed_ms=0,
        )

    monkeypatch.setattr(cli, "run_replay", fake_run)
    monkeypatch.setattr(selenium_driver, "build_webdriver", lambda: _StubDriver())
    artifact = _risky_artifact()
    policy = _policy()
    operator = FakeOperator(ReplayFakeDriver(_pages(), START))

    result = cli._execute_replay(
        artifact,
        {},
        policy,
        approved=True,
        max_timeout_ms=500,
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    assert seen["operator"] is operator
    assert seen["approved"] is True
    assert seen["step_timeout_ms"] == 500

    cli._execute_replay(
        artifact,
        {},
        policy,
        approved=False,
        max_timeout_ms=None,
    )
    assert seen["operator"] is None
    assert seen["approved"] is False
    assert seen["step_timeout_ms"] is None


def test_handoff_public_exports_live_in_the_replay_package() -> None:
    import computer_use_automation_system.replay as replay_pkg

    for name in ("HandoffRequest", "HandoffRecord", "Operator", "ControlState"):
        assert name in replay_pkg.__all__, name
        assert getattr(replay_pkg, name, None) is not None, name


def test_replay_status_is_still_success_or_failure_only() -> None:
    assert [member.value for member in ReplayStatus] == ["success", "failure"]


def test_handoff_mechanism_never_sleeps_or_restarts_the_browser() -> None:
    import pathlib

    package = pathlib.Path("src/computer_use_automation_system/replay")
    for name in ("engine.py", "handoff.py", "models.py"):
        source = (package / name).read_text(encoding="utf-8")
        assert "time.sleep" not in source, name
        assert ".quit(" not in source, name
        assert "build_webdriver" not in source, name


def test_pause_reason_passes_through_redaction_even_for_policy_text() -> None:
    rule = PolicyRule(
        match_action_type=ActionType.CLICK,
        match_url_pattern="*/execute",
        decision="confirm",
        reason="manual transfer of 4111-1111-1111-1111",
    )
    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="resume")])
    result = replay(
        _risky_artifact(),
        {},
        driver,
        _policy([rule]),
        operator=operator,
    )
    assert result.status is ReplayStatus.SUCCESS
    request = result.handoff[0].request
    assert "[REDACTED_CARD]" in request.reason
    assert "4111-1111-1111-1111" not in request.reason
    assert "4111" not in request.model_dump_json()


def test_abort_results_map_to_the_original_exit_codes() -> None:
    import computer_use_automation_system.cli as cli

    driver = ReplayFakeDriver(_pages(), START)
    operator = FakeOperator(driver, responses=[OperatorResponse(decision="abort")])
    confirm_abort = replay(
        _risky_artifact(),
        {},
        driver,
        _policy(_confirm_rules()),
        operator=operator,
    )
    assert confirm_abort.status is ReplayStatus.FAILURE
    assert cli._replay_exit_code(confirm_abort) == 11

    flaky = _FlakyTypeDriver(_pages(), START, code="element_not_found", failures=99)
    hard_operator = FakeOperator(flaky, responses=[OperatorResponse(decision="abort")])
    hard_abort = replay(
        _type_artifact(),
        {"q": "alice"},
        flaky,
        _policy(),
        operator=hard_operator,
    )
    assert hard_abort.status is ReplayStatus.FAILURE
    assert hard_abort.error is not None
    assert hard_abort.error.stage is ReplayStage.STEP
    assert cli._replay_exit_code(hard_abort) == 1
