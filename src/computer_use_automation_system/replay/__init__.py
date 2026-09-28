"""Deterministic replay engine (Phases 6-7): executes a typed artifact
without invoking any LLM, with failure taxonomy. Public exports."""

from computer_use_automation_system.replay.models import (
    DecisionRecord,
    FailureCategory,
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
    "DecisionRecord",
    "FailureCategory",
    "ReplayError",
    "ReplayResult",
    "ReplayStage",
    "ReplayStatus",
    "TaxonomyConfig",
    "classify_failure",
    "load_taxonomy",
]
