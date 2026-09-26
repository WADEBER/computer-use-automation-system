import pytest

from computer_use_automation_system.safety.models import DecisionKind, PolicyConfig
from computer_use_automation_system.safety.policy import evaluate, load_policy


def _policy(**overrides) -> PolicyConfig:
    data = {
        "allowed_origins": ["http://127.0.0.1:5000/"],
        "allowed_routes": ["/", "/members"],
        "allowed_action_types": ["navigate", "click", "type", "extract", "select"],
        "rules": [],
        "redaction": {
            "patterns": [{"name": "money", "regex": "\\b\\d+\\.\\d{2}\\b", "replacement": "[AMT]"}],
            "literals": ["Alice Hartwell"],
            "field_keys": ["full_name"],
        },
    }
    data.update(overrides)
    return PolicyConfig(**data)


def test_external_origin_is_blocked() -> None:
    decision = evaluate(_policy(), "click", "https://evil.example/steal?cookie=1")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_origins" in decision.reason


def test_route_outside_allowlist_is_blocked() -> None:
    decision = evaluate(_policy(), "click", "http://127.0.0.1:5000/admin/users")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_routes" in decision.reason


def test_disallowed_action_type_is_blocked() -> None:
    policy = _policy(allowed_action_types=["navigate", "click"])
    decision = evaluate(policy, "extract", "http://127.0.0.1:5000/members/M-1001")
    assert decision.decision is DecisionKind.BLOCK
    assert "extract" in decision.reason


def test_action_inside_perimeter_is_not_blocked() -> None:
    decision = evaluate(_policy(), "click", "http://127.0.0.1:5000/members/M-1001")
    assert decision.decision is not DecisionKind.BLOCK
    assert decision.reason


def test_home_route_allowed_and_admin_subpath_blocked() -> None:
    policy = _policy(allowed_routes=["/members"])
    home = evaluate(policy, "navigate", "http://127.0.0.1:5000/")
    assert home.decision is DecisionKind.BLOCK
    inside = evaluate(policy, "navigate", "http://127.0.0.1:5000/members/search?q=a")
    assert inside.decision is not DecisionKind.BLOCK


def test_relative_path_skips_origin_check() -> None:
    decision = evaluate(_policy(), "navigate", "/members/M-1001")
    assert decision.decision is not DecisionKind.BLOCK


def test_evaluate_rejects_unknown_action_string() -> None:
    with pytest.raises(ValueError):
        evaluate(_policy(), "teleport", "http://127.0.0.1:5000/")  # type: ignore[arg-type]


def test_default_policy_evaluates_entry_url() -> None:
    policy = load_policy()
    decision = evaluate(policy, "navigate", "http://127.0.0.1:5000/")
    assert decision.decision is not DecisionKind.BLOCK


def _policy_with_rules() -> PolicyConfig:
    return _policy(
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
        ]
    )


def test_rule_confirm_on_execute_route() -> None:
    decision = evaluate(
        _policy_with_rules(),
        "click",
        "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute",
    )
    assert decision.decision is DecisionKind.CONFIRM
    assert decision.matched_rule is not None
    assert "human approval" in decision.reason


def test_rule_flag_on_extract() -> None:
    decision = evaluate(_policy_with_rules(), "extract", "http://127.0.0.1:5000/members/M-1001")
    assert decision.decision is DecisionKind.FLAG
    assert "audit" in decision.reason


def test_allow_when_no_rule_matches() -> None:
    decision = evaluate(
        _policy_with_rules(), "type", "http://127.0.0.1:5000/members/search?q=M-1001"
    )
    assert decision.decision is DecisionKind.ALLOW
    assert decision.matched_rule is None
    assert decision.reason


def test_all_four_verdicts_covered() -> None:
    policy = _policy_with_rules()
    verdicts = {
        evaluate(policy, "click", "https://evil.example/x").decision,  # block
        evaluate(
            policy, "click", "http://127.0.0.1:5000/members/x/loans/y/execute"
        ).decision,  # confirm
        evaluate(policy, "extract", "http://127.0.0.1:5000/members/x").decision,  # flag
        evaluate(policy, "navigate", "http://127.0.0.1:5000/members/x").decision,  # allow
    }
    assert verdicts == {
        DecisionKind.BLOCK,
        DecisionKind.CONFIRM,
        DecisionKind.FLAG,
        DecisionKind.ALLOW,
    }


def test_first_matching_rule_wins() -> None:
    policy = _policy(
        rules=[
            {
                "match_action_type": "extract",
                "decision": "block",
                "reason": "extract forbidden in this deployment",
            },
            {
                "match_action_type": "extract",
                "decision": "flag",
                "reason": "second rule must never apply",
            },
        ]
    )
    decision = evaluate(policy, "extract", "http://127.0.0.1:5000/members/M-1001")
    assert decision.decision is DecisionKind.BLOCK
    assert "forbidden" in decision.reason


def test_every_decision_carries_a_reason() -> None:
    policy = _policy_with_rules()
    decisions = [
        evaluate(policy, "click", "https://evil.example/"),
        evaluate(policy, "click", "http://127.0.0.1:5000/a/execute"),
        evaluate(policy, "extract", "http://127.0.0.1:5000/members/M-1001"),
        evaluate(policy, "navigate", "http://127.0.0.1:5000/members/M-1001"),
    ]
    for decision in decisions:
        assert decision.reason.strip()


def test_safe_action_types_allowed_inside_perimeter() -> None:
    policy = _policy_with_rules()
    url = "http://127.0.0.1:5000/members/search?q=M-1001"
    for action in ("navigate", "click", "type", "select"):
        decision = evaluate(policy, action, url)
        assert decision.decision is DecisionKind.ALLOW, action


def test_perimeter_block_cannot_be_overridden_by_rules() -> None:
    policy = _policy(
        rules=[
            {
                "match_url_pattern": "*",
                "decision": "allow",
                "reason": "catch-all rule must not bypass the perimeter",
            }
        ]
    )
    decision = evaluate(policy, "click", "https://evil.example/x")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_origins" in decision.reason


def test_scheme_relative_url_is_blocked() -> None:
    decision = evaluate(_policy(), "navigate", "//evil.example/members")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_origins" in decision.reason


def test_scheme_relative_url_to_allowed_host_still_blocked() -> None:
    decision = evaluate(_policy(), "navigate", "//127.0.0.1:5000/members")
    assert decision.decision is DecisionKind.BLOCK


def test_dot_segment_path_cannot_escape_allowed_routes() -> None:
    decision = evaluate(_policy(), "navigate", "http://127.0.0.1:5000/members/../admin")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_routes" in decision.reason


def test_percent_encoded_dot_segments_cannot_escape_allowed_routes() -> None:
    decision = evaluate(_policy(), "navigate", "http://127.0.0.1:5000/members/%2e%2e/admin")
    assert decision.decision is DecisionKind.BLOCK
    assert "allowed_routes" in decision.reason


def test_origin_check_is_exact_not_prefix() -> None:
    policy = _policy(allowed_origins=["http://127.0.0.1:5000"])
    decision = evaluate(policy, "navigate", "http://127.0.0.1:50008/members")
    assert decision.decision is DecisionKind.BLOCK


def test_origin_match_works_with_or_without_trailing_slash_in_config() -> None:
    with_slash = evaluate(_policy(), "navigate", "http://127.0.0.1:5000/members")
    without_slash = evaluate(
        _policy(allowed_origins=["http://127.0.0.1:5000"]),
        "navigate",
        "http://127.0.0.1:5000/members",
    )
    assert with_slash.decision is not DecisionKind.BLOCK
    assert without_slash.decision is not DecisionKind.BLOCK
