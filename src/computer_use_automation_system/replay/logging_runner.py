"""Append-only JSONL event log for replay runs, redacted at write time
(Phase 9 evidence source).

Mirrors ``discovery.logging_runner.StepLogger``: every line written to disk
passes through ``redact_mapping`` first, so secrets, PII and sensitive field
keys are masked by the single ``RedactionConfig`` from ``config/policy.json``.
The engine emits raw-ish timeline events; this writer is the redaction layer
for both the engine callbacks and the CLI's start/result envelopes.
"""

import json
from pathlib import Path

from computer_use_automation_system.safety.models import RedactionConfig
from computer_use_automation_system.safety.redaction import redact_mapping


class ReplayLogger:
    """Writes one redacted JSON line per replay event."""

    def __init__(self, log_path: str | Path, redaction: RedactionConfig) -> None:
        self.log_path = Path(log_path)
        self.redaction = redaction

    def write(self, payload: dict[str, object]) -> None:
        line = json.dumps(redact_mapping(payload, self.redaction), ensure_ascii=False)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
