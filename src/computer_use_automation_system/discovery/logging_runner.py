"""Append-only JSONL step log, redacted at write time (Phase 4 source).

Every line written to disk (and echoed to stdout) passes through
``redact_mapping`` first: secrets, PII and sensitive field keys are masked
by the single ``RedactionConfig`` from ``config/policy.json`` (injected here
for tests). The final summary event is appended to the log file and echoed
to stdout, so the JSONL file is self-contained (steps + summary).
"""

import json
import sys
from pathlib import Path
from typing import TextIO

from computer_use_automation_system.discovery.models import RunStatus, StepRecord
from computer_use_automation_system.safety.models import RedactionConfig
from computer_use_automation_system.safety.redaction import redact_mapping


class StepLogger:
    """Writes one JSON line per step and a final summary line."""

    def __init__(
        self,
        log_path: str | Path,
        redaction: RedactionConfig,
        *,
        stdout: TextIO | None = None,
    ) -> None:
        self.log_path = Path(log_path)
        self.redaction = redaction
        self._stdout = stdout if stdout is not None else sys.stdout

    def write_step(self, record: StepRecord) -> None:
        payload = redact_mapping(record.model_dump(mode="json"), self.redaction)
        line = json.dumps(payload, ensure_ascii=False)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._stdout.write(line + "\n")

    def write_summary(self, status: RunStatus, *, steps: int) -> None:
        payload = redact_mapping(
            {"event": "summary", "status": str(status), "steps": steps}, self.redaction
        )
        line = json.dumps(payload, ensure_ascii=False)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._stdout.write(line + "\n")
