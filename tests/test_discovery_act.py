from computer_use_automation_system.artifact.models import ActionType
from computer_use_automation_system.discovery.act import perform
from computer_use_automation_system.discovery.models import LLMAction, ObservedElement


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.raise_error: str | None = None
        self.extracted = "4250.75"

    def _record(self, name: str, *args) -> None:
        if self.raise_error:
            from computer_use_automation_system.discovery.act import DriverActionError

            raise DriverActionError(self.raise_error)
        self.calls.append((name, *args))

    def observe_raw(self) -> list[dict]:
        return []

    def current_url(self) -> str:
        return "http://127.0.0.1:5000/members/M-1001"

    def navigate(self, url: str) -> None:
        self._record("navigate", url)

    def click(self, element: ObservedElement) -> None:
        self._record("click", element)

    def type_text(self, element: ObservedElement, text: str) -> None:
        self._record("type_text", element, text)

    def select_option(self, element: ObservedElement, option: str) -> None:
        self._record("select_option", element, option)

    def extract_text(self, element: ObservedElement) -> str:
        self._record("extract_text", element)
        return self.extracted

    def quit(self) -> None:
        self._record("quit")


def _element(ref: int = 1) -> ObservedElement:
    return ObservedElement(ref=ref, tag="a", role="link", name="View Detail")


def test_navigate_dispatches_url_without_element() -> None:
    driver = FakeDriver()
    action = LLMAction(action=ActionType.NAVIGATE, value="http://127.0.0.1:5000/", reason="go")
    outcome = perform(driver, action, None)
    assert outcome.outcome == "ok"
    assert driver.calls == [("navigate", "http://127.0.0.1:5000/")]


def test_click_dispatches_with_element() -> None:
    driver = FakeDriver()
    element = _element(2)
    action = LLMAction(action=ActionType.CLICK, element_ref=2, reason="open")
    outcome = perform(driver, action, element)
    assert outcome.outcome == "ok"
    assert driver.calls == [("click", element)]


def test_type_dispatches_element_and_value() -> None:
    driver = FakeDriver()
    element = _element(1)
    action = LLMAction(action=ActionType.TYPE, element_ref=1, value="M-1001", reason="enter id")
    perform(driver, action, element)
    assert driver.calls == [("type_text", element, "M-1001")]


def test_select_dispatches_option() -> None:
    driver = FakeDriver()
    element = _element(3)
    action = LLMAction(action=ActionType.SELECT, element_ref=3, value="CHK-2201", reason="pick")
    perform(driver, action, element)
    assert driver.calls == [("select_option", element, "CHK-2201")]


def test_extract_returns_text() -> None:
    driver = FakeDriver()
    element = _element(4)
    action = LLMAction(action=ActionType.EXTRACT, element_ref=4, reason="read balance")
    outcome = perform(driver, action, element)
    assert outcome.outcome == "ok"
    assert outcome.extracted == "4250.75"


def test_missing_element_is_typed_outcome_without_driver_call() -> None:
    driver = FakeDriver()
    action = LLMAction(action=ActionType.CLICK, element_ref=5, reason="click")
    outcome = perform(driver, action, None)
    assert outcome.outcome == "element_not_found"
    assert driver.calls == []


def test_driver_timeout_maps_to_outcome() -> None:
    driver = FakeDriver()
    driver.raise_error = "timeout"
    action = LLMAction(action=ActionType.CLICK, element_ref=1, reason="click")
    outcome = perform(driver, action, _element())
    assert outcome.outcome == "timeout"


def test_driver_stale_maps_to_outcome() -> None:
    driver = FakeDriver()
    driver.raise_error = "stale"
    action = LLMAction(action=ActionType.TYPE, element_ref=1, value="x", reason="type")
    outcome = perform(driver, action, _element())
    assert outcome.outcome == "stale"
