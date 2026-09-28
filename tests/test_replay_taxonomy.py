"""Phase 7: error taxonomy contract, config loading and classification
(spec HU-1..HU-4): FailureCategory on ReplayError, config/taxonomy.json
validation, and the deterministic classifier precedence."""

import pytest
from pydantic import ValidationError

from computer_use_automation_system.replay.models import ReplayError, ReplayStage


def test_step_error_accepts_failure_category() -> None:
    error = ReplayError(
        stage=ReplayStage.STEP,
        step_id=2,
        message="failed",
        failure_category="business_outcome",
    )
    assert error.failure_category == "business_outcome"


def test_checkpoint_error_accepts_failure_category() -> None:
    error = ReplayError(
        stage=ReplayStage.CHECKPOINT,
        step_id=6,
        message="not visible",
        failure_category="hard",
    )
    assert error.failure_category == "hard"


def test_failure_category_defaults_to_none() -> None:
    error = ReplayError(stage=ReplayStage.STEP, step_id=1, message="x")
    assert error.failure_category is None


@pytest.mark.parametrize("stage", ["input_validation", "output_validation"])
def test_validation_stages_reject_failure_category(stage) -> None:
    with pytest.raises(ValidationError):
        ReplayError(stage=stage, message="x", failure_category="hard")


def test_policy_stage_rejects_failure_category() -> None:
    with pytest.raises(ValidationError):
        ReplayError(
            stage=ReplayStage.POLICY,
            step_id=1,
            policy_kind="blocked",
            message="x",
            failure_category="hard",
        )


def test_failure_category_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        ReplayError(stage=ReplayStage.STEP, step_id=1, message="x", failure_category="weird")


def test_round_trip_preserves_failure_category() -> None:
    error = ReplayError(
        stage=ReplayStage.STEP,
        step_id=3,
        message="failed: element_not_found",
        failure_category="business_outcome",
    )
    restored = ReplayError.model_validate_json(error.model_dump_json())
    assert restored == error
    assert restored.failure_category == "business_outcome"


def test_load_default_taxonomy_from_repo_config() -> None:
    from computer_use_automation_system.replay.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()
    assert taxonomy.version.count(".") == 2
    assert taxonomy.max_recoverable_attempts >= 1
    assert "No records found" in taxonomy.patterns.business_outcome
    assert "stale" in taxonomy.recoverable_driver_codes
    assert isinstance(taxonomy.known_dialogs, list)


def test_load_taxonomy_reads_alternate_path(tmp_path) -> None:
    from computer_use_automation_system.replay.taxonomy import load_taxonomy

    alt = tmp_path / "alt.json"
    alt.write_text(
        '{"version": "2.0.0", "max_recoverable_attempts": 1,'
        ' "patterns": {"business_outcome": ["gone"], "recoverable": ["slow"],'
        ' "hard": ["denied"]},'
        ' "recoverable_driver_codes": ["timeout"], "known_dialogs": []}',
        encoding="utf-8",
    )
    taxonomy = load_taxonomy(alt)
    assert taxonomy.version == "2.0.0"
    assert taxonomy.patterns.business_outcome == ["gone"]


def test_broken_json_fails_with_clear_error(tmp_path) -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import load_taxonomy

    broken = tmp_path / "broken.json"
    broken.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_taxonomy(broken)


def test_missing_config_file_raises_os_error(tmp_path) -> None:
    from computer_use_automation_system.replay.taxonomy import load_taxonomy

    with pytest.raises(OSError):
        load_taxonomy(tmp_path / "missing.json")


def _base_config(**overrides) -> dict:
    payload = {
        "version": "1.0.0",
        "max_recoverable_attempts": 3,
        "patterns": {
            "business_outcome": ["No records found"],
            "recoverable": ["Loading"],
            "hard": ["Permission denied"],
        },
        "recoverable_driver_codes": ["stale", "timeout"],
        "known_dialogs": [],
    }
    payload.update(overrides)
    return payload


def test_unknown_top_level_key_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(_base_config(surprise=True))


def test_missing_category_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config()
    del payload["patterns"]["hard"]
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(payload)


def test_unknown_category_key_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config()
    payload["patterns"]["weird"] = ["x"]
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(payload)


def test_empty_pattern_string_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config()
    payload["patterns"]["business_outcome"] = [""]
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(payload)


def test_patterns_reject_control_characters() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config()
    payload["patterns"]["recoverable"] = ["Loading\r\nforged stderr line: OK"]
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(payload)


def test_known_dialog_pattern_rejects_control_characters() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config(
        known_dialogs=[
            {
                "pattern": "Session about to expire\x1b[31m",
                "dismiss_locator": {"type": "css", "value": "#dialog-dismiss"},
            }
        ]
    )
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(payload)


def test_attempts_below_one_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(_base_config(max_recoverable_attempts=0))


def test_unknown_driver_code_rejected() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(_base_config(recoverable_driver_codes=["mystery"]))


def test_semver_version_enforced() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(_base_config(version="next"))


def test_known_dialog_requires_dismiss_locator() -> None:
    from pydantic import ValidationError

    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(
            _base_config(known_dialogs=[{"pattern": "Session about to expire"}])
        )


def _taxonomy(**config_overrides):
    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = _base_config()
    payload.update(config_overrides)
    return TaxonomyConfig.model_validate(payload)


def _elements(*rows: dict) -> list[dict]:
    return list(rows)


def test_business_pattern_beats_driver_code() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        "element_not_found",
        _elements({"tag": "div", "text": 'No records found for "zzz"'}),
        _taxonomy(),
    )
    assert result.category == "business_outcome"
    assert "No records found" in result.signal
    assert result.dismiss_locator is None


def test_business_pattern_is_case_insensitive() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        None, _elements({"tag": "p", "text": "no RECORDS found"}), _taxonomy()
    )
    assert result.category == "business_outcome"


def test_business_beats_explicit_hard_pattern() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        None,
        _elements({"tag": "div", "text": "Permission denied. No records found."}),
        _taxonomy(),
    )
    assert result.category == "business_outcome"


def test_unknown_dialog_is_hard() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        None,
        _elements({"tag": "div", "role": "dialog", "text": "Surprise modal"}),
        _taxonomy(),
    )
    assert result.category == "hard"
    assert "dialog" in result.signal
    assert result.dismiss_locator is None


def test_unknown_dialog_beats_recoverable_code() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        "timeout",
        _elements({"tag": "div", "role": "alertdialog", "text": "Weird alert"}),
        _taxonomy(),
    )
    assert result.category == "hard"


def test_known_dialog_is_recoverable_with_dismiss_locator() -> None:
    from computer_use_automation_system.artifact.models import Locator
    from computer_use_automation_system.replay.taxonomy import classify_failure

    config = _taxonomy(
        known_dialogs=[
            {
                "pattern": "Session about to expire",
                "dismiss_locator": {"type": "css", "value": "#dialog-dismiss"},
            }
        ]
    )
    result = classify_failure(
        None,
        _elements({"tag": "div", "role": "dialog", "text": "Session about to expire soon"}),
        config,
    )
    assert result.category == "recoverable"
    assert result.dismiss_locator == Locator(type="css", value="#dialog-dismiss")
    assert "Session about to expire" in result.signal


def test_known_dialog_stays_recoverable_with_recoverable_code() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    config = _taxonomy(
        known_dialogs=[
            {
                "pattern": "Session about to expire",
                "dismiss_locator": {"type": "css", "value": "#dialog-dismiss"},
            }
        ]
    )
    result = classify_failure(
        "timeout",
        _elements({"tag": "div", "role": "dialog", "text": "Session about to expire"}),
        config,
    )
    assert result.category == "recoverable"
    assert result.dismiss_locator is not None


def test_explicit_hard_pattern_beats_known_dialog() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    config = _taxonomy(
        known_dialogs=[
            {
                "pattern": "Session about to expire",
                "dismiss_locator": {"type": "css", "value": "#dialog-dismiss"},
            }
        ]
    )
    result = classify_failure(
        None,
        _elements(
            {"tag": "div", "text": "Permission denied"},
            {"tag": "div", "role": "dialog", "text": "Session about to expire"},
        ),
        config,
    )
    assert result.category == "hard"
    assert result.dismiss_locator is None


def test_recoverable_driver_code_classified() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    for code in ("stale", "timeout"):
        result = classify_failure(code, _elements(), _taxonomy())
        assert result.category == "recoverable"
        assert code in result.signal


def test_recoverable_page_pattern_classified() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        None, _elements({"tag": "div", "text": "Loading, please wait"}), _taxonomy()
    )
    assert result.category == "recoverable"


def test_unmatched_code_defaults_to_hard() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure("element_not_found", _elements(), _taxonomy())
    assert result.category == "hard"
    assert "element_not_found" in result.signal


def test_no_code_no_signal_defaults_to_hard() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(None, _elements({"tag": "div", "text": "hello"}), _taxonomy())
    assert result.category == "hard"


def test_page_text_joins_text_name_and_value_fields() -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure

    result = classify_failure(
        None,
        _elements(
            {"tag": "h1", "name": "Header"},
            {"tag": "div", "value": "No records found"},
        ),
        _taxonomy(),
    )
    assert result.category == "business_outcome"


def test_editing_only_the_taxonomy_json_changes_classification(tmp_path) -> None:
    from computer_use_automation_system.replay.taxonomy import classify_failure, load_taxonomy

    elements = _elements({"tag": "div", "text": "Member suspended pending review"})
    assert classify_failure(None, elements, load_taxonomy()).category == "hard"

    alt = tmp_path / "taxonomy.json"
    alt.write_text(
        '{"version": "1.0.0", "max_recoverable_attempts": 3,'
        ' "patterns": {"business_outcome": ["Member suspended pending review"],'
        ' "recoverable": ["slow"], "hard": ["denied"]},'
        ' "recoverable_driver_codes": ["timeout"], "known_dialogs": []}',
        encoding="utf-8",
    )
    changed = classify_failure(None, elements, load_taxonomy(alt))
    assert changed.category == "business_outcome"
    assert "Member suspended pending review" in changed.signal
