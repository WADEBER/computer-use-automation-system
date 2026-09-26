import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from computer_use_automation_system.artifact.models import ActionType, Artifact
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    LLMAction,
    PolicyDecisionRecord,
    RunStatus,
    StepRecord,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _artifact() -> Artifact:
    raw = json.loads((FIXTURES / "valid_artifact.json").read_text(encoding="utf-8"))
    return Artifact(**raw)


def _config(**overrides) -> DiscoveryConfig:
    data = {"goal": "find the balance of member M-1001", "entry_url": "http://127.0.0.1:5000/"}
    data.update(overrides)
    return DiscoveryConfig(**data)


def test_config_defaults_match_spec() -> None:
    config = _config()
    assert config.max_steps == 15
    assert config.step_timeout_ms == 15000
    assert config.total_timeout_ms == 300000
    assert config.repeat_threshold == 3
    assert config.max_snapshot_chars == 8000
    assert config.max_llm_retries == 2
    assert "evidence" in str(config.artifact_out)
    assert "evidence" in str(config.log_out)


def test_config_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        _config(goal="")


def test_config_rejects_non_http_entry() -> None:
    with pytest.raises(ValidationError):
        _config(entry_url="ftp://example.com/")


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_steps": 0},
        {"step_timeout_ms": 0},
        {"total_timeout_ms": 0},
        {"repeat_threshold": 1},
        {"max_snapshot_chars": 0},
        {"max_llm_retries": -1},
    ],
)
def test_config_rejects_out_of_range_numbers(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        _config(**overrides)


def test_config_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        _config(unknown_field=1)


def test_run_status_values_match_spec() -> None:
    assert {status.value for status in RunStatus} == {
        "goal_reached",
        "max_steps",
        "timeout",
        "dead_end",
        "blocked",
        "needs_approval",
        "llm_error",
    }


def test_llm_action_valid_navigate() -> None:
    action = LLMAction(action=ActionType.NAVIGATE, value="http://127.0.0.1:5000/", reason="go home")
    assert action.element_ref is None
    assert action.value == "http://127.0.0.1:5000/"


def test_llm_action_valid_click() -> None:
    action = LLMAction(action=ActionType.CLICK, element_ref=3, reason="open detail")
    assert action.value is None


def test_llm_action_requires_reason() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.CLICK, element_ref=1, reason="")


def test_llm_action_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.CLICK, element_ref=1, reason="x", confidence=0.9)


def test_llm_action_click_requires_element_ref() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.CLICK, reason="need a ref")


def test_llm_action_type_requires_value() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.TYPE, element_ref=2, reason="type")


def test_llm_action_type_requires_element_ref() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.TYPE, value="M-1001", reason="type")


def test_llm_action_click_must_not_carry_value() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.CLICK, element_ref=1, value="oops", reason="x")


def test_llm_action_navigate_must_not_carry_element_ref() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.NAVIGATE, element_ref=1, value="http://x/", reason="x")


def test_llm_action_navigate_requires_http_url() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action=ActionType.NAVIGATE, value="javascript:alert(1)", reason="x")


def test_llm_action_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        LLMAction(action="teleport", element_ref=1, reason="x")


def _record(**overrides) -> StepRecord:
    data = {
        "step_index": 1,
        "action": ActionType.NAVIGATE,
        "reason": "open the console",
        "outcome": "ok",
        "snapshot_hash": "abc123",
        "elapsed_ms": 42,
        "max_steps": 15,
    }
    data.update(overrides)
    return StepRecord(**data)


def test_step_record_valid_round_trip() -> None:
    record = _record(
        policy_decision=PolicyDecisionRecord(decision="allow", reason="inside perimeter"),
        value_preview="http://127.0.0.1:5000/",
    )
    assert record.policy_decision is not None
    assert record.policy_decision.decision.value == "allow"
    assert json.loads(record.model_dump_json())["step_index"] == 1


def test_step_record_rejects_zero_step_index() -> None:
    with pytest.raises(ValidationError):
        _record(step_index=0)


def test_step_record_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        _record(debug=True)


def test_step_record_rejects_empty_policy_reason() -> None:
    with pytest.raises(ValidationError):
        _record(policy_decision=PolicyDecisionRecord(decision="allow", reason=""))


def test_result_requires_artifact_on_goal_reached() -> None:
    with pytest.raises(ValidationError):
        DiscoveryResult(status=RunStatus.GOAL_REACHED, steps=[])


def test_result_rejects_artifact_without_goal_reached() -> None:
    with pytest.raises(ValidationError):
        DiscoveryResult(status=RunStatus.BLOCKED, steps=[], artifact=_artifact())


def test_result_goal_reached_with_artifact_ok() -> None:
    result = DiscoveryResult(
        status=RunStatus.GOAL_REACHED,
        steps=[_record()],
        artifact=_artifact(),
        artifact_path=Path("evidence/artifact.json"),
        log_path=Path("evidence/log.jsonl"),
    )
    assert result.artifact is not None
    assert result.artifact.capability_id == "lookup_member_balance"


def test_result_rejects_artifact_path_without_artifact() -> None:
    with pytest.raises(ValidationError):
        DiscoveryResult(status=RunStatus.BLOCKED, steps=[], artifact_path=Path("evidence/x.json"))
