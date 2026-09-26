"""Clean, text-only DOM snapshot for the LLM (Phase 5).

The model is text-only: observe serializes interactive elements to a small
JSON list (the prompt contract fields only) — never screenshots, never
scripts/styles. Internal `ObservedElement.locators` keep fallback candidates
for artifact compilation but never reach the prompt.
"""

import hashlib
import json
from dataclasses import dataclass

from computer_use_automation_system.artifact.models import Locator, LocatorType
from computer_use_automation_system.discovery.models import ObservedElement

_SKIP_TAGS = frozenset({"script", "style", "link", "meta", "noscript", "head", "title", "base"})
_ROLE_BY_TAG = {
    "a": "link",
    "button": "button",
    "input": "textbox",
    "textarea": "textbox",
    "select": "combobox",
    "form": "form",
}
_TRUNCATION_MARKER = "\n[TRUNCATED]"


@dataclass(frozen=True)
class Snapshot:
    """One observe result: internal elements + prompt-ready text."""

    elements: list[ObservedElement]
    prompt_text: str
    truncated: bool
    digest: str


def _clip(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def _derive_role(tag: str, raw_role: str) -> str:
    return raw_role or _ROLE_BY_TAG.get(tag) or tag


def _safe(value: str) -> str:
    return value.replace('"', "'")


def _build_locators(
    element_id: str, name_attr: str, classes: list[str], tag: str, role: str, name: str, text: str
) -> list[Locator]:
    locators: list[Locator] = []
    if element_id:
        locators.append(Locator(type=LocatorType.ID, value=element_id))
    if element_id:
        css = f"{tag}#{element_id}"
    elif name_attr:
        css = f'{tag}[name="{_safe(name_attr)}"]'
    elif classes:
        css = f"{tag}.{classes[0]}"
    else:
        css = tag
    locators.append(Locator(type=LocatorType.CSS, value=css))
    if role:
        locators.append(Locator(type=LocatorType.ROLE, value=f"{role}::{name}" if name else role))
    if text:
        locators.append(Locator(type=LocatorType.TEXT, value=text[:50]))
    if element_id:
        xpath = f'//{tag}[@id="{_safe(element_id)}"]'
    elif text:
        xpath = f'//{tag}[contains(normalize-space(.), "{_safe(text[:30])}")]'  # noqa: E501
    else:
        xpath = f"//{tag}"
    locators.append(Locator(type=LocatorType.XPATH, value=xpath))
    return locators


def _prompt_item(element: ObservedElement) -> dict:
    return {
        "ref": element.ref,
        "tag": element.tag,
        "role": element.role,
        "name": element.name,
        "value": element.value,
        "href": element.href,
        "text": element.text,
    }


def build_snapshot(raw_elements: list[dict], max_chars: int) -> Snapshot:
    """Build a Snapshot from raw DOM dictionaries (whatever the driver
    produced). Deterministic: same input -> same prompt text and digest."""
    elements: list[ObservedElement] = []
    ref = 0
    for raw in raw_elements:
        tag = str(raw.get("tag") or "").lower()
        if not tag or tag in _SKIP_TAGS:
            continue
        ref += 1
        element_id = str(raw.get("id") or "").strip()
        name_attr = str(raw.get("name_attr") or "").strip()
        classes = [str(item) for item in (raw.get("classes") or [])]
        role = _derive_role(tag, str(raw.get("role") or "").strip())
        text = _clip(str(raw.get("text") or "").strip(), 120) or ""
        name_source = str(raw.get("label") or "").strip() or text or name_attr
        element = ObservedElement(
            ref=ref,
            tag=tag,
            role=role,
            name=name_source[:80],
            value=_clip(str(raw.get("value") or ""), 120),
            href=_clip(str(raw.get("href") or ""), 200),
            text=_clip(text, 120),
            locators=_build_locators(
                element_id, name_attr, classes, tag, role, name_source[:80], text
            ),
        )
        elements.append(element)

    pieces: list[str] = []
    used = 2  # brackets of the JSON list
    truncated = False
    for element in elements:
        piece = json.dumps(_prompt_item(element), ensure_ascii=True, separators=(",", ":"))
        extra = len(piece) + (1 if pieces else 0)
        if used + extra > max_chars:
            truncated = True
            break
        pieces.append(piece)
        used += extra

    prompt_text = "[" + ",".join(pieces) + "]"
    if truncated:
        prompt_text += _TRUNCATION_MARKER
    digest = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
    return Snapshot(elements=elements, prompt_text=prompt_text, truncated=truncated, digest=digest)
