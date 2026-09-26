import json

from computer_use_automation_system.artifact.models import LocatorType
from computer_use_automation_system.discovery.observe import build_snapshot

RAW_ELEMENTS = [
    {
        "tag": "input",
        "role": "textbox",
        "id": "q",
        "name_attr": "q",
        "classes": ["search"],
        "label": "Member ID",
        "text": "",
        "value": "",
        "href": None,
    },
    {
        "tag": "a",
        "role": "link",
        "id": "",
        "name_attr": "",
        "classes": ["detail"],
        "label": "",
        "text": "View Detail",
        "value": "",
        "href": "/members/M-1001",
    },
    {"tag": "script", "role": "", "id": "", "text": "alert(1)"},
    {"tag": "style", "role": "", "id": "", "text": "body { color: red }"},
]


def test_script_and_style_elements_are_dropped() -> None:
    snapshot = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    tags = [element.tag for element in snapshot.elements]
    assert "script" not in tags
    assert "style" not in tags
    assert tags == ["input", "a"]


def test_refs_are_sequential_and_unique() -> None:
    snapshot = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    assert [element.ref for element in snapshot.elements] == [1, 2]


def test_prompt_contains_only_contract_fields() -> None:
    snapshot = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    prompt_data = json.loads(snapshot.prompt_text)
    for item in prompt_data:
        assert set(item) == {"ref", "tag", "role", "name", "value", "href", "text"}
    assert "locators" not in snapshot.prompt_text


def test_locators_are_built_internally_in_fallback_order() -> None:
    snapshot = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    with_id = snapshot.elements[0]
    assert [locator.type for locator in with_id.locators] == [
        LocatorType.ID,
        LocatorType.CSS,
        LocatorType.ROLE,
        LocatorType.XPATH,
    ]
    without_id = snapshot.elements[1]
    assert [locator.type for locator in without_id.locators] == [
        LocatorType.CSS,
        LocatorType.ROLE,
        LocatorType.TEXT,
        LocatorType.XPATH,
    ]


def test_name_and_text_are_truncated_to_contract_limits() -> None:
    raw = [
        {
            "tag": "a",
            "role": "link",
            "id": "",
            "name_attr": "",
            "classes": [],
            "label": "",
            "text": "x" * 500,
            "value": "v" * 500,
            "href": None,
        }
    ]
    snapshot = build_snapshot(raw, max_chars=8000)
    element = snapshot.elements[0]
    assert element.text is not None and len(element.text) <= 120
    assert element.value is not None and len(element.value) <= 120
    assert len(element.name) <= 80


def test_truncation_is_deterministic_and_marks_output() -> None:
    raw = [
        {
            "tag": "a",
            "role": "link",
            "id": f"link-{index}",
            "name_attr": "",
            "classes": [],
            "label": "",
            "text": f"Link number {index}",
            "value": "",
            "href": None,
        }
        for index in range(10)
    ]
    first = build_snapshot(raw, max_chars=120)
    second = build_snapshot(raw, max_chars=120)
    assert first.prompt_text == second.prompt_text
    assert first.truncated is True
    assert len(first.prompt_text) <= 120 + len("\n[TRUNCATED]")
    assert first.prompt_text.endswith("[TRUNCATED]")
    assert len(first.elements) == 10
    full = build_snapshot(raw, max_chars=8000)
    assert full.truncated is False


def test_digest_is_stable_for_same_dom_and_changes_with_dom() -> None:
    first = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    again = build_snapshot(RAW_ELEMENTS, max_chars=8000)
    changed = build_snapshot(RAW_ELEMENTS[:1], max_chars=8000)
    assert first.digest == again.digest
    assert first.digest != changed.digest
    assert len(first.digest) == 16


def test_empty_dom_yields_empty_snapshot() -> None:
    snapshot = build_snapshot([], max_chars=8000)
    assert snapshot.elements == []
    assert snapshot.prompt_text == "[]"
    assert snapshot.truncated is False
