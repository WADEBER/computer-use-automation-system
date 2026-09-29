"""Operator seam for the human-in-the-loop handoff (spec Phase 8, HU-6).

The engine never talks to stdin, a TTY or a browser UI: it builds a typed
`HandoffRequest`, hands it to an injected `Operator` and blocks on the
answer. Implementations: `FakeOperator` (tests) and `PromptOperator`
(CLI). No LLM is imported or invoked in this module.
"""

from typing import Protocol, runtime_checkable

from computer_use_automation_system.replay.models import (
    HandoffRequest,
    OperatorResponse,
)


@runtime_checkable
class Operator(Protocol):
    """Human (or fake) that receives a pause package and returns a decision."""

    def intervene(self, request: HandoffRequest) -> OperatorResponse: ...
