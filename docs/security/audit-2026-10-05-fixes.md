# Security Audit - computer-use-automation-system (Backlog-Fix Delta)

**Date:** 2026-10-05
**Auditor:** audit-code skill (opencode / mimo)
**Scope:** Working tree on top of `a9aeeb2` (uncommitted changes): `src/computer_use_automation_system/cli.py`, `discovery/models.py`, `discovery/runner.py`, `discovery/selenium_driver.py`, `replay/models.py`, `replay/engine.py`, `.github/workflows/security.yml`, `.gitignore`, new `docs/security/README.md`, docs consistency edits (`README.md`, `REPORT.md`, `CLAUDE.md`, `docs/plans/0_plan_maestro.md`) and the four touched test files. This is a delta audit over the remediation of the phase backlog (SEC-503, SEC-505, SEC-805, DEF-803, OBS-801, CI dependency gate).
**Threat model:** Local developer CLI + localhost-only demo target app (Flask on 127.0.0.1). No remote users, no internet-facing surface, no real customer data (synthetic seed data only). LLM is local (Ollama `qwen2.5-coder:7b`); DOM text observed from the local target app is untrusted input. CI (GitHub Actions on `Liebana`) is the automated gate before merge. Compliance target: take-home review hygiene (no secrets, no PII in repo/evidence).
**Stack:** Python 3.11, Flask 3.1, Selenium 4.49, Pydantic 2.13, pytest 9.1, uv, GitHub Actions.

---

## 1. Executive Summary

No critical, high or medium findings under the reviewed scope. The four backlog remediations landed with regression tests and fail closed: URL-scheme restriction in the driver, write containment for `--artifact-out`, size caps on the handoff package, and narrowed best-effort `except` clauses. Dependency scanning in CI now audits the `uv.lock` export instead of the runner environment, which fixes the failing security gate without weakening it. One Low finding is new and pre-existing in nature: the secret-scanning CI job uses `detect-secrets` in a mode that generates a baseline and exits 0, so it never blocks a push containing a secret.

**Findings by severity:**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 0 |
| Medium   | 0 |
| Low      | 1 |
| Info     | 3 |

---

## 2. Top Priorities

1. **[SEC-901] Secret-scanning CI job never fails on findings** - `detect-secrets scan` writes a baseline to stdout and exits 0, so secrets reaching the repository are not blocked by CI. -> section 3.1
2. **[OBS-901] Library `run_discovery` writes stay unconstrained without `out_root`** - the CLI is contained, but direct API callers keep the pre-fix contract. -> section 3.2
3. **[DEF-901] Pin the `pip-audit` version used by CI** - `uvx pip-audit` resolves the latest release on every run. -> section 4

---

## 3. Findings

### 3.1 [SEC-901] Secret-scanning CI job exits 0 regardless of findings - **Low**

- **File:** [.github/workflows/security.yml:86](.github/workflows/security.yml#L86)
- **CWE:** CWE-693 (Protection Mechanism Failure)
- **OWASP:** A09 - Security Logging and Monitoring Failures (gate that cannot fail)
- **Confidence:** Confirmed (tool CLI semantics verified locally with `detect-secrets --help`: only the `scan` and `audit` subcommands exist, and `scan` is documented as "Creates a baseline by scanning a repository for secrets")
- **Tool:** manual review of the workflow

**Description**

The `python-secrets` job runs `detect-secrets scan --all-files` when no `.secrets.baseline` exists. `detect-secrets scan` is a baseline generator: it prints JSON to stdout and returns exit code 0 no matter how many secrets it finds. The branch has no `.secrets.baseline`, so the job is a no-op gate. If a baseline were added later, the job would switch to `detect-secrets audit .secrets.baseline`, which validates the *stored* baseline rather than re-scanning the repository, so newly added secrets would still go unnoticed.

**Vulnerable code**

```yaml
# .github/workflows/security.yml:100
- name: Scan for secrets
  run: |
    if [ -f .secrets.baseline ]; then
      detect-secrets audit .secrets.baseline
    else
      detect-secrets scan --all-files
    fi
```

**Impact**

A credential committed to a branch on which this workflow runs is not blocked by CI. The other mitigations still hold (`.env` gitignored, manual regex sweeps in past audits found nothing, `pip-audit`/bandit unaffected), so the exposure is the loss of the automated backstop, not a present leak.

**Reproduction / PoC sketch** (do NOT run)

> Add a file containing `AWS_SECRET_ACCESS_KEY = "<placeholder>"` and push. The `python-secrets` job still reports success, because `detect-secrets scan` only emits a baseline blob.

**Remediation**

Either gate on a fresh scan diffed against a committed baseline, or switch to a tool with a failing exit code:

```yaml
# .github/workflows/security.yml - option A (stay on detect-secrets)
- name: Scan for secrets
  run: |
    detect-secrets scan --all-files > /tmp/new.baseline
    if [ -f .secrets.baseline ]; then
      git diff --no-index --exit-code .secrets.baseline /tmp/new.baseline
    else
      echo "No .secrets.baseline in the repo yet: commit /tmp/new.baseline as one." >&2
      exit 1
    fi
```

Option B: `gitleaks detect --source . --redact --exit-code 1` (fails on any finding). Option C: local pre-commit hook (`detect-secrets-pre-commit` or `gitleaks protect`), tracked as DEF-902.

Implemented variant (see section 8): a fresh scan is compared against the committed baseline at the `(filename, hashed_secret)` level instead of diffing whole baseline files, because the baseline carries a `generated_at` timestamp that makes a raw `git diff` always fail.

**References**
- [CWE-693](https://cwe.mitre.org/data/definitions/693.html)
- detect-secrets CLI reference (scan = baseline generator, no failing gate)
- Carried recommendation DEF-001/DEF-802 in [audit-2026-09-29-fase-8.md](audit-2026-09-29-fase-8.md)

---

### 3.2 [OBS-901] Library `run_discovery` writes unconstrained without `out_root` - **Info**

- **File:** [src/computer_use_automation_system/discovery/models.py:56](src/computer_use_automation_system/discovery/models.py#L56), [src/computer_use_automation_system/discovery/runner.py:205](src/computer_use_automation_system/discovery/runner.py#L205)
- **CWE:** CWE-22 family (path control), not exploitable as-is
- **OWASP:** A01 - Broken Access Control (local trusted caller only)
- **Confidence:** Confirmed (behaviour), Not-exploitable (threat model)
- **Tool:** manual review

**Description**

SEC-505 containment is wired through `DiscoveryConfig.out_root`, which the CLI sets to `Path.cwd()`. The field defaults to `None`, so library callers keep the pre-fix contract: `artifact_out` may point anywhere the process can write. This is a deliberate contract (documented in the field comment) mirroring how `--log-out` and `StepLogger` are treated (release OBS-001).

**Impact**

None under the shipped threat model: the CLI path is contained twice (early check in `_run_discover_command` plus `safe_write_text(base_dir=...)` at write time).

**Remediation**

Accept as designed. If the library ever runs inside a service, default `out_root` to the working directory instead of `None`.

**References**
- [CWE-22](https://cwe.mitre.org/data/definitions/22.html)
- Phase 5 audit SEC-505 ([audit-2026-09-25-fase-5.md](audit-2026-09-25-fase-5.md))

---

### 3.3 [OBS-902] Narrowed capability catch assumes descriptors raise only `AttributeError`/`TypeError` - **Info**

- **File:** [src/computer_use_automation_system/replay/engine.py:218](src/computer_use_automation_system/replay/engine.py#L218)
- **CWE:** CWE-755 (Improper Handling of Exceptional Conditions)
- **OWASP:** A05 - Security Misconfiguration (robustness of best-effort evidence)
- **Confidence:** Possible (latent; no current driver exposes the property)
- **Tool:** manual review

**Description**

`_screenshot` and the `getattr` in `_classify` now catch `(AttributeError, TypeError)` only, per fase-8 DEF-803. Today `SeleniumDriver` exposes no `screenshot_b64` attribute (its `page_text` is a plain method that swallows its own errors), so nothing can raise through `getattr`. If a future driver implements `screenshot_b64` as a property that can raise a Selenium exception during access, that exception now propagates out of `_pause` and aborts the handoff instead of degrading to "no screenshot".

**Impact**

Latent availability issue on the handoff path, not a data-exposure issue.

**Remediation**

When a real driver grows a screenshot property, catch the driver's exception type at the property body (return `None`), not in the engine - the engine's narrow catch is the correct default.

**References**
- fase-8 DEF-803 ([audit-2026-09-29-fase-8.md](audit-2026-09-29-fase-8.md))

---

### 3.4 [OBS-903] Truncation can split a redaction marker - **Info**

- **File:** [src/computer_use_automation_system/replay/engine.py:251](src/computer_use_automation_system/replay/engine.py#L251)
- **CWE:** CWE-117 (log truncation artefact, not injection)
- **OWASP:** A09 - Security Logging and Monitoring Failures (cosmetic)
- **Confidence:** Likely (reachable with a >2000 char reason/note)
- **Tool:** manual review

**Description**

Handoff text is redacted first and then sliced to `MAX_HANDOFF_TEXT` (2000). A `REDACTED_*` marker straddling the boundary is written as a partial token (for example `[REDACTED_CA`).

**Impact**

Cosmetic: truncation happens after redaction, so no unredacted data can be produced by the cut. Evidence consumers matching full markers could miss one occurrence.

**Remediation**

Optional: cut on a boundary that does not lie inside a marker, or append a short `...[truncated]` suffix instead of a hard slice.

**References**
- Phase 8 audit SEC-805 ([audit-2026-09-29-fase-8.md](audit-2026-09-29-fase-8.md))

---

## 4. Defense-in-Depth Recommendations

- **[DEF-901] Pin the `pip-audit` version used by CI.** `uvx pip-audit -r requirements.ci.txt --strict --desc` resolves the newest release on every run; pin with `uvx --from pip-audit==<version> ...` (or a `requirements-dev.txt` entry) so the gate is reproducible and a bad upstream release cannot flip CI. The same applies to `astral-sh/setup-uv@v5`, which - like the other actions in this repo - is referenced by tag rather than commit SHA.
- **[DEF-902] Pre-commit secret scanning** (carry-over from fase-5 DEF-503, fase-8 DEF-802, release DEF-001). CI-side gating is covered by SEC-901's remediation; a local hook closes the "commit first, CI later" window.
- **[DEF-903] Keep the `uv.lock` export as the audited input.** The workflow now audits `uv export --no-hashes --no-emit-project`; re-run the same command locally when changing `pyproject.toml`, so local and CI views of the dependency set stay identical.

---

## 5. Remediation Verified (phase backlog -> this delta)

| ID | Report | Fix in this working tree | Regression test |
|----|--------|--------------------------|-----------------|
| SEC-503 | fase-5 | [selenium_driver.py:155](src/computer_use_automation_system/discovery/selenium_driver.py#L155) rejects non-`http(s)` schemes with `DriverActionError("invalid_value")` before `driver.get()` | `test_navigate_only_accepts_http_schemes` (`tests/test_discovery_selenium_driver.py`) |
| SEC-505 | fase-5 | `DiscoveryConfig.out_root` + CLI `_within()` check ([cli.py:310](src/computer_use_automation_system/cli.py#L310), early exit 2 at [cli.py:350](src/computer_use_automation_system/cli.py#L350)) + `safe_write_text(..., base_dir=config.out_root)` ([runner.py:205](src/computer_use_automation_system/discovery/runner.py#L205)) | `test_artifact_out_outside_the_working_tree_exits_2` (`tests/test_cli_discover.py`), `test_out_root_allows_the_artifact_write_inside_it`, `test_out_root_blocks_the_artifact_write_outside_it` (`tests/test_discovery_runner.py`) |
| SEC-805 | fase-8 | `MAX_SNAPSHOT_ELEMENTS = 100`, `MAX_HANDOFF_TEXT = 2000` model caps ([models.py:101](src/computer_use_automation_system/replay/models.py#L101)) plus truncation at capture in the engine ([engine.py:216](src/computer_use_automation_system/replay/engine.py#L216), [engine.py:251](src/computer_use_automation_system/replay/engine.py#L251)) | `test_pause_package_enforces_text_and_snapshot_caps`, `test_pause_package_is_truncated_at_capture_and_broken_evidence_helpers` (`tests/test_replay_handoff.py`) |
| DEF-803 | fase-8 | `_classify`/`_screenshot` `getattr` catches narrowed to `(AttributeError, TypeError)` ([engine.py:198](src/computer_use_automation_system/replay/engine.py#L198)) | broken-descriptor case inside `test_pause_package_is_truncated_at_capture_and_broken_evidence_helpers` |
| OBS-801 | fase-8 | Consolidated catalog created at [docs/security/README.md](docs/security/README.md) | n/a (documentation) |
| DEF-001 / DEF-501 / DEF-801 | fase-4 / fase-5 / fase-8 | CI dependency gate now runs `uv export` + `uvx pip-audit --strict` over the locked set ([security.yml:63](.github/workflows/security.yml#L63)); locally: 0 known vulnerabilities | n/a (workflow); verified by running the exact CI commands |

Post-fix verification (2026-10-05): 474 tests green; `ruff check src/ tests/` clean; `ruff format --check` clean; `mypy src` clean; `bandit -r src/ -ll` 0 findings; `ruff check --select=S src/` 0 findings; `pip-audit` over the `uv.lock` export: 0 known vulnerabilities.

---

## 6. Coverage

### What was reviewed
- The full diff vs `a9aeeb2` (all six `src/` files, `.github/workflows/security.yml`, `.gitignore`, `docs/security/README.md`) read line by line.
- Entry points re-checked: CLI `discover`/`replay` argument flow, `_run_discover_command` failure ordering (config -> containment -> policy -> run), `replay()` pause path.
- Containment logic: `_within()` uses `Path.resolve()` + `relative_to` on both sides (symlinks normalized, `..` collapsed, fail closed on mismatch).
- Handoff construction: `HandoffRequest`/`HandoffRecord` are built only in `replay/engine.py`, and every string/snapshot is redacted-then-truncated before construction, so the new `max_length` caps cannot turn into an unhandled `ValidationError` on the pause path.
- Dependency manifest: `uv.lock` (47 packages) against the pip-audit database as of 2026-10-05 - 0 known vulnerabilities.
- Secret sweep: regex scan for credential-shaped literals and private-key headers across `src/`, `config/`, workflows and docs - 0 hits.

### What was NOT reviewed (and why)
- Unchanged modules outside the diff (covered by the fase-4/5/7/8 and release audits); only their interaction with the changed lines was checked.
- `tests/` - reviewed for the four touched files only.
- Runtime behaviour of the workflow on GitHub (no `gh` CLI/auth in this environment); job semantics were verified by re-running the exact shell commands locally where possible.
- `detect-secrets`/`gitleaks`/`semgrep` full scans were not executed (not installed; installation not requested).

### Tools run
| Tool | Status | Findings |
|------|--------|----------|
| bandit (`-r src/ -ll -i`) | Run | 0 |
| ruff `--select=S src/` | Run | 0 |
| pip-audit (`uv.lock` export, `--strict`) | Run | 0 CVEs |
| mypy (`src`) | Run | 0 issues |
| detect-secrets | Not executed (CLI semantics verified via `--help`) | SEC-901 raised from workflow review |
| gitleaks | Not installed | Recommended (DEF-902) |
| semgrep | Not installed | Recommended (carry-over fase-7 DEF-003) |
| manual review | Completed | 1 low, 3 info |

### Methodology
- Phase 1 - Scope & Context: diff-first scope; threat model inherited from the release audit.
- Phase 2 - Automated Scanning: bandit, ruff S-rules, pip-audit, mypy, test suite (474).
- Phase 3 - Manual Review: `references/python-security.md` and `references/secrets-patterns.md` consulted; every changed input path traced to its sink (CLI flag -> config -> `safe_write_text`; URL string -> `driver.get`; operator text -> redaction -> cap -> model).
- Phase 4 - Exploit Reasoning: PoC sketches drafted for SEC-901 only; none executed.
- Phase 5 - Report: this document.

### Caveats
- This audit reflects the working tree on top of commit `a9aeeb2`; subsequent changes are not reviewed.
- SEC-901 rests on documented `detect-secrets` CLI behaviour verified locally with `--help`, not on an executed failing run.
- The CLI containment check and the write-time check both resolve the path at check time; a same-user local TOCTOU between check and open remains theoretically possible and is accepted for a single-user local CLI (same stance as release OBS-001).

---

## 7. Next Steps

1. SEC-901 fixed in the same session under explicit authorization - see section 8.
2. Commit and push this delta; confirm the `security` workflow turns green on the push.
3. Track DEF-901/DEF-902 in the backlog catalog ([docs/security/README.md](docs/security/README.md)).
4. Re-run `/8-auditar` at the next release gate.

---

## 8. Remediation (post-report, authorized by user 2026-10-05)

| ID | Fix | Verification | Status |
|----|-----|--------------|--------|
| SEC-901 | [security.yml](.github/workflows/security.yml) `python-secrets` job rewritten: `detect-secrets==1.5.0` pinned (compatible with the committed [.secrets.baseline](.secrets.baseline)), fresh scan with the same flags used to build the baseline (`--exclude-files '(\.claude|\.secrets\.baseline)'`), then a comparison step fails the job when a fresh `(filename, hashed_secret)` pair is absent from the baseline. Paths are normalized (`\` -> `/`) because the baseline is generated on Windows and the gate runs on Linux; new findings are emitted as `::error file=...` workflow annotations without printing the secret value | Baseline generated and committed (5 known findings: 3 hex-entropy lines in `evidence/discovery_run.log`, 1 keyword in each of `tests/test_redaction.py` / `tests/test_replay_logging.py`; `.claude/` excluded because the skill docs intentionally contain secret-shaped examples, and `.secrets.baseline` excluded because detect-secrets otherwise flags its own `hashed_secret` entries as new findings on every run - both issues caught by running the extracted job script under Linux/WSL before push). The exact `run` block was extracted from the YAML and executed under bash in both directions: clean tree -> exit 0 (`known=5 found=5 new=0`); planted probe file -> exit 1 (`::error file=probe...`). The `python -` comparison logic was additionally run directly against a real `detect-secrets` scan (clean -> 0, probe -> 1) | **Fixed** |

**Post-fix verification (2026-10-05):** 474 tests green; `ruff check`/`format --check` clean; `mypy src` clean; `bandit -r src/ -ll` clean; `ruff --select=S src/` clean; `pip-audit` over the `uv.lock` export: 0 known vulnerabilities.

---

*Report generated by the `audit-code` skill. To re-run: invoke the skill on the same scope and compare reports.*
