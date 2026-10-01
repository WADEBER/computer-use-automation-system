# Security Audit — computer-use-automation-system (Phase 9 Release Gate)

**Date:** 2026-10-01
**Auditor:** audit-code skill (Claude Code)
**Scope:** Full release surface with focus on the Phase 9 working tree (uncommitted changes on top of `a73b5f1`): `replay/logging_runner.py` (new), `replay/engine.py` (events callback, fix-4 `_classify`), `cli.py` (`--log-out`, `--total-timeout-ms`), `discovery/selenium_driver.py` (fix-1 observe fields, `page_text`), `discovery/observe.py` (fix-3), `discovery/logging_runner.py` (fix-2), `.gitignore`, `evidence/` deliverables, `README.md`, `REPORT.md`. Release gate also re-checks entry points and dependency state.
**Threat model:** Local developer CLI + localhost-only demo target app (Flask on 127.0.0.1). No remote users, no internet-facing surface, no real customer data (synthetic seed data only). LLM is local (Ollama `qwen2.5-coder:7b`); DOM text observed from the local target app can carry prompt-injection style content and is treated as untrusted input. Compliance target: take-home review hygiene (no secrets, no PII in repo/evidence).
**Stack:** Python 3.11, Flask 3.1, Selenium 4.49, Pydantic 2.13, pytest 9.1, uv.

---

## 1. Executive Summary

No critical or high-severity findings were identified under the reviewed scope. The Phase 9 surface (structured replay logging, page-text failure classification, live evidence files, and documentation) follows the write-time redaction discipline established in Phase 4 and introduces no new remote or executable attack surface: every new input path is a local CLI flag or a constant in-process script. Automated scanning (bandit, ruff S-rules, pip-audit) is clean, and no secrets or raw PII appear in the repository or in the evidence deliverables. Remaining items are defense-in-depth recommendations (pre-commit secret scanning) and accepted design observations (arbitrary local log paths, timestamp-free logs).

**Findings by severity:**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 0 |
| Medium   | 0 |
| Low      | 0 |
| Info     | 3 |

---

## 2. Top Priorities

No Critical/High findings — no release blockers. Ordered follow-ups:

1. **[DEF-001] Pre-commit secret scanning** — CI scans for secrets, but nothing stops a developer committing one locally first. → §4
2. **[OBS-001] Local log paths are unconstrained** — `--log-out` writes wherever the invoking user points it (same contract as `StepLogger`); harmless for a local CLI, worth a containment check if the CLI ever grows a service mode. → §3.1
3. **[OBS-003] Timestamp-free logs** — determinism decision, but it limits forensics of live runs. → §3.3

---

## 3. Findings

### 3.1 [OBS-001] Log writers accept arbitrary local paths — **Info**

- **File:** [src/computer_use_automation_system/replay/logging_runner.py:21](src/computer_use_automation_system/replay/logging_runner.py#L21), [src/computer_use_automation_system/discovery/logging_runner.py:30](src/computer_use_automation_system/discovery/logging_runner.py#L30)
- **CWE:** CWE-22 family (path control), not exploitable as-is
- **OWASP:** A01 — Broken Access Control (theoretical only)
- **Confidence:** Confirmed (behaviour), Not-exploitable (threat model)
- **Tool:** manual review

**Description**

`ReplayLogger.__init__` stores `Path(log_path)` and creates parent directories on write. The path comes from the `--log-out` CLI flag with no base-directory containment check. This mirrors `StepLogger` exactly (the pattern approved in the Phase 4 audit), and `safe_write_text` containment (SEC-003) applies to artifact writes, not these loggers.

**Vulnerable code**

```python
# src/computer_use_automation_system/replay/logging_runner.py:21
def __init__(self, log_path: str | Path, redaction: RedactionConfig) -> None:
    self.log_path = Path(log_path)
```

**Impact**

Only the user who launches the CLI can choose the destination — the same power their shell already has. There is no remote or cross-user vector in this threat model (local CLI, single user). No data is read back from the path; content written is redacted JSON.

**Reproduction / PoC sketch** (do NOT run)

> `replay --artifact a.json --input q=x --log-out ../../anywhere.log` creates the file outside the repo. This is user-intended behaviour (like shell redirection), not an attack.

**Remediation**

Accept as designed for the local CLI. If the tool ever runs as a service or receives paths from a remote caller, route all log writes through `safe_write_text(..., base_dir=...)` (the containment helper already used for artifacts).

**References**
- [CWE-22](https://cwe.mitre.org/data/definitions/22.html)
- Phase 4 audit SEC-003 (write-time path containment for artifacts)

---

### 3.2 [OBS-002] Page text flows into failure messages — **Info**

- **File:** [src/computer_use_automation_system/replay/engine.py:186](src/computer_use_automation_system/replay/engine.py#L186), [src/computer_use_automation_system/replay/taxonomy.py:109](src/computer_use_automation_system/replay/taxonomy.py#L109)
- **CWE:** CWE-209 / CWE-532 family (information exposure) — mitigated
- **OWASP:** A02 — Cryptographic Failures (sensitive data exposure) — mitigated
- **Confidence:** Confirmed
- **Tool:** manual review (fix-4 review)

**Description**

fix-4 appends the bounded `page_text()` output (visible body text, <= 20000 chars) to the elements passed to `classify_failure` so static messages like "No records found" are classifiable. The design keeps raw page text out of persisted output: `Classification.signal` carries only the matched pattern fragment (explicitly documented "never raw page text, so it carries no PII"), and every log line still passes `redact_mapping` at write time. The JavaScript is a constant string with no interpolation of observed data.

**Impact**

None under current design: error messages and logs expose the pattern name only (e.g. `page pattern: No records found`), redaction remains the last line of defense.

**Remediation**

None required. Keep the invariant: never widen `signal` to include surrounding page text; add a regression test if `Classification` ever grows a "context" field.

**References**
- [CWE-532](https://cwe.mitre.org/data/definitions/532.html)

---

### 3.3 [OBS-003] Timestamp-free evidence logs — **Info**

- **File:** [src/computer_use_automation_system/discovery/logging_runner.py:42](src/computer_use_automation_system/discovery/logging_runner.py#L42), [src/computer_use_automation_system/replay/logging_runner.py:25](src/computer_use_automation_system/replay/logging_runner.py#L25)
- **CWE:** CWE-778 (Insufficient Logging) — accepted trade-off
- **OWASP:** A09 — Security Logging and Monitoring Failures
- **Confidence:** Confirmed
- **Tool:** manual review

**Description**

Neither logger writes timestamps; this is a deliberate determinism/testability decision recorded in `REPORT.md` (Cuts) and in the Phase 9 plan. For a local take-home demo it is fine; for production it would complicate incident timelines.

**Impact**

Live-run logs cannot be correlated with wall-clock events. No confidentiality or integrity impact.

**Remediation**

If the system graduates beyond a demo: add an optional `--timestamps` flag (default off keeps tests deterministic).

**References**
- [CWE-778](https://cwe.mitre.org/data/definitions/778.html)

---

## 4. Defense-in-Depth Recommendations

- **[DEF-001] Add pre-commit secret scanning.** Install `gitleaks` or `detect-secrets` as a pre-commit hook; CI already runs `detect-secrets` (`.github/workflows/security.yml`), but a local hook closes the "commit first, CI later" window. No `.secrets.baseline` exists yet, so creating one during the first run is expected.
- **[DEF-002] Keep dependency scanning in CI.** `pip-audit` (run manually for this audit: 0 known vulnerabilities) is wired in `security.yml`; keep failing the build on High+ CVEs as it grows.

---

## 5. Coverage

### What was reviewed
- Phase 9 working-tree diff on top of `a73b5f1`: all modified and new source files listed in Scope, full read.
- Entry points re-checked: CLI argument parsing (`cli.py` `build_parser`/`main`), Flask routes entry (`proxy_app/app.py` `resolve_config`/`main`), console script `computer-use-automation-system`.
- `proxy_app` debug gating: `PROXY_APP_DEBUG` defaults to off; `app.run` binds 127.0.0.1 (localhost-only).
- `evidence/` deliverables: valid JSON/JSONL, English, synthetic data only, no secret-shaped strings (mechanical sweep + manual read of the exception log).
- `.gitignore` negations: exactly four deliverable paths, ordered after `evidence/*` and `*.log`.
- Dependency versions checked against `pip-audit` database as of 2026-10-01 (0 CVEs).
- Prior audit reports (`docs/security/audit-2026-09-25-fase-4.md`, `-fase-5.md`, `audit-2026-09-28-fase-7.md`, `audit-2026-09-29-fase-8.md`) consulted so already-fixed findings (SEC-801..803) are not re-counted; SEC-804/805 remain in the backlog of the Phase 8 report and are unchanged by this diff.

### What was NOT reviewed (and why)
- `tests/` — spot-checked only (no production code paths execute there).
- `docs/` and plan/spec markdown — documentation only, except the security reports referenced above.
- Runtime OS/network configuration (firewall, OneDrive sync, endpoint AV) — outside code scope.
- Prompt-injection resistance of `qwen2.5-coder:7b` at model level — covered by design in the Phase 5 audit (policy perimeter + HITL); not re-tested here.

### Tools run
| Tool | Status | Findings |
|------|--------|----------|
| bandit (`uvx bandit -r src/ -ll`) | Run | 0 |
| ruff `--select=S src/` | Run | 0 |
| pip-audit (`uvx pip-audit --desc`) | Run | 0 known vulnerabilities |
| gitleaks / detect-secrets (local) | Not installed | Recommended (DEF-001); CI workflow exists |
| semgrep | Not installed | Recommended for future runs |
| manual review | Completed | 0 critical/high, 3 info observations |

### Methodology
- Phase 1 — Scope & Context: release scope taken from `git status` of the Phase 9 working tree plus entry points; threat model = local CLI + localhost demo.
- Phase 2 — Automated Scanning: bandit, ruff S-rules, pip-audit (all green); `tests/` S101 assert noise excluded by scanning `src/` only.
- Phase 3 — Manual Review: `audit-code/references/python-security.md` and `report-template.md` read end-to-end; quick-scan regex cheat sheet applied to `src/` (0 hits: no eval/exec/pickle/yaml.load/shell=True/md5/random-token patterns); write paths of both loggers, fix-4 classification flow, observe script, and `.gitignore` verified by reading the code.
- Phase 4 — Exploit Reasoning: each observation reasoned against the threat model (local single-user CLI; no remote input path exists in Phase 9 surface).
- Phase 5 — Report: this document.

### Caveats
- This audit reflects the working tree at branch `Liebana`, HEAD `a73b5f1` plus uncommitted Phase 9 changes; a subsequent commit changes the reviewed state.
- Absence of findings is not proof of absence: semgrep and secret scanners were not run locally (not installed; no installs performed without asking per skill rules).
- Business-logic correctness of disbursement flows is exercised by the synthetic proxy app only.

---

## 6. Next Steps

1. No Critical/High to triage — proceed to `/9-documentar`.
2. Consider DEF-001 (pre-commit secret scanning) as repository hygiene, not a release blocker.
3. Re-audit on the next phase that touches auth, crypto, subprocess, or external input (per `CLAUDE.md` audit policy).

---

*Report generated by the `audit-code` skill. To re-run: invoke the skill on the same scope and compare reports.*
