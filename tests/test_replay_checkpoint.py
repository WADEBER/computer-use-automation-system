"""Phase 6: checkpoint evaluation (`visible` / `text_present` / `url_contains`)
with locator fallback, per spec HU-4."""

from computer_use_automation_system.artifact.models import Checkpoint, Locator, LocatorType
from computer_use_automation_system.replay.checkpoint import check_checkpoint
from fakes import ReplayFakeDriver

URL = "http://127.0.0.1:5000/members/M-1001"

PAGES = {
    URL: [
        {"tag": "div", "id": "accountsTable", "selectors": ["#accountsTable"]},
        {
            "tag": "td",
            "text": "15200.00",
            "selectors": ["#accountsTable td.savings"],
            "role": "",
        },
        {"tag": "h2", "id": "emptyName", "text": "   ", "selectors": ["#emptyName"]},
    ]
}


def _driver() -> ReplayFakeDriver:
    return ReplayFakeDriver(PAGES, start_url=URL)


def _checkpoint(condition: str, locators: list[Locator]) -> Checkpoint:
    return Checkpoint(
        description="verify state",
        locators=locators,
        expected_condition=condition,
    )


def test_visible_passes_when_locator_resolves() -> None:
    ok, message = check_checkpoint(
        _driver(),
        _checkpoint("visible", [Locator(type=LocatorType.CSS, value="#accountsTable")]),
    )
    assert ok is True
    assert message == ""


def test_visible_uses_locator_fallback() -> None:
    ok, _ = check_checkpoint(
        _driver(),
        _checkpoint(
            "visible",
            [
                Locator(type=LocatorType.CSS, value="#missing"),
                Locator(type=LocatorType.CSS, value="#accountsTable"),
            ],
        ),
    )
    assert ok is True


def test_visible_fails_when_no_locator_matches() -> None:
    ok, message = check_checkpoint(
        _driver(),
        _checkpoint("visible", [Locator(type=LocatorType.CSS, value="#missing")]),
    )
    assert ok is False
    assert "not found" in message


def test_text_present_requires_non_empty_text() -> None:
    ok, _ = check_checkpoint(
        _driver(),
        _checkpoint(
            "text_present", [Locator(type=LocatorType.CSS, value="#accountsTable td.savings")]
        ),
    )
    assert ok is True
    empty, message = check_checkpoint(
        _driver(),
        _checkpoint("text_present", [Locator(type=LocatorType.CSS, value="#emptyName")]),
    )
    assert empty is False
    assert "text" in message


def test_url_contains_passes_on_matching_http_locator_value() -> None:
    ok, _ = check_checkpoint(
        _driver(),
        _checkpoint(
            "url_contains",
            [Locator(type=LocatorType.CSS, value="http://127.0.0.1:5000/members")],
        ),
    )
    assert ok is True


def test_url_contains_fails_when_url_does_not_contain_value() -> None:
    ok, message = check_checkpoint(
        _driver(),
        _checkpoint(
            "url_contains",
            [Locator(type=LocatorType.CSS, value="http://127.0.0.1:5000/loans")],
        ),
    )
    assert ok is False
    assert "url" in message


def test_url_contains_fails_closed_without_http_locator_value() -> None:
    ok, message = check_checkpoint(
        _driver(),
        _checkpoint("url_contains", [Locator(type=LocatorType.CSS, value="#accountsTable")]),
    )
    assert ok is False
    assert "http" in message
