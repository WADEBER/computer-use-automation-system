# CLAUDE.md — computer-use-automation-system

Reglas y contexto del proyecto para el agente. Leer siempre antes de hacer cambios.

---

## ¿Qué es este proyecto?

Take-home técnico de **interface.ai**: un sistema de automatización computer-use que da "manos" a agentes IA sobre aplicaciones back-office bancarias legadas sin API. Convierte una corrida de descubrimiento con LLM en un artefacto tipado y reutilizable, lo reejecuta de forma determinista sin LLM, escala a un humano en la misma sesión viva cuando se bloquea y aplica guardrails de seguridad sobre datos financieros regulados.

**Estado actual:** Fases 1-9 cerradas (Project Scaffold, Proxy Target App, Artifact Schema, Safety & Policy Core, Discovery Loop, Deterministic Replay Engine, Error Taxonomy, Human-in-the-Loop Handoff, Evidence/REPORT/Delivery). 474 tests verdes; ruff/format/mypy/bandit en verde; auditorías de seguridad en `docs/security/` (fases 4, 5, 7, 8 y release 2026-10-01 — 0 Critical/High) con catálogo consolidado en `docs/security/README.md`. Delta 2026-10-05 (`audit-2026-10-05-fixes.md`): cierra SEC-503/505/805, DEF-803 y SEC-901 (job de secretos en CI ahora puede fallar, con `.secrets.baseline` commiteado) del backlog; sin hallazgos abiertos por encima de Info. Patrones de clasificación de fallos en `config/taxonomy.json`. Evidencia en vivo en `evidence/` (artefacto de ejemplo + logs de discovery/replay, incluida una excepción clasificada `business_outcome`); con ella se cierra el T13 pendiente de Fase 5. Fixes 1-4 aplicados durante Fase 9 (ver §Correctivos de los planes de fase). Las 9 fases están definidas en `docs/plans/0_plan_maestro.md`.

---

## Comandos de desarrollo

```bash
uv sync                              # Instalar dependencias
uv run pytest                        # Ejecutar tests
uv run ruff check src/ tests/        # Linting
uv run ruff format src/ tests/       # Formato
uv run mypy src                      # Type check (opcional)
uv run computer-use-automation-system  # CLI help (no args prints usage, exit 0)
uv run python -m proxy_app.app       # Levantar proxy target app (Fase 2)
```

**Para arrancar la proxy app:** `uv run python -m proxy_app.app` — abre `http://127.0.0.1:5000`

---

## Arquitectura

### Estructura de archivos

```
src/
├── computer_use_automation_system/   # Paquete principal CLI
│   └── __init__.py                   # Punto de entrada main()
└── proxy_app/                        # Proxy target app Flask (Fase 2)
    ├── __init__.py
    └── app.py                        # create_app() factory + main()
tests/
├── test_smoke.py                     # Test humo CLI
└── test_proxy_app_smoke.py           # Test humo proxy app
evidence/                             # Artefactos de corrida, logs, evidencia
docs/
├── plans/                            # Specs y planes por fase (SDD)
├── refs/                             # Documentos de referencia (Assignment A, etc.)
├── security/                         # Informes de auditoría
└── templates/                        # Plantillas de documentos
```

### Patrón arquitectónico

El proyecto es un sistema de automatización UI con dos componentes principales:

1. **Proxy target app** (`src/proxy_app/`): app Flask local que simula una interfaz bancaria legada. Es el target de automatización — deliberadamente realista, sin test IDs perfectos.

2. **Motor de automatización** (futuro en `src/computer_use_automation_system/`): bucle `observe → decide → act` con Selenium + LLM (Ollama), replay determinista, guardrails de seguridad y handoff humano.

### Patrones relevantes

- **Selenium sin `time.sleep`**: solo `WebDriverWait` para esperas explícitas.
- **Observe = DOM/a11y tree limpio**, no screenshots crudos (el modelo es de texto).
- **Artefacto JSON** parametrizado con `{{input.*}}`, fallback locators, checkpoint.

---

## Tech Stack

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Runtime | Python | 3.11+ |
| Package manager | uv | 0.12.x |
| Proxy app | Flask | 3.1.x |
| Browser automation | Selenium | 4.49.x |
| LLM client | ollama | 0.6.x |
| Data validation | Pydantic | 2.13.x |
| Tests | pytest | 9.1.x |
| Linting | ruff | 0.16.x |
| Type check | mypy | 2.3.x (opcional) |
| LLM local | Ollama `qwen2.5-coder:7b` | — |

---

## Variables de entorno

```env
OLLAMA_BASE_URL=http://localhost:11434   # URL del servidor Ollama local
OLLAMA_MODEL=qwen2.5-coder:7b            # Modelo a usar para discovery
PROXY_APP_PORT=5000                      # Puerto de la proxy app
PROXY_APP_HOST=127.0.0.1                 # Host de la proxy app
```

**Nunca** commitear `.env` — solo `.env.example` sin secretos reales.

---

## Convenciones de código

- **Idioma**: inglés en código, docs, logs y entregables (README, REPORT, evidence).
- **Unicode**: NO usar emojis, flechas Unicode (`→`), ni símbolos especiales en `print()`, logging o strings de código Python. Usar `[OK]`, `[ERROR]`, `[WARN]`, `->`, `-`/`*`.
- **Excepción**: archivos `.md` de documentación SÍ pueden usar caracteres Unicode.
- **Type hints**: todas las funciones nuevas llevan tipado.
- **Tests**: en `tests/`, espejo de la estructura de `src/`.
- **Ruff**: línea max 100, target `py311`, formato automático.

---

## Permisos del agente

✅ **SIEMPRE** (hacer sin preguntar):
- Ejecutar tests antes de dar por completada una tarea
- Seguir las convenciones de este CLAUDE.md
- Tipar todas las funciones nuevas
- Ejecutar `ruff format` y `ruff check`

⚠️ **PREGUNTAR PRIMERO** (suspender y pedir confirmación):
- Añadir nuevas dependencias a `pyproject.toml`
- Cambiar configuración de CI/CD (`.github/workflows/`)
- Modificar `.env.example` o variables de entorno
- Editar specs o planes existentes en `docs/plans/`

🚫 **NUNCA** (prohibido sin excepción):
- Commitear secretos o credenciales
- Borrar tests sin resolverlos primero
- Usar `time.sleep()` en código Selenium (usar `WebDriverWait`)
- Usar screenshots crudos como input al LLM (usar DOM/a11y limpio)
- Introducir Unicode especial en `print()` o logging de Python
- Editar archivos en `.venv/` o archivos generados

---

## Anti-patrones del proyecto

🚫 `time.sleep()` en automatización Selenium — usar `WebDriverWait` con esperas explícitas.
🚫 Screenshot como input al modelo — el modelo es de texto; usar DOM o accessibility tree limpio.
🚫 Valores hardcodeados en artefactos — parametrizar con `{{input.*}}`.
🚫 Locator de un solo punto de fallo — usar array prioritario de fallback locators.
🚫 Business outcome como crash — clasificar correctamente en la taxonomía de errores (Fase 7).
🚫 Reiniciar navegador en HITL — mantener la misma sesión viva para el handoff humano.
🚫 PII o secretos en logs — redactar en la capa de escritura (Fase 4).

---

## Gotchas conocidos

1. **Modelo sin visión**: `qwen2.5-coder:7b` es solo texto — no hay screenshots como input. El "observe" debe ser DOM/a11y tree.
2. **`requires-python = ">=3.11"`**: el CI usa 3.11; no subir a 3.12+ sin actualizar el workflow.
3. **`src/` en `tool.ruff.src`**: ruff y pytest usan `pythonpath = ["src"]` — los tests importan desde `src/` directamente.
4. **Proxy app es el target**: `src/proxy_app/` NO es el sistema principal — es la UI bancaria simulada que se automatiza.
5. **Idioma obligatorio**: todo entregable final en inglés (README, REPORT, evidence).

---

## Plan de evolución

El roadmap completo está en `docs/plans/0_plan_maestro.md`.

**Antes de cualquier cambio:**
- Fase nueva → `/4-especificar` → `/5-planear` → `/6-implementar` → `/7-verificar` → `/8-auditar` → `/9-documentar`
- Bug fix → `/5-planear` (si no es trivial) → `/6-implementar` → `/7-verificar` → `/8-auditar` (si toca auth, crypto, input externo, subprocess o deserialización)
- Antes de empaquetar/release → `/8-auditar completo` como release gate

**Auditoría obligatoria** al cerrar fases: **4, 5, 7, 8**.

Invocar `/prime` al inicio de cada sesión para cargar el contexto.

---

## Auditoría de seguridad

El comando `/8-auditar` (skill `audit-code` en `.claude/skills/`) ejecuta una auditoría de seguridad profesional antes de `/9-documentar`. Es un paso **obligatorio** del flujo de fase cuando el código toca:

- Autenticación / autorización
- Criptografía o almacenamiento de credenciales
- Entrada externa (correo, web, archivos subidos por usuario)
- `subprocess` / ejecución de comandos
- Deserialización (pickle, yaml.load, json.loads sobre input no validado)
- Dependencias nuevas o actualizadas

La auditoría produce un informe en `docs/security/audit-YYYY-MM-DD-<modo>.md` con severidad, CWE, OWASP, file:line y fix propuesto. Cada hallazgo bloqueante (Critical/High) se resuelve con un `fix-N` antes de cerrar la fase. El catálogo consolidado vive en `docs/security/README.md`.

---

## Fuentes de verdad

- `docs/refs/Assignment A — Computer-Use Automation System.pdf` — especificación oficial
- `docs/plans/0_plan_maestro.md` — roadmap y decisiones de diseño
- `CLAUDE.md` (este archivo) — reglas del agente
- `pyproject.toml` — dependencias y configuración real
