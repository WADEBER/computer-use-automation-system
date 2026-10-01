"""Phase 6: deterministic replay engine — happy path (step 4), failures
(step 5) and determinism/anti-LLM guards (step 6), per spec HU-1..HU-4."""

import json
from pathlib import Path

from computer_use_automation_system.artifact.models import (
    ActionType,
    Artifact,
    Locator,
    LocatorType,
    Step,
)
from computer_use_automation_system.replay import ReplayStage, ReplayStatus
from computer_use_automation_system.replay.engine import replay
from computer_use_automation_system.replay.models import ReplayResult
from computer_use_automation_system.safety.models import (
    PolicyConfig,
    PolicyRule,
    RedactionConfig,
    RedactionPattern,
)
from fakes import ReplayFakeDriver

ENTRY = "http://127.0.0.1:5000/"
SEARCH = "http://127.0.0.1:5000/members/search"
DETAIL = "http://127.0.0.1:5000/members/M-1001"

PAGES: dict[str, list[dict]] = {
    ENTRY: [
        {"tag": "div", "id": "main", "selectors": ["#main"], "text": "MemberServ"},
        {"tag": "body", "selectors": ["body"], "text": "MemberServ Console"},
        {
            "tag": "input",
            "id": "q",
            "type": "text",
            "value": "",
            "name": "q",
            "selectors": ["#q", "input[name='q']"],
            "role": "textbox",
        },
        {
            "tag": "input",
            "type": "submit",
            "value": "Search",
            "text": "Search",
            "selectors": ["input[type='submit']"],
            "href": "/members/search",
            "role": "button",
        },
    ],
    SEARCH: [
        {
            "tag": "a",
            "text": "View Detail",
            "href": "/members/M-1001",
            "selectors": ["table.results a"],
            "role": "link",
        },
    ],
    DETAIL: [
        {
            "tag": "h2",
            "id": "memberName",
            "text": "Alice Hartwell",
            "selectors": ["#memberName"],
            "role": "",
        },
        {
            "tag": "td",
            "id": "",
            "text": "15200.00",
            "selectors": ["#accountsTable td.savings"],
            "role": "",
        },
    ],
}


def _fixture() -> Artifact:
    raw = json.loads(Path("tests/fixtures/valid_artifact.json").read_text(encoding="utf-8"))
    return Artifact(**raw)


def _policy(rules: list[PolicyRule] | None = None) -> PolicyConfig:
    return PolicyConfig(
        allowed_origins=["http://127.0.0.1:5000"],
        allowed_routes=["/", "/members"],
        allowed_action_types=list(ActionType),
        rules=rules or [],
        redaction=RedactionConfig(
            patterns=[
                RedactionPattern(
                    name="card",
                    regex=r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",
                    replacement="[REDACTED_CARD]",
                )
            ],
            literals=["dummy-999"],
            field_keys=["password", "pin"],
        ),
    )


def _driver() -> ReplayFakeDriver:
    return ReplayFakeDriver(PAGES, start_url=ENTRY)


def test_happy_path_fixture_reaches_success_with_outputs() -> None:
    result = replay(
        _fixture(),
        {"member_id": "M-1001"},
        _driver(),
        _policy(),
    )
    assert result.status is ReplayStatus.SUCCESS
    assert result.error is None
    assert result.outputs == {
        "member_name": "Alice Hartwell",
        "savings_balance": "15200.00",
    }
    assert result.steps_executed == 6
    assert result.capability_id == "lookup_member_balance"
    assert result.version == "1.0.0"
    assert result.elapsed_ms >= 0


def test_happy_path_records_one_policy_decision_per_step() -> None:
    result = replay(_fixture(), {"member_id": "M-1001"}, _driver(), _policy())
    assert len(result.decisions) == 6
    assert {record.action_type for record in result.decisions} == {
        ActionType.NAVIGATE,
        ActionType.TYPE,
        ActionType.CLICK,
        ActionType.EXTRACT,
    }
    assert all(record.decision.value in ("allow", "flag") for record in result.decisions)
    assert result.decisions[0].action_type is ActionType.NAVIGATE
    assert result.decisions[0].url == ENTRY


def test_happy_path_resolves_inputs_and_falls_back_between_locators() -> None:
    driver = _driver()
    replay(_fixture(), {"member_id": "M-1001"}, driver, _policy())
    typed = [call for call in driver.calls if call[0] == "type"]
    assert typed == [("type", "q", "M-1001")]
    clicks = [call for call in driver.calls if call[0] == "click"]
    assert len(clicks) == 2
    found_values = [call[2] for call in driver.calls if call[0] == "found"]
    assert "q" in found_values
    assert "View Detail" in found_values


def test_locator_fallback_when_first_candidate_is_missing() -> None:
    pages = {url: [dict(element) for element in elements] for url, elements in PAGES.items()}
    # Simulate a legacy DOM where the preferred id locator vanished: step 1
    # must fall back to the second candidate (`body`) and still succeed.
    pages[ENTRY] = [element for element in pages[ENTRY] if element.get("id") != "main"]
    result = replay(_fixture(), {"member_id": "M-1001"}, ReplayFakeDriver(pages, ENTRY), _policy())
    assert result.status is ReplayStatus.SUCCESS
    assert result.steps_executed == 6


def test_navigate_step_is_the_first_and_reaches_entry_url() -> None:
    driver = _driver()
    result = replay(_fixture(), {"member_id": "M-1001"}, driver, _policy())
    assert result.status is ReplayStatus.SUCCESS
    assert driver.calls[0] == ("navigate", ENTRY)


def test_flag_rule_keeps_action_and_records_verdict() -> None:
    rules = [
        PolicyRule(
            match_action_type=ActionType.EXTRACT,
            decision="flag",
            reason="audit extract",
        )
    ]
    result = replay(_fixture(), {"member_id": "M-1001"}, _driver(), _policy(rules))
    assert result.status is ReplayStatus.SUCCESS
    flag_records = [r for r in result.decisions if r.decision.value == "flag"]
    assert len(flag_records) == 2
    assert flag_records[0].reason == "audit extract"


EXECUTE_URL = "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute"


def _mini(
    steps: list[Step],
    *,
    checkpoint_locators: list[Locator] | None = None,
    output_properties: dict | None = None,
    output_required: list[str] | None = None,
    extra_input_properties: dict | None = None,
) -> Artifact:
    return Artifact(
        capability_id="mini_capability",
        version="1.0.0",
        description="mini flow for failure-path tests",
        target_app={"name": "MemberServ", "entry_url": ENTRY},
        input_schema={
            "type": "object",
            "properties": {
                "member_id": {"type": "string"},
                **(extra_input_properties or {}),
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": output_properties or {"value": {"type": "string"}},
            "required": output_required or [],
        },
        steps=steps,
        checkpoint={
            "description": "member name visible",
            "locators": checkpoint_locators or [{"type": "css", "value": "#memberName"}],
            "expected_condition": "visible",
        },
    )


def _navigate_step(url: str) -> Step:
    return Step(
        step_id=1,
        action_type=ActionType.NAVIGATE,
        description="open the target page",
        locators=[Locator(type=LocatorType.ID, value="main")],
        value=url,
    )


def test_input_validation_failure_never_touches_the_driver() -> None:
    driver = _driver()
    result = replay(_fixture(), {}, driver, _policy())
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.INPUT_VALIDATION
    assert "member_id" in result.error.message
    assert result.error.step_id is None
    assert result.steps_executed == 0
    assert driver.calls == []


def test_step_failure_when_no_locator_matches() -> None:
    driver = ReplayFakeDriver({}, start_url=ENTRY)
    result = replay(_fixture(), {"member_id": "M-1001"}, driver, _policy())
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.STEP
    assert result.error.step_id == 2
    assert "element_not_found" in result.error.message
    assert result.outputs is None
    assert result.steps_executed == 1


def test_policy_blocked_navigate_outside_perimeter() -> None:
    driver = _driver()
    result = replay(_mini([_navigate_step("http://evil.example/")]), {}, driver, _policy())
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "blocked"
    assert driver.calls == []  # the action never reached the driver
    assert result.outputs is None


def test_policy_needs_approval_on_execute_without_approved_flag() -> None:
    rules = [
        PolicyRule(
            match_url_pattern="*/execute",
            decision="confirm",
            reason="irreversible execution",
        )
    ]
    driver = _driver()
    result = replay(_mini([_navigate_step(EXECUTE_URL)]), {}, driver, _policy(rules))
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "needs_approval"
    assert driver.calls == []
    assert len(result.decisions) == 1


def test_policy_confirm_runs_when_approved_flag_is_set() -> None:
    rules = [
        PolicyRule(
            match_url_pattern="*/execute",
            decision="confirm",
            reason="irreversible execution",
        )
    ]
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    pages[EXECUTE_URL] = [
        {"tag": "h2", "id": "memberName", "text": "Alice", "selectors": ["#memberName"]}
    ]
    driver = ReplayFakeDriver(pages, ENTRY)
    result = replay(_mini([_navigate_step(EXECUTE_URL)]), {}, driver, _policy(rules), approved=True)
    assert result.status is ReplayStatus.SUCCESS
    assert driver.calls[0] == ("navigate", EXECUTE_URL)
    confirm = [r for r in result.decisions if r.decision.value == "confirm"]
    assert len(confirm) == 1


def test_checkpoint_failure_blocks_success() -> None:
    driver = _driver()
    artifact = _mini(
        [_navigate_step(DETAIL)],
        checkpoint_locators=[Locator(type=LocatorType.CSS, value="#ghost")],
    )
    result = replay(artifact, {}, driver, _policy())
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.CHECKPOINT
    assert result.error.step_id == 1
    assert result.outputs is None


def test_output_validation_failure_when_required_output_missing() -> None:
    artifact = _mini(
        [
            _navigate_step(DETAIL),
            Step(
                step_id=2,
                action_type=ActionType.EXTRACT,
                description="extract the member name",
                locators=[Locator(type=LocatorType.CSS, value="#memberName")],
                output_key="member_name",
            ),
        ],
        output_properties={"member_name": {"type": "string"}, "balance": {"type": "string"}},
        output_required=["balance"],
    )
    result = replay(artifact, {}, _driver(), _policy())
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.OUTPUT_VALIDATION
    assert "balance" in result.error.message
    assert result.error.step_id is None
    assert result.outputs is None


def _run_fixture() -> tuple:
    driver = _driver()
    result = replay(_fixture(), {"member_id": "M-1001"}, driver, _policy())
    return result, driver.calls


def test_replay_is_deterministic_across_runs() -> None:
    first, first_calls = _run_fixture()
    second, second_calls = _run_fixture()
    assert first.outputs == second.outputs
    assert first.steps_executed == second.steps_executed
    assert first_calls == second_calls

    def trace(result: ReplayResult) -> list[tuple]:
        return [(d.action_type, d.url, d.decision) for d in result.decisions]

    assert trace(first) == trace(second)


def test_time_budget_exceeded_fails_fast_with_step_stage() -> None:
    ticks = iter([0.0, 10.0, 0.0])

    def clock() -> float:
        return next(ticks)

    result = replay(
        _fixture(),
        {"member_id": "M-1001"},
        _driver(),
        _policy(),
        step_timeout_ms=1000,
        clock=clock,
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.STEP
    assert result.error.step_id == 1
    assert "budget" in result.error.message


def test_replay_package_never_imports_llm_modules() -> None:
    import pathlib

    package = pathlib.Path("src/computer_use_automation_system/replay")
    forbidden = ("discovery.decide", "discovery.goal", "llm_client", "ollama")
    checked = 0
    for path in sorted(package.glob("*.py")):
        checked += 1
        source = path.read_text(encoding="utf-8")
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for name in forbidden:
                assert name not in line, f"{path.name} imports {name}: {line}"
    assert checked >= 5


def test_select_step_reaches_the_driver_with_resolved_value() -> None:
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    pages[DETAIL] = pages[DETAIL] + [{"tag": "select", "id": "currency"}]
    artifact = _mini(
        [
            _navigate_step(DETAIL),
            Step(
                step_id=2,
                action_type=ActionType.SELECT,
                description="pick the display currency",
                locators=[Locator(type=LocatorType.ID, value="currency")],
                value="{{input.currency}}",
            ),
        ],
        extra_input_properties={"currency": {"type": "string"}},
    )
    driver = ReplayFakeDriver(pages, ENTRY)
    result = replay(artifact, {"currency": "EUR"}, driver, _policy())
    assert result.status is ReplayStatus.SUCCESS
    assert ("select", "currency", "EUR") in driver.calls


def test_execute_route_click_is_not_performed_without_approved() -> None:
    rules = [
        PolicyRule(
            match_action_type=ActionType.CLICK,
            match_url_pattern="*/execute",
            decision="confirm",
            reason="irreversible execution",
        )
    ]
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    pages[EXECUTE_URL] = [{"tag": "button", "id": "confirmBtn", "text": "Confirm"}]
    artifact = _mini(
        [
            _navigate_step(EXECUTE_URL),
            Step(
                step_id=2,
                action_type=ActionType.CLICK,
                description="confirm the disbursement",
                locators=[Locator(type=LocatorType.ID, value="confirmBtn")],
            ),
        ]
    )
    driver = ReplayFakeDriver(pages, ENTRY)
    result = replay(artifact, {}, driver, _policy(rules))
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.POLICY
    assert result.error.policy_kind == "needs_approval"
    assert result.error.step_id == 2
    assert not any(call[0] == "click" for call in driver.calls)


def _taxonomy_config(**overrides):
    from computer_use_automation_system.replay.taxonomy import TaxonomyConfig

    payload = {
        "version": "1.0.0",
        "max_recoverable_attempts": 3,
        "patterns": {
            "business_outcome": ["No records found"],
            "recoverable": ["Loading, please wait"],
            "hard": ["Permission denied"],
        },
        "recoverable_driver_codes": ["stale", "timeout"],
        "known_dialogs": [],
    }
    payload.update(overrides)
    return TaxonomyConfig.model_validate(payload)


NOT_FOUND_PAGE = [
    {"tag": "div", "id": "flash", "text": 'No records found for "zzz"'},
]


def test_step_failure_with_business_signal_is_business_outcome() -> None:
    pages = {ENTRY: NOT_FOUND_PAGE}
    artifact = _mini(
        [
            Step(
                step_id=1,
                action_type=ActionType.TYPE,
                description="type into a missing field",
                locators=[Locator(type=LocatorType.CSS, value="#ghost")],
                value="{{input.q}}",
            )
        ],
        extra_input_properties={"q": {"type": "string"}},
    )
    result = replay(
        artifact,
        {"q": "zzz"},
        ReplayFakeDriver(pages, ENTRY),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.stage is ReplayStage.STEP
    assert result.error.failure_category == "business_outcome"
    assert "No records found" in result.error.message
    assert "element_not_found" in result.error.message


def test_business_signal_beats_hard_pattern_in_engine() -> None:
    pages = {
        ENTRY: [
            {"tag": "div", "text": "Permission denied. No records found."},
        ]
    }
    artifact = _mini(
        [
            Step(
                step_id=1,
                action_type=ActionType.TYPE,
                description="type into a missing field",
                locators=[Locator(type=LocatorType.CSS, value="#ghost")],
                value="{{input.q}}",
            )
        ],
        extra_input_properties={"q": {"type": "string"}},
    )
    result = replay(
        artifact,
        {"q": "zzz"},
        ReplayFakeDriver(pages, ENTRY),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"


def test_optional_page_text_capability_feeds_classification() -> None:
    """fix-4: a real browser only observes interactive elements, so static
    messages ("No records found" in a plain <p>) are invisible to
    ``observe_raw``. The optional ``page_text()`` capability (same getattr
    pattern as ``screenshot_b64``) extends the classification text."""

    class PageTextDriver(ReplayFakeDriver):
        def page_text(self) -> str:
            return 'Search Results. No records found. Member not found for "zzz".'

    pages = {ENTRY: [{"tag": "a", "text": "Back to search", "href": "/"}]}
    artifact = _mini(
        [
            Step(
                step_id=1,
                action_type=ActionType.TYPE,
                description="type into a missing field",
                locators=[Locator(type=LocatorType.CSS, value="#ghost")],
                value="{{input.q}}",
            )
        ],
        extra_input_properties={"q": {"type": "string"}},
    )
    result = replay(
        artifact,
        {"q": "zzz"},
        PageTextDriver(pages, ENTRY),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"
    assert "No records found" in result.error.message


def test_driver_without_page_text_keeps_the_legacy_classification() -> None:
    pages = {ENTRY: [{"tag": "a", "text": "Back to search", "href": "/"}]}
    artifact = _mini(
        [
            Step(
                step_id=1,
                action_type=ActionType.TYPE,
                description="type into a missing field",
                locators=[Locator(type=LocatorType.CSS, value="#ghost")],
                value="{{input.q}}",
            )
        ],
        extra_input_properties={"q": {"type": "string"}},
    )
    result = replay(
        artifact,
        {"q": "zzz"},
        ReplayFakeDriver(pages, ENTRY),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.error is not None
    assert result.error.failure_category == "hard"
    assert "element_not_found" in result.error.message


def test_step_failure_without_signal_is_hard_and_keeps_code() -> None:
    driver = ReplayFakeDriver({}, start_url=ENTRY)
    result = replay(
        _fixture(),
        {"member_id": "M-1001"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.error is not None
    assert result.error.failure_category == "hard"
    assert "element_not_found" in result.error.message


def test_checkpoint_failure_is_classified_as_hard() -> None:
    artifact = _mini(
        [_navigate_step(DETAIL)],
        checkpoint_locators=[Locator(type=LocatorType.CSS, value="#ghost")],
    )
    driver = _driver()
    result = replay(artifact, {}, driver, _policy(), taxonomy=_taxonomy_config())
    assert result.error is not None
    assert result.error.stage is ReplayStage.CHECKPOINT
    assert result.error.failure_category == "hard"


def test_checkpoint_failure_with_business_signal_is_business_outcome() -> None:
    pages = {DETAIL: NOT_FOUND_PAGE}
    artifact = _mini(
        [_navigate_step(DETAIL)],
        checkpoint_locators=[Locator(type=LocatorType.CSS, value="#ghost")],
    )
    result = replay(
        artifact,
        {},
        ReplayFakeDriver(pages, ENTRY),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"
    assert "No records found" in result.error.message


def test_time_budget_failure_is_hard_category() -> None:
    ticks = iter([0.0, 10.0, 0.0])

    def clock() -> float:
        return next(ticks)

    result = replay(
        _fixture(),
        {"member_id": "M-1001"},
        _driver(),
        _policy(),
        step_timeout_ms=1000,
        clock=clock,
        taxonomy=_taxonomy_config(),
    )
    assert result.error is not None
    assert result.error.failure_category == "hard"
    assert "budget" in result.error.message


def test_non_execution_stages_carry_no_category() -> None:
    result = replay(_fixture(), {}, _driver(), _policy(), taxonomy=_taxonomy_config())
    assert result.error is not None
    assert result.error.stage is ReplayStage.INPUT_VALIDATION
    assert result.error.failure_category is None

    blocked = replay(
        _mini([_navigate_step("http://evil.example/")]),
        {},
        _driver(),
        _policy(),
        taxonomy=_taxonomy_config(),
    )
    assert blocked.error is not None
    assert blocked.error.stage is ReplayStage.POLICY
    assert blocked.error.failure_category is None


def test_engine_loads_default_taxonomy_when_not_injected() -> None:
    driver = ReplayFakeDriver({}, start_url=ENTRY)
    result = replay(_fixture(), {"member_id": "M-1001"}, driver, _policy())
    assert result.error is not None
    assert result.error.failure_category == "hard"


class FlakyTypeDriver(ReplayFakeDriver):
    """ReplayFakeDriver whose type_text fails with `code` for the first
    `failures` attempts (then behaves normally). `outcomes` overrides per
    attempt (None entries succeed); optional `on_failure` hook mutates the
    page when an attempt fails."""

    def __init__(
        self,
        pages: dict[str, list[dict]],
        start_url: str,
        code: str = "timeout",
        failures: int = 1,
        outcomes: list[str | None] | None = None,
        on_failure=None,
    ) -> None:
        super().__init__(pages, start_url)
        self._code = code
        self._failures = failures
        self._outcomes = outcomes
        self._on_failure = on_failure
        self.type_attempts = 0

    def type_text(self, element, text: str) -> None:
        self.type_attempts += 1
        if self._outcomes is not None:
            index = min(self.type_attempts - 1, len(self._outcomes) - 1)
            outcome = self._outcomes[index]
            if outcome is not None:
                if self._on_failure is not None:
                    self._on_failure(self)
                from computer_use_automation_system.discovery.act import (
                    DriverActionError,
                )

                raise DriverActionError(outcome)
            return super().type_text(element, text)
        if self.type_attempts <= self._failures:
            from computer_use_automation_system.discovery.act import DriverActionError

            raise DriverActionError(self._code)
        return super().type_text(element, text)


def _type_artifact() -> "Artifact":
    return _mini(
        [
            _navigate_step(ENTRY),
            Step(
                step_id=2,
                action_type=ActionType.TYPE,
                description="type the query",
                locators=[Locator(type=LocatorType.ID, value="q")],
                value="{{input.q}}",
            ),
        ],
        checkpoint_locators=[Locator(type=LocatorType.ID, value="q")],
        extra_input_properties={"q": {"type": "string"}},
    )


def test_recoverable_transient_failure_is_retried_until_success() -> None:
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    driver = FlakyTypeDriver(pages, ENTRY, code="timeout", failures=1)
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=3),
    )
    assert result.status is ReplayStatus.SUCCESS
    assert driver.type_attempts == 2
    assert result.steps_executed == 2


def test_recoverable_failure_exhausts_retries_with_category() -> None:
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    driver = FlakyTypeDriver(pages, ENTRY, code="timeout", failures=99)
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=3),
    )
    assert result.status is ReplayStatus.FAILURE
    assert result.error is not None
    assert result.error.failure_category == "recoverable"
    assert "timeout" in result.error.message
    assert "attempts exhausted: 3" in result.error.message
    assert driver.type_attempts == 3
    assert result.steps_executed == 1


def test_hard_failure_is_not_retried() -> None:
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    driver = FlakyTypeDriver(pages, ENTRY, code="element_not_found", failures=99)
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=3),
    )
    assert result.error is not None
    assert result.error.failure_category == "hard"
    assert driver.type_attempts == 1


def test_reclassification_each_attempt_can_turn_failure_into_business() -> None:
    def show_not_found(flaky: FlakyTypeDriver) -> None:
        if flaky.type_attempts >= 2:
            flaky.pages[flaky.url].append({"tag": "div", "text": "No records found"})

    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    driver = FlakyTypeDriver(
        pages,
        ENTRY,
        outcomes=["timeout", "element_not_found"],
        on_failure=show_not_found,
    )
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=5),
    )
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"
    assert driver.type_attempts == 2


def test_known_dialog_is_dismissed_then_step_retried() -> None:
    class DialogDriver(ReplayFakeDriver):
        def type_text(self, element, text: str) -> None:
            from computer_use_automation_system.discovery.act import DriverActionError

            if any(e.get("role") == "dialog" for e in self.pages.get(self.url, [])):
                self.type_attempts += 1
                raise DriverActionError("stale")
            self.type_attempts += 1
            return super().type_text(element, text)

        def click(self, element) -> None:
            super().click(element)
            if any(loc.value == "#dialog-dismiss" for loc in element.locators):
                self.pages[self.url] = [
                    e for e in self.pages[self.url] if e.get("role") != "dialog"
                ]

        type_attempts = 0

    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    pages[ENTRY] = pages[ENTRY] + [
        {"tag": "div", "role": "dialog", "text": "Session about to expire soon"},
        {"tag": "button", "id": "dialog-dismiss", "text": "Dismiss"},
    ]
    taxonomy = _taxonomy_config(
        max_recoverable_attempts=3,
        known_dialogs=[
            {
                "pattern": "Session about to expire",
                "dismiss_locator": {"type": "css", "value": "#dialog-dismiss"},
            }
        ],
    )
    driver = DialogDriver(pages, ENTRY)
    result = replay(_type_artifact(), {"q": "alice"}, driver, _policy(), taxonomy=taxonomy)
    assert result.status is ReplayStatus.SUCCESS
    assert driver.type_attempts == 2
    assert not any(e.get("role") == "dialog" for e in driver.pages[ENTRY])


def test_unknown_dialog_is_neither_dismissed_nor_retried() -> None:
    class UnknownDialogDriver(ReplayFakeDriver):
        def type_text(self, element, text: str) -> None:
            from computer_use_automation_system.discovery.act import DriverActionError

            self.type_attempts += 1
            if any(e.get("role") == "dialog" for e in self.pages.get(self.url, [])):
                raise DriverActionError("stale")
            return super().type_text(element, text)

        type_attempts = 0

    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    pages[ENTRY] = pages[ENTRY] + [
        {"tag": "div", "role": "dialog", "text": "Surprise modal"},
    ]
    driver = UnknownDialogDriver(pages, ENTRY)
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=3),
    )
    assert result.error is not None
    assert result.error.failure_category == "hard"
    assert "dialog" in result.error.message
    assert driver.type_attempts == 1
    assert not any(call[0] == "click" for call in driver.calls)


def test_attempts_bound_comes_from_taxonomy_config() -> None:
    pages = {url: [dict(e) for e in els] for url, els in PAGES.items()}
    driver = FlakyTypeDriver(pages, ENTRY, code="stale", failures=99)
    result = replay(
        _type_artifact(),
        {"q": "alice"},
        driver,
        _policy(),
        taxonomy=_taxonomy_config(max_recoverable_attempts=1),
    )
    assert result.error is not None
    assert result.error.failure_category == "recoverable"
    assert "attempts exhausted: 1" in result.error.message
    assert driver.type_attempts == 1


def test_business_message_is_redacted_before_it_is_stored() -> None:
    taxonomy = _taxonomy_config(
        patterns={
            "business_outcome": ["Account 1111-2222-3333-4444 closed"],
            "recoverable": ["Loading, please wait"],
            "hard": ["Permission denied"],
        }
    )
    pages = {ENTRY: [{"tag": "div", "text": "Account 1111-2222-3333-4444 closed"}]}
    artifact = _mini(
        [
            Step(
                step_id=1,
                action_type=ActionType.TYPE,
                description="type into a missing field",
                locators=[Locator(type=LocatorType.CSS, value="#ghost")],
                value="{{input.q}}",
            )
        ],
        extra_input_properties={"q": {"type": "string"}},
    )
    result = replay(
        artifact,
        {"q": "zzz"},
        ReplayFakeDriver(pages, ENTRY),
        _policy(),
        taxonomy=taxonomy,
    )
    assert result.error is not None
    assert result.error.failure_category == "business_outcome"
    assert "1111-2222-3333-4444" not in result.error.message
    assert "[REDACTED_CARD]" in result.error.message
