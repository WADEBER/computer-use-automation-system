from computer_use_automation_system.artifact.models import Artifact, Locator, LocatorType
from computer_use_automation_system.discovery.artifact_builder import StepSource, build_artifact
from computer_use_automation_system.discovery.models import ActionType, ObservedElement, StepRecord


def _record(
    step_index: int = 1,
    action: ActionType = ActionType.CLICK,
    value_preview: str | None = None,
    outcome: str = "ok",
    reason: str = "open member detail",
) -> StepRecord:
    return StepRecord(
        step_index=step_index,
        action=action,
        element_ref=step_index,
        value_preview=value_preview,
        reason=reason,
        outcome=outcome,
        snapshot_hash="abc123",
        elapsed_ms=10,
        max_steps=15,
    )


def _element(
    ref: int = 1,
    name: str = "Member ID",
    locators: list[Locator] | None = None,
) -> ObservedElement:
    return ObservedElement(
        ref=ref,
        tag="input",
        role="textbox",
        name=name,
        locators=locators
        or [
            Locator(type=LocatorType.ID, value="member-id"),
            Locator(type=LocatorType.CSS, value="input#member-id"),
        ],
    )


def test_minimal_click_artifact_validates() -> None:
    artifact = build_artifact(
        goal="Find the balance of member M-1001",
        entry_url="http://127.0.0.1:5000/",
        steps=[StepSource(record=_record(), element=_element())],
    )
    assert isinstance(artifact, Artifact)
    assert artifact.capability_id == "find_the_balance_of_member_m_1001"
    assert artifact.version == "1.0.0"
    assert artifact.target_app.entry_url == "http://127.0.0.1:5000/"
    Artifact.model_validate_json(artifact.model_dump_json())


def test_navigate_step_keeps_url_and_body_fallback_locators() -> None:
    artifact = build_artifact(
        goal="open the app",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(
                    action=ActionType.NAVIGATE, value_preview="http://127.0.0.1:5000/login"
                )
            )
        ],
    )
    step = artifact.steps[0]
    assert step.value == "http://127.0.0.1:5000/login"
    assert step.locators[0] == Locator(type=LocatorType.CSS, value="body")


def test_type_step_is_parametrized_with_input_ref() -> None:
    artifact = build_artifact(
        goal="search a member",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(action=ActionType.TYPE, value_preview="M-1001"), element=_element()
            )
        ],
    )
    step = artifact.steps[0]
    assert step.value == "{{input.member_id}}"
    assert "member_id" in artifact.input_schema.properties
    assert artifact.input_schema.required == ["member_id"]
    assert "M-1001" not in artifact.model_dump_json()


def test_input_key_falls_back_to_step_position_without_name() -> None:
    artifact = build_artifact(
        goal="search",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(action=ActionType.TYPE, value_preview="x"),
                element=_element(name="  "),
            )
        ],
    )
    assert "step1_value" in artifact.input_schema.properties
    assert artifact.steps[0].value == "{{input.step1_value}}"


def test_input_key_collision_gets_position_suffix() -> None:
    artifact = build_artifact(
        goal="search twice",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(record=_record(1, ActionType.TYPE, "aaa"), element=_element(1, "Query")),
            StepSource(record=_record(2, ActionType.TYPE, "bbb"), element=_element(1, "Query")),
        ],
    )
    keys = set(artifact.input_schema.properties)
    assert {"query", "query_2"} <= keys
    assert artifact.steps[1].value == "{{input.query_2}}"


def test_extract_sets_output_key_in_output_schema() -> None:
    artifact = build_artifact(
        goal="read the balance",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(1, ActionType.EXTRACT, "4250.75"),
                element=_element(1, "Balance"),
            )
        ],
    )
    step = artifact.steps[0]
    assert step.output_key == "output1"
    assert artifact.output_schema.properties == {"output1": {"type": "string"}}
    assert artifact.output_schema.required == ["output1"]
    assert step.value is None


def test_failed_steps_are_excluded_and_step_ids_renumbered() -> None:
    artifact = build_artifact(
        goal="reach the ledger",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(1, ActionType.CLICK, outcome="element_not_found"),
                element=_element(1),
            ),
            StepSource(record=_record(2, ActionType.CLICK), element=_element(2)),
        ],
    )
    assert len(artifact.steps) == 1
    assert artifact.steps[0].step_id == 1


def test_schemas_have_fallback_property_when_empty() -> None:
    artifact = build_artifact(
        goal="just navigate",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(
                record=_record(action=ActionType.NAVIGATE, value_preview="http://127.0.0.1:5000/")
            )
        ],
    )
    assert len(artifact.input_schema.properties) >= 1
    assert len(artifact.output_schema.properties) >= 1
    assert artifact.output_schema.required == []


def test_locators_keep_fallback_priority_order() -> None:
    locators = [
        Locator(type=LocatorType.ID, value="q"),
        Locator(type=LocatorType.CSS, value="input#q"),
        Locator(type=LocatorType.XPATH, value="//input[@id='q']"),
    ]
    artifact = build_artifact(
        goal="type",
        entry_url="http://127.0.0.1:5000/",
        steps=[
            StepSource(record=_record(1, ActionType.TYPE, "v"), element=_element(1, "Q", locators))
        ],
    )
    assert artifact.steps[0].locators == locators


def test_dump_json_is_stable_across_builds() -> None:
    sources = [
        StepSource(
            record=_record(1, ActionType.NAVIGATE, "http://127.0.0.1:5000/login"),
        ),
        StepSource(record=_record(2, ActionType.TYPE, "M-1001"), element=_element(1)),
        StepSource(record=_record(3, ActionType.CLICK), element=_element(2, "Search")),
        StepSource(record=_record(4, ActionType.EXTRACT, "100"), element=_element(3, "Total")),
    ]
    first = build_artifact("get total", "http://127.0.0.1:5000/", sources)
    second = build_artifact("get total", "http://127.0.0.1:5000/", sources)
    assert first.model_dump_json() == second.model_dump_json()
    Artifact.model_validate_json(first.model_dump_json())
