# computer-use-automation-system

A goal-driven **computer-use automation system** that gives AI agents "hands" over legacy, API-less back-office banking applications. An LLM-driven discovery run is compiled into a typed, reusable **artifact**; the artifact is then replayed **deterministically without an LLM**, escalates to a **human in the same live session** when blocked, and applies **safety guardrails** around regulated financial data.

Built as a take-home technical assignment for **interface.ai**.

## Table of contents

- [How it works](#how-it-works)
- [Project status](#project-status)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [The proxy target app (MemberServ Console)](#the-proxy-target-app-memberserv-console)
- [The artifact schema](#the-artifact-schema)
- [The safety policy](#the-safety-policy)
- [The discovery loop (Phase 5)](#the-discovery-loop-phase-5)
- [Development](#development)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Workflow (spec-driven development)](#workflow-spec-driven-development)

---

## How it works

The system turns a one-off LLM discovery run into a reusable automation capability:

1. **Discovery (Phase 5, implemented)** — the `discover` CLI drives an `observe -> decide -> act` loop with a local LLM (Ollama `qwen2.5-coder:7b`). Observe uses a clean DOM/accessibility tree, never raw screenshots (the model is text-only); every action is validated (typed schema + policy enforcement) before it reaches the browser.
2. **Artifact (Phase 3, implemented)** — discovery output is serialized into a typed JSON contract: ordered steps, prioritized fallback locators, typed input/output schemas and a success checkpoint. This is the "focal point" of the evaluation: a human reviewer or calling agent must understand the capability from the artifact alone.
3. **Replay (Phase 6, planned)** — the same artifact is executed deterministically, with no LLM in the loop, reusing the same locators, parameters (`{{input.*}}`) and checkpoint.
4. **Safety (Phase 4, implemented)** — a JSON policy drives allowlists (origins, routes, action types), action classification (block / confirm / flag) and write-time redaction of secrets/financial PII, enforced without any LLM in the loop.
5. **Human-in-the-loop (Phase 8, planned)** — blocked runs escalate to a human on the **same live browser session**; no session restarts.

The target application is a deliberately realistic legacy banking console (**MemberServ**) living in this repository (`src/proxy_app/`), so the whole loop can be developed and demonstrated locally without external systems.

---

## Project status

| Phase | Name | Status |
|-------|------|--------|
| 1 | Project Scaffold & Tooling | Completed |
| 2 | Proxy Target App (MemberServ) | Completed |
| 3 | Artifact Schema | Completed |
| 4 | Safety & Policy Core | Completed |
| 5 | Discovery Loop (LLM) | Implemented (live run pending) |
| 6 | Deterministic Replay Engine | Pending |
| 7 | Error Taxonomy | Pending |
| 8 | Human-in-the-Loop Handoff | Pending |
| 9 | Evidence, REPORT & Delivery | Pending |

Current test suite: **261 tests passing** (pytest), with ruff (lint + format), mypy and bandit in green.

Roadmap and design decisions: [`docs/plans/0_plan_maestro.md`](docs/plans/0_plan_maestro.md).

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager; the lockfile pins every version)
- Chrome/Chromium — required from Phase 5 (Selenium) onwards
- [Ollama](https://ollama.com/) with the `qwen2.5-coder:7b` model — required from Phase 5 onwards

Phases 1-4 only need Python + uv.

---

## Quick start

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure the environment

```bash
cp .env.example .env        # macOS / Linux
Copy-Item .env.example .env # Windows PowerShell
```

Then edit `.env` if needed. **Never commit `.env`** — only `.env.example` (it contains no secrets).

| Variable | Default | Used by |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Discovery loop (Phase 5) |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Discovery loop (Phase 5) |
| `PROXY_APP_HOST` | `127.0.0.1` | Proxy target app |
| `PROXY_APP_PORT` | `5000` | Proxy target app |
| `PROXY_APP_DEBUG` | `false` (`1`/`true`/`yes` enables) | Proxy target app (debug stays off by default) |
| `BROWSER` / `HEADLESS` | `chrome` / `true` (commented in `.env.example`) | Browser automation (Phase 5+) |

### 3. Run the test suite

```bash
uv run pytest        # 261 tests
```

### 4. (Optional) Run the target application

```bash
uv run python -m proxy_app.app
# open http://127.0.0.1:5000/
```

---

## The proxy target app (MemberServ Console)

`src/proxy_app/` is a local Flask app that simulates a **legacy banking back-office UI** ("MemberServ Console v4.2"). It is the *target* of the automation system, not the automation itself: intentionally realistic markup (tables, `name`-based fields, no perfect test IDs) with a multi-step business flow, exception scenarios and deterministic seed data.

### Running it

```bash
uv run python -m proxy_app.app
```

- URL: `http://127.0.0.1:5000/` (override host/port with `PROXY_APP_HOST` / `PROXY_APP_PORT`)
- Data lives in memory: **every restart resets balances and receipt numbering**

### Seed data (deterministic)

| Member ID | Full name | Accounts | Credit limit |
|-----------|-----------|----------|--------------|
| `M-1001` | Alice Hartwell | `CHK-2201` checking 4250.75 · `SAV-5101` savings 15200.00 | 10000.00 |
| `M-1002` | Brian Okafor | `CHK-2202` checking 980.40 | 2500.00 |
| `M-1003` | Carla Mendes | `CHK-2203` checking 312.00 · `SAV-5103` savings 8700.50 | 500.00 |

Search matches member ID or (partial) name, case-insensitive.

### End-to-end flow

1. **Home / Member Search** (`/`) — enter an ID (e.g. `M-1001`) or a name, press **Search**.
2. **Search Results** (`/members/search?q=...`) — matches in table `#searchResults`; each row links **View Detail**. No matches shows *"No records found. Member not found for ..."*, a business outcome rather than an error page.
3. **Member Detail** (`/members/<member_id>`) — member data plus the accounts table (`#accountsTable`); **New Loan Disbursement** starts the flow. Unknown ID -> 404 page.
4. **Loan Disbursement form** (`GET/POST /members/<member_id>/loans/disburse`) — pick a disbursement account and enter an amount; **Review Disbursement** validates server-side and redisplays the form with a red error box on failure.
5. **Confirm Disbursement** (`POST` -> confirm page) — review-only summary (member, account, amount); **Confirm Disbursement** executes, **Cancel** returns to the form. Confirmation is a second POST: the money only moves after it.
6. **Receipt** (`.../disburse/execute`) — shows `Disbursement No.` (`DISB-0001`, sequential), amount and the resulting balance (base balance + previous disbursements to that account + amount).

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Member search (home) |
| GET | `/members/search?q=` | Search results |
| GET | `/members/<member_id>` | Member detail (404 if unknown) |
| GET/POST | `/members/<member_id>/loans/disburse` | Disbursement form + validation |
| POST | `/members/<member_id>/loans/disburse/execute` | Execute after confirmation |

### Validation rules (exact messages)

| Rule | Message |
|------|---------|
| No account selected / unknown account | `Invalid account selection.` |
| Empty amount | `Amount is required.` |
| Non-numeric amount | `Amount must be a number.` |
| Amount <= 0 | `Amount must be greater than zero.` |
| Amount above the member's credit limit | `Amount exceeds credit limit of <limit>.` |
| Missing member | 404 page: `The requested record was not found: <id>.` |

---

## The artifact schema

The **artifact** is the reusable contract produced by discovery and consumed by deterministic replay (Assignment section 3.2). Pydantic models are the source of truth; the JSON Schema file is *derived* from them.

- Source of truth: `src/computer_use_automation_system/artifact/models.py`
- Exported contract: [`docs/schemas/artifact.schema.json`](docs/schemas/artifact.schema.json) (English, reviewable)

### Model reference

| Model | Key fields | Rules |
|-------|-----------|-------|
| `Artifact` | `capability_id`, `version`, `description`, `target_app`, `input_schema`, `output_schema`, `steps`, `checkpoint` | `capability_id` snake_case (`^[a-z][a-z0-9_]*$`), `version` semver `X.Y.Z`, `description` non-empty, `steps` >= 1, `checkpoint` mandatory, no extra fields |
| `TargetApp` | `name`, `entry_url` | `entry_url` must be `http(s)://` |
| `Step` | `step_id`, `action_type`, `description`, `locators`, `value`, `output_key`, `timeout_ms` | `step_id` sequential from 1; `action_type` in `navigate`/`click`/`type`/`extract`/`select`; `timeout_ms` > 0, default 5000 |
| `Locator` | `type`, `value` | `type` in `id`/`css`/`xpath`/`role`/`text`; `value` non-empty. **Array order = fallback priority** |
| `Checkpoint` | `description`, `locators`, `expected_condition` | condition in `visible`/`text_present`/`url_contains` |
| `JSONSchemaObject` | `type`, `properties`, `required` | `type` fixed `"object"`; `properties` non-empty, each property declares a string `type`; `required` must be a subset of `properties` |

### Validation rules

- **No hardcoded run values**: `value` of `type`/`select` steps must embed at least one `{{input.*}}` reference; `navigate` requires an http(s) URL; `click`/`extract` must not declare `value`.
- **Cross-invariants** (checked on the whole artifact, so drift fails validation early):
  - every `{{input.X}}` must exist in `input_schema.properties`
  - every `extract` `output_key` must exist in `output_schema.properties`
  - `output_key` is only allowed on `extract` steps
  - `step_id` must be exactly `1..n` in order
- **Strict serialization**: every model uses `extra="forbid"` — unknown keys are rejected, round-trips are idempotent.

### Loading and validating an artifact

```python
import json
from pathlib import Path

from computer_use_automation_system.artifact.models import Artifact

raw = json.loads(Path("tests/fixtures/valid_artifact.json").read_text(encoding="utf-8"))
artifact = Artifact(**raw)  # raises pydantic.ValidationError on any violation

print(artifact.capability_id, artifact.version)
serialized = artifact.model_dump_json(indent=2)  # stable JSON for storage/review
```

### Fixtures

| File | Purpose |
|------|---------|
| `tests/fixtures/valid_artifact.json` | Complete, realistic artifact: `lookup_member_balance` (6 steps against the MemberServ app) — passes validation |
| `tests/fixtures/invalid/bad_locator.json` | Breaks the locator-type enum (`"magic"`) |
| `tests/fixtures/invalid/bad_input_ref.json` | References `{{input.account_id}}`, which is not declared in `input_schema` |
| `tests/fixtures/invalid/missing_checkpoint.json` | Omits the mandatory `checkpoint` |

### Exported JSON Schema

`docs/schemas/artifact.schema.json` is generated from the models. An anti-drift test
(`tests/test_artifact_fixtures.py::test_exported_schema_matches_model`) fails if the file no
longer matches `Artifact.model_json_schema()`. Regenerate it after changing models:

```bash
uv run python -c "import json, pathlib; from computer_use_automation_system.artifact.models import Artifact; p = pathlib.Path('docs/schemas/artifact.schema.json'); p.write_text(json.dumps(Artifact.model_json_schema(), indent=2, sort_keys=True) + chr(10), encoding='utf-8')"
```

---

## The safety policy

Phase 4 adds the guardrail layer: a versioned JSON policy plus typed models that decide what the automation is allowed to do and redact what it writes. Pure Python, no LLM in the loop.

- Source of truth: [`config/policy.json`](config/policy.json) — loaded and strictly validated (`extra="forbid"`) by `load_policy()`; models in `src/computer_use_automation_system/safety/models.py`
- Engine: `evaluate(policy, action_type, url)` returns a `Decision` (`allow` / `confirm` / `flag` / `block`); `enforce(...)` raises `PolicyViolation` for anything not permitted
- Order: **perimeter first** (allowed origins, routes, action types — a `block` can never be overridden by rules), then classification rules (**first match wins**), default `allow` inside the perimeter

### Policy sections

| Section | Controls |
|---------|----------|
| `allowed_origins`, `allowed_routes`, `allowed_action_types` | Perimeter: exact origin match (scheme-relative `//...` rejected), normalized path (`..` / `%2e%2e` collapsed) before the route allowlist, action types a subset of the artifact enum |
| `rules` | Classification: `*/execute` -> `confirm` (human approval), `extract` -> `flag` (audit mark); each rule carries a mandatory `reason` |
| `redaction` | Write-time masking: regex patterns (`secret_assignment`, `account_number`, `money_amount`), known name literals, sensitive `field_keys` |

### Redaction at write time

- `redact_text` / `redact_mapping` — mask secrets, account numbers, amounts and names; structure and `M-1001`/URLs/`step_id` are preserved; idempotent
- `RedactionFilter` — logging filter that masks **and** escapes CR/LF (no log forging)
- `safe_write_text` — writes files redacted; with `base_dir` set, paths outside it raise `PermissionError`

### Using the engine

```python
from computer_use_automation_system.safety import PolicyViolation, enforce, evaluate, load_policy

policy = load_policy()  # reads config/policy.json

decide = evaluate(policy, "navigate", "http://127.0.0.1:5000/members/M-1001")
print(decide.decision, decide.reason)          # allow inside perimeter

enforce(policy, "navigate", "//evil.example/members")   # raises PolicyViolation (block)
enforce(policy, "click", "http://127.0.0.1:5000/members/M-1001/loans/disburse/execute")
# raises PolicyViolation (confirm): irreversible execution needs approved=True
```

The engine is a library; discovery wires into it on every action (Phase 5) and replay does the same later. Config changes (origins, routes, rules, redaction patterns) are made by editing `config/policy.json` only — no code changes.

---

## The discovery loop (Phase 5)

The `discover` subcommand runs the LLM-driven loop against the target UI and compiles what it learned into a Phase 3 artifact:

```bash
uv run computer-use-automation-system discover \
  --goal "Find the balance of member M-1001" \
  --entry http://127.0.0.1:5000/ \
  --max-steps 15
```

Prerequisites: the proxy app running (`uv run python -m proxy_app.app`), Ollama serving `qwen2.5-coder:7b`, and Chrome.

| Option | Purpose | Default |
|--------|---------|---------|
| `--goal` | Task in natural language (required) | — |
| `--entry` | Entry URL, must be `http(s)://` (required) | — |
| `--max-steps` | Step budget before stopping (positive int) | `15` |
| `--artifact-out` | Where to write the typed artifact | `evidence/discovery/artifact.json` |
| `--log-out` | Where to write the step log (JSONL, redacted) | `evidence/discovery/steps.jsonl` |

**Exit codes** map the final run status: `0` goal_reached, `10` blocked (policy), `11` needs_approval, `12` max_steps, `13` timeout, `14` dead_end, `15` llm_error; argparse usage errors exit `2`.

How a step runs: `observe` (clean DOM snapshot, deduped by hash) -> `decide` (structured prompt, strictly typed `LLMAction`, retries are feedback-corrected) -> `enforce` (Phase 4 policy) -> `act` (Selenium, locator fallback chain) -> repeat; `goal` is checked with a strict `{goal_reached, reason}` verdict. Loop guards: step budget, total-time budget, repeated-snapshot threshold (anti-bucle) and dead-end detection. Every step is appended to the JSONL log with the policy verdict, elapsed time and a redacted value preview.

Library usage (the CLI is a thin wrapper — tests inject a fake LLM/driver):

```python
from computer_use_automation_system.discovery.models import DiscoveryConfig
from computer_use_automation_system.discovery.runner import run_discovery

result = run_discovery(config, driver, client, policy)  # typed DiscoveryResult
```

---

### Commands

| Command | What it does |
|---------|--------------|
| `uv sync` | Install/refresh dependencies from `uv.lock` |
| `uv run pytest` | Run the full test suite (261 tests) |
| `uv run ruff check src/ tests/` | Lint |
| `uv run ruff format src/ tests/` | Format |
| `uv run ruff format --check src/ tests/` | Verify formatting (CI) |
| `uv run mypy src` | Type check (optional locally, not a CI gate) |
| `uvx bandit -r src/ -ll -i` | Security scan (same settings as the CI workflow) |
| `uv run python -m proxy_app.app` | Run the target app |
| `uv run computer-use-automation-system discover --goal ... --entry ...` | Run a discovery (Phase 5); no args prints the placeholder |

### Test suite

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_smoke.py` | 1 | CLI placeholder |
| `tests/test_proxy_app_smoke.py` | 2 | App factory / landing page |
| `tests/test_proxy_data.py` | 6 | Deterministic seed data |
| `tests/test_proxy_flow.py` | 7 | Search -> detail -> disburse -> confirm -> receipt |
| `tests/test_proxy_validation.py` | 9 | Disbursement validation messages |
| `tests/test_artifact_models.py` | 37 | Models, conditional rules, cross-invariants |
| `tests/test_artifact_fixtures.py` | 6 | Fixtures, round-trip, schema anti-drift |
| `tests/test_policy_models.py` | 16 | Policy/redaction models, strict validation |
| `tests/test_policy_load.py` | 6 | Policy JSON loading, error messages, JSON-only edits |
| `tests/test_policy_evaluate.py` | 22 | Perimeter (origins/routes/actions), rules, verdicts |
| `tests/test_policy_enforce.py` | 7 | Refusal semantics (block/confirm gates) |
| `tests/test_redaction.py` | 20 | Text/mapping/filter/writer redaction, log forging, path containment |
| `tests/test_discovery_models.py` | 30 | Discovery config/status/record models, env defaults |
| `tests/test_discovery_observe.py` | 8 | DOM snapshot, locators, digest dedup |
| `tests/test_discovery_decide.py` | 12 | Prompt building, strict action parsing, retries |
| `tests/test_discovery_llm_client.py` | 5 | Ollama client, fake transport, error mapping |
| `tests/test_discovery_act.py` | 8 | click/type/navigate/extract semantics |
| `tests/test_discovery_selenium_driver.py` | 12 | By mapping, XPath escaping, script translation, static anti-sleep |
| `tests/test_discovery_goal.py` | 11 | Goal verdict prompt/parse, retries |
| `tests/test_discovery_artifact.py` | 10 | Step sources -> artifact, parametrization, slugs |
| `tests/test_discovery_logging.py` | 5 | JSONL steps, summary, redaction per line |
| `tests/test_discovery_runner.py` | 11 | Full loop per status, determinism, policy invariant |
| `tests/test_cli_discover.py` | 10 | Parser, dispatch, exit-code mapping |
| **Total** | **261** | |

### Quality gates

- **Lint + tests**: `.github/workflows/ci.yml`
- **Security** (bandit + pip-audit + detect-secrets): `.github/workflows/security.yml`
- Local equivalents are listed in the [Commands](#commands) table; all are green at each phase close.

### Code conventions

- English in code, docs, logs and deliverables; no special Unicode in Python `print()`/logging output.
- Type hints on every new function; ruff line length 100, target `py311`.
- Selenium (from Phase 5): only `WebDriverWait` explicit waits — `time.sleep()` is forbidden.
- Tests live flat in `tests/`, mirroring `src/` prefixes.

---

## Project structure

```
.
├── README.md                          # This file
├── CLAUDE.md                          # Agent rules and project context
├── pyproject.toml                     # Dependencies, ruff/mypy/pytest config
├── uv.lock                            # Locked dependency versions
├── .env.example                       # Environment template (no secrets)
├── config/
│   └── policy.json                     # Phase 4: allowlist + rules + redaction (single source)
├── .github/workflows/                 # ci.yml (lint+test), security.yml (SAST)
├── .claude/commands/                  # SDD slash commands (/1 .. /9)
├── src/
│   ├── computer_use_automation_system/    # Main package (CLI entry point)
│   │   ├── artifact/                      # Phase 3: typed artifact schema
│   │   │   ├── __init__.py                # Public exports
│   │   │   └── models.py                  # Pydantic models + invariants
│   │   ├── discovery/                     # Phase 5: observe/decide/act loop
│   │   │   ├── models.py                  # DiscoveryConfig, RunStatus, records
│   │   │   ├── observe.py                 # DOM snapshot -> typed elements
│   │   │   ├── decide.py                  # Prompt + strict LLMAction parsing
│   │   │   ├── goal.py                    # Strict goal_reached verdict
│   │   │   ├── act.py                     # Typed action -> driver calls
│   │   │   ├── llm_client.py              # OllamaClient (protocol + live)
│   │   │   ├── selenium_driver.py         # BrowserDriver + build_webdriver
│   │   │   ├── runner.py                  # run_discovery loop + enforce
│   │   │   ├── artifact_builder.py        # Steps -> typed Artifact
│   │   │   └── logging_runner.py          # Redacted JSONL step log
│   │   ├── safety/                        # Phase 4: policy engine + redaction
│   │   │   ├── __init__.py                # Public exports
│   │   │   ├── models.py                  # PolicyConfig/Decision/RedactionConfig
│   │   │   ├── policy.py                  # load_policy / evaluate / enforce
│   │   │   └── redaction.py               # redact_text / filter / safe_write_text
│   │   └── cli.py                         # Phase 5: `discover` subcommand
│   └── proxy_app/                         # Phase 2: MemberServ target app
│       ├── app.py                         # create_app() factory + main()
│       ├── routes.py                      # Search/detail/disburse flows
│       ├── data.py                        # Deterministic in-memory seed
│       └── templates/                     # Legacy-style HTML (no test IDs)
├── tests/                                 # Flat test suite (261 tests)
│   ├── fixtures/                          # Artifact fixtures
│   │   ├── valid_artifact.json
│   │   └── invalid/                       # bad_locator, bad_input_ref, ...
│   ├── fakes.py                           # FakeLLMClient / FakeDriver (Phase 5)
│   └── test_*.py
├── docs/
│   ├── plans/                             # SDD specs and phase plans
│   │   ├── 0_plan_maestro.md              # Master roadmap (source of truth)
│   │   ├── fase_1/ ... fase_5/            # spec + implementation plan
│   ├── schemas/artifact.schema.json       # Exported JSON Schema (derived)
│   ├── refs/                              # Assignment A PDF, research notes
│   ├── security/                          # Security audit reports
│   ├── templates/                         # Document templates
│   └── GUIA_USUARIO.md                    # End-user guide (Spanish)
├── evidence/                              # Run artifacts, logs, evidence
└── REPORT.md                              # Final report (planned, Phase 9)
```

---

## Documentation

| Document | What it contains |
|----------|------------------|
| [`docs/plans/0_plan_maestro.md`](docs/plans/0_plan_maestro.md) | Master roadmap, design decisions, phase status |
| [`docs/plans/fase_1/1.spec.md`](docs/plans/fase_1/1.spec.md) → `fase_5/5.spec.md` | Functional spec + acceptance criteria per phase |
| [`docs/plans/fase_1/1.0_project_scaffold.md`](docs/plans/fase_1/1.0_project_scaffold.md) → `fase_5/5.0_discovery_loop.md` | Step-by-step implementation plans (test-first) |
| [`docs/schemas/artifact.schema.json`](docs/schemas/artifact.schema.json) | Machine-readable artifact contract |
| [`docs/security/audit-2026-09-25-fase-4.md`](docs/security/audit-2026-09-25-fase-4.md) | Phase 4 security audit (findings + remediation) |
| [`docs/security/audit-2026-09-25-fase-5.md`](docs/security/audit-2026-09-25-fase-5.md) | Phase 5 security audit (findings + remediation) |
| [`docs/GUIA_USUARIO.md`](docs/GUIA_USUARIO.md) | End-user guide for MemberServ + the `discover` command (Spanish) |
| [`CLAUDE.md`](CLAUDE.md) | Repository conventions and agent rules |

---

## Workflow (spec-driven development)

Every phase follows the same cycle with slash commands (`.claude/commands/`):

```
/4-especificar  ->  /5-planear  ->  /6-implementar  ->  /7-verificar  ->  /8-auditar  ->  /9-documentar
   spec (what)       plan (how)      test-first code    verify every      security         user docs
                                      red -> green       criterion         audit            + README
```

- Each implementation step is **test-first**: write the test, see it fail, make it pass, tick the step.
- Security audits (`/8-auditar`) are mandatory when closing phases that touch auth, crypto, external input, subprocess or deserialization (phases 4, 5, 7, 8) and as a release gate.
- Specs and plans live in `docs/plans/fase_X/`; phase closure is recorded in `docs/plans/0_plan_maestro.md`.
