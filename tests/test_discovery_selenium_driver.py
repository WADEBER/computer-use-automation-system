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
from computer_use_automation_system.discovery.selenium_driver import (
    OBSERVE_SCRIPT,
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


def test_observe_script_targets_interactive_elements_only() -> None:
    assert "querySelectorAll" in OBSERVE_SCRIPT
    for selector in ("input", "button", "select", "textarea", "a["):
        assert selector in OBSERVE_SCRIPT


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
