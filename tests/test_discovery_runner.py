import io
import json
from pathlib import Path
from urllib.parse import urljoin

import pytest

from computer_use_automation_system.artifact.models import ActionType, Artifact, ExpectedCondition
from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    LLMAction,
    RunStatus,
)
from computer_use_automation_system.discovery.runner import _make_record, run_discovery
from computer_use_automation_system.safety.models import (
    DecisionKind,
    PolicyConfig,
    PolicyRule,
    RedactionConfig,
    RedactionPattern,
)

ENTRY_URL = "http://127.0.0.1:5000/"
MEMBERS_URL = "http://127.0.0.1:5000/members/M-1001"

_ENTRY_RAW = [{"tag": "a", "id": "view-detail", "label": "View Detail", "href": "/members/M-1001"}]
_MEMBERS_RAW = [{"tag": "span", "id": "balance", "label": "Balance", "text": "4250.75"}]
_SEARCH_RAW = [{"tag": "input", "id": "member-id", "name_attr": "member_id", "label": "Member ID"}]


class FakeDriver:
    def __init__(self, pages: dict[str, list[dict]], start_url: str) -> None:
        self.pages = pages
        self.url = start_url
        self.calls: list[tuple] = []

    def observe_raw(self) -> list[dict]:
        return self.pages.get(self.url, [])

    def current_url(self) -> str:
        return self.url

    def navigate(self, url: str) -> None:
        self.calls.append(("navigate", url))
        self.url = url

    def click(self, element) -> None:
        self.calls.append(("click", element.ref, self.url))
        if element.href:
            self.url = urljoin(self.url, element.href)

    def type_text(self, element, text: str) -> None:
        self.calls.append(("type", element.ref, text))

    def select_option(self, element, option: str) -> None:
        self.calls.append(("select", element.ref, option))

    def extract_text(self, element) -> str:
        self.calls.append(("extract", element.ref, self.url))
        return "4250.75"

    def quit(self) -> None:
        self.calls.append(("quit",))


class ScriptedLLM:
    def __init__(self, actions: list[str], goals: list[str] | None = None) -> None:
        self.actions = list(actions)
        self.goals = list(goals or [])
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "goal_reached" in prompt:
            if not self.goals:
                return '{"goal_reached": false, "reason": "not yet"}'
            return self.goals.pop(0)
        return self.actions.pop(0)


def _policy(rules: list[PolicyRule] | None = None) -> PolicyConfig:
    return PolicyConfig(
        allowed_origins=["http://127.0.0.1:5000"],
        allowed_routes=["/", "/members"],
        allowed_action_types=list(ActionType),
        rules=rules or [],
        redaction=RedactionConfig(
            patterns=[
                RedactionPattern(
                    name="card", regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b", replacement="[REDACTED_CARD]"
                )
            ],
            literals=["Alice Smith"],
            field_keys=["value_preview"],
        ),
    )


def _config(tmp_path: Path, **overrides) -> DiscoveryConfig:
    base: dict = {
        "goal": "Open the member detail and read the balance",
        "entry_url": ENTRY_URL,
        "max_steps": 6,
        "repeat_threshold": 3,
        "artifact_out": tmp_path / "artifact.json",
        "log_out": tmp_path / "steps.jsonl",
    }
    base.update(overrides)
    return DiscoveryConfig(**base)


def _run(config, driver, llm, policy, clock=lambda: 0.0) -> DiscoveryResult:
    out = io.StringIO()
    logger = StepLogger(config.log_out, policy.redaction, stdout=out)
    result = run_discovery(config, driver, llm, policy, logger=logger, clock=clock)
    return result


def test_goal_reached_writes_valid_artifact_and_evidence(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW, MEMBERS_URL: _MEMBERS_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}',
            '{"action": "extract", "element_ref": 1, "value": null, "reason": "read balance"}',
        ],
        goals=[
            '{"goal_reached": false, "reason": "not there yet"}',
            '{"goal_reached": false, "reason": "not there yet"}',
            '{"goal_reached": true, "reason": "balance is on screen"}',
        ],
    )
    result = _run(_config(tmp_path), driver, llm, _policy())

    assert result.status is RunStatus.GOAL_REACHED
    assert result.artifact is not None
    artifact = Artifact.model_validate_json(result.artifact.model_dump_json())
    assert [step.action_type for step in artifact.steps] == [ActionType.CLICK, ActionType.EXTRACT]
    checkpoint = artifact.checkpoint
    assert checkpoint.expected_condition == ExpectedCondition.URL_CONTAINS
    assert checkpoint.locators[0].value == "http://127.0.0.1:5000/members"
    assert "M-1001" not in checkpoint.model_dump_json()
    assert result.artifact_path is not None and Path(result.artifact_path).exists()
    raw = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))
    Artifact.model_validate(raw)
    assert result.log_path is not None and Path(result.log_path).exists()
    log_lines = Path(result.log_path).read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 3  # 2 steps + final summary event
    summary = json.loads(log_lines[-1])
    assert summary == {"event": "summary", "status": "goal_reached", "steps": 2}
    assert len(result.steps) == 2
    assert all(step.policy_decision is not None for step in result.steps)
    assert driver.calls[0][0] == "click"


def test_blocked_action_never_reaches_driver(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "navigate", "element_ref": null, "value": "https://evil.example/x", '
            '"reason": "go elsewhere"}'
        ]
    )
    result = _run(_config(tmp_path), driver, llm, _policy())

    assert result.status is RunStatus.BLOCKED
    assert driver.calls == []
    assert result.artifact is None
    assert len(result.steps) == 1
    last = result.steps[0]
    assert last.policy_decision is not None
    assert last.policy_decision.decision is DecisionKind.BLOCK
    assert last.outcome == "blocked"
    assert last.value_preview == "https://evil.example/x"


def test_confirm_verdict_ends_with_needs_approval_without_acting(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=['{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}']
    )
    policy = _policy(
        [
            PolicyRule(
                match_action_type=ActionType.CLICK,
                decision=DecisionKind.CONFIRM,
                reason="clicks require human approval",
            )
        ]
    )
    result = _run(_config(tmp_path), driver, llm, policy)

    assert result.status is RunStatus.NEEDS_APPROVAL
    assert driver.calls == []
    assert result.steps[0].policy_decision is not None
    assert result.steps[0].policy_decision.decision is DecisionKind.CONFIRM
    assert result.steps[0].outcome == "needs_approval"


def test_flag_verdict_still_executes_and_is_recorded(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW, MEMBERS_URL: _MEMBERS_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=['{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}'],
        goals=[
            '{"goal_reached": false, "reason": "not yet"}',
            '{"goal_reached": true, "reason": "detail visible"}',
        ],
    )
    policy = _policy(
        [
            PolicyRule(
                match_action_type=ActionType.CLICK,
                decision=DecisionKind.FLAG,
                reason="clicks are audited",
            )
        ]
    )
    result = _run(_config(tmp_path), driver, llm, policy)

    assert result.status is RunStatus.GOAL_REACHED
    assert driver.calls[0][0] == "click"
    assert result.steps[0].policy_decision is not None
    assert result.steps[0].policy_decision.decision is DecisionKind.FLAG


def test_repeated_snapshot_hash_ends_dead_end(tmp_path) -> None:
    stuck_page = [{"tag": "button", "id": "retry", "label": "Retry"}]
    driver = FakeDriver({ENTRY_URL: stuck_page}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=['{"action": "click", "element_ref": 1, "value": null, "reason": "try again"}']
    )
    config = _config(tmp_path, repeat_threshold=2, max_steps=10)
    result = _run(config, driver, llm, _policy())

    assert result.status is RunStatus.DEAD_END
    assert result.artifact is None
    click_calls = [call for call in driver.calls if call[0] == "click"]
    assert len(click_calls) == 1
    assert len(result.steps) == 1


def test_invalid_llm_decisions_fail_closed_as_llm_error(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=["this is not json"], goals=['{"goal_reached": false, "reason": "no"}']
    )
    config = _config(tmp_path, max_llm_retries=0)
    result = _run(config, driver, llm, _policy())

    assert result.status is RunStatus.LLM_ERROR
    assert result.steps == []
    assert driver.calls == []
    assert result.artifact is None


def test_max_steps_stops_the_loop(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=['{"action": "click", "element_ref": 1, "value": null, "reason": "click"}'] * 3
    )
    config = _config(tmp_path, max_steps=1, repeat_threshold=5)
    result = _run(config, driver, llm, _policy())

    assert result.status is RunStatus.MAX_STEPS
    assert len(result.steps) == 1
    assert result.steps[0].max_steps == 1
    assert result.artifact is None


def test_global_timeout_stops_before_any_action(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(actions=[])
    config = _config(tmp_path, total_timeout_ms=300000)
    ticks = iter([0.0, 1000.0])
    result = _run(config, driver, llm, _policy(), clock=lambda: next(ticks, 1000.0))

    assert result.status is RunStatus.TIMEOUT
    assert result.steps == []
    assert driver.calls == []


def test_type_values_are_redacted_before_log_and_result(tmp_path) -> None:
    driver = FakeDriver({ENTRY_URL: _SEARCH_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "type", "element_ref": 1, "value": "4111-1111-1111-1111", '
            '"reason": "enter card number"}'
        ],
        goals=[
            '{"goal_reached": false, "reason": "no"}',
            '{"goal_reached": true, "reason": "done"}',
        ],
    )
    result = _run(_config(tmp_path), driver, llm, _policy())

    assert result.status is RunStatus.GOAL_REACHED
    assert result.steps[0].value_preview == "[REDACTED_CARD]"
    dumped = json.dumps(result.model_dump(mode="json"))
    assert "4111-1111-1111-1111" not in dumped
    log_content = Path(result.log_path).read_text(encoding="utf-8")
    assert "4111-1111-1111-1111" not in log_content
    assert "4111" not in Path(result.artifact_path).read_text(encoding="utf-8")


def test_same_fakes_produce_identical_step_sequences(tmp_path) -> None:
    def one_run(folder: Path):
        driver = FakeDriver({ENTRY_URL: _ENTRY_RAW, MEMBERS_URL: _MEMBERS_RAW}, ENTRY_URL)
        llm = ScriptedLLM(
            actions=[
                '{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}',
                '{"action": "extract", "element_ref": 1, "value": null, "reason": "read balance"}',
            ],
            goals=[
                '{"goal_reached": false, "reason": "no"}',
                '{"goal_reached": false, "reason": "no"}',
                '{"goal_reached": true, "reason": "yes"}',
            ],
        )
        return _run(_config(folder), driver, llm, _policy())

    first = one_run(tmp_path / "a")
    second = one_run(tmp_path / "b")
    seq_a = [
        (s.step_index, s.action, s.outcome, s.snapshot_hash, s.elapsed_ms) for s in first.steps
    ]
    seq_b = [
        (s.step_index, s.action, s.outcome, s.snapshot_hash, s.elapsed_ms) for s in second.steps
    ]
    assert seq_a == seq_b
    assert first.status is second.status
    assert first.artifact is not None and second.artifact is not None
    assert first.artifact.model_dump_json() == second.artifact.model_dump_json()


def test_result_invariants_hold_for_every_status(tmp_path) -> None:
    cases = []
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(actions=["not json"], goals=['{"goal_reached": false, "reason": "no"}'])
    cases.append(_run(_config(tmp_path / "llm", max_llm_retries=0), driver, llm, _policy()))

    driver2 = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm2 = ScriptedLLM(
        actions=['{"action": "click", "element_ref": 1, "value": null, "reason": "click"}'],
        goals=['{"goal_reached": false, "reason": "no"}'],
    )
    cases.append(_run(_config(tmp_path / "steps", max_steps=1), driver2, llm2, _policy()))

    for result in cases:
        DiscoveryResult.model_validate(result.model_dump())
        assert (result.artifact is not None) == (result.status is RunStatus.GOAL_REACHED)


def test_navigate_value_reaches_the_artifact_untruncated(tmp_path) -> None:
    long_url = "http://127.0.0.1:5000/members/search?" + "&".join(f"k{i}={i}" for i in range(40))
    assert len(long_url) > 80
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "navigate", "element_ref": null, "value": "'
            + long_url
            + '", "reason": "open search results"}'
        ],
        goals=[
            '{"goal_reached": false, "reason": "no"}',
            '{"goal_reached": true, "reason": "yes"}',
        ],
    )
    result = _run(_config(tmp_path), driver, llm, _policy())

    assert result.status is RunStatus.GOAL_REACHED
    assert result.steps[0].value_preview == long_url
    assert result.artifact is not None
    assert result.artifact.steps[0].value == long_url
    assert result.artifact.checkpoint.locators[0].value == "http://127.0.0.1:5000/members"


def test_non_navigate_values_stay_bounded_in_the_preview(tmp_path) -> None:
    config = _config(tmp_path)
    policy = _policy()
    type_action = LLMAction(
        action=ActionType.TYPE, element_ref=1, value="v" * 200, reason="fill the field"
    )
    type_record = _make_record(
        config,
        policy,
        step_index=1,
        action=type_action,
        outcome="ok",
        policy_record=None,
        snapshot_hash="h",
        elapsed_ms=1,
    )
    assert type_record.value_preview is not None
    assert len(type_record.value_preview) == 80

    nav_action = LLMAction(
        action=ActionType.NAVIGATE,
        value="http://127.0.0.1:5000/" + "x" * 120,
        reason="go deep",
    )
    nav_record = _make_record(
        config,
        policy,
        step_index=2,
        action=nav_action,
        outcome="ok",
        policy_record=None,
        snapshot_hash="h",
        elapsed_ms=1,
    )
    assert nav_record.value_preview == nav_action.value


def test_out_root_allows_the_artifact_write_inside_it(tmp_path) -> None:
    """SEC-505: with an explicit out_root the run still writes normally
    when the artifact resolves inside that root."""
    root = tmp_path / "root"
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW, MEMBERS_URL: _MEMBERS_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}',
            '{"action": "extract", "element_ref": 1, "value": null, "reason": "read balance"}',
        ],
        goals=[
            '{"goal_reached": false, "reason": "not yet"}',
            '{"goal_reached": false, "reason": "not yet"}',
            '{"goal_reached": true, "reason": "balance is on screen"}',
        ],
    )
    config = _config(tmp_path, artifact_out=root / "artifact.json", out_root=root)
    result = _run(config, driver, llm, _policy())

    assert result.status is RunStatus.GOAL_REACHED
    assert result.artifact_path is not None
    assert Path(result.artifact_path).exists()


def test_out_root_blocks_the_artifact_write_outside_it(tmp_path) -> None:
    """SEC-505: a mistyped destination outside out_root fails closed with a
    PermissionError instead of writing anywhere on disk."""
    root = tmp_path / "root"
    root.mkdir()
    driver = FakeDriver({ENTRY_URL: _ENTRY_RAW, MEMBERS_URL: _MEMBERS_RAW}, ENTRY_URL)
    llm = ScriptedLLM(
        actions=[
            '{"action": "click", "element_ref": 1, "value": null, "reason": "open detail"}',
            '{"action": "extract", "element_ref": 1, "value": null, "reason": "read balance"}',
        ],
        goals=[
            '{"goal_reached": false, "reason": "not yet"}',
            '{"goal_reached": false, "reason": "not yet"}',
            '{"goal_reached": true, "reason": "balance is on screen"}',
        ],
    )
    config = _config(tmp_path, artifact_out=tmp_path / "outside.json", out_root=root)
    with pytest.raises(PermissionError, match="escapes base_dir"):
        _run(config, driver, llm, _policy())
    assert not (tmp_path / "outside.json").exists()
