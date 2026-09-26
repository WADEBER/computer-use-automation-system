import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from computer_use_automation_system.artifact.models import Artifact

FIXTURES = Path(__file__).parent / "fixtures"
VALID_FIXTURE = FIXTURES / "valid_artifact.json"
INVALID_DIR = FIXTURES / "invalid"
SCHEMA_PATH = Path(__file__).parents[1] / "docs" / "schemas" / "artifact.schema.json"


def test_valid_fixture_loads() -> None:
    raw = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    artifact = Artifact(**raw)
    assert artifact.capability_id == "lookup_member_balance"
    assert len(artifact.steps) >= 3
    assert artifact.checkpoint is not None


def test_invalid_bad_locator_rejected() -> None:
    raw = json.loads((INVALID_DIR / "bad_locator.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError) as exc:
        Artifact(**raw)
    assert "magic" in str(exc.value)


def test_invalid_bad_input_ref_rejected() -> None:
    raw = json.loads((INVALID_DIR / "bad_input_ref.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError) as exc:
        Artifact(**raw)
    assert "account_id" in str(exc.value)


def test_invalid_missing_checkpoint_rejected() -> None:
    raw = json.loads((INVALID_DIR / "missing_checkpoint.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError) as exc:
        Artifact(**raw)
    assert "checkpoint" in str(exc.value)


def test_round_trip_preserves_artifact() -> None:
    raw = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    artifact = Artifact(**raw)
    serialized = artifact.model_dump_json(indent=2)
    reloaded = Artifact.model_validate_json(serialized)
    assert reloaded.model_dump(mode="json") == artifact.model_dump(mode="json")


def test_exported_schema_matches_model() -> None:
    assert SCHEMA_PATH.exists(), (
        "docs/schemas/artifact.schema.json is missing; regenerate it as described "
        "in README.md, section 'Exported JSON Schema'"
    )
    exported = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    current = Artifact.model_json_schema()
    assert exported == current, (
        "Exported JSON Schema is out of date; regenerate docs/schemas/artifact.schema.json"
    )
