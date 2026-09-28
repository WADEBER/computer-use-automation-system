"""Error taxonomy configuration and classification (spec Phase 7).

Pure, deterministic helpers: page text + driver codes are matched against
patterns loaded from ``config/taxonomy.json``. No LLM, no clock, no I/O
beyond reading the config file. Classification precedence (spec HU-4):
business pattern > unknown dialog > explicit hard pattern > recoverable
(code or pattern, incl. dismissable known dialogs) > hard by default.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from computer_use_automation_system.artifact.models import Locator
from computer_use_automation_system.replay.models import FailureCategory

DEFAULT_TAXONOMY_PATH = Path("config") / "taxonomy.json"

DRIVER_CODES = frozenset({"element_not_found", "stale", "timeout", "invalid_value"})

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

DIALOG_ROLES = frozenset({"dialog", "alertdialog", "alert"})


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 for ch in value)


def _non_empty_strings(values: list[str]) -> list[str]:
    for value in values:
        if not value.strip():
            raise ValueError("patterns must not contain empty strings")
        if _has_control_chars(value):
            raise ValueError("patterns must not contain control characters")
    return values


class TaxonomyPatterns(BaseModel):
    """One non-empty pattern list per failure category (all three required)."""

    model_config = ConfigDict(extra="forbid")

    business_outcome: list[str]
    recoverable: list[str]
    hard: list[str]

    @field_validator("business_outcome", "recoverable", "hard", mode="after")
    @classmethod
    def _check_strings(cls, values: list[str]) -> list[str]:
        return _non_empty_strings(values)


class KnownDialog(BaseModel):
    """A dialog the automation may dismiss once before retrying a step."""

    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(min_length=1)
    dismiss_locator: Locator

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        if _has_control_chars(value):
            raise ValueError("pattern must not contain control characters")
        return value


class TaxonomyConfig(BaseModel):
    """Strict model backing ``config/taxonomy.json`` (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    version: str
    max_recoverable_attempts: int = Field(ge=1)
    patterns: TaxonomyPatterns
    recoverable_driver_codes: list[str] = Field(default_factory=list)
    known_dialogs: list[KnownDialog] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _check_semver(cls, value: str) -> str:
        if not _SEMVER.match(value):
            raise ValueError("version must be semver X.Y.Z")
        return value

    @field_validator("recoverable_driver_codes")
    @classmethod
    def _check_codes(cls, values: list[str]) -> list[str]:
        unknown = sorted(set(values) - DRIVER_CODES)
        if unknown:
            raise ValueError(f"unknown driver codes: {', '.join(unknown)}")
        return values


def load_taxonomy(path: Path = DEFAULT_TAXONOMY_PATH) -> TaxonomyConfig:
    """Read and strictly validate the taxonomy config; raises OSError or
    pydantic ValidationError with a clear message (never a hot AttributeError)."""
    return TaxonomyConfig.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Classification:
    """Outcome of one classification: category plus a safe, config-derived
    signal (never raw page text, so it carries no PII)."""

    category: FailureCategory
    signal: str
    dismiss_locator: Locator | None = None


def page_text(elements: Sequence[dict]) -> str:
    """Flatten observable elements into one searchable text blob."""
    parts: list[str] = []
    for element in elements:
        for key in ("text", "name", "value"):
            value = element.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    return " ".join(parts).lower()


def _dialog_elements(elements: Sequence[dict]) -> list[dict]:
    return [
        element for element in elements if str(element.get("role") or "").lower() in DIALOG_ROLES
    ]


def _matches_known_dialog(dialogs: Sequence[dict], taxonomy: TaxonomyConfig) -> KnownDialog | None:
    dialog_texts = [page_text([dialog]) for dialog in dialogs]
    for known in taxonomy.known_dialogs:
        needle = known.pattern.lower()
        if any(needle in text for text in dialog_texts):
            return known
    return None


def classify_failure(
    code: str | None, elements: Sequence[dict], taxonomy: TaxonomyConfig
) -> Classification:
    """Deterministically classify one failure (spec HU-4 precedence):
    business pattern > unknown dialog > explicit hard pattern > recoverable
    (code/pattern/known dialog) > hard by default."""
    text = page_text(elements)
    dialogs = _dialog_elements(elements)
    known = _matches_known_dialog(dialogs, taxonomy)

    # 1. Business outcome always wins: the app answered normally.
    for pattern in taxonomy.patterns.business_outcome:
        if pattern.lower() in text:
            return Classification("business_outcome", f"page pattern: {pattern}")

    # 2. An unknown dialog is never dismissed blindly -> hard.
    if dialogs and known is None:
        return Classification("hard", "unexpected dialog")

    # 3. Explicit hard patterns (e.g. permission denial).
    for pattern in taxonomy.patterns.hard:
        if pattern.lower() in text:
            return Classification("hard", f"page pattern: {pattern}")

    # 4. Recoverable: driver code, page pattern, or a dismissable known dialog.
    if code is not None and code in taxonomy.recoverable_driver_codes:
        return Classification(
            "recoverable", f"driver code: {code}", known.dismiss_locator if known else None
        )
    for pattern in taxonomy.patterns.recoverable:
        if pattern.lower() in text:
            return Classification(
                "recoverable", f"page pattern: {pattern}", known.dismiss_locator if known else None
            )
    if known is not None:
        return Classification(
            "recoverable", f"known dialog: {known.pattern}", known.dismiss_locator
        )

    # 5. Default: hard, with whatever the driver reported.
    signal = f"driver code: {code}" if code else "no signal matched"
    return Classification("hard", signal)
