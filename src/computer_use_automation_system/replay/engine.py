"""Deterministic replay engine (spec Phase 6): executes a typed artifact
step by step with NO LLM anywhere in this module.

Every action passes the Phase 4 policy (`enforce`) before reaching the
driver, the checkpoint gates success, and outputs are validated against
`output_schema`. Failures return a typed `ReplayResult`, never a raw
exception.
"""

import time
from collections.abc import Callable, Mapping

from computer_use_automation_system.artifact.models import ActionType, Artifact, Step
from computer_use_automation_system.discovery.act import BrowserDriver, perform
from computer_use_automation_system.discovery.models import LLMAction, ObservedElement
from computer_use_automation_system.replay.checkpoint import check_checkpoint
from computer_use_automation_system.replay.inputs import (
    matches_type,
    referenced_input_keys,
    resolve_value,
    validate_inputs,
)
from computer_use_automation_system.replay.models import (
    DecisionRecord,
    FailureCategory,
    ReplayError,
    ReplayResult,
    ReplayStage,
    ReplayStatus,
)
from computer_use_automation_system.replay.taxonomy import (
    TaxonomyConfig,
    classify_failure,
    load_taxonomy,
)
from computer_use_automation_system.safety.models import DecisionKind, PolicyConfig
from computer_use_automation_system.safety.policy import PolicyViolation, enforce
from computer_use_automation_system.safety.redaction import redact_text


def _synthetic_element(step: Step) -> ObservedElement:
    """Minimal element carrying the step's fallback locators; the driver
    resolves them exactly like it resolves discovery elements."""
    return ObservedElement(
        ref=step.step_id,
        tag="div",
        role="replay",
        name=step.description,
        locators=list(step.locators),
    )


def _build_action(step: Step, resolved_value: str | None) -> LLMAction:
    is_navigate = step.action_type is ActionType.NAVIGATE
    return LLMAction(
        action=step.action_type,
        element_ref=None if is_navigate else step.step_id,
        value=resolved_value,
        reason=step.description,
    )


def _validate_outputs(artifact: Artifact, outputs: Mapping[str, object]) -> list[str]:
    schema = artifact.output_schema
    problems: list[str] = []
    for name in sorted(set(schema.required)):
        if name not in outputs:
            problems.append(f"missing required output: {name}")
    for name, value in outputs.items():
        prop = schema.properties.get(name)
        if prop is None:
            problems.append(f"undeclared output: {name}")
            continue
        declared = prop.get("type")
        if isinstance(declared, str) and not matches_type(value, declared):
            problems.append(f"output {name} must be {declared}, got {type(value).__name__}")
    return problems


def replay(
    artifact: Artifact,
    inputs: Mapping[str, object],
    driver: BrowserDriver,
    policy: PolicyConfig,
    *,
    approved: bool = False,
    step_timeout_ms: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    taxonomy: TaxonomyConfig | None = None,
) -> ReplayResult:
    """Replay `artifact` with `inputs` against `driver`, enforcing `policy`.

    Returns a typed `ReplayResult` for every outcome (spec HU-1..HU-4);
    driver/policy/taxonomy are injected so CI never needs Chrome or a network.
    `taxonomy=None` loads `config/taxonomy.json` (same pattern as policy).
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()
    started = clock()
    decisions: list[DecisionRecord] = []

    def _finish(
        status: ReplayStatus,
        *,
        steps_executed: int,
        outputs: dict[str, object] | None = None,
        error: ReplayError | None = None,
    ) -> ReplayResult:
        elapsed_ms = max(0, int((clock() - started) * 1000))
        return ReplayResult(
            status=status,
            capability_id=artifact.capability_id,
            version=artifact.version,
            outputs=outputs,
            steps_executed=steps_executed,
            elapsed_ms=elapsed_ms,
            decisions=decisions,
            error=error,
        )

    def _failure(
        stage: ReplayStage,
        message: str,
        *,
        steps: int,
        category: FailureCategory | None = None,
        **kwargs,
    ) -> ReplayResult:
        return _finish(
            ReplayStatus.FAILURE,
            steps_executed=steps,
            error=ReplayError(stage=stage, message=message, failure_category=category, **kwargs),
        )

    def _classify(code: str | None):
        return classify_failure(code, driver.observe_raw(), taxonomy)

    def _dismiss(locator, step: Step) -> None:
        """Dismiss a known dialog. Every attempt goes through `enforce()`:
        a refused verdict records the decision and skips the click."""
        url = driver.current_url()
        try:
            decision = enforce(policy, ActionType.CLICK, url, approved=approved)
        except PolicyViolation as exc:
            decision = exc.decision
            decisions.append(
                DecisionRecord(
                    action_type=ActionType.CLICK,
                    url=url,
                    decision=decision.decision,
                    reason=decision.reason,
                )
            )
            return
        decisions.append(
            DecisionRecord(
                action_type=ActionType.CLICK,
                url=url,
                decision=decision.decision,
                reason=decision.reason,
            )
        )
        dismiss_element = ObservedElement(
            ref=step.step_id,
            tag="button",
            role="button",
            name="dismiss known dialog",
            locators=[locator],
        )
        perform(
            driver,
            LLMAction(
                action=ActionType.CLICK,
                element_ref=step.step_id,
                reason="dismiss known dialog",
            ),
            dismiss_element,
        )

    # 1. Validate inputs (and every {{input.*}} used by the steps) before
    # the browser receives a single call.
    step_values = [step.value for step in artifact.steps]
    problems = validate_inputs(
        artifact.input_schema,
        inputs,
        extra_required=referenced_input_keys(step_values),
    )
    if problems:
        return _failure(ReplayStage.INPUT_VALIDATION, "; ".join(problems), steps=0)

    outputs: dict[str, object] = {}
    steps_executed = 0

    # 2. Execute steps in order; the first failure stops the run (fail fast).
    for step in artifact.steps:
        if step_timeout_ms is not None:
            spent_ms = int((clock() - started) * 1000)
            if spent_ms > step_timeout_ms:
                return _failure(
                    ReplayStage.STEP,
                    "replay time budget exceeded",
                    steps=steps_executed,
                    step_id=step.step_id,
                    category="hard",
                )

        resolved = resolve_value(step.value, inputs)
        attempts = 0
        while True:
            attempts += 1
            target_url = driver.current_url()
            if step.action_type is ActionType.NAVIGATE and resolved:
                target_url = resolved

            try:
                decision = enforce(policy, step.action_type, target_url, approved=approved)
            except PolicyViolation as exc:
                decision = exc.decision
                decisions.append(
                    DecisionRecord(
                        action_type=step.action_type,
                        url=target_url,
                        decision=decision.decision,
                        reason=decision.reason,
                    )
                )
                kind = "blocked" if decision.decision is DecisionKind.BLOCK else "needs_approval"
                return _failure(
                    ReplayStage.POLICY,
                    decision.reason,
                    steps=steps_executed,
                    step_id=step.step_id,
                    policy_kind=kind,
                )
            decisions.append(
                DecisionRecord(
                    action_type=step.action_type,
                    url=target_url,
                    decision=decision.decision,
                    reason=decision.reason,
                )
            )

            element = None if step.action_type is ActionType.NAVIGATE else _synthetic_element(step)
            outcome = perform(driver, _build_action(step, resolved), element)
            if outcome.outcome == "ok":
                break

            classification = _classify(outcome.outcome)
            if (
                classification.category == "recoverable"
                and attempts < taxonomy.max_recoverable_attempts
            ):
                if classification.dismiss_locator is not None:
                    _dismiss(classification.dismiss_locator, step)
                continue

            suffix = (
                f" (attempts exhausted: {attempts})"
                if classification.category == "recoverable"
                else ""
            )
            message = redact_text(
                f"step {step.step_id} ({step.action_type.value}) failed: "
                f"{outcome.outcome}; classified {classification.category}: "
                f"{classification.signal}{suffix}",
                policy.redaction,
            )
            return _failure(
                ReplayStage.STEP,
                message,
                steps=steps_executed,
                step_id=step.step_id,
                category=classification.category,
            )

        steps_executed += 1
        if step.action_type is ActionType.EXTRACT and step.output_key:
            outputs[step.output_key] = outcome.extracted

    # 3. The checkpoint gates success: no verified state, no success.
    passed, message = check_checkpoint(driver, artifact.checkpoint)
    if not passed:
        classification = _classify(None)
        detailed = redact_text(
            f"{message}; classified {classification.category}: {classification.signal}",
            policy.redaction,
        )
        return _failure(
            ReplayStage.CHECKPOINT,
            detailed,
            steps=steps_executed,
            step_id=steps_executed,
            category=classification.category,
        )

    # 4. Outputs must satisfy output_schema before we hand them back.
    problems = _validate_outputs(artifact, outputs)
    if problems:
        return _failure(ReplayStage.OUTPUT_VALIDATION, "; ".join(problems), steps=steps_executed)

    return _finish(ReplayStatus.SUCCESS, steps_executed=steps_executed, outputs=outputs)
