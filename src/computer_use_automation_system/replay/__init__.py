"""Deterministic replay engine (Phases 6-8): executes a typed artifact
without invoking any LLM, with failure taxonomy and human-in-the-loop
handoff. Public exports."""

from computer_use_automation_system.replay.handoff import Operator
from computer_use_automation_system.replay.models import (
    ControlState,
    DecisionRecord,
    FailureCategory,
    HandoffDecision,
    HandoffRecord,
    HandoffRequest,
    HandoffTrigger,
    OperatorResponse,
    ReplayError,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)
from computer_use_automation_system.replay.taxonomy import (
    Classification,
    TaxonomyConfig,
    classify_failure,
    load_taxonomy,
)

__all__ = [
    "Classification",
    "ControlState",
    "DecisionRecord",
    "FailureCategory",
    "HandoffDecision",
    "HandoffRecord",
    "HandoffRequest",
    "HandoffTrigger",
    "Operator",
    "OperatorResponse",
    "ReplayError",
    "ReplayResult",
    "ReplayStage",
    "ReplayStatus",
    "TaxonomyConfig",
    "classify_failure",
    "load_taxonomy",
]
