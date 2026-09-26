"""Typed models for the safety policy core (Phase 4).

The policy file (``config/policy.json``) is the single source of truth for
the allowlist, the action-classification rules and the redaction patterns.
Pydantic models here validate it strictly (``extra="forbid"``).
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from computer_use_automation_system.artifact.models import ActionType


class DecisionKind(StrEnum):
    """Verdict returned by the policy engine for a single action."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    FLAG = "flag"
    BLOCK = "block"


class PolicyRule(BaseModel):
    """One classification rule. Rules are evaluated in file order and the
    first match wins. Every rule carries an auditable ``reason``."""

    model_config = ConfigDict(extra="forbid")

    match_action_type: ActionType | None = None
    match_url_pattern: str | None = None
    decision: DecisionKind
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _at_least_one_condition(self) -> "PolicyRule":
        if self.match_action_type is None and self.match_url_pattern is None:
            raise ValueError("rule needs at least one match condition")
        return self


class RedactionPattern(BaseModel):
    """A regex masking rule applied at write time.

    ``replacement`` uses Python ``re.sub`` backreferences (e.g. ``\\1``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    regex: str
    replacement: str = Field(min_length=1)

    @field_validator("regex")
    @classmethod
    def _regex_must_compile(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return value


class RedactionConfig(BaseModel):
    """Patterns, literals and structured keys masked before any write."""

    model_config = ConfigDict(extra="forbid")

    patterns: list[RedactionPattern] = Field(min_length=1)
    literals: list[str] = Field(min_length=1)
    field_keys: list[str] = Field(min_length=1)


class Decision(BaseModel):
    """Outcome of evaluating one action against the policy."""

    model_config = ConfigDict(extra="forbid")

    decision: DecisionKind
    reason: str = Field(min_length=1)
    matched_rule: str | None = None


class PolicyConfig(BaseModel):
    """The full safety policy: perimeter, classification rules and
    redaction, loaded from ``config/policy.json``."""

    model_config = ConfigDict(extra="forbid")

    allowed_origins: list[str] = Field(min_length=1)
    allowed_routes: list[str] = Field(min_length=1)
    allowed_action_types: list[ActionType] = Field(min_length=1)
    rules: list[PolicyRule] = Field(default_factory=list)
    redaction: RedactionConfig
