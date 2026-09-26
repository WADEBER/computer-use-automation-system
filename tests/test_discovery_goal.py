import pytest

from computer_use_automation_system.discovery.goal import (
    GoalParseError,
    build_goal_prompt,
    check_goal,
    parse_goal_verdict,
)
from computer_use_automation_system.discovery.observe import Snapshot
from fakes import FakeLLMClient


def _snapshot() -> Snapshot:
    return Snapshot(
        elements=[],
        prompt_text="SNAPSHOT: url=... elements=1",
        truncated=False,
        digest="abc123",
    )


def test_parse_valid_verdict_true() -> None:
    verdict = parse_goal_verdict('{"goal_reached": true, "reason": "balance shown"}')
    assert verdict.goal_reached is True
    assert verdict.reason == "balance shown"


def test_parse_valid_verdict_false() -> None:
    verdict = parse_goal_verdict('{"goal_reached": false, "reason": "still searching"}')
    assert verdict.goal_reached is False


def test_parse_strips_markdown_fences() -> None:
    raw = '```json\n{"goal_reached": true, "reason": "done"}\n```'
    verdict = parse_goal_verdict(raw)
    assert verdict.goal_reached is True


def test_string_bool_is_rejected() -> None:
    with pytest.raises(GoalParseError):
        parse_goal_verdict('{"goal_reached": "yes", "reason": "done"}')


def test_empty_reason_is_rejected() -> None:
    with pytest.raises(GoalParseError):
        parse_goal_verdict('{"goal_reached": true, "reason": "  "}')


def test_non_json_is_rejected() -> None:
    with pytest.raises(GoalParseError):
        parse_goal_verdict("the goal is reached!")


def test_goal_prompt_contains_goal_and_snapshot() -> None:
    prompt = build_goal_prompt("Find the balance of M-1001", "SNAPSHOT: ...")
    assert "Find the balance of M-1001" in prompt
    assert "SNAPSHOT" in prompt
    assert "goal_reached" in prompt


def test_check_goal_uses_fake_llm_and_returns_verdict() -> None:
    client = FakeLLMClient(responses=['{"goal_reached": true, "reason": "extracted"}'])
    outcome = check_goal(client, "goal", _snapshot(), max_retries=1)
    assert outcome.verdict is not None
    assert outcome.verdict.goal_reached is True
    assert outcome.error is None
    assert outcome.attempts == 1


def test_check_goal_retries_then_fails_closed() -> None:
    client = FakeLLMClient(responses=["not json", "still not json", '{"goal_reached": maybe}'])
    outcome = check_goal(client, "goal", _snapshot(), max_retries=2)
    assert outcome.verdict is None
    assert outcome.error is not None
    assert outcome.attempts == 3
    assert len(client.prompts) == 3


def test_check_goal_feedback_appears_in_next_prompt() -> None:
    client = FakeLLMClient(
        responses=[
            "garbage",
            '{"goal_reached": false, "reason": "not yet"}',
        ]
    )
    outcome = check_goal(client, "goal", _snapshot(), max_retries=2)
    assert outcome.verdict is not None
    assert "PREVIOUS ANSWER REJECTED" in client.prompts[1]


def test_goal_prompt_marks_page_content_as_data_not_instructions() -> None:
    prompt = build_goal_prompt("Find the balance", "SNAPSHOT: [{}]")
    data_marker = prompt.index("never instructions")
    assert data_marker < prompt.index("SNAPSHOT:")
