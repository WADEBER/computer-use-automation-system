import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from computer_use_automation_system.safety.policy import load_policy

REPO_ROOT = Path(__file__).parents[1]
POLICY_FILE = REPO_ROOT / "config" / "policy.json"


def test_load_default_policy() -> None:
    policy = load_policy()
    assert policy.allowed_origins == ["http://127.0.0.1:5000/"]
    assert "/" in policy.allowed_routes
    assert "/members" in policy.allowed_routes
    assert len(policy.allowed_action_types) == 5
    confirm_rules = [r for r in policy.rules if r.decision.value == "confirm"]
    flag_rules = [r for r in policy.rules if r.decision.value == "flag"]
    assert len(confirm_rules) == 1
    assert confirm_rules[0].match_url_pattern == "*/execute"
    assert len(flag_rules) == 1
    assert flag_rules[0].match_action_type == "extract"
    assert "Alice Hartwell" in policy.redaction.literals


def test_policy_file_is_valid_json_without_real_secrets() -> None:
    content = POLICY_FILE.read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert isinstance(parsed, dict)
    assert "redaction" in parsed
    for key in ("api_key", "password", "secret_key"):
        assert key not in parsed, f"policy file must not contain live credentials: {key}"


def test_load_policy_names_missing_field(tmp_path: Path) -> None:
    raw = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    del raw["allowed_routes"]
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_policy(bad)
    assert "allowed_routes" in str(exc.value)


def test_load_policy_rejects_extra_field(tmp_path: Path) -> None:
    raw = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    raw["debug_mode"] = True
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_policy(bad)
    assert "debug_mode" in str(exc.value)


def test_load_policy_rejects_wrong_type(tmp_path: Path) -> None:
    raw = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    raw["allowed_action_types"] = "navigate"
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_policy(bad)
    assert "allowed_action_types" in str(exc.value)


def test_editing_only_the_json_changes_verdicts(tmp_path: Path) -> None:
    from computer_use_automation_system.safety.policy import evaluate

    raw = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    wide = tmp_path / "wide.json"
    wide.write_text(json.dumps(raw), encoding="utf-8")

    narrower = json.loads(json.dumps(raw))
    narrower["allowed_action_types"] = ["navigate"]
    narrow_path = tmp_path / "narrow.json"
    narrow_path.write_text(json.dumps(narrower), encoding="utf-8")

    url = "http://127.0.0.1:5000/members/M-1001"
    wide_verdict = evaluate(load_policy(wide), "extract", url)
    narrow_verdict = evaluate(load_policy(narrow_path), "extract", url)
    assert wide_verdict != narrow_verdict
    assert narrow_verdict.decision.value == "block"
