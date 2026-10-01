# fix-4: la excepcion de replay se clasificaba `hard` en vez de `business_outcome`

- **Fecha**: 2026-10-01
- **Fase afectada**: 7 (taxonomia de errores) — detectado al verificar el CA 1.5 de Fase 9.
- **Severidad**: menor (etiqueta de evidencia incorrecta; exit code y flujo intactos).

## Sintoma

`uv run python -m computer_use_automation_system.cli replay --artifact
evidence/artifact_v3.json --input q=M-9999 --log-out evidence/replay_exception.log`
termina con exit 1 (correcto) pero el evento de fallo clasifica
`"failure_category": "hard"` en lugar de `"business_outcome"`.

La pagina real si muestra el mensaje de negocio:
`No records found. Member not found for "{{ query }}".`
(`src/proxy_app/templates/search_results.html:23`, patron ya presente en
`config/taxonomy.json` bajo `business_outcome`).

## Causa

`replay/taxonomy.py::page_text()` construye el texto de clasificacion uniendo
`text`/`name`/`value` de `driver.observe_raw()`. Pero `observe_raw`
(`OBSERVE_SCRIPT`) solo recolecta **elementos interactivos** (input, button,
select, textarea, links): el `<p class="notfound">` estatico nunca aparece,
`classify_failure` no encuentra patron alguno y devuelve `hard`
(`engine.py::_classify` pasaba `driver.observe_raw()` tal cual).

## Fix (test-first)

1. Tests rojos en `tests/test_replay_engine.py`:
   - `test_optional_page_text_capability_feeds_classification`: driver con
     `page_text()` que devuelve el mensaje completo clasifica `business_outcome`.
   - `test_driver_without_page_text_keeps_the_legacy_classification`: driver sin
     el metodo sigue clasificando `hard` (proteccion de regresion).
2. Test estatico `test_page_text_reads_bounded_body_innertext` en
   `tests/test_discovery_selenium_driver.py`.
3. `SeleniumDriver.page_text()`: `execute_script("return document.body ?
   document.body.innerText : ''")`, truncado a 20000 chars, `""` en cualquier
   excepcion (best-effort, nunca rompe el replay).
4. `replay/engine.py::_classify`: si el driver expone `page_text` via
   `getattr` (mismo patron opcional que `_screenshot`/`screenshot_b64`), se
   anade `{"text": body}` al final de la lista de elementos antes de
   `classify_failure`. Los fakes de CI sin el metodo no cambian de
   comportamiento.

## Impacto

- `uv run pytest`: 455 verdes (3 tests nuevos).
- `ruff check` / `ruff format` / `mypy` / `bandit -ll`: verdes.
- Evidencia Fase 9: `replay_exception.log` regenerado con
  `--input q=M-9999` clasificando `business_outcome` (CA 1.5).
- Los patrones de negocio solo se buscan en texto de pagina; no se persiste
  ni se loguea el cuerpo completo (solo el nombre del patron encontrado).

## Referencias

- Plan Fase 7: `docs/plans/fase_7/7.0_error_taxonomy.md` (seccion Correctivos)
- Plan Fase 9: `docs/plans/fase_9/9.0_evidence_report_delivery.md` (seccion Correctivos)
