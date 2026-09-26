"""Safety policy loading and evaluation (Phase 4).

``load_policy`` reads ``config/policy.json`` (the single source of truth);
``evaluate``/``enforce`` apply the perimeter and the classification rules
without any LLM involvement, so discovery and replay share one guardrail.
"""

import posixpath
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import unquote, urlsplit

from computer_use_automation_system.artifact.models import ActionType
from computer_use_automation_system.safety.models import (
    Decision,
    DecisionKind,
    PolicyConfig,
)

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "policy.json"


def load_policy(path: str | Path | None = None) -> PolicyConfig:
    """Load and strictly validate the policy file.

    Raises ``pydantic.ValidationError`` naming the offending field.
    """
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    return PolicyConfig.model_validate_json(policy_path.read_text(encoding="utf-8"))


def _origin_allowed(url: str, allowed_origins: list[str]) -> bool:
    """Fail-closed origin check using parsed URL components.

    Scheme-relative URLs (``//host/path``) are rejected outright, relative
    paths stay same-origin, and full URLs must match an allowed origin
    exactly (scheme + netloc), never by string prefix.
    """
    if url.startswith("//"):
        return False
    parts = urlsplit(url)
    if not parts.scheme and not parts.netloc:
        return True
    if not parts.scheme or not parts.netloc:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    return origin in {entry.rstrip("/") for entry in allowed_origins}


def _normalized_path(url: str) -> str:
    """Decode and normalize the URL path so the allowlist sees the path the
    browser will actually request (collapses ``..`` and ``%2e%2e``)."""
    raw = unquote(urlsplit(url).path or "/")
    path = posixpath.normpath(raw)
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _route_allowed(path: str, allowed_routes: list[str]) -> bool:
    for route in allowed_routes:
        if path == route:
            return True
        if route != "/" and path.startswith(route + "/"):
            return True
    return False


def evaluate(policy: PolicyConfig, action_type: ActionType | str, url: str) -> Decision:
    """Return the verdict for one action: perimeter first (block cannot be
    overridden by later rules), then rules, defaulting to allow."""
    action = ActionType(action_type)
    path = _normalized_path(url)

    if action not in policy.allowed_action_types:
        return Decision(
            decision=DecisionKind.BLOCK,
            reason=f"action type '{action.value}' is not in allowed_action_types",
        )
    if not _origin_allowed(url, policy.allowed_origins):
        return Decision(
            decision=DecisionKind.BLOCK,
            reason=f"origin not in allowed_origins: {url}",
        )
    if not _route_allowed(path, policy.allowed_routes):
        return Decision(
            decision=DecisionKind.BLOCK,
            reason=f"route '{path}' is not in allowed_routes",
        )

    for rule in policy.rules:
        if rule.match_action_type is not None and rule.match_action_type is not action:
            continue
        if rule.match_url_pattern is not None and not fnmatch(url, rule.match_url_pattern):
            continue
        return Decision(
            decision=rule.decision,
            reason=rule.reason,
            matched_rule=rule.reason,
        )

    return Decision(decision=DecisionKind.ALLOW, reason="inside perimeter, no rule matched")


class PolicyViolation(Exception):
    """Raised when ``enforce`` refuses to run an action."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(f"policy {decision.decision.value}: {decision.reason}")
        self.decision = decision


def enforce(
    policy: PolicyConfig,
    action_type: ActionType | str,
    url: str,
    *,
    approved: bool = False,
) -> Decision:
    """Evaluate and refuse anything the policy does not permit.

    - ``block``: always raises.
    - ``confirm``: raises unless ``approved=True`` (human gate).
    - ``flag`` / ``allow``: returns the decision (flag stays auditable).
    """
    decision = evaluate(policy, action_type, url)
    if decision.decision is DecisionKind.BLOCK:
        raise PolicyViolation(decision)
    if decision.decision is DecisionKind.CONFIRM and not approved:
        raise PolicyViolation(decision)
    return decision
