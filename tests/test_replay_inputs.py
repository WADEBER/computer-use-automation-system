"""Phase 6: input validation against `input_schema` + `{{input.*}}` resolution."""

import pytest

from computer_use_automation_system.artifact.models import JSONSchemaObject
from computer_use_automation_system.replay.inputs import resolve_value, validate_inputs

SCHEMA = JSONSchemaObject(
    type="object",
    properties={
        "member_id": {"type": "string"},
        "retries": {"type": "integer"},
        "ratio": {"type": "number"},
        "verbose": {"type": "boolean"},
    },
    required=["member_id"],
)


def test_all_required_present_returns_no_problems() -> None:
    assert validate_inputs(SCHEMA, {"member_id": "M-1001"}) == []


def test_missing_required_is_reported() -> None:
    problems = validate_inputs(SCHEMA, {})
    assert len(problems) == 1
    assert "member_id" in problems[0]


def test_type_mismatch_is_reported() -> None:
    problems = validate_inputs(SCHEMA, {"member_id": 42})
    assert len(problems) == 1
    assert "member_id" in problems[0]
    assert "string" in problems[0]


def test_optional_fields_are_validated_when_present() -> None:
    assert validate_inputs(SCHEMA, {"member_id": "M-1", "retries": 3}) == []
    problems = validate_inputs(SCHEMA, {"member_id": "M-1", "retries": "3"})
    assert len(problems) == 1
    assert "retries" in problems[0]


def test_integer_rejects_bool_and_float_and_number_accepts_int() -> None:
    assert validate_inputs(SCHEMA, {"member_id": "M", "retries": 5}) == []
    assert validate_inputs(SCHEMA, {"member_id": "M", "retries": True}) != []
    assert validate_inputs(SCHEMA, {"member_id": "M", "retries": 1.5}) != []
    assert validate_inputs(SCHEMA, {"member_id": "M", "ratio": 2}) == []


def test_extra_required_keys_for_step_references() -> None:
    problems = validate_inputs(SCHEMA, {"member_id": "M-1001"}, extra_required={"destination"})
    assert len(problems) == 1
    assert "destination" in problems[0]


def test_unknown_properties_are_not_rejected() -> None:
    assert validate_inputs(SCHEMA, {"member_id": "M", "typo": "x"}) == []


def test_resolve_value_substitutes_single_reference() -> None:
    assert resolve_value("{{input.member_id}}", {"member_id": "M-1001"}) == "M-1001"


def test_resolve_value_substitutes_mixed_and_literal_text() -> None:
    resolved = resolve_value(
        "/members/{{input.member_id}}/edit?n={{input.retries}}",
        {"member_id": "M-9", "retries": 2},
    )
    assert resolved == "/members/M-9/edit?n=2"
    assert resolve_value("plain text", {}) == "plain text"
    assert resolve_value(None, {}) is None


def test_resolve_value_raises_on_missing_reference() -> None:
    with pytest.raises(KeyError):
        resolve_value("{{input.ghost}}", {"member_id": "M-1001"})
