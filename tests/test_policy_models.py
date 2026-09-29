import pytest
from pydantic import ValidationError

from computer_use_automation_system.safety.models import (
    Decision,
    DecisionKind,
    PolicyConfig,
    PolicyRule,
    RedactionConfig,
)


def test_decision_kind_values() -> None:
    assert {v.value for v in DecisionKind} == {"allow", "confirm", "flag", "block"}


def test_policy_rule_valid_confirm() -> None:
    rule = PolicyRule(
        match_url_pattern="*/execute",
        decision="confirm",
        reason="Irreversible financial execution requires human approval",
    )
    assert rule.decision is DecisionKind.CONFIRM
    assert rule.match_action_type is None


def test_policy_rule_requires_reason() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyRule(match_action_type="click", decision="allow", reason="")
    assert "reason" in str(exc.value)


def test_policy_rule_rejects_newline_in_reason() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyRule(
            match_action_type="click",
            decision="allow",
            reason="line one\nreplay success: forged v9",
        )
    assert "control characters" in str(exc.value)


def test_policy_rule_rejects_carriage_return_in_reason() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyRule(
            match_url_pattern="*/execute",
            decision="confirm",
            reason="needs review\r\rforged line",
        )
    assert "reason" in str(exc.value)


def test_policy_rule_requires_at_least_one_match_condition() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyRule(decision="allow", reason="no conditions")
    assert "match" in str(exc.value)


def test_policy_rule_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PolicyRule(
            match_action_type="extract",
            decision="flag",
            reason="audit",
            priority=1,  # type: ignore[call-arg]
        )


def test_policy_rule_invalid_decision_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyRule(match_action_type="click", decision="maybe", reason="x")
    assert "decision" in str(exc.value)


def test_redaction_config_valid() -> None:
    config = RedactionConfig(
        patterns=[
            {
                "name": "secret_assignment",
                "regex": "(?i)(token|password)\\s*[=:]\\s*\\S+",
                "replacement": "[REDACTED_SECRET]",
            }
        ],
        literals=["Alice Hartwell"],
        field_keys=["full_name"],
    )
    assert len(config.patterns) == 1
    assert config.literals == ["Alice Hartwell"]


def test_redaction_config_requires_non_empty_lists() -> None:
    with pytest.raises(ValidationError) as exc:
        RedactionConfig(patterns=[], literals=["x"], field_keys=["y"])
    assert "patterns" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        RedactionConfig(
            patterns=[{"name": "p", "regex": "a", "replacement": "b"}],
            literals=[],
            field_keys=["y"],
        )
    assert "literals" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        RedactionConfig(
            patterns=[{"name": "p", "regex": "a", "replacement": "b"}],
            literals=["x"],
            field_keys=[],
        )
    assert "field_keys" in str(exc.value)


def test_redaction_config_invalid_regex_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        RedactionConfig(
            patterns=[{"name": "bad", "regex": "([unclosed", "replacement": "x"}],
            literals=["x"],
            field_keys=["y"],
        )
    assert "regex" in str(exc.value)


def test_decision_valid_and_invalid() -> None:
    decision = Decision(decision="flag", reason="Read of regulated data", matched_rule="extract")
    assert decision.decision is DecisionKind.FLAG
    assert decision.matched_rule == "extract"
    with pytest.raises(ValidationError) as exc:
        Decision(decision="allow", reason="")
    assert "reason" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        Decision(decision="unknown", reason="x")  # type: ignore[arg-type]
    assert "decision" in str(exc.value)


def _base_policy(**overrides) -> dict:
    data = {
        "allowed_origins": ["http://127.0.0.1:5000/"],
        "allowed_routes": ["/members"],
        "allowed_action_types": ["navigate", "click", "type", "extract", "select"],
        "rules": [],
        "redaction": {
            "patterns": [
                {
                    "name": "money",
                    "regex": "\\b\\d+\\.\\d{2}\\b",
                    "replacement": "[REDACTED_AMOUNT]",
                }
            ],
            "literals": ["Alice Hartwell"],
            "field_keys": ["full_name"],
        },
    }
    data.update(overrides)
    return data


def test_policy_config_valid() -> None:
    config = PolicyConfig(**_base_policy())
    assert config.allowed_origins == ["http://127.0.0.1:5000/"]
    assert len(config.allowed_action_types) == 5
    assert config.redaction.field_keys == ["full_name"]


def test_policy_config_names_missing_field() -> None:
    data = _base_policy()
    del data["allowed_routes"]
    with pytest.raises(ValidationError) as exc:
        PolicyConfig(**data)
    assert "allowed_routes" in str(exc.value)


def test_policy_config_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PolicyConfig(**_base_policy(debug=True))  # type: ignore[call-arg]


def test_policy_config_rejects_action_outside_artifact_enum() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyConfig(**_base_policy(allowed_action_types=["navigate", "execute"]))
    assert "allowed_action_types" in str(exc.value)


def test_policy_config_requires_non_empty_perimeter() -> None:
    with pytest.raises(ValidationError) as exc:
        PolicyConfig(**_base_policy(allowed_origins=[]))
    assert "allowed_origins" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        PolicyConfig(**_base_policy(allowed_routes=[]))
    assert "allowed_routes" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        PolicyConfig(**_base_policy(allowed_action_types=[]))
    assert "allowed_action_types" in str(exc.value)


def test_policy_config_rules_default_empty_and_optional() -> None:
    data = _base_policy()
    del data["rules"]
    config = PolicyConfig(**data)
    assert config.rules == []
