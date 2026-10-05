import inspect
from pathlib import Path

import pytest
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By

from computer_use_automation_system.artifact.models import Locator, LocatorType
from computer_use_automation_system.discovery.act import DriverActionError
from computer_use_automation_system.discovery.selenium_driver import (
    OBSERVE_SCRIPT,
    SeleniumDriver,
    locator_to_by,
    normalize_script_result,
    translate_driver_error,
)


def test_locator_resolution_for_id_css_xpath() -> None:
    assert locator_to_by(Locator(type=LocatorType.ID, value="q")) == (By.ID, "q")
    assert locator_to_by(Locator(type=LocatorType.CSS, value="input[name='q']")) == (
        By.CSS_SELECTOR,
        "input[name='q']",
    )
    assert locator_to_by(Locator(type=LocatorType.XPATH, value="//a")) == (By.XPATH, "//a")


def test_role_locator_with_name_builds_xpath() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.ROLE, value="link::View Detail"))
    assert by == By.XPATH
    assert "View Detail" in value
    assert "normalize-space" in value


def test_role_locator_without_name_builds_css() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.ROLE, value="textbox"))
    assert by == By.CSS_SELECTOR
    assert "input" in value


def test_text_locator_builds_xpath() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.TEXT, value="Search"))
    assert by == By.XPATH
    assert "Search" in value


def test_url_locator_is_never_resolved_as_an_element_selector() -> None:
    with pytest.raises(ValueError, match="checkpoint expectations"):
        locator_to_by(Locator(type=LocatorType.URL, value="http://127.0.0.1:5000/members"))


def test_normalize_script_result_filters_junk() -> None:
    raw = [
        {"tag": "a", "text": "ok"},
        "not-a-dict",
        {"text": "missing tag"},
        None,
        {"tag": "INPUT", "text": "typed"},
    ]
    out = normalize_script_result(raw)
    assert [item["tag"] for item in out] == ["a", "INPUT"]


def test_translate_driver_errors_to_typed_codes() -> None:
    assert translate_driver_error(TimeoutException()).code == "timeout"
    assert translate_driver_error(StaleElementReferenceException()).code == "stale"
    assert translate_driver_error(NoSuchElementException()).code == "element_not_found"
    with pytest.raises(WebDriverException):
        translate_driver_error(WebDriverException("boom"))


def test_navigate_only_accepts_http_schemes() -> None:
    """SEC-503 (defense in depth): LLMAction/Step already require http(s),
    but the driver itself must never hand file:// or data: to the browser."""

    class StubWebDriver:
        def __init__(self) -> None:
            self.visited: list[str] = []

        def get(self, url: str) -> None:
            self.visited.append(url)

        def execute_script(self, script: str) -> str:
            return "complete"

    stub = StubWebDriver()
    driver = SeleniumDriver(stub)  # type: ignore[arg-type]

    for bad in ("file:///etc/passwd", "data:text/html,<script>x</script>", "chrome://settings"):
        with pytest.raises(DriverActionError) as exc:
            driver.navigate(bad)
        assert exc.value.code == "invalid_value"
    assert stub.visited == []

    driver.navigate("http://127.0.0.1:5000/")
    assert stub.visited == ["http://127.0.0.1:5000/"]


def test_observe_script_targets_interactive_elements_only() -> None:
    assert "querySelectorAll" in OBSERVE_SCRIPT
    for selector in ("input", "button", "select", "textarea", "a["):
        assert selector in OBSERVE_SCRIPT


def test_observe_script_exports_build_snapshot_fields() -> None:
    """fix-1: build_snapshot reads id/name_attr/classes/text/label, so the
    real script must export them (otherwise every locator degrades to a bare
    tag selector and clicks resolve to the first matching element)."""
    for fragment in (
        "label:",
        "id: (el.id",
        "name_attr:",
        "classes:",
        "text:",
    ):
        assert fragment in OBSERVE_SCRIPT


def test_page_text_reads_bounded_body_innertext() -> None:
    """fix-4: replay classification needs static page messages that
    observe_raw (interactive-only) never collects."""
    source = inspect.getsource(SeleniumDriver.page_text)
    assert "innerText" in source
    assert "execute_script" in source
    assert "20000" in source  # bounded


def test_no_time_sleep_in_discovery_sources() -> None:
    discovery_dir = (
        Path(__file__).parents[1] / "src" / "computer_use_automation_system" / "discovery"
    )
    for path in discovery_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "time.sleep(" not in source, f"time.sleep() forbidden in {path.name}"


def test_text_locator_escapes_double_quotes_with_single_quotes() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.TEXT, value='He said "hi"'))
    assert by == By.XPATH
    assert value == "//*[normalize-space(.)='He said \"hi\"']"


def test_text_locator_with_both_quote_types_uses_concat() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.TEXT, value='It\'s "x"'))
    assert by == By.XPATH
    assert value.startswith("//*[normalize-space(.)=concat(")
    assert "'\"'" in value
    assert '"It\'s "' in value


def test_role_locator_name_escapes_double_quotes() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.ROLE, value='link::View "Detail"'))
    assert by == By.XPATH
    assert "normalize-space(.)='View \"Detail\"']" in value
    assert 'normalize-space(.)="View ' not in value


def test_plain_text_locator_without_quotes_is_unchanged() -> None:
    by, value = locator_to_by(Locator(type=LocatorType.TEXT, value="Search"))
    assert value == '//*[normalize-space(.)="Search"]'
