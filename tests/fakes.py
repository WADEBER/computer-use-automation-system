"""Shared fakes for Phase 5/6 tests. CI never opens network, Ollama or Chrome."""

from collections.abc import Callable
from urllib.parse import urljoin

from computer_use_automation_system.artifact.models import Locator, LocatorType
from computer_use_automation_system.discovery.act import DriverActionError
from computer_use_automation_system.discovery.models import ObservedElement


class FakeLLMClient:
    """Scripted LLM: pops queued string responses, or delegates to a handler."""

    def __init__(
        self,
        responses: list[str] | None = None,
        handler: Callable[[str], str] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.handler = handler
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.handler is not None:
            return self.handler(prompt)
        if not self.responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses")
        return self.responses.pop(0)


def _locator_matches(page_element: dict, locator: Locator) -> bool:
    """Resolve one artifact locator against a simulated page element."""
    if locator.type is LocatorType.ID:
        return page_element.get("id") == locator.value
    if locator.type is LocatorType.TEXT:
        return locator.value == (page_element.get("text") or "").strip()
    if locator.type is LocatorType.ROLE:
        role, _, name = locator.value.partition("::")
        if page_element.get("role") != role.strip():
            return False
        if not name.strip():
            return True
        haystack = page_element.get("text") or page_element.get("name") or ""
        return name.strip() == haystack.strip()
    if locator.type is LocatorType.CSS:
        if locator.value in page_element.get("selectors", []):
            return True
        if locator.value.startswith("#"):
            return page_element.get("id") == locator.value[1:]
        if locator.value.isalpha():
            return page_element.get("tag") == locator.value
        return False
    return False  # XPath is not simulated by the fake driver


class ReplayFakeDriver:
    """`BrowserDriver` backed by a dict of URL -> element list.

    Each element is a plain dict: tag/id/role/text/href plus an optional
    `selectors` list declaring which CSS selectors it matches. Locator
    fallback is exercised for real: unmatched locators are skipped until one
    matches, otherwise `DriverActionError` is raised.
    """

    def __init__(self, pages: dict[str, list[dict]], start_url: str) -> None:
        self.pages = pages
        self.url = start_url
        self.calls: list[tuple] = []

    def observe_raw(self) -> list[dict]:
        return [dict(element) for element in self.pages.get(self.url, [])]

    def current_url(self) -> str:
        return self.url

    def navigate(self, url: str) -> None:
        self.calls.append(("navigate", url))
        self.url = url

    def _find(self, element: ObservedElement) -> dict:
        for locator in element.locators:
            for page_element in self.pages.get(self.url, []):
                if _locator_matches(page_element, locator):
                    self.calls.append(("found", locator.type.value, locator.value))
                    return page_element
        raise DriverActionError("element_not_found")

    def click(self, element: ObservedElement) -> None:
        target = self._find(element)
        self.calls.append(("click", target.get("id") or target.get("text"), self.url))
        if target.get("href"):
            self.url = urljoin(self.url, target["href"])

    def type_text(self, element: ObservedElement, text: str) -> None:
        target = self._find(element)
        target["value"] = text
        self.calls.append(("type", target.get("id"), text))

    def select_option(self, element: ObservedElement, option: str) -> None:
        target = self._find(element)
        self.calls.append(("select", target.get("id"), option))

    def extract_text(self, element: ObservedElement) -> str:
        target = self._find(element)
        return (target.get("text") or "").strip() or (target.get("value") or "")

    def quit(self) -> None:
        self.calls.append(("quit",))
