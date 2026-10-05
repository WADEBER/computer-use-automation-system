"""Selenium implementation of `BrowserDriver` (Phase 6/5).

Explicit waits only (`WebDriverWait`) -- `time.sleep` is forbidden by the
project rules (enforced by `test_no_time_sleep_in_discovery_sources`).
The observe payload is collected with one bounded `execute_script` call that
reads only interactive elements; no screenshots ever reach the model.
"""

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from computer_use_automation_system.artifact.models import Locator, LocatorType
from computer_use_automation_system.discovery.act import DriverActionError
from computer_use_automation_system.discovery.models import ObservedElement

OBSERVE_SCRIPT = """
const out = [];
const nodes = document.querySelectorAll(
  "input, button, select, textarea, a[href], [role='link'], [role='button'], " +
  "[role='textbox'], [role='combobox']"
);
for (const el of nodes) {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0 && !el.offsetParent) continue;
  out.push({
    tag: (el.tagName || "").toLowerCase(),
    role: el.getAttribute("role") || "",
    label: (el.getAttribute("aria-label") || el.innerText || el.value || "").trim().slice(0, 120),
    id: (el.id || "").slice(0, 100),
    name_attr: (el.getAttribute("name") || "").slice(0, 100),
    classes: Array.from(el.classList || []).slice(0, 10),
    text: (el.innerText || "").trim().slice(0, 120),
    type: el.getAttribute("type") || "",
    value: (el.value || "").trim().slice(0, 200),
    placeholder: el.getAttribute("placeholder") || "",
    href: el.getAttribute("href") || "",
    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
  });
}
return out;
"""

_ROLE_TAGS = {
    "link": ["a"],
    "button": ["button"],
    "textbox": ["input", "textarea"],
    "combobox": ["select"],
    "form": ["form"],
}

_ROLE_CSS = {
    "link": "a[href], [role='link']",
    "button": "button, [role='button']",
    "textbox": "input, textarea, [role='textbox']",
    "combobox": "select, [role='combobox']",
}


def _xpath_literal(value: str) -> str:
    """XPath 1.0 has no escaping: split on quotes and use concat()."""
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    parts = value.split('"')
    return "concat(" + ", '\"', ".join(f'"{part}"' for part in parts) + ")"


def locator_to_by(locator: Locator) -> tuple[str, str]:
    """Map a typed artifact locator to a Selenium (By, value) pair."""
    if locator.type is LocatorType.ID:
        return By.ID, locator.value
    if locator.type is LocatorType.CSS:
        return By.CSS_SELECTOR, locator.value
    if locator.type is LocatorType.XPATH:
        return By.XPATH, locator.value
    if locator.type is LocatorType.ROLE:
        return _role_to_by(locator.value)
    if locator.type is LocatorType.URL:
        # Schema validation keeps url locators on checkpoints only; never
        # resolve them as element selectors.
        raise ValueError("'url' locators are checkpoint expectations, not element selectors")
    # LocatorType.TEXT
    return By.XPATH, f"//*[normalize-space(.)={_xpath_literal(locator.value)}]"


def _role_to_by(value: str) -> tuple[str, str]:
    role, _, name = value.partition("::")
    role, name = role.strip(), name.strip()
    if not name:
        css = _ROLE_CSS.get(role, f"[role='{role}']")
        return By.CSS_SELECTOR, css
    tags = _ROLE_TAGS.get(role, [])
    predicates = " or ".join(f"self::{tag}" for tag in tags) or "self::*"
    literal = _xpath_literal(name)
    xpath = (
        f'//*[(@role="{role}" or {predicates}) and normalize-space(.)={literal}]'
        if tags
        else f'//*[@role="{role}" and normalize-space(.)={literal}]'
    )
    return By.XPATH, xpath


def normalize_script_result(raw: list) -> list[dict]:
    """Keep only dict rows that carry a tag (defensive against DOM junk)."""
    cleaned: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and item.get("tag"):
            cleaned.append(item)
    return cleaned


def translate_driver_error(exc: Exception) -> DriverActionError:
    """Map Selenium exceptions to the typed `DriverActionError` codes."""
    if isinstance(exc, TimeoutException):
        return DriverActionError("timeout")
    if isinstance(exc, StaleElementReferenceException):
        return DriverActionError("stale")
    if isinstance(exc, NoSuchElementException):
        return DriverActionError("element_not_found")
    raise exc


class SeleniumDriver:
    """`BrowserDriver` bound to an existing `webdriver.Chrome` instance."""

    def __init__(self, driver: WebDriver, timeout_s: float = 10.0) -> None:
        self._driver = driver
        self._timeout = timeout_s
        self._wait = WebDriverWait(driver, timeout_s)

    def observe_raw(self) -> list[dict]:
        raw = self._driver.execute_script(OBSERVE_SCRIPT) or []
        return normalize_script_result(raw)

    def page_text(self) -> str:
        """Visible body text, bounded: feeds replay failure classification,
        which otherwise only sees interactive elements (observe_raw)."""
        try:
            raw = self._driver.execute_script("return document.body ? document.body.innerText : ''")
        except Exception:
            return ""
        return str(raw or "")[:20000]

    def current_url(self) -> str:
        return self._driver.current_url

    def navigate(self, url: str) -> None:
        # SEC-503 (defense in depth): LLMAction/Step already require an
        # http(s) URL, but the driver itself never lets file://, data: or
        # chrome:// reach the browser (local files must not become readable
        # through extract_text).
        if not url.startswith(("http://", "https://")):
            raise DriverActionError("invalid_value")
        try:
            self._driver.get(url)
            self._wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        except Exception as exc:
            raise translate_driver_error(exc) from exc

    def _find(self, element: ObservedElement):
        last_error: Exception | None = None
        for locator in element.locators:
            by, value = locator_to_by(locator)
            try:
                return WebDriverWait(self._driver, self._timeout).until(
                    ec.presence_of_element_located((by, value))
                )
            except TimeoutException as exc:
                last_error = exc
        if last_error is not None:
            raise DriverActionError("element_not_found")
        raise DriverActionError("element_not_found")

    def click(self, element: ObservedElement) -> None:
        try:
            target = self._find(element)
            self._wait.until(ec.element_to_be_clickable(target))
            target.click()
        except DriverActionError:
            raise
        except Exception as exc:
            raise translate_driver_error(exc) from exc

    def type_text(self, element: ObservedElement, text: str) -> None:
        try:
            target = self._find(element)
            target.clear()
            target.send_keys(text)
        except DriverActionError:
            raise
        except Exception as exc:
            raise translate_driver_error(exc) from exc

    def select_option(self, element: ObservedElement, option: str) -> None:
        try:
            target = self._find(element)
            if (target.tag_name or "").lower() == "select":
                from selenium.webdriver.support.ui import Select

                Select(target).select_by_visible_text(option)
            else:
                target.clear()
                target.send_keys(option)
        except DriverActionError:
            raise
        except Exception as exc:
            raise translate_driver_error(exc) from exc

    def extract_text(self, element: ObservedElement) -> str:
        try:
            target = self._find(element)
            return target.text or target.get_attribute("value") or ""
        except DriverActionError:
            raise
        except Exception as exc:
            raise translate_driver_error(exc) from exc

    def quit(self) -> None:
        self._driver.quit()


def build_webdriver(headless: bool = True, timeout_s: float = 10.0) -> SeleniumDriver:
    """Real Chrome session for the CLI (never used by CI tests)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-gpu")
    return SeleniumDriver(webdriver.Chrome(options=options), timeout_s=timeout_s)
