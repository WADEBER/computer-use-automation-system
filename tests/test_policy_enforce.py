import pytest

from computer_use_automation_system.safety.models import DecisionKind, PolicyConfig
from computer_use_automation_system.safety.policy import (
    PolicyViolation,
    enforce,
    evaluate,
)


def _policy() -> PolicyConfig:
    return PolicyConfig(
        allowed_origins=["http://127.0.0.1:5000/"],
        allowed_routes=["/", "/members"],
        allowed_action_types=["navigate", "click", "type", "extract", "select"],
        rules=[
            {
                "match_url_pattern": "*/execute",
                "decision": "confirm",
                "reason": "Irreversible financial execution requires human approval",
            },
            {
                "match_action_type": "extract",
                "decision": "flag",
                "reason": "Read of regulated data leaves an audit mark",
            },
        ],
        redaction={
            "patterns": [{"name": "money", "regex": "\\b\\d+\\.\\d{2}\\b", "replacement": "[AMT]"}],
            "literals": ["Alice Hartwell"],
            "field_keys": ["full_name"],
        },
    )


def test_enforce_raises_on_block() -> None:
    with pytest.raises(PolicyViolation) as exc:
        enforce(_policy(), "click", "https://evil.example/x")
    assert exc.value.decision.decision is DecisionKind.BLOCK
    assert "allowed_origins" in str(exc.value)


def test_enforce_raises_on_unapproved_confirm() -> None:
    with pytest.raises(PolicyViolation) as exc:
        enforce(
            _policy(),
            "click",
            "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute",
        )
    assert exc.value.decision.decision is DecisionKind.CONFIRM


def test_enforce_passes_on_approved_confirm() -> None:
    decision = enforce(
        _policy(),
        "click",
        "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute",
        approved=True,
    )
    assert decision.decision is DecisionKind.CONFIRM
    assert decision.reason


def test_enforce_passes_flagged_action() -> None:
    decision = enforce(_policy(), "extract", "http://127.0.0.1:5000/members/M-1001")
    assert decision.decision is DecisionKind.FLAG
    assert decision.matched_rule is not None


def test_enforce_passes_allow_action() -> None:
    decision = enforce(_policy(), "navigate", "http://127.0.0.1:5000/")
    assert decision.decision is DecisionKind.ALLOW


def test_enforce_approval_ignored_without_confirm_rule() -> None:
    decision = enforce(_policy(), "navigate", "http://127.0.0.1:5000/members/M-1001", approved=True)
    assert decision.decision is DecisionKind.ALLOW


def test_evaluate_and_enforce_agree() -> None:
    policy = _policy()
    url = "http://127.0.0.1:5000/members/M-1001"
    assert evaluate(policy, "click", url).decision == enforce(policy, "click", url).decision
