# Plan Maestro: Computer-Use Automation System

## ¿Qué es este producto?

Take-home técnico de **interface.ai**: un sistema de automatización computer-use que da "manos" a agentes IA sobre aplicaciones back-office bancarias legadas sin API. Convierte una corrida de descubrimiento con LLM en un **artefacto tipado y reutilizable**, lo reejecuta de forma **determinista sin LLM**, escala a un **humano en la misma sesión viva** cuando se bloquea y aplica **guardrails de seguridad** sobre datos financieros regulados. Entrega: repositorio público con vertical slice completo, `README.md`, `REPORT.md` (7 headings exactos) y `/evidence/`.

**Fuente de verdad:** `docs/refs/Assignment A — Computer-Use Automation System.pdf` (oficial). Las fuentes NotebookLM son apoyo; ante conflicto, manda Assignment A.

---

## Decisiones de diseño ya tomadas

| Tema | Decisión | Origen |
|------|----------|--------|
| Lenguaje | Python 3.11+ | NotebookLM Fase 1 |
| Automatización UI | Selenium WebDriver (WebDriverWait, sin `time.sleep`) | NotebookLM Fase 1 |
| LLM | Ollama local `qwen2.5-coder:7b` (texto; observe = DOM/a11y tree limpio, no screenshots) | NotebookLM Fase 1 |
| Proxy target | App web local **dentro de este repo** (`src/proxy_app/`) con escenarios bancarios | Confirmado por usuario |
| Idioma del proyecto | **Inglés** en código, docs, logs y entregables (`README`, `REPORT`, `evidence`) | NotebookLM Fase 1 |
| Artefacto | JSON serializable, versionado, parametrizado (`{{input.*}}`), fallback locators, checkpoint | NotebookLM Fase 2 (propuesto) |
| Nombre repo | `computer-use-automation-system` | Ya creado |
| Alcance infra | Sin colas/clusters/multitenant plumbing; solo diseño en REPORT §Heterogeneity | Assignment §5, §7 |

---

## Convención de documentación

Toda modificación, mejora o corrección sigue este protocolo antes de tocar código:

```
docs/plans/
├── 0_plan_maestro.md          # Este archivo — visión global
├── fase_1/
│   ├── 1.spec.md              # Especificación funcional (QUÉ + POR QUÉ) — /4-especificar
│   ├── 1.0_nombre_fase.md     # Plan de implementación (CÓMO) — /5-planear
│   ├── 1.tasks.md             # (Opcional) Tareas atómicas — solo fases complejas
│   └── 1.Y_nombre.md          # Desviación/problema correlativo (Y = 1, 2, 3…)
├── fase_2/
│   └── ...
└── fixes/
    └── fix-N_nombre.md        # Bug fix puntual (correlativo global)
```

- **`X.spec.md`** → Especificación funcional. Se crea con `/4-especificar` ANTES de planificar.
- **`X.0`** → Plan de implementación. Se crea con `/5-planear` DESPUÉS de la spec.
- **`X.tasks.md`** → Tareas atómicas. Opcional, solo si la fase tiene >10 pasos.
- **`X.Y`** → Desviación, problema inesperado o ajuste fuera del plan (Y correlativo).

**Flujo de trabajo por fase:** `/4-especificar` → `/5-planear` → `/6-implementar` → `/7-verificar` → (`/8-auditar` si aplica) → marcar `[x]`

**Auditoría obligatoria** (`/8-auditar`) al cerrar fases que toquen seguridad: **4, 5, 7, 8**. Release gate completo antes de enviar.

---

## Estado de fases

| Fase | Nombre | Spec | Estado |
|------|--------|------|--------|
| 1 | Project Scaffold & Tooling | `fase_1/1.spec.md` | Completada |
| 2 | Proxy Target App | `fase_2/2.spec.md` | Completada |
| 3 | Artifact Schema | `fase_3/3.spec.md` | Completada |
| 4 | Safety & Policy Core | `fase_4/4.spec.md` | Completada |
| 5 | Discovery Loop (LLM) | `fase_5/5.spec.md` | Completada |
| 6 | Deterministic Replay Engine | `fase_6/6.spec.md` | Completada |
| 7 | Error Taxonomy | `fase_7/7.spec.md` | Completada |
| 8 | Human-in-the-Loop Handoff | `fase_8/8.spec.md` | Completada |
| 9 | Evidence, REPORT & Delivery | Pendiente | Pendiente |

---

## Fase 1: Project Scaffold & Tooling
- [x] Estructura `src/`, `tests/`, `evidence/`, `docs/` en inglés
- [x] `pyproject.toml` con deps: selenium, cliente Ollama, pydantic, pytest, ruff (+ mypy opcional)
- [x] `.env.example` (p.ej. `OLLAMA_BASE_URL`, `OLLAMA_MODEL=qwen2.5-coder:7b`) sin secretos reales
- [x] `.gitignore` hereda Python + `.env` + `.venv` + evidence volátil si aplica
- [x] Comandos dev: `pytest`, `ruff check`, runner mínimo de CLI placeholder
- [x] CI mínimo (`.github/workflows`) con lint + test en verde sobre vacío
- [x] README base en inglés (setup de ejemplo; demo path se completa en Fase 9)

**Cierre:** `pytest` y `ruff` pasan; repo sin credenciales; todo texto de proyecto en inglés.
**Cerrada:** 2026-09-25 — ruff/format/pytest (4 tests)/bandit/pip-audit en verde; sin secretos; spec + plan en `fase_1/`.

---

## Fase 2: Proxy Target App
- [x] App web local en `src/proxy_app/` (mismo repo)
- [x] Flujo bancario multi-step no trivial: search → detail → action con confirmación
- [x] Escenarios de excepción: "member not found" (business outcome), modal/confirmación, estado de validación
- [x] Superficie intencionadamente realista (marcado heredado aceptable; sin depender de test IDs perfectos)
- [x] Datos de prueba seed (member IDs, saldos) deterministas
- [x] Cómo levantarla documentado (`make run-app` o comando equivalente)
- [x] Test de humo del flujo core

**Cierre:** flujo completo funciona a mano en local; tests de humo pasan; forma parte de este repo.
**Cerrada:** 2026-09-25 — 25 tests verdes; ruff/format/mypy/bandit OK; walkthrough HTTP manual OK; spec + plan en `fase_2/`.

---

## Fase 3: Artifact Schema
- [x] Esquema JSON + modelos Pydantic tipados (serializable, versionado)
- [x] Campos mínimos Assignment §3.2: steps ordenados, estrategia de localización por step, `input_schema`, `output_schema`, `checkpoint`
- [x] Parametrización `{{input.*}}` (sin valores de corrida hardcodeados)
- [x] Array prioritario de fallback locators (id → css → xpath semántico / role / text)
- [x] Metadatos: `capability_id`, `version`, `description`, `target_app`
- [x] Validación estricta + fixture de ejemplo válida e inválida
- [x] Tests de round-trip (load/save/validate)

**Cierre:** fixture válida pasa validación; inválida falla con error claro; schema documentado en inglés.

**Cerrada:** 2026-09-25 — 18/18 CA verificados; 68 tests verdes; ruff/format/mypy/bandit OK; spec + plan en `fase_3/`.

---

## Fase 4: Safety & Policy Core
- [x] Allowlist configurable: dominios/rutas permitidos y tipos de acción permitidos
- [x] El agente/replay **no** actúa fuera de la allowlist (tests negativos)
- [x] Clasificación de acciones: safe/reversible vs risky/irreversible (política: bloquear / confirmar / flag — justificada)
- [x] Redacción de secretos y PII financiera en logs y artefactos (capa de escritura, no solo “acordarse”)
- [x] Tests de allowlist + redacción
- [x] `/8-auditar` de la fase

**Cierre:** tests de guardrails en verde; sin secretos ni PII crudos en outputs de test; auditoría sin Critical/High abiertos.

**Cerrada:** 2026-09-25 — 23/23 CA verificados; 139 tests verdes; ruff/format/mypy/bandit OK; auditoría `docs/security/audit-2026-09-25-fase-4.md` (1 High + 2 Low corregidos con tests de regresión, sin Critical/High abiertos); spec + plan en `fase_4/`.

---

## Fase 5: Discovery Loop (LLM)
- [x] Bucle `observe → decide → act` con meta en lenguaje natural + target (URL/entry)
- [x] Observe: snapshot limpio de DOM o accessibility tree (sin scripts/ruido; **no** screenshots crudos — el modelo es de texto)
- [x] Decide: prompts estructurados con Ollama `qwen2.5-coder:7b`; salida tipada de acción
- [x] Act: clic, type, navigate sobre la UI real (Selenium)
- [x] Stopping conditions: goal alcanzado, max steps, timeout, dead-end
- [x] Contadores y detección de estados repetidos (anti-bucle infinito)
- [x] Structured logs de cada step (qué, por qué, resultado)
- [ ] **Corrida real** contra `proxy_app`: genera artefacto vía Fase 3
- [ ] Evidencia inicial en `evidence/` (log + artefacto)
- [x] `/8-auditar` de la fase

**Cierre:** al menos una corrida LLM real completa sobre superficie viva; artefacto emitido; log en `evidence/`.

**Estado:** 2026-09-25 — 8/10 CA verificados (30/31 en `fase_5/5.spec.md`); 261 tests verdes; ruff/format/mypy/bandit OK; auditoría `docs/security/audit-2026-09-25-fase-5.md` (0 Critical/High; SEC-501/502 corregidos con tests de regresión, Low/Info en backlog); spec + plan en `fase_5/`. **Pendiente de cierre:** T13 (corrida real con Ollama + proxy_app y evidencia en `evidence/`) — gate manual con el operador.

---

## Fase 6: Deterministic Replay Engine
- [x] Motor que consume artefacto + parámetros de entrada **sin invocar al LLM**
- [x] Localización estable con fallback locators y esperas explícitas (`WebDriverWait`)
- [x] Validación de `checkpoint` antes de declarar éxito
- [x] Devolución de `output_schema` tipado al invocador
- [x] Result contract base: success (con outputs)
- [x] Tests de replay happy path con la fixture

**Cierre:** replay determinista del artefacto de Fase 5 (o fixture) pasa y verifica checkpoint.

**Cerrada:** 2026-09-27 — 28/28 CA verificados en `fase_6/6.spec.md`; 324 tests verdes; ruff/format/mypy/bandit OK; spec + plan en `fase_6/`; CLI `replay` con exit codes 0/10/11/1/2; test estático anti-LLM sobre `replay/`. Desviación menor registrada (nota 12 del plan: `step.timeout_ms` no se propaga al `WebDriverWait` del driver; presupuesto global vía `--max-timeout-ms`). **Pendiente manual:** corrida E2E real (Chrome + proxy_app) compartida con T13 de la Fase 5.

---

## Fase 7: Error Taxonomy
- [x] Taxonomía explícita en el result contract:
  - **Business outcome esperado** (p.ej. member not found) → resultado limpio, no crash
  - **Condición recuperable** (diálogo conocido, carga lenta) → retry/dismiss controlado
  - **Hard failure** → stop + error debuggable (step, esperado, observado)
- [x] Detección en replay de validation error, not found, permission denial, dialog inesperado, timeout de sesión, load failure
- [x] ≥1 test por cada una de las 3 categorías
- [x] Caso de excepción pensado para la evidencia de Fase 9
- [x] `/8-auditar` de la fase

**Cierre:** 3 tests de taxonomía en verde; business outcome nunca se clasifica como hard failure.

**Cerrada:** 2026-09-28 — 23/23 CA verificados en `fase_7/7.spec.md`; 381 tests verdes; ruff/format/mypy/bandit OK; spec + plan en `fase_7/`; `failure_category` en el result contract (`business_outcome`/`recoverable`/`hard`) con clasificador determinista (`observe_raw` + `config/taxonomy.json`), reintentos/dismiss controlados sin `time.sleep()` y mensajes pasando por `redact_text`; CLI eager `load_taxonomy()` (exit 2 sin tocar la seam `_execute_replay`). Auditoría `docs/security/audit-2026-09-28-fase-7.md`: 0 Critical/High; SEC-001 y SEC-002 (Low) corregidos en el cierre (§7 del informe), SEC-003 (Info) en backlog; DEF-001..004 en defense-in-depth. **Pendiente manual:** corrida E2E real (Chrome + proxy_app) compartida con T13 de la Fase 5.

---

## Fase 8: Human-in-the-Loop Handoff
- [x] Detección de stuck (reintentos fallidos, dead-end) y de step risky/irreversible
- [x] Intervention request con contexto: meta/capability, step actual, screenshot o snapshot, motivo
- [x] Pausa de la automatización en la **misma sesión viva** (antipatrón prohibido: navegador nuevo)
- [x] Bandera/clase de control: `automation` vs `human` (sin carreras)
- [x] Interfaz de operador **mínima/mock deliberada** (scope note Assignment §3.6) pero mecanismo de transferencia real
- [x] Registro de acciones humanas + evidencia del handoff
- [x] Señal de resume → el run continúa o completa
- [x] `/8-auditar` de la fase

**Cierre:** demo pausa → humano controla la misma sesión → retoma; evidencia persistida.
**Cerrada:** 2026-09-29 — 433 tests verdes; ruff/format/mypy/bandit en verde; auditoría `docs/security/audit-2026-09-29-fase-8.md` (0 Critical/High; SEC-801/802/803 corregidos, SEC-804/805 en backlog); registros `ReplayResult.handoff` serializables (la persistencia en `evidence/` es de Fase 9); spec + plan en `fase_8/`.

---

## Fase 9: Evidence, REPORT & Delivery
- [ ] `/evidence/` final: artefacto de ejemplo + log de discovery real + log de replay exitoso + **≥1 replay con error/estado de excepción** manejado
- [ ] `REPORT.md` (~1–3 páginas) con **exactamente** estos headings (inglés):
  1. Architecture
  2. Artifact schema
  3. Determinism & error handling
  4. Heterogeneity & multi-tenant
  5. Escalation & handoff
  6. Safety
  7. Cuts
- [ ] `README.md`: setup (keys/config), cómo correr sin servicios live si aplica, **demo path** con comandos exactos discovery → replay
- [ ] Verificar: sin secretos/PII en repo; tipado; rutas de entregable exactas
- [ ] Release gate: `/8-auditar` completo
- [ ] Stretch opcional solo si hay base sólida (si no → documentar en Cuts)
- [ ] Preparar defensa de trade-offs para la entrevista

**Cierre:** entregables en rutas exactas; evidencia completa; auditoría release sin Critical/High; repo listo para `assignments@interface.ai`.

---

## Criterios de evaluación (Assignment §7) — referencia para priorizar

1. System design
2. Correctness of the core loop
3. Robustness & error handling
4. Human-in-the-loop escalation
5. Generalization to the real environment (diseño)
6. Safety & data handling
7. Code quality
8. Communication

**No premian:** amplitud de features, name-dropping de frameworks, infra de escalado prematura.

**Thin-but-real > subconjunto pulido:** cada requisito núcleo debe existir en versión mínima real antes de profundizar de más en uno solo.

---

## Riesgos y pitfalls vigilados

| Riesgo | Mitigación (fase) |
|--------|-------------------|
| Modelo de texto sin visión | Observe = DOM/a11y limpio (5) |
| `time.sleep` frágil | Solo `WebDriverWait` (1, 6) |
| Valores hardcodeados en artefacto | `{{input.*}}` (3) |
| Locator de un solo punto de fallo | Array fallback (3, 6) |
| Business outcome como crash | Taxonomía (7) |
| Éxito falso sin checkpoint | Validación checkpoint (6) |
| Reiniciar navegador en HITL | Misma sesión viva (8) |
| PII/secretos en logs | Redacción en capa de escritura (4) |
| Bucle infinito del LLM | max-steps + repeat detection (5) |
| Headers de REPORT mal escritos | Lista exacta de 7 headings (9) |
| Documentación en español | Todo el entregable en inglés (todas) |

---

## Stretch goals (opcionales — solo tras núcleo sólido)

- Capability catalog / interfaz invocable por agente
- Code generation desde artefacto
- Confidence & approval (draft → approved)
- Assisted fallback acotado en replay
- Canonicalización / cross-tenant reuse demo
- Multi-run stability signal

Si no se hacen: **Cuts** en REPORT.md.

---

## Fuentes de referencia

- `docs/refs/Assignment A — Computer-Use Automation System.pdf` — especificación oficial
- `docs/refs/NotebookLM Indicaciones.txt` — entrevista, decisiones de stack, roadmap, schema JSON propuesto
- `docs/refs/Informe NotebookLM.txt` — informe técnico de apoyo
- `docs/refs/SDD_Guia_Integrada_Definitiva.md` — método SDD
- `CLAUDE.md` — constitución / reglas del agente

---

## Correctivos

[Referencias a fix-N de funcionalidades sin plan de fase propio]
