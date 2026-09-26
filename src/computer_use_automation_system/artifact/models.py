"""Typed artifact schema: the reusable contract emitted by discovery and
consumed by deterministic replay (Assignment section 3.2).

Pydantic models are the source of truth. The exported JSON Schema lives in
``docs/schemas/artifact.schema.json`` and is kept in sync by tests.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
INPUT_REF_PATTERN = re.compile(r"\{\{input\.([a-z][a-z0-9_]*)\}\}")


class LocatorType(StrEnum):
    """How a target element/control is identified, in priority order."""

    ID = "id"
    CSS = "css"
    XPATH = "xpath"
    ROLE = "role"
    TEXT = "text"


class ActionType(StrEnum):
    """Action performed in a single ordered step of the flow."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    EXTRACT = "extract"
    SELECT = "select"


class ExpectedCondition(StrEnum):
    """Success condition verified on the checkpoint before declaring success."""

    VISIBLE = "visible"
    TEXT_PRESENT = "text_present"
    URL_CONTAINS = "url_contains"


class Locator(BaseModel):
    """A single element locator. The order of locators in a list is the
    fallback priority: the replay engine tries them from first to last."""

    model_config = ConfigDict(extra="forbid")

    type: LocatorType
    value: str = Field(min_length=1)


class TargetApp(BaseModel):
    """Metadata identifying the application surface this capability runs on."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    entry_url: str = Field(pattern=r"^https?://")


class JSONSchemaObject(BaseModel):
    """JSON-Schema-like description of typed inputs or outputs.

    Only the structural subset the system relies on is allowed: an object
    with per-field ``type`` entries and a ``required`` subset of them.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern=r"^object$")
    properties: dict[str, dict] = Field(min_length=1)
    required: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _required_subset_of_properties(self) -> "JSONSchemaObject":
        for name, prop in self.properties.items():
            if not isinstance(prop, dict) or not isinstance(prop.get("type"), str):
                raise ValueError(f"property '{name}' must declare a string 'type' field")
        unknown = [key for key in self.required if key not in self.properties]
        if unknown:
            raise ValueError(f"required fields not present in properties: {unknown}")
        return self


class Step(BaseModel):
    """One ordered action of the flow.

    Conditional rules by ``action_type``:
    - ``navigate``: ``value`` is the destination URL.
    - ``type`` / ``select``: ``value`` must embed at least one
      ``{{input.*}}`` reference so run values are never hardcoded.
    - ``click``: no ``value``.
    - ``extract``: requires ``output_key`` (membership in the artifact
      output schema is enforced by :class:`Artifact`), no ``value``.
    """

    model_config = ConfigDict(extra="forbid")

    step_id: int = Field(ge=1)
    action_type: ActionType
    description: str = Field(min_length=1)
    locators: list[Locator] = Field(min_length=1)
    value: str | None = None
    output_key: str | None = None
    timeout_ms: int = Field(default=5000, gt=0)

    @model_validator(mode="after")
    def _conditional_rules(self) -> "Step":
        has_input_ref = bool(INPUT_REF_PATTERN.search(self.value or ""))

        if self.action_type is ActionType.NAVIGATE:
            if not self.value or not self.value.startswith(("http://", "https://")):
                raise ValueError("navigate steps require an http(s) URL in 'value'")
        elif self.action_type in (ActionType.TYPE, ActionType.SELECT):
            if not self.value:
                raise ValueError(f"{self.action_type.value} steps require a 'value'")
            if not has_input_ref:
                raise ValueError(
                    f"{self.action_type.value} steps must reference {{{{input.*}}}} "
                    "in 'value' (no hardcoded run values)"
                )
        elif self.action_type is ActionType.CLICK:
            if self.value is not None:
                raise ValueError("click steps must not declare 'value'")
        elif self.action_type is ActionType.EXTRACT:
            if not self.output_key:
                raise ValueError("extract steps require an 'output_key'")
            if self.value is not None:
                raise ValueError("extract steps must not declare 'value'")

        if self.action_type is not ActionType.EXTRACT and self.output_key is not None:
            raise ValueError("'output_key' is only allowed on extract steps")

        return self


class Checkpoint(BaseModel):
    """Success condition verified before declaring the replay successful."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    locators: list[Locator] = Field(min_length=1)
    expected_condition: ExpectedCondition


class Artifact(BaseModel):
    """A typed, versioned, serializable capability (Assignment section 3.2).

    Reviewers and calling agents must understand what the capability does,
    what it needs and what it returns from this contract alone.
    """

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN.pattern)
    version: str = Field(pattern=SEMVER_PATTERN.pattern)
    description: str = Field(min_length=1)
    target_app: TargetApp
    input_schema: JSONSchemaObject
    output_schema: JSONSchemaObject
    steps: list[Step] = Field(min_length=1)
    checkpoint: Checkpoint

    @model_validator(mode="after")
    def _cross_invariants(self) -> "Artifact":
        for position, step in enumerate(self.steps, start=1):
            if step.step_id != position:
                raise ValueError(
                    f"step_id must be sequential starting at 1: "
                    f"expected {position}, got {step.step_id}"
                )

            for ref in INPUT_REF_PATTERN.findall(step.value or ""):
                if ref not in self.input_schema.properties:
                    raise ValueError(
                        f"step {step.step_id} references {{{{input.{ref}}}}} "
                        "which is not defined in input_schema.properties"
                    )

            if (
                step.action_type is ActionType.EXTRACT
                and step.output_key not in self.output_schema.properties
            ):
                raise ValueError(
                    f"step {step.step_id} output_key '{step.output_key}' "
                    "is not defined in output_schema.properties"
                )

        return self
