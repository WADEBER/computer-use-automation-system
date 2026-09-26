"""Apply a validated `LLMAction` through the `BrowserDriver` protocol.

Drivers raise `DriverActionError` with a typed code; `perform` maps it to an
`ActionOutcome` so the runner records what happened instead of crashing.
"""

from dataclasses import dataclass
from typing import Protocol

from computer_use_automation_system.artifact.models import ActionType
from computer_use_automation_system.discovery.models import LLMAction, ObservedElement


class DriverActionError(Exception):
    """Typed driver failure: `code` in {element_not_found, stale, timeout}."""

    def __init__(self, code: str) -> None:
        super().__init__(f"driver action failed: {code}")
        self.code = code


@dataclass(frozen=True)
class ActionOutcome:
    """What actually happened when the action was applied."""

    outcome: str
    extracted: str | None = None


class BrowserDriver(Protocol):
    """Everything the discovery loop needs from a browser (real: Selenium)."""

    def observe_raw(self) -> list[dict]: ...

    def current_url(self) -> str: ...

    def navigate(self, url: str) -> None: ...

    def click(self, element: ObservedElement) -> None: ...

    def type_text(self, element: ObservedElement, text: str) -> None: ...

    def select_option(self, element: ObservedElement, option: str) -> None: ...

    def extract_text(self, element: ObservedElement) -> str: ...

    def quit(self) -> None: ...


def perform(
    driver: BrowserDriver, action: LLMAction, element: ObservedElement | None
) -> ActionOutcome:
    """Dispatch one action. `element` is the resolved snapshot entry (None
    only for navigate, or when the ref vanished)."""
    if action.action is not ActionType.NAVIGATE and element is None:
        return ActionOutcome("element_not_found")
    try:
        if action.action is ActionType.NAVIGATE:
            if action.value is None:
                return ActionOutcome("invalid_value")
            driver.navigate(action.value)
        elif action.action is ActionType.CLICK:
            driver.click(element)  # type: ignore[arg-type]
        elif action.action is ActionType.TYPE:
            if action.value is None:
                return ActionOutcome("invalid_value")
            driver.type_text(element, action.value)  # type: ignore[arg-type]
        elif action.action is ActionType.SELECT:
            if action.value is None:
                return ActionOutcome("invalid_value")
            driver.select_option(element, action.value)  # type: ignore[arg-type]
        else:  # extract
            text = driver.extract_text(element)  # type: ignore[arg-type]
            return ActionOutcome("ok", text)
    except DriverActionError as exc:
        return ActionOutcome(exc.code)
    return ActionOutcome("ok")
