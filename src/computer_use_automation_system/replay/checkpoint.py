"""Evaluate the artifact's success checkpoint before declaring a replay run
successful (spec Phase 6, HU-4). Locator fallback and explicit waits live in
the driver; this module never sleeps and never raises."""

from computer_use_automation_system.artifact.models import Checkpoint, ExpectedCondition
from computer_use_automation_system.discovery.act import BrowserDriver, DriverActionError
from computer_use_automation_system.discovery.models import ObservedElement


def _http_values(checkpoint: Checkpoint) -> list[str]:
    return [
        locator.value
        for locator in checkpoint.locators
        if locator.value.startswith(("http://", "https://"))
    ]


def check_checkpoint(driver: BrowserDriver, checkpoint: Checkpoint) -> tuple[bool, str]:
    """Return ``(passed, message)``; an empty message means success.

    - ``visible``: the element resolves through the fallback chain.
    - ``text_present``: the resolved element carries non-empty text.
    - ``url_contains``: the current URL contains the expected http(s) value
      declared among the checkpoint locators; without one the condition
      fails closed (the Phase 3 contract stores no expected-value field).
    """
    if checkpoint.expected_condition is ExpectedCondition.URL_CONTAINS:
        expected = _http_values(checkpoint)
        if not expected:
            return False, "url_contains requires an http(s) value among checkpoint locators"
        current = driver.current_url()
        if any(value in current for value in expected):
            return True, ""
        return False, f"url {current!r} does not contain {expected[0]!r}"

    element = ObservedElement(
        ref=1,
        tag="div",
        role="replay",
        name=checkpoint.description,
        locators=list(checkpoint.locators),
    )
    try:
        text = driver.extract_text(element)
    except DriverActionError as exc:
        return False, f"checkpoint element not found ({exc.code})"

    if checkpoint.expected_condition is ExpectedCondition.TEXT_PRESENT:
        if text.strip():
            return True, ""
        return False, "checkpoint text missing (text_present not satisfied)"
    return True, ""
