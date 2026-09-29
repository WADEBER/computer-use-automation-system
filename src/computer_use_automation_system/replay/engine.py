"""Deterministic replay engine (spec Phase 6): executes a typed artifact
step by step with NO LLM anywhere in this module.

Every action passes the Phase 4 policy (`enforce`) before reaching the
driver, the checkpoint gates success, and outputs are validated against
`output_schema`. Failures return a typed `ReplayResult`, never a raw
exception. With an injected `Operator` (Phase 8) the run pauses instead of
dying on the four closed handoff triggers, transfers control of the SAME
live session, applies the operator decision and records the intervention.
"""

import time
from collections.abc import Callable, Mapping

from computer_use_automation_system.artifact.models import ActionType, Artifact, Step
from computer_use_automation_system.discovery.act import BrowserDriver, perform
from computer_use_automation_system.discovery.models import LLMAction, ObservedElement
from computer_use_automation_system.replay.checkpoint import check_checkpoint
from computer_use_automation_system.replay.handoff import Operator
from computer_use_automation_system.replay.inputs import (
    matches_type,
    referenced_input_keys,
    resolve_value,
    validate_inputs,
)
from computer_use_automation_system.replay.models import (
    ControlState,
    DecisionRecord,
    FailureCategory,
    HandoffDecision,
    HandoffRecord,
    HandoffRequest,
    HandoffTrigger,
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
from computer_use_automation_system.safety.policy import PolicyViolation, enforce, evaluate
from computer_use_automation_system.safety.redaction import redact_mapping, redact_text


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
    operator: Operator | None = None,
) -> ReplayResult:
    """Replay `artifact` with `inputs` against `driver`, enforcing `policy`.

    Returns a typed `ReplayResult` for every outcome (spec HU-1..HU-4);
    driver/policy/taxonomy are injected so CI never needs Chrome or a network.
    `taxonomy=None` loads `config/taxonomy.json` (same pattern as policy).
    `operator=None` keeps the Phase 6/7 behavior bit for bit; an injected
    operator pauses on the four handoff triggers over the same session.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()
    started = clock()
    decisions: list[DecisionRecord] = []
    control: ControlState = "automation"
    handoff_records: list[HandoffRecord] = []
    handed_off_steps: set[int] = set()
    checkpoint_handed_off = False
    finished_by_operator = False
    approved_for_step = False

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
            handoff=handoff_records,
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

    def _snapshot() -> list[dict[str, object]]:
        """Redacted DOM snapshot; the engine only observes while it owns control."""
        if control == "human":
            raise AssertionError("driver touched while human has control")
        raw: list[dict[str, object]] = redact_mapping(driver.observe_raw(), policy.redaction)
        return raw

    def _screenshot() -> str | None:
        """Best-effort evidence image: `None` when the driver exposes none (CI)."""
        try:
            shot = getattr(driver, "screenshot_b64", None)
        except Exception:
            return None
        return shot if isinstance(shot, str) else None

    def _pause(
        op: Operator,
        trigger: HandoffTrigger,
        *,
        stage: ReplayStage,
        step_id: int | None,
        action: ActionType | None,
        reason: str,
    ) -> HandoffDecision:
        """Freeze the run on the live session, block on the operator answer
        (the wait is the block, never a sleep) and append the intervention
        record that keeps the control cycle as evidence for Phase 9."""
        nonlocal control, checkpoint_handed_off
        if stage in (ReplayStage.STEP, ReplayStage.POLICY):
            if step_id is not None:
                handed_off_steps.add(step_id)
        else:
            checkpoint_handed_off = True
        request = HandoffRequest(
            trigger=trigger,
            stage=stage,
            step_id=step_id,
            action=action,
            reason=redact_text(reason, policy.redaction),
            capability=f"{artifact.capability_id} v{artifact.version}",
            description=redact_text(artifact.description, policy.redaction),
            snapshot=_snapshot(),
            screenshot=_screenshot(),
        )
        control = "human"
        try:
            response = op.intervene(request)
        finally:
            control = "automation"
        handoff_records.append(
            HandoffRecord(
                index=len(handoff_records),
                request=request,
                decision=response.decision,
                note=(
                    redact_text(response.note, policy.redaction)
                    if response.note is not None
                    else None
                ),
                resumed_snapshot=None if response.decision == "abort" else _snapshot(),
            )
        )
        return response.decision

    def _dismiss(locator, step: Step) -> HandoffDecision | None:
        """Dismiss a known dialog. Every attempt goes through `enforce()`:
        a refused verdict records the decision and skips the click, while a
        `confirm` verdict pauses for the injected operator (needs_approval)
        and a resume retries the click approved for this step. Returns
        finish/abort for the caller to apply; None means handled or skipped
        (a `block` never escalates)."""
        nonlocal approved_for_step
        while True:
            url = driver.current_url()
            try:
                decision = enforce(
                    policy, ActionType.CLICK, url, approved=approved or approved_for_step
                )
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
                if (
                    decision.decision is DecisionKind.CONFIRM
                    and operator is not None
                    and step.step_id not in handed_off_steps
                ):
                    answer = _pause(
                        operator,
                        "needs_approval",
                        stage=ReplayStage.POLICY,
                        step_id=step.step_id,
                        action=ActionType.CLICK,
                        reason=decision.reason,
                    )
                    if answer == "resume":
                        approved_for_step = True
                        continue
                    return answer
                return None
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
            return None

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
                budget_message = "replay time budget exceeded"
                if operator is not None and step.step_id not in handed_off_steps:
                    answer = _pause(
                        operator,
                        "hard_failure",
                        stage=ReplayStage.STEP,
                        step_id=step.step_id,
                        action=step.action_type,
                        reason=budget_message,
                    )
                    if answer == "abort":
                        return _failure(
                            ReplayStage.STEP,
                            budget_message,
                            steps=steps_executed,
                            step_id=step.step_id,
                            category="hard",
                        )
                    if answer == "finish":
                        finished_by_operator = True
                        break
                else:
                    return _failure(
                        ReplayStage.STEP,
                        budget_message,
                        steps=steps_executed,
                        step_id=step.step_id,
                        category="hard",
                    )

        approved_for_step = False
        resolved = resolve_value(step.value, inputs)
        attempts = 0
        while True:
            target_url = driver.current_url()
            if step.action_type is ActionType.NAVIGATE and resolved:
                target_url = resolved

            # Risky-step pre-check: a `confirm` verdict detected BEFORE the
            # action executes pauses with trigger "risky_step" (Phase 8).
            if (
                operator is not None
                and attempts == 0
                and not approved
                and not approved_for_step
                and step.step_id not in handed_off_steps
            ):
                verdict = evaluate(policy, step.action_type, target_url)
                if verdict.decision is DecisionKind.CONFIRM:
                    answer = _pause(
                        operator,
                        "risky_step",
                        stage=ReplayStage.POLICY,
                        step_id=step.step_id,
                        action=step.action_type,
                        reason=verdict.reason,
                    )
                    if answer == "abort":
                        return _failure(
                            ReplayStage.POLICY,
                            verdict.reason,
                            steps=steps_executed,
                            step_id=step.step_id,
                            policy_kind="needs_approval",
                        )
                    if answer == "finish":
                        finished_by_operator = True
                        break
                    approved_for_step = True

            try:
                decision = enforce(
                    policy,
                    step.action_type,
                    target_url,
                    approved=approved or approved_for_step,
                )
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
                if (
                    operator is not None
                    and decision.decision is DecisionKind.CONFIRM
                    and step.step_id not in handed_off_steps
                ):
                    answer = _pause(
                        operator,
                        "needs_approval",
                        stage=ReplayStage.POLICY,
                        step_id=step.step_id,
                        action=step.action_type,
                        reason=decision.reason,
                    )
                    if answer == "abort":
                        return _failure(
                            ReplayStage.POLICY,
                            decision.reason,
                            steps=steps_executed,
                            step_id=step.step_id,
                            policy_kind="needs_approval",
                        )
                    if answer == "finish":
                        finished_by_operator = True
                        break
                    approved_for_step = True
                    continue
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
            attempts += 1
            outcome = perform(driver, _build_action(step, resolved), element)
            if outcome.outcome == "ok":
                break

            classification = _classify(outcome.outcome)
            if (
                classification.category == "recoverable"
                and attempts < taxonomy.max_recoverable_attempts
            ):
                if classification.dismiss_locator is not None:
                    dismissed = _dismiss(classification.dismiss_locator, step)
                    if dismissed == "finish":
                        finished_by_operator = True
                        break
                    if dismissed == "abort":
                        return _failure(
                            ReplayStage.POLICY,
                            handoff_records[-1].request.reason,
                            steps=steps_executed,
                            step_id=step.step_id,
                            policy_kind="needs_approval",
                        )
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
            if operator is not None and step.step_id not in handed_off_steps:
                trigger: HandoffTrigger | None = None
                if classification.category == "recoverable":
                    trigger = "retries_exhausted"
                elif classification.category == "hard":
                    trigger = "hard_failure"
                if trigger is not None:
                    answer = _pause(
                        operator,
                        trigger,
                        stage=ReplayStage.STEP,
                        step_id=step.step_id,
                        action=step.action_type,
                        reason=message,
                    )
                    if answer == "abort":
                        return _failure(
                            ReplayStage.STEP,
                            message,
                            steps=steps_executed,
                            step_id=step.step_id,
                            category=classification.category,
                        )
                    if answer == "finish":
                        finished_by_operator = True
                        break
                    attempts = 0
                    continue
            return _failure(
                ReplayStage.STEP,
                message,
                steps=steps_executed,
                step_id=step.step_id,
                category=classification.category,
            )

        if finished_by_operator:
            break
        steps_executed += 1
        if step.action_type is ActionType.EXTRACT and step.output_key:
            outputs[step.output_key] = outcome.extracted

    # 3. The checkpoint gates success: no verified state, no success.
    checkpoint_id = steps_executed if steps_executed > 0 else 1
    while True:
        passed, message = check_checkpoint(driver, artifact.checkpoint)
        if passed:
            break
        classification = _classify(None)
        detailed = redact_text(
            f"{message}; classified {classification.category}: {classification.signal}",
            policy.redaction,
        )
        if operator is not None and not checkpoint_handed_off and classification.category == "hard":
            answer = _pause(
                operator,
                "hard_failure",
                stage=ReplayStage.CHECKPOINT,
                step_id=checkpoint_id,
                action=None,
                reason=detailed,
            )
            if answer == "abort":
                return _failure(
                    ReplayStage.CHECKPOINT,
                    detailed,
                    steps=steps_executed,
                    step_id=checkpoint_id,
                    category=classification.category,
                )
            if answer == "finish":
                finished_by_operator = True
            continue
        return _failure(
            ReplayStage.CHECKPOINT,
            detailed,
            steps=steps_executed,
            step_id=checkpoint_id,
            category=classification.category,
        )

    # 4. Outputs must satisfy output_schema before we hand them back; a
    # `finish` decision skips them because the operator accepted the state.
    if not finished_by_operator:
        problems = _validate_outputs(artifact, outputs)
        if problems:
            return _failure(
                ReplayStage.OUTPUT_VALIDATION, "; ".join(problems), steps=steps_executed
            )

    return _finish(ReplayStatus.SUCCESS, steps_executed=steps_executed, outputs=outputs)
