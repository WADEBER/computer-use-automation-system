"""Validate caller inputs against the artifact's `input_schema` and resolve
`{{input.*}}` references before the replay touches the browser."""

import re
from collections.abc import Iterable, Mapping

from computer_use_automation_system.artifact.models import INPUT_REF_PATTERN, JSONSchemaObject

_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def matches_type(value: object, declared: str) -> bool:
    """JSON-Schema-style type check for the structural subset we support."""
    expected = _TYPE_CHECKS.get(declared)
    if expected is None:
        return True  # unknown declared type: structural check only
    if isinstance(value, bool) and declared in ("integer", "number"):
        return False  # bool is an int subclass; JSON Schema says otherwise
    return isinstance(value, expected)


def validate_inputs(
    schema: JSONSchemaObject,
    inputs: Mapping[str, object],
    *,
    extra_required: Iterable[str] = (),
) -> list[str]:
    """Return a list of human-readable problems (empty means valid).

    ``extra_required`` adds keys that must be present because the artifact's
    steps reference them via ``{{input.*}}`` even when `input_schema` marks
    them optional.
    """
    problems: list[str] = []
    required = set(schema.required) | set(extra_required)
    for name in sorted(required):
        if name not in inputs:
            problems.append(f"missing required input: {name}")
    for name, value in inputs.items():
        prop = schema.properties.get(name)
        if prop is None:
            continue  # undeclared extras are passed through (JSON Schema default)
        declared = prop.get("type")
        if isinstance(declared, str) and not matches_type(value, declared):
            problems.append(f"input {name} must be {declared}, got {type(value).__name__}")
    return problems


def referenced_input_keys(values: Iterable[str | None]) -> set[str]:
    """All ``{{input.X}}`` keys referenced by the given step values."""
    keys: set[str] = set()
    for value in values:
        if value:
            keys.update(INPUT_REF_PATTERN.findall(value))
    return keys


def resolve_value(template: str | None, inputs: Mapping[str, object]) -> str | None:
    """Substitute every ``{{input.X}}`` with the caller-provided value.

    Raises ``KeyError`` for a reference that was not validated up front
    (defense in depth: `validate_inputs` should have caught it already).
    """
    if template is None:
        return None

    def _substitute(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in inputs:
            raise KeyError(key)
        return str(inputs[key])

    return INPUT_REF_PATTERN.sub(_substitute, template)
