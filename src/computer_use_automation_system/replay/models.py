"""Typed result contract of a deterministic replay run (spec Phase 6, HU-4).

Invariants enforced by the models themselves:
- ``status == success``  <=> ``error is None`` and ``outputs`` is not None.
- ``status == failure``  <=> ``error`` is set and ``outputs`` is None.
- ``policy_kind`` only on ``stage == "policy"``; input/output validation
  failures never carry a ``step_id``.
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
    error: ReplayError | None = None

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
