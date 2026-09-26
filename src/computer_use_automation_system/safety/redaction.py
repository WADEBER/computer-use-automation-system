"""Write-time redaction of secrets and financial PII (Phase 4).

Everything that reaches a log handler or a file on disk goes through this
module first. Patterns, literals and field keys come from the single
``RedactionConfig`` in ``config/policy.json`` -- nothing is hardcoded here.
"""

import logging
import re
from pathlib import Path
from typing import Any

from computer_use_automation_system.safety.models import RedactionConfig


class RedactionFilter(logging.Filter):
    """Logging filter that masks the formatted message before any handler
    sees it. Attach it to the package logger (or a handler)."""

    def __init__(self, config: RedactionConfig) -> None:
        super().__init__()
        self._config = config

    def filter(self, record: logging.LogRecord) -> bool:
        message = redact_text(record.getMessage(), self._config)
        record.msg = message.replace("\r", "\\r").replace("\n", "\\n")
        record.args = None
        return True


def redact_text(text: str, config: RedactionConfig) -> str:
    """Mask secrets, account numbers, amounts and known literals.

    Regex patterns run first (in configured order, using ``re.sub``
    backreferences), then known literals are replaced by name.
    Idempotent: redacting twice equals redacting once.
    """
    result = text
    for pattern in config.patterns:
        result = re.sub(pattern.regex, pattern.replacement, result)
    for literal in config.literals:
        result = result.replace(literal, "[REDACTED_NAME]")
    return result


def redact_mapping(data: Any, config: RedactionConfig) -> Any:
    """Return a copy of ``data`` safe to write: values under sensitive
    keys (``field_keys``) are replaced by ``[REDACTED_<KEY>]`` and every
    other string goes through :func:`redact_text`. Structure is preserved.
    """
    if isinstance(data, dict):
        sensitive = set(config.field_keys)
        return {
            key: (
                f"[REDACTED_{key.upper()}]" if key in sensitive else redact_mapping(value, config)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_mapping(item, config) for item in data]
    if isinstance(data, str):
        return redact_text(data, config)
    return data


def safe_write_text(
    path: str | Path,
    text: str,
    config: RedactionConfig | None = None,
    *,
    base_dir: str | Path | None = None,
) -> None:
    """Write ``text`` to ``path`` redacted, creating parent directories.

    With no explicit ``config`` it uses the redaction section of
    ``config/policy.json`` -- the same single source the logging filter
    uses. When ``base_dir`` is given, the resolved target must stay inside
    it or ``PermissionError`` is raised (fail closed).
    """
    from computer_use_automation_system.safety.policy import load_policy

    redaction = config if config is not None else load_policy().redaction
    target = Path(path)
    if base_dir is not None:
        base = Path(base_dir).resolve()
        target = target.resolve() if target.is_absolute() else (base / target).resolve()
        if target != base and base not in target.parents:
            raise PermissionError(f"write path escapes base_dir: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(redact_text(text, redaction), encoding="utf-8")
