"""Typed result contract of a deterministic replay run (spec Phase 6, HU-4).

Invariants enforced by the models themselves:
- ``status == success``  <=> ``error is None`` and ``outputs`` is not None.
- ``status == failure``  <=> ``error`` is set and ``outputs`` is None.
- ``policy_kind`` only on ``stage == "policy"``; input/output validation
  failures never carry a ``step_id``.
- Phase 8 (handoff, HU-2/HU-5): the pause package and its evidence record
  are strict models (``extra="forbid"``, no timestamps); confirm triggers
  pause at ``stage == "policy"`` (so ``abort`` keeps exit 11), failures at
  ``step``/``checkpoint`` (exit 1); ``ReplayResult.handoff`` is additive
  with correlated indexes starting at 0.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from computer_use_automation_system.artifact.models import ActionType
from computer_use_automation_system.safety.models import DecisionKind


class ReplayStatus(StrEnum):
    """Final status of one replay run. Every run ends in exactly one."""

    SUCCESS = "success"
    FAILURE = "failure"


class ReplayStage(StrEnum):
    """Where the failure happened, from input validation to output checks."""

    INPUT_VALIDATION = "input_validation"
    STEP = "step"
    POLICY = "policy"
    CHECKPOINT = "checkpoint"
    OUTPUT_VALIDATION = "output_validation"


PolicyKind = Literal["blocked", "needs_approval"]

FailureCategory = Literal["business_outcome", "recoverable", "hard"]


class ReplayError(BaseModel):
    """Why a replay failed: stage, optional step and a safe message."""

    model_config = ConfigDict(extra="forbid")

    stage: ReplayStage
    step_id: int | None = Field(default=None, ge=1)
    policy_kind: PolicyKind | None = None
    failure_category: FailureCategory | None = None
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def _stage_rules(self) -> "ReplayError":
        if self.stage is ReplayStage.POLICY and self.policy_kind is None:
            raise ValueError("policy failures require a 'policy_kind'")
        if self.stage is not ReplayStage.POLICY and self.policy_kind is not None:
            raise ValueError("'policy_kind' is only allowed when stage is 'policy'")
        if self.stage in (ReplayStage.INPUT_VALIDATION, ReplayStage.OUTPUT_VALIDATION):
            if self.step_id is not None:
                raise ValueError(f"stage '{self.stage.value}' must not declare 'step_id'")
        elif self.step_id is None:
            raise ValueError(f"stage '{self.stage.value}' requires a 'step_id'")
        if self.failure_category is not None and self.stage not in (
            ReplayStage.STEP,
            ReplayStage.CHECKPOINT,
        ):
            raise ValueError("'failure_category' is only allowed for stage 'step' or 'checkpoint'")
        return self


class DecisionRecord(BaseModel):
    """One policy verdict produced while replaying a step (audit trail)."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    url: str = Field(min_length=1)
    decision: DecisionKind
    reason: str = Field(min_length=1)


HandoffTrigger = Literal[
    "hard_failure",
    "retries_exhausted",
    "needs_approval",
    "risky_step",
]

HandoffDecision = Literal["resume", "finish", "abort"]

ControlState = Literal["automation", "human"]

# SEC-805: bounds on the pause package so a hostile or huge page can not
# flood the operator prompt or the persisted evidence. The engine truncates
# at capture; these limits fail closed if a caller skips that path.
MAX_SNAPSHOT_ELEMENTS = 100
MAX_HANDOFF_TEXT = 2000


class HandoffRequest(BaseModel):
    """Intervention package handed to the operator (spec Phase 8, HU-2).

    Strict (``extra="forbid"``) and timestamp-free for determinism; text
    fields arrive already redacted by the engine. Confirm signals
    (``needs_approval``/``risky_step``) pause at the policy stage so an
    ``abort`` maps to exit 11; failures pause at step/checkpoint (exit 1).
    """

    model_config = ConfigDict(extra="forbid")

    trigger: HandoffTrigger
    stage: ReplayStage
    step_id: int | None = Field(default=None, ge=1)
    action: ActionType | None = None
    reason: str = Field(min_length=1, max_length=MAX_HANDOFF_TEXT)
    capability: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=MAX_HANDOFF_TEXT)
    snapshot: list[dict[str, object]] = Field(max_length=MAX_SNAPSHOT_ELEMENTS)
    screenshot: str | None = None

    @model_validator(mode="after")
    def _stage_rules(self) -> "HandoffRequest":
        if self.stage not in (
            ReplayStage.STEP,
            ReplayStage.POLICY,
            ReplayStage.CHECKPOINT,
        ):
            raise ValueError(f"stage '{self.stage.value}' can not pause for handoff")
        confirm = self.trigger in ("needs_approval", "risky_step")
        if confirm and self.stage is not ReplayStage.POLICY:
            raise ValueError(f"trigger '{self.trigger}' requires stage 'policy'")
        if not confirm and self.stage is ReplayStage.POLICY:
            raise ValueError("stage 'policy' requires a confirm trigger")
        if self.trigger == "retries_exhausted" and self.stage is not ReplayStage.STEP:
            raise ValueError("'retries_exhausted' pauses at stage 'step'")
        if self.stage in (ReplayStage.STEP, ReplayStage.POLICY) and self.step_id is None:
            raise ValueError(f"stage '{self.stage.value}' requires a 'step_id'")
        return self


class HandoffRecord(BaseModel):
    """Evidence of one operator intervention (spec Phase 8, HU-5)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    request: HandoffRequest
    decision: HandoffDecision
    note: str | None = Field(default=None, min_length=1, max_length=MAX_HANDOFF_TEXT)
    resumed_snapshot: list[dict[str, object]] | None = Field(
        default=None, max_length=MAX_SNAPSHOT_ELEMENTS
    )

    @model_validator(mode="after")
    def _decision_rules(self) -> "HandoffRecord":
        if self.decision == "abort" and self.resumed_snapshot is not None:
            raise ValueError("'abort' must not declare 'resumed_snapshot'")
        if self.decision != "abort" and self.resumed_snapshot is None:
            raise ValueError(f"'{self.decision}' requires 'resumed_snapshot'")
        return self


class OperatorResponse(BaseModel):
    """What the operator answers to a pause: a decision plus an optional
    note (spec Phase 8, HU-6); the note is redacted before it is recorded."""

    model_config = ConfigDict(extra="forbid")

    decision: HandoffDecision
    note: str | None = Field(default=None, min_length=1)


class ReplayResult(BaseModel):
    """Outcome of a full deterministic replay run."""

    model_config = ConfigDict(extra="forbid")

    status: ReplayStatus
    capability_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    outputs: dict[str, object] | None = None
    steps_executed: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    decisions: list[DecisionRecord] = Field(default_factory=list)
    handoff: list[HandoffRecord] = Field(default_factory=list)
    error: ReplayError | None = None

    @model_validator(mode="after")
    def _handoff_indexes(self) -> "ReplayResult":
        for position, record in enumerate(self.handoff):
            if record.index != position:
                raise ValueError("handoff records must use correlated indexes starting at 0")
        return self

    @model_validator(mode="after")
    def _status_invariants(self) -> "ReplayResult":
        if self.status is ReplayStatus.SUCCESS:
            if self.error is not None:
                raise ValueError("success results must not declare an error")
            if self.outputs is None:
                raise ValueError("success results require 'outputs'")
        else:
            if self.error is None:
                raise ValueError("failure results require an error")
            if self.outputs is not None:
                raise ValueError("failure results must not expose outputs")
        return self
