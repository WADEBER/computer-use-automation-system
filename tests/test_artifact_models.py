import pytest
from pydantic import ValidationError

from computer_use_automation_system.artifact.models import Locator


def test_locator_valid_types() -> None:
    for locator_type in ("id", "css", "xpath", "role", "text"):
        locator = Locator(type=locator_type, value="something")
        assert locator.type == locator_type


def test_locator_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Locator(type="name", value="x")
    assert "type" in str(exc.value)


def test_locator_empty_value_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Locator(type="id", value="")
    assert "value" in str(exc.value)


def test_locator_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Locator(type="id", value="x", priority=1)  # type: ignore[call-arg]


def test_target_app_valid() -> None:
    from computer_use_automation_system.artifact.models import TargetApp

    app = TargetApp(name="MemberServ", entry_url="http://127.0.0.1:5000/")
    assert app.name == "MemberServ"
    assert app.entry_url == "http://127.0.0.1:5000/"


def test_target_app_requires_http_url() -> None:
    from computer_use_automation_system.artifact.models import TargetApp

    with pytest.raises(ValidationError) as exc:
        TargetApp(name="MemberServ", entry_url="ftp://example.com")
    assert "entry_url" in str(exc.value)


def test_json_schema_object_valid() -> None:
    from computer_use_automation_system.artifact.models import JSONSchemaObject

    schema = JSONSchemaObject(
        type="object",
        properties={"member_id": {"type": "string", "description": "id"}},
        required=["member_id"],
    )
    assert schema.type == "object"
    assert "member_id" in schema.properties


def test_json_schema_object_requires_non_empty_properties() -> None:
    from computer_use_automation_system.artifact.models import JSONSchemaObject

    with pytest.raises(ValidationError) as exc:
        JSONSchemaObject(type="object", properties={})
    assert "properties" in str(exc.value)


def test_json_schema_object_required_must_be_subset_of_properties() -> None:
    from computer_use_automation_system.artifact.models import JSONSchemaObject

    with pytest.raises(ValidationError) as exc:
        JSONSchemaObject(
            type="object",
            properties={"a": {"type": "string"}},
            required=["b"],
        )
    assert "required" in str(exc.value)


def test_json_schema_object_wrong_type_rejected() -> None:
    from computer_use_automation_system.artifact.models import JSONSchemaObject

    with pytest.raises(ValidationError) as exc:
        JSONSchemaObject(type="array", properties={"a": {"type": "string"}})
    assert "type" in str(exc.value)


def test_json_schema_object_property_requires_type() -> None:
    from computer_use_automation_system.artifact.models import JSONSchemaObject

    with pytest.raises(ValidationError) as exc:
        JSONSchemaObject(type="object", properties={"a": {"format": "uuid"}})
    assert "'a'" in str(exc.value)


def _base_step(**overrides) -> dict:
    data = {
        "step_id": 1,
        "action_type": "click",
        "description": "Click the search button",
        "locators": [{"type": "id", "value": "btn-search"}],
    }
    data.update(overrides)
    return data


def test_step_valid_click() -> None:
    from computer_use_automation_system.artifact.models import Step

    step = Step(**_base_step())
    assert step.action_type == "click"
    assert step.timeout_ms == 5000


def test_step_valid_type_with_template() -> None:
    from computer_use_automation_system.artifact.models import Step

    step = Step(**_base_step(action_type="type", value="{{input.member_id}}"))
    assert step.value == "{{input.member_id}}"


def test_step_type_without_value_rejected() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="type"))
    assert "value" in str(exc.value)


def test_step_type_literal_value_rejected() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="type", value="M-1001"))
    assert "input" in str(exc.value).lower()


def test_step_select_requires_template_value() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError):
        Step(**_base_step(action_type="select"))
    with pytest.raises(ValidationError):
        Step(**_base_step(action_type="select", value="literal"))
    step = Step(**_base_step(action_type="select", value="{{input.account}}"))
    assert step.value == "{{input.account}}"


def test_step_click_with_value_rejected() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="click", value="x"))
    assert "value" in str(exc.value)


def test_step_extract_requires_output_key() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="extract"))
    assert "output_key" in str(exc.value)
    step = Step(**_base_step(action_type="extract", output_key="balance"))
    assert step.output_key == "balance"


def test_step_extract_with_value_rejected() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="extract", output_key="balance", value="x"))
    assert "value" in str(exc.value)


def test_step_navigate_requires_url_value() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError):
        Step(**_base_step(action_type="navigate"))
    with pytest.raises(ValidationError):
        Step(**_base_step(action_type="navigate", value="not-a-url"))
    step = Step(**_base_step(action_type="navigate", value="http://127.0.0.1:5000/"))
    assert step.value.startswith("http")


def test_step_timeout_default_and_validation() -> None:
    from computer_use_automation_system.artifact.models import Step

    step = Step(**_base_step())
    assert step.timeout_ms == 5000
    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(timeout_ms=0))
    assert "timeout_ms" in str(exc.value)


def test_step_requires_locators_and_positive_step_id() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError):
        Step(**_base_step(locators=[]))
    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(step_id=0))
    assert "step_id" in str(exc.value)


def test_step_unknown_action_type_rejected() -> None:
    from computer_use_automation_system.artifact.models import Step

    with pytest.raises(ValidationError) as exc:
        Step(**_base_step(action_type="banana"))
    assert "action_type" in str(exc.value)


def test_checkpoint_valid() -> None:
    from computer_use_automation_system.artifact.models import Checkpoint

    checkpoint = Checkpoint(
        description="Results table is visible",
        locators=[{"type": "css", "value": "#searchResults"}],
        expected_condition="visible",
    )
    assert checkpoint.expected_condition == "visible"


def test_checkpoint_requires_locators() -> None:
    from computer_use_automation_system.artifact.models import Checkpoint

    with pytest.raises(ValidationError) as exc:
        Checkpoint(
            description="x",
            locators=[],
            expected_condition="visible",
        )
    assert "locators" in str(exc.value)


def test_checkpoint_unknown_condition_rejected() -> None:
    from computer_use_automation_system.artifact.models import Checkpoint

    with pytest.raises(ValidationError) as exc:
        Checkpoint(
            description="x",
            locators=[{"type": "id", "value": "y"}],
            expected_condition="clicked",
        )
    assert "expected_condition" in str(exc.value)


def test_checkpoint_all_conditions_accepted() -> None:
    from computer_use_automation_system.artifact.models import Checkpoint

    for condition in ("visible", "text_present", "url_contains"):
        checkpoint = Checkpoint(
            description="ok",
            locators=[{"type": "id", "value": "y"}],
            expected_condition=condition,
        )
        assert checkpoint.expected_condition == condition


def _base_artifact(**overrides) -> dict:
    data = {
        "capability_id": "lookup_member_balance",
        "version": "1.0.0",
        "description": "Searches for a member and extracts their balance.",
        "target_app": {"name": "MemberServ", "entry_url": "http://127.0.0.1:5000/"},
        "input_schema": {
            "type": "object",
            "properties": {"member_id": {"type": "string"}},
            "required": ["member_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"savings_balance": {"type": "string"}},
            "required": ["savings_balance"],
        },
        "steps": [
            {
                "step_id": 1,
                "action_type": "type",
                "description": "Enter the member ID",
                "locators": [{"type": "id", "value": "q"}],
                "value": "{{input.member_id}}",
            },
            {
                "step_id": 2,
                "action_type": "extract",
                "description": "Extract the balance",
                "locators": [{"type": "css", "value": "#bal"}],
                "output_key": "savings_balance",
            },
        ],
        "checkpoint": {
            "description": "Results visible",
            "locators": [{"type": "css", "value": "#searchResults"}],
            "expected_condition": "visible",
        },
    }
    data.update(overrides)
    return data


def test_artifact_valid_full() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    artifact = Artifact(**_base_artifact())
    assert artifact.capability_id == "lookup_member_balance"
    assert artifact.version == "1.0.0"
    assert len(artifact.steps) == 2
    assert artifact.steps[0].step_id == 1


def test_artifact_missing_field_names_field() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    data = _base_artifact()
    del data["target_app"]
    with pytest.raises(ValidationError) as exc:
        Artifact(**data)
    assert "target_app" in str(exc.value)


def test_artifact_bad_capability_id_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    with pytest.raises(ValidationError) as exc:
        Artifact(**_base_artifact(capability_id="LookupBalance"))
    assert "capability_id" in str(exc.value)


def test_artifact_bad_version_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    with pytest.raises(ValidationError) as exc:
        Artifact(**_base_artifact(version="1.0"))
    assert "version" in str(exc.value)


def test_artifact_empty_description_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    with pytest.raises(ValidationError) as exc:
        Artifact(**_base_artifact(description=""))
    assert "description" in str(exc.value)


def test_artifact_dangling_input_ref_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    data = _base_artifact()
    data["steps"][0]["value"] = "{{input.account_id}}"
    with pytest.raises(ValidationError) as exc:
        Artifact(**data)
    message = str(exc.value)
    assert "account_id" in message
    assert "input" in message.lower()


def test_artifact_unknown_output_key_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    data = _base_artifact()
    data["steps"][1]["output_key"] = "balance"
    with pytest.raises(ValidationError) as exc:
        Artifact(**data)
    message = str(exc.value)
    assert "balance" in message
    assert "output" in message.lower()


def test_artifact_non_sequential_step_ids_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    data = _base_artifact()
    data["steps"][1]["step_id"] = 5
    with pytest.raises(ValidationError) as exc:
        Artifact(**data)
    assert "step_id" in str(exc.value)


def test_artifact_without_steps_rejected() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    with pytest.raises(ValidationError) as exc:
        Artifact(**_base_artifact(steps=[]))
    assert "steps" in str(exc.value)


def test_artifact_forbids_extra_fields() -> None:
    from computer_use_automation_system.artifact.models import Artifact

    with pytest.raises(ValidationError):
        Artifact(**_base_artifact(tenant_id="acme"))  # type: ignore[call-arg]
