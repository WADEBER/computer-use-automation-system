"""Typed contracts for the discovery loop (Phase 5).

The spec (`docs/plans/fase_5/5.spec.md`) defines the data contracts; the
models here enforce them strictly (`extra="forbid"`) so a malformed LLM
answer, a stray log line or an inconsistent run result fails fast instead
of reaching the browser or the artifact.
"""

import os
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from computer_use_automation_system.artifact.models import ActionType, Artifact, Locator
from computer_use_automation_system.safety.models import DecisionKind


def _default_artifact_out() -> Path:
    return Path("evidence") / "discovery" / "artifact.json"


def _default_log_out() -> Path:
    return Path("evidence") / "discovery" / "steps.jsonl"


class RunStatus(StrEnum):
    """Final status of one discovery run. Every run ends in exactly one."""

    GOAL_REACHED = "goal_reached"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    DEAD_END = "dead_end"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs_approval"
    LLM_ERROR = "llm_error"


class DiscoveryConfig(BaseModel):
    """Input of a discovery run. The policy file is NOT part of the config:
    it always comes from `config/policy.json` (single source, Phase 4)."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    entry_url: str = Field(pattern=r"^https?://")
    max_steps: int = Field(default=15, gt=0)
    step_timeout_ms: int = Field(default=15000, gt=0)
    total_timeout_ms: int = Field(default=300000, gt=0)
    repeat_threshold: int = Field(default=3, ge=2)
    max_snapshot_chars: int = Field(default=8000, gt=0)
    max_llm_retries: int = Field(default=2, ge=0)
    artifact_out: Path = Field(default_factory=_default_artifact_out)
    log_out: Path = Field(default_factory=_default_log_out)
    ollama_base_url: str = Field(
        default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = Field(
        default_factory=lambda: os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    )


class LLMAction(BaseModel):
    """Strict, typed action returned by the LLM. Validated BEFORE touching
    the driver: an invalid answer is a retry/`llm_error`, never an action."""

    model_config = ConfigDict(extra="forbid")

    action: ActionType
    element_ref: int | None = Field(default=None, ge=1)
    value: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _conditional_rules(self) -> "LLMAction":
        if self.action is ActionType.NAVIGATE:
            if self.element_ref is not None:
                raise ValueError("navigate actions must not declare 'element_ref'")
            if not self.value or not self.value.startswith(("http://", "https://")):
                raise ValueError("navigate actions require an http(s) URL in 'value'")
        elif self.action in (ActionType.TYPE, ActionType.SELECT):
            if self.element_ref is None:
                raise ValueError(f"{self.action.value} actions require an 'element_ref'")
            if not self.value:
                raise ValueError(f"{self.action.value} actions require a 'value'")
        else:  # click, extract
            if self.element_ref is None:
                raise ValueError(f"{self.action.value} actions require an 'element_ref'")
            if self.value is not None:
                raise ValueError(f"{self.action.value} actions must not declare 'value'")
        return self


class PolicyDecisionRecord(BaseModel):
    """Audit copy of the Phase 4 verdict applied before an action."""

    model_config = ConfigDict(extra="forbid")

    decision: DecisionKind
    reason: str = Field(min_length=1)


class StepRecord(BaseModel):
    """One line of the JSONL step log (contract keys from the spec)."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=1)
    action: ActionType
    element_ref: int | None = Field(default=None, ge=1)
    value_preview: str | None = None
    reason: str = Field(min_length=1)
    policy_decision: PolicyDecisionRecord | None = None
    outcome: str = Field(min_length=1)
    snapshot_hash: str = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    max_steps: int = Field(gt=0)


class ObservedElement(BaseModel):
    """One interactive element as seen by observe. `locators` are internal
    (used to compile the artifact) and never reach the LLM prompt."""

    model_config = ConfigDict(extra="forbid")

    ref: int = Field(ge=1)
    tag: str = Field(min_length=1)
    role: str = Field(min_length=1)
    name: str = ""
    value: str | None = None
    href: str | None = None
    text: str | None = None
    locators: list[Locator] = Field(default_factory=list)


class DiscoveryResult(BaseModel):
    """Outcome of a full run. Invariant: the artifact exists iff (and only
    if) the status is `goal_reached`."""

    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    steps: list[StepRecord] = Field(default_factory=list)
    artifact: Artifact | None = None
    artifact_path: Path | None = None
    log_path: Path | None = None

    @model_validator(mode="after")
    def _artifact_iff_goal_reached(self) -> "DiscoveryResult":
        if (self.artifact is not None) != (self.status is RunStatus.GOAL_REACHED):
            raise ValueError("artifact must be present iff status == 'goal_reached'")
        if self.artifact is None and self.artifact_path is not None:
            raise ValueError("artifact_path requires an artifact")
        return self
