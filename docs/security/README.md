# Security Audit Catalog

Consolidated index of every finding raised by `/8-auditar` (skill `audit-code`)
across the phase gates. Each report keeps the full write-up (description,
vulnerable code, impact, PoC sketch, remediation, regression tests); this file
is the single place to see severity and status at a glance.

## Reports

| Report | Date | Scope |
|--------|------|-------|
| [audit-2026-09-25-fase-4.md](audit-2026-09-25-fase-4.md) | 2026-09-25 | Safety & policy core (Phase 4 perimeter, redaction, writes) |
| [audit-2026-09-25-fase-5.md](audit-2026-09-25-fase-5.md) | 2026-09-25 | Discovery loop (LLM client, observe/decide/act, driver) |
| [audit-2026-09-28-fase-7.md](audit-2026-09-28-fase-7.md) | 2026-09-28 | Error taxonomy & replay classification |
| [audit-2026-09-29-fase-8.md](audit-2026-09-29-fase-8.md) | 2026-09-29 | Human-in-the-loop handoff |
| [audit-2026-10-01-release.md](audit-2026-10-01-release.md) | 2026-10-01 | Release gate (evidence, REPORT/README, logging, entry points) |
| [audit-2026-10-05-fixes.md](audit-2026-10-05-fixes.md) | 2026-10-05 | Backlog-fix delta (SEC-503, SEC-505, SEC-805, DEF-803, CI dependency gate) |

## ID convention

Finding IDs restart on every report: **fase-4** and **fase-7** both mint
`SEC-001`, and `OBS-003` exists in fase-5 with a different meaning than in the
release report. Always qualify an ID with its report (e.g. `fase-7 SEC-001`).
Newer reports use phase-encoded ranges (`SEC-5xx` = Phase 5, `SEC-8xx` =
Phase 8, `SEC-9xx`/`DEF-9xx`/`OBS-9xx` = 2026-10-05 delta); keep that style
for future audits.

Statuses used below:

- **Fixed** - landed with a regression test; the report's section 7 records the fix.
- **Backlog** - accepted for now, listed in the report's next steps.
- **Accepted** - audited and deliberately left as designed for the local-CLI threat model.

## Findings

| Report | ID | Severity | Title | Status |
|--------|----|----------|-------|--------|
| fase-4 | SEC-001 | High | Perimeter bypass: scheme-relative URLs and non-normalized paths | Fixed 2026-09-25 |
| fase-4 | SEC-002 | Low | Log injection: CRLF not neutralized by RedactionFilter | Fixed 2026-09-25 |
| fase-4 | SEC-003 | Low | `safe_write_text` performs no path containment check | Fixed 2026-09-25 |
| fase-5 | SEC-501 | Medium | XPath/selector injection from DOM-controlled values | Fixed 2026-09-25 |
| fase-5 | SEC-502 | Medium | Prompt injection via snapshot (DOM text reaches the LLM prompt) | Fixed 2026-09-25 |
| fase-5 | SEC-503 | Low | Driver `navigate()` does not restrict the URL scheme | Fixed 2026-10-05 |
| fase-5 | SEC-504 | Low | Ollama client call has no timeout | Fixed (per-call `timeout_s`) |
| fase-5 | SEC-505 | Low | Artifact written without base-directory containment | Fixed 2026-10-05 |
| fase-7 | SEC-001 | Low | Validation errors echo the offending config value to stderr | Fixed 2026-09-28 |
| fase-7 | SEC-002 | Low | CRLF in taxonomy patterns forges CLI output lines | Fixed 2026-09-28 |
| fase-7 | SEC-003 | Info | Time budget not re-checked during bounded retries | Backlog |
| fase-8 | SEC-801 | Low | Policy rule reason reaches interactive prints with CRLF intact | Fixed 2026-09-29 |
| fase-8 | SEC-802 | Low | Replay outputs reach stdout without redaction | Fixed 2026-09-29 |
| fase-8 | SEC-803 | Low | Interactive command surfaces raw tracebacks on unhandled exceptions | Fixed 2026-09-29 |
| fase-8 | SEC-804 | Info | Handoff pause blocks indefinitely with no deadline | Backlog |
| fase-8 | SEC-805 | Info | Handoff records carry unbounded snapshot/note/description sizes | Fixed 2026-10-05 |
| fase-5 | OBS-501 | Info | Input field values flow into the LLM prompt | Accepted |
| fase-5 | OBS-502 | Info | Raw LLM responses kept in memory outcomes | Accepted |
| fase-5 | OBS-003 | Info | CLI ignores unknown arguments when `discover` is absent | Backlog |
| fase-5 | OBS-504 | Info | Evidence files inherit default OS permissions | Accepted |
| release | OBS-001 | Info | Log writers accept arbitrary local paths (`--log-out`) | Accepted |
| release | OBS-002 | Info | Page text flows into failure messages | Accepted (redacted) |
| release | OBS-003 | Info | Timestamp-free evidence logs | Accepted (determinism) |
| 2026-10-05 | SEC-901 | Low | Secret-scanning CI job exits 0 regardless of findings | Fixed 2026-10-05 |
| 2026-10-05 | OBS-901 | Info | Library `run_discovery` writes unconstrained without `out_root` | Accepted |
| 2026-10-05 | OBS-902 | Info | Narrowed capability catch assumes `AttributeError`/`TypeError` only | Accepted (latent) |
| 2026-10-05 | OBS-903 | Info | Truncation can split a redaction marker | Accepted (cosmetic) |

## Defense-in-depth and tooling

| Report | ID | Item | Status |
|--------|----|------|--------|
| fase-4 | DEF-001 | Dependency + secret scanning in CI | Done: `.github/workflows/security.yml` runs bandit, `pip-audit` over the `uv.lock` export and `detect-secrets` |
| fase-4 | DEF-002 | Attach `RedactionFilter` centrally on the package logger | Backlog |
| fase-4 | DEF-003 | Single URL-checking helper shared by every consumer | Backlog |
| fase-5 | DEF-501 | (duplicate of fase-4 DEF-001) | Done |
| fase-5 | DEF-502 | Harden prompts against injected page text (strip control chars, cap field length) | Backlog |
| fase-5 | DEF-503 | Pre-commit secret scanning (`gitleaks`/`detect-secrets` hook) | Backlog |
| fase-5 | DEF-504 | Session watchdog around `run_discovery` | Backlog (bounded today by `total_timeout_ms`, step timeouts and the LLM transport timeout) |
| fase-7 | DEF-001 | `pip-audit` in CI | Done (see fase-4 DEF-001) |
| fase-7 | DEF-002 | Pre-commit secret scanning | Backlog |
| fase-7 | DEF-003 | `semgrep` rule packs in CI | Backlog |
| fase-7 | DEF-004 | Treat `config/taxonomy.json` as a trust anchor (permissions/checksum) | Backlog |
| fase-8 | DEF-801 | Dependency scanning in CI | Done (see fase-4 DEF-001) |
| fase-8 | DEF-802 | Pre-commit secret scanning | Backlog |
| fase-8 | DEF-803 | Narrow the best-effort `screenshot_b64` catch to `(AttributeError, TypeError)` | Fixed 2026-10-05 |
| fase-8 | OBS-801 | Create this catalog (`docs/security/README.md`) | Fixed (this file) |
| release | DEF-001 | Pre-commit secret scanning | Backlog |
| release | DEF-002 | Keep dependency scanning failing the build on High+ CVEs | Done (2026-10-05: `security.yml` audits the `uv.lock` export instead of the runner environment) |
| 2026-10-05 | DEF-901 | Pin the `pip-audit` version (and Actions SHAs) used by CI | Backlog |
| 2026-10-05 | DEF-902 | Pre-commit secret scanning (local hook) | Backlog |
| 2026-10-05 | DEF-903 | Keep the `uv.lock` export as the single audited dependency input | Done (convention) |

## Open backlog (summary)

1. **SEC-804** - deadline for the blocking handoff pause (`handoff_timeout_ms`).
2. **SEC-003 (fase-7)** - re-check the global time budget inside the bounded retry loop.
3. **Pre-commit secret scanning** (DEF-503/DEF-802/DEF-902/release DEF-001) - CI-side gating landed with SEC-901 (baseline comparison); a local hook closes the "commit first, CI later" window.
4. **`semgrep` in CI** (fase-7 DEF-003), **`RedactionFilter` auto-attachment** (fase-4 DEF-002), **pin `pip-audit` in CI** (DEF-901).
5. **`config/taxonomy.json` trust anchor** (fase-7 DEF-004) if the threat model ever includes tampering.

## Re-running an audit

`/8-auditar` (or the `audit-code` skill directly) over the current scope, then
file the new report next to these and add its rows to this table. Audits are
mandatory when closing phases 4, 5, 7 and 8, and as the release gate before
packaging.
