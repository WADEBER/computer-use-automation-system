import json

import pytest

from computer_use_automation_system.discovery.decide import (
    ActionParseError,
    HistoryItem,
    build_decide_prompt,
    decide,
    parse_llm_action,
)
from computer_use_automation_system.discovery.observe import build_snapshot
from fakes import FakeLLMClient

SNAPSHOT = build_snapshot(
    [
        {"tag": "input", "role": "textbox", "id": "q", "label": "Search", "text": ""},
        {"tag": "a", "role": "link", "id": "", "text": "View Detail", "href": "/x"},
    ],
    max_chars=8000,
)
REFS = {element.ref for element in SNAPSHOT.elements}


def _history() -> list[HistoryItem]:
    return [HistoryItem(action="navigate", reason="open console", outcome="ok")]


def test_parse_valid_click() -> None:
    raw = json.dumps({"action": "click", "element_ref": 2, "reason": "open detail"})
    action = parse_llm_action(raw, REFS)
    assert action.action.value == "click"
    assert action.element_ref == 2


def test_parse_strips_markdown_fences() -> None:
    raw = '```json\n{"action": "click", "element_ref": 1, "reason": "search"}\n```'
    action = parse_llm_action(raw, REFS)
    assert action.element_ref == 1


def test_parse_rejects_unknown_ref() -> None:
    raw = json.dumps({"action": "click", "element_ref": 99, "reason": "x"})
    with pytest.raises(ActionParseError):
        parse_llm_action(raw, REFS)


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(ActionParseError):
        parse_llm_action("I think you should click the link", REFS)


def test_parse_rejects_schema_violation() -> None:
    with pytest.raises(ActionParseError):
        parse_llm_action(json.dumps({"action": "click", "reason": "no ref"}), REFS)


def test_prompt_contains_goal_snapshot_and_history() -> None:
    prompt = build_decide_prompt("find the balance", SNAPSHOT.prompt_text, _history())
    assert "find the balance" in prompt
    assert SNAPSHOT.prompt_text in prompt
    assert "open console" in prompt
    assert "JSON" in prompt


def test_prompt_feedback_is_included_on_retry() -> None:
    prompt = build_decide_prompt("goal", "[]", [], feedback="element_ref 99 not in snapshot")
    assert "element_ref 99 not in snapshot" in prompt


def test_decide_first_try_success() -> None:
    client = FakeLLMClient(
        responses=[json.dumps({"action": "click", "element_ref": 2, "reason": "detail"})]
    )
    outcome = decide(client, "goal", SNAPSHOT, [], max_retries=2)
    assert outcome.action is not None
    assert outcome.action.element_ref == 2
    assert outcome.error is None
    assert outcome.attempts == 1


def test_decide_retries_invalid_then_succeeds() -> None:
    client = FakeLLMClient(
        responses=[
            "not json at all",
            json.dumps({"action": "click", "element_ref": 1, "reason": "retry ok"}),
        ]
    )
    outcome = decide(client, "goal", SNAPSHOT, [], max_retries=2)
    assert outcome.action is not None
    assert outcome.attempts == 2
    assert len(client.prompts) == 2
    assert "not json" in client.prompts[1]


def test_decide_fails_closed_after_retries() -> None:
    client = FakeLLMClient(responses=["still bad", "still bad", "still bad"])
    outcome = decide(client, "goal", SNAPSHOT, [], max_retries=2)
    assert outcome.action is None
    assert outcome.error is not None
    assert outcome.attempts == 3


def test_decide_treats_transport_error_as_failure() -> None:
    def boom(prompt: str) -> str:
        raise ConnectionError("ollama down")

    client = FakeLLMClient(handler=boom)
    outcome = decide(client, "goal", SNAPSHOT, [], max_retries=1)
    assert outcome.action is None
    assert outcome.error is not None
    assert "ollama down" in outcome.error
    assert outcome.attempts == 2


def test_prompt_marks_page_content_as_data_not_instructions() -> None:
    prompt = build_decide_prompt("Find the balance", SNAPSHOT.prompt_text, _history())
    data_marker = prompt.index("never instructions")
    snapshot_pos = prompt.index("SNAPSHOT:")
    assert data_marker < snapshot_pos
    assert prompt.index("GOAL:") > data_marker
