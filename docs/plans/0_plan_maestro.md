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
| 1 | Project Scaffold & Tooling | Pendiente | Pendiente |
| 2 | Proxy Target App | Pendiente | Pendiente |
| 3 | Artifact Schema | Pendiente | Pendiente |
| 4 | Safety & Policy Core | Pendiente | Pendiente |
| 5 | Discovery Loop (LLM) | Pendiente | Pendiente |
| 6 | Deterministic Replay Engine | Pendiente | Pendiente |
| 7 | Error Taxonomy | Pendiente | Pendiente |
| 8 | Human-in-the-Loop Handoff | Pendiente | Pendiente |
| 9 | Evidence, REPORT & Delivery | Pendiente | Pendiente |

---

## Fase 1: Project Scaffold & Tooling
- [ ] Estructura `src/`, `tests/`, `evidence/`, `docs/` en inglés
- [ ] `pyproject.toml` con deps: selenium, cliente Ollama, pydantic, pytest, ruff (+ mypy opcional)
- [ ] `.env.example` (p.ej. `OLLAMA_BASE_URL`, `OLLAMA_MODEL=qwen2.5-coder:7b`) sin secretos reales
- [ ] `.gitignore` hereda Python + `.env` + `.venv` + evidence volátil si aplica
- [ ] Comandos dev: `pytest`, `ruff check`, runner mínimo de CLI placeholder
- [ ] CI mínimo (`.github/workflows`) con lint + test en verde sobre vacío
- [ ] README base en inglés (setup de ejemplo; demo path se completa en Fase 9)

**Cierre:** `pytest` y `ruff` pasan; repo sin credenciales; todo texto de proyecto en inglés.

---

## Fase 2: Proxy Target App
- [ ] App web local en `src/proxy_app/` (mismo repo)
- [ ] Flujo bancario multi-step no trivial: search → detail → action con confirmación
- [ ] Escenarios de excepción: "member not found" (business outcome), modal/confirmación, estado de validación
- [ ] Superficie intencionadamente realista (marcado heredado aceptable; sin depender de test IDs perfectos)
- [ ] Datos de prueba seed (member IDs, saldos) deterministas
- [ ] Cómo levantarla documentado (`make run-app` o comando equivalente)
- [ ] Test de humo del flujo core

**Cierre:** flujo completo funciona a mano en local; tests de humo pasan; forma parte de este repo.

---

## Fase 3: Artifact Schema
- [ ] Esquema JSON + modelos Pydantic tipados (serializable, versionado)
- [ ] Campos mínimos Assignment §3.2: steps ordenados, estrategia de localización por step, `input_schema`, `output_schema`, `checkpoint`
- [ ] Parametrización `{{input.*}}` (sin valores de corrida hardcodeados)
- [ ] Array prioritario de fallback locators (id → css → xpath semántico / role / text)
- [ ] Metadatos: `capability_id`, `version`, `description`, `target_app`
- [ ] Validación estricta + fixture de ejemplo válida e inválida
- [ ] Tests de round-trip (load/save/validate)

**Cierre:** fixture válida pasa validación; inválida falla con error claro; schema documentado en inglés.

---

## Fase 4: Safety & Policy Core
- [ ] Allowlist configurable: dominios/rutas permitidos y tipos de acción permitidos
- [ ] El agente/replay **no** actúa fuera de la allowlist (tests negativos)
- [ ] Clasificación de acciones: safe/reversible vs risky/irreversible (política: bloquear / confirmar / flag — justificada)
- [ ] Redacción de secretos y PII financiera en logs y artefactos (capa de escritura, no solo “acordarse”)
- [ ] Tests de allowlist + redacción
- [ ] `/8-auditar` de la fase

**Cierre:** tests de guardrails en verde; sin secretos ni PII crudos en outputs de test; auditoría sin Critical/High abiertos.

---

## Fase 5: Discovery Loop (LLM)
- [ ] Bucle `observe → decide → act` con meta en lenguaje natural + target (URL/entry)
- [ ] Observe: snapshot limpio de DOM o accessibility tree (sin scripts/ruido; **no** screenshots crudos — el modelo es de texto)
- [ ] Decide: prompts estructurados con Ollama `qwen2.5-coder:7b`; salida tipada de acción
- [ ] Act: clic, type, navigate sobre la UI real (Selenium)
- [ ] Stopping conditions: goal alcanzado, max steps, timeout, dead-end
- [ ] Contadores y detección de estados repetidos (anti-bucle infinito)
- [ ] Structured logs de cada step (qué, por qué, resultado)
- [ ] **Corrida real** contra `proxy_app`: genera artefacto vía Fase 3
- [ ] Evidencia inicial en `evidence/` (log + artefacto)
- [ ] `/8-auditar` de la fase

**Cierre:** al menos una corrida LLM real completa sobre superficie viva; artefacto emitido; log en `evidence/`.

---

## Fase 6: Deterministic Replay Engine
- [ ] Motor que consume artefacto + parámetros de entrada **sin invocar al LLM**
- [ ] Localización estable con fallback locators y esperas explícitas (`WebDriverWait`)
- [ ] Validación de `checkpoint` antes de declarar éxito
- [ ] Devolución de `output_schema` tipado al invocador
- [ ] Result contract base: success (con outputs)
- [ ] Tests de replay happy path con la fixture

**Cierre:** replay determinista del artefacto de Fase 5 (o fixture) pasa y verifica checkpoint.

---

## Fase 7: Error Taxonomy
- [ ] Taxonomía explícita en el result contract:
  - **Business outcome esperado** (p.ej. member not found) → resultado limpio, no crash
  - **Condición recuperable** (diálogo conocido, carga lenta) → retry/dismiss controlado
  - **Hard failure** → stop + error debuggable (step, esperado, observado)
- [ ] Detección en replay de validation error, not found, permission denial, dialog inesperado, timeout de sesión, load failure
- [ ] ≥1 test por cada una de las 3 categorías
- [ ] Caso de excepción pensado para la evidencia de Fase 9
- [ ] `/8-auditar` de la fase

**Cierre:** 3 tests de taxonomía en verde; business outcome nunca se clasifica como hard failure.

---

## Fase 8: Human-in-the-Loop Handoff
- [ ] Detección de stuck (reintentos fallidos, dead-end) y de step risky/irreversible
- [ ] Intervention request con contexto: meta/capability, step actual, screenshot o snapshot, motivo
- [ ] Pausa de la automatización en la **misma sesión viva** (antipatrón prohibido: navegador nuevo)
- [ ] Bandera/clase de control: `automation` vs `human` (sin carreras)
- [ ] Interfaz de operador **mínima/mock deliberada** (scope note Assignment §3.6) pero mecanismo de transferencia real
- [ ] Registro de acciones humanas + evidencia del handoff
- [ ] Señal de resume → el run continúa o completa
- [ ] `/8-auditar` de la fase

**Cierre:** demo pausa → humano controla la misma sesión → retoma; evidencia persistida.

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
