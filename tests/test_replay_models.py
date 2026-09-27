"""Phase 6: ReplayResult / ReplayError contract invariants (spec HU-4)."""

import json

import pytest
from pydantic import ValidationError

from computer_use_automation_system.artifact.models import ActionType
from computer_use_automation_system.replay.models import (
    DecisionRecord,
    ReplayError,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)
from computer_use_automation_system.safety.models import DecisionKind


def _success(**overrides) -> ReplayResult:
    payload = {
        "status": ReplayStatus.SUCCESS,
        "capability_id": "lookup_member_balance",
        "version": "1.0.0",
        "outputs": {"savings_balance": "15200.00"},
        "steps_executed": 6,
        "elapsed_ms": 12,
        "decisions": [],
        "error": None,
    }
    payload.update(overrides)
    return ReplayResult(**payload)


def _failure(**overrides) -> ReplayResult:
    payload = {
        "status": ReplayStatus.FAILURE,
        "capability_id": "lookup_member_balance",
        "version": "1.0.0",
        "outputs": None,
        "steps_executed": 2,
        "elapsed_ms": 3,
        "decisions": [],
        "error": ReplayError(stage=ReplayStage.STEP, step_id=2, message="locator not found"),
    }
    payload.update(overrides)
    return ReplayResult(**payload)


def test_success_result_contract() -> None:
    result = _success()
    assert result.status is ReplayStatus.SUCCESS
    assert result.error is None
    assert result.outputs == {"savings_balance": "15200.00"}
    assert result.capability_id == "lookup_member_balance"


def test_success_rejects_error() -> None:
    with pytest.raises(ValidationError):
        _success(error=ReplayError(stage=ReplayStage.STEP, step_id=1, message="x"))


def test_success_requires_outputs() -> None:
    with pytest.raises(ValidationError):
        _success(outputs=None)


def test_failure_requires_error() -> None:
    with pytest.raises(ValidationError):
        _failure(error=None)


def test_failure_rejects_outputs() -> None:
    with pytest.raises(ValidationError):
        _failure(outputs={"savings_balance": "15200.00"})


def test_policy_kind_required_only_on_policy_stage() -> None:
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.POLICY, message="blocked")  # missing policy_kind
    with pytest.raises(ValidationError):
        ReplayError(
            stage=ReplayStage.STEP,
            step_id=1,
            policy_kind="blocked",
            message="x",
        )  # policy_kind outside policy stage


def test_input_and_output_stages_must_not_carry_step_id() -> None:
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.INPUT_VALIDATION, step_id=1, message="missing member_id")
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.OUTPUT_VALIDATION, step_id=2, message="missing key")


def test_policy_and_checkpoint_stages_accept_step_id() -> None:
    error = ReplayError(
        stage=ReplayStage.POLICY, step_id=4, policy_kind="needs_approval", message="confirm"
    )
    assert error.step_id == 4
    checkpoint = ReplayError(stage=ReplayStage.CHECKPOINT, step_id=6, message="not visible")
    assert checkpoint.step_id == 6


def test_error_rejects_step_id_below_one_and_empty_message() -> None:
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.STEP, step_id=0, message="x")
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.STEP, step_id=1, message="")


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ReplayResult(
            status=ReplayStatus.SUCCESS,
            capability_id="c",
            version="1.0.0",
            outputs={},
            steps_executed=0,
            elapsed_ms=0,
            decisions=[],
            error=None,
            surprise=True,
        )


def test_decision_record_contract() -> None:
    record = DecisionRecord(
        action_type=ActionType.CLICK,
        url="http://127.0.0.1:5000/members/M-1001",
        decision=DecisionKind.ALLOW,
        reason="inside perimeter",
    )
    assert record.action_type is ActionType.CLICK
    assert record.decision is DecisionKind.ALLOW
    with pytest.raises(ValidationError):
        DecisionRecord(
            action_type=ActionType.CLICK,
            url="http://127.0.0.1:5000/",
            decision=DecisionKind.ALLOW,
            reason="",
        )


def test_round_trip_json() -> None:
    result = _success()
    restored = ReplayResult.model_validate_json(result.model_dump_json())
    assert restored == result
    data = json.loads(result.model_dump_json())
    assert data["status"] == "success"
    assert data["error"] is None
