"""The discovery loop: observe -> goal check -> decide -> enforce -> act -> log.

Every dependency (LLM, driver, policy, logger, clock) is injected so CI runs
purely on fakes: no Ollama, no Chrome, no network. The Phase 4 policy is
enforced before every action; a `block`/`confirm` verdict ends the run
without ever touching the driver.
"""

import time
from collections.abc import Callable
from pathlib import Path

from computer_use_automation_system.artifact.models import ActionType, Artifact
from computer_use_automation_system.discovery.act import BrowserDriver, perform
from computer_use_automation_system.discovery.artifact_builder import StepSource, build_artifact
from computer_use_automation_system.discovery.decide import HistoryItem, LLMClient, decide
from computer_use_automation_system.discovery.goal import check_goal
from computer_use_automation_system.discovery.logging_runner import StepLogger
from computer_use_automation_system.discovery.models import (
    DiscoveryConfig,
    DiscoveryResult,
    LLMAction,
    PolicyDecisionRecord,
    RunStatus,
    StepRecord,
)
from computer_use_automation_system.discovery.observe import build_snapshot
from computer_use_automation_system.safety.models import DecisionKind, PolicyConfig
from computer_use_automation_system.safety.policy import PolicyViolation, enforce
from computer_use_automation_system.safety.redaction import redact_text, safe_write_text

_VALUE_PREVIEW_MAX = 80
_REASON_MAX = 200


def _action_url(driver: BrowserDriver, action: LLMAction) -> str:
    if action.action is ActionType.NAVIGATE:
        return action.value or ""
    return driver.current_url()


def _make_record(
    config: DiscoveryConfig,
    policy: PolicyConfig,
    *,
    step_index: int,
    action: LLMAction,
    outcome: str,
    policy_record: PolicyDecisionRecord | None,
    snapshot_hash: str,
    elapsed_ms: int,
) -> StepRecord:
    # Navigate values are destinations that get compiled into the artifact:
    # truncating them would bake a broken URL, so they are only redacted.
    if action.value is None:
        preview = None
    elif action.action is ActionType.NAVIGATE:
        preview = action.value
    else:
        preview = action.value[:_VALUE_PREVIEW_MAX]
    return StepRecord(
        step_index=step_index,
        action=action.action,
        element_ref=action.element_ref,
        value_preview=redact_text(preview, policy.redaction) if preview is not None else None,
        reason=redact_text(action.reason[:_REASON_MAX], policy.redaction),
        policy_decision=policy_record,
        outcome=outcome,
        snapshot_hash=snapshot_hash,
        elapsed_ms=max(0, elapsed_ms),
        max_steps=config.max_steps,
    )


def run_discovery(
    config: DiscoveryConfig,
    driver: BrowserDriver,
    client: LLMClient,
    policy: PolicyConfig,
    *,
    logger: StepLogger | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> DiscoveryResult:
    """Run one discovery loop until a stopping condition fires.

    Statuses: `goal_reached` (artifact emitted), `blocked` / `needs_approval`
    (Phase 4 verdict, action never executed), `dead_end` (repeated snapshot
    hash or goal met with nothing executed), `llm_error` (fail closed),
    `max_steps`, `timeout` (global budget).
    """
    step_logger = logger or StepLogger(config.log_out, policy.redaction)
    started = clock()
    status = RunStatus.MAX_STEPS
    records: list[StepRecord] = []
    sources: list[StepSource] = []
    history: list[HistoryItem] = []
    artifact: Artifact | None = None
    last_digest = ""
    streak = 0

    while True:
        if (clock() - started) * 1000 > config.total_timeout_ms:
            status = RunStatus.TIMEOUT
            break

        snapshot = build_snapshot(driver.observe_raw(), config.max_snapshot_chars)
        if snapshot.digest == last_digest:
            streak += 1
        else:
            streak, last_digest = 1, snapshot.digest
        if streak >= config.repeat_threshold:
            status = RunStatus.DEAD_END
            break

        goal_outcome = check_goal(client, config.goal, snapshot, config.max_llm_retries)
        if goal_outcome.error is not None:
            status = RunStatus.LLM_ERROR
            break
        if goal_outcome.verdict is not None and goal_outcome.verdict.goal_reached:
            successful = [source for source in sources if source.record.outcome == "ok"]
            if successful:
                artifact = build_artifact(
                    config.goal,
                    config.entry_url,
                    successful,
                    final_url=driver.current_url(),
                )
                status = RunStatus.GOAL_REACHED
            else:
                status = RunStatus.DEAD_END
            break

        if len(records) >= config.max_steps:
            status = RunStatus.MAX_STEPS
            break

        decision_outcome = decide(client, config.goal, snapshot, history, config.max_llm_retries)
        if decision_outcome.action is None:
            status = RunStatus.LLM_ERROR
            break
        action = decision_outcome.action

        step_started = clock()
        step_index = len(records) + 1
        url = _action_url(driver, action)

        try:
            verdict = enforce(policy, action.action, url)
            policy_record = PolicyDecisionRecord(decision=verdict.decision, reason=verdict.reason)
        except PolicyViolation as exc:
            blocked_kind = (
                RunStatus.BLOCKED
                if exc.decision.decision is DecisionKind.BLOCK
                else RunStatus.NEEDS_APPROVAL
            )
            outcome_label = (
                "blocked" if exc.decision.decision is DecisionKind.BLOCK else "needs_approval"
            )
            record = _make_record(
                config,
                policy,
                step_index=step_index,
                action=action,
                outcome=outcome_label,
                policy_record=PolicyDecisionRecord(
                    decision=exc.decision.decision, reason=exc.decision.reason
                ),
                snapshot_hash=snapshot.digest,
                elapsed_ms=int((clock() - step_started) * 1000),
            )
            records.append(record)
            step_logger.write_step(record)
            status = blocked_kind
            break

        element = next((item for item in snapshot.elements if item.ref == action.element_ref), None)
        action_outcome = perform(driver, action, element)
        record = _make_record(
            config,
            policy,
            step_index=step_index,
            action=action,
            outcome=action_outcome.outcome,
            policy_record=policy_record,
            snapshot_hash=snapshot.digest,
            elapsed_ms=int((clock() - step_started) * 1000),
        )
        records.append(record)
        sources.append(StepSource(record=record, element=element))
        history.append(
            HistoryItem(
                action=action.action.value,
                reason=action.reason,
                outcome=action_outcome.outcome,
            )
        )
        step_logger.write_step(record)

    artifact_path: Path | None = None
    if artifact is not None:
        safe_write_text(
            config.artifact_out,
            artifact.model_dump_json(indent=2),
            policy.redaction,
            base_dir=config.out_root,
        )
        artifact_path = Path(config.artifact_out)

    step_logger.write_summary(status, steps=len(records))
    return DiscoveryResult(
        status=status,
        steps=records,
        artifact=artifact,
        artifact_path=artifact_path,
        log_path=step_logger.log_path,
    )
