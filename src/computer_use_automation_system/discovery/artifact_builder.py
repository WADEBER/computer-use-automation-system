"""Compile successful `StepRecord`s into a Phase 3 typed `Artifact`.

Only steps with `outcome == "ok"` are compiled (failed attempts are noise,
not part of the reusable flow). Type/select values are parameterized as
`{{input.*}}` so run values are never hardcoded; extracts get automatic
`output{N}` keys. Fallback schemas keep the Fase 3 invariants (at least one
property per schema) when a flow has no inputs or no extracts.

The checkpoint is derived from the final URL observed when the goal fired:
an input-agnostic ``url_contains`` on the app-area prefix (scheme + netloc +
first path segment, query stripped), so a replay with different inputs still
passes while a run that ended on the wrong page does not.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from computer_use_automation_system.artifact.models import (
    Artifact,
    Checkpoint,
    ExpectedCondition,
    JSONSchemaObject,
    Locator,
    LocatorType,
    Step,
    TargetApp,
)
from computer_use_automation_system.discovery.models import ActionType, ObservedElement, StepRecord

_ARTIFACT_VERSION = "1.0.0"
_BODY_LOCATOR = Locator(type=LocatorType.CSS, value="body")
_MAX_SLUG = 60


def area_prefix(url: str | None) -> str | None:
    """Return the input-agnostic prefix of ``url``: scheme + netloc + first
    path segment, with query/fragment stripped.

    ``http://127.0.0.1:5000/members/M-1001?tab=loans`` becomes
    ``http://127.0.0.1:5000/members`` (no run value such as a member ID is
    kept, so the checkpoint stays valid for any input). Non-http(s) or empty
    input returns ``None`` (caller falls back to a visible checkpoint).
    """
    if not url:
        return None
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    prefix = f"{parts.scheme}://{parts.netloc}"
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments:
        prefix = f"{prefix}/{segments[0]}"
    return prefix


@dataclass(frozen=True)
class StepSource:
    """One compiled input: the log record plus the element resolved in the
    snapshot of that step (`None` for navigate)."""

    record: StepRecord
    element: ObservedElement | None = None


def slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")[:_MAX_SLUG].strip("_")
    if not slug or not slug[0].isalpha():
        return f"{fallback}_{slug}".strip("_") if slug else fallback
    return slug


def _element_locators(element: ObservedElement | None) -> list[Locator]:
    if element is not None and element.locators:
        return list(element.locators)
    return [_BODY_LOCATOR]


def build_artifact(
    goal: str,
    entry_url: str,
    steps: list[StepSource],
    *,
    final_url: str | None = None,
) -> Artifact:
    """Compile a successful run into an artifact that passes Fase 3 checks.

    ``final_url`` is the driver URL observed when the goal check passed; it
    feeds the checkpoint (``url_contains`` on the area prefix when it is an
    http(s) URL, otherwise the generic visible checkpoint).
    """
    sources = [source for source in steps if source.record.outcome == "ok"]
    if not sources:
        raise ValueError("cannot build an artifact without successful steps")

    input_properties: dict[str, dict] = {}
    output_properties: dict[str, dict] = {}
    artifact_steps: list[Step] = []
    has_extract = False

    for position, source in enumerate(sources, start=1):
        record, element = source.record, source.element
        value: str | None = None
        output_key: str | None = None

        if record.action is ActionType.NAVIGATE:
            value = record.value_preview
        elif record.action in (ActionType.TYPE, ActionType.SELECT):
            base = element.name.strip() if element is not None and element.name.strip() else ""
            key = slugify(base, fallback=f"step{position}_value")
            if key in input_properties:
                key = f"{key}_{position}"
            input_properties[key] = {"type": "string"}
            value = "{{input." + key + "}}"
        elif record.action is ActionType.EXTRACT:
            has_extract = True
            output_key = f"output{position}"
            output_properties[output_key] = {"type": "string"}

        artifact_steps.append(
            Step(
                step_id=position,
                action_type=record.action,
                description=record.reason,
                locators=_element_locators(element),
                value=value,
                output_key=output_key,
            )
        )

    if not input_properties:
        input_properties["notes"] = {"type": "string"}
    if not output_properties:
        output_properties["summary"] = {"type": "string"}

    input_schema = JSONSchemaObject(
        type="object",
        properties=input_properties,
        required=sorted(input_properties),
    )
    output_schema = JSONSchemaObject(
        type="object",
        properties=output_properties,
        required=sorted(output_properties) if has_extract else [],
    )

    prefix = area_prefix(final_url)
    if prefix is not None:
        checkpoint = Checkpoint(
            description=f"Goal reached: {goal}",
            locators=[Locator(type=LocatorType.URL, value=prefix)],
            expected_condition=ExpectedCondition.URL_CONTAINS,
        )
    else:
        checkpoint = Checkpoint(
            description=f"Goal reached: {goal}",
            locators=[_BODY_LOCATOR],
            expected_condition=ExpectedCondition.VISIBLE,
        )

    return Artifact(
        capability_id=slugify(goal, fallback="capability"),
        version=_ARTIFACT_VERSION,
        description=goal,
        target_app=TargetApp(name=urlparse(entry_url).netloc or "target-app", entry_url=entry_url),
        input_schema=input_schema,
        output_schema=output_schema,
        steps=artifact_steps,
        checkpoint=checkpoint,
    )
