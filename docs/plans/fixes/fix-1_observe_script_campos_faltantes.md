# Fix 1: OBSERVE_SCRIPT no exporta los campos que `build_snapshot` espera

- **Fase afectada:** 5 (Discovery Loop) — detectado al generar la evidencia en vivo de la Fase 9 (T13).
- **Fecha:** 2026-10-01
- **Severidad:** bloqueante para evidencia/demo (no para CI)

## Bug

La corrida real de discovery nunca navega al hacer clic en el botón "Search":
el clic se resuelve contra el **primer `<input>` de la página** (el campo de
texto), outcome `ok` pero sin efecto, el snapshot no cambia y el loop muere en
`dead_end` tras repetir 3 veces el mismo hash.

## Causa raíz

Contrato roto entre dos capas de la Fase 5:

- `OBSERVE_SCRIPT` (`selenium_driver.py`) exporta solo
  `{tag, role, name, type, value, placeholder, href, rect}`.
- `build_snapshot` (`observe.py`) construye locators leyendo
  `id`, `name_attr`, `classes`, `text` y `label` — **ninguno existe** en la
  salida real del script.

Con `id=""`, `classes=[]` y `text=""`, `_build_locators` degrada para
cualquier input a `css=input` / `xpath=//input`, así que `driver.click(ref=2)`
encuentra `input#q` (primer match) y nunca el submit. Los tests de Fase 5
alimentan `build_snapshot` con fixtures que sí incluyen esos campos — el gap
de integración solo se ve con el navegador real (T13 estaba pendiente justo
por esto).

## Solución

`OBSERVE_SCRIPT` pasa a exportar los cinco campos que el contrato de
`build_snapshot` espera:

- `label`: aria-label || innerText || value (el `name` antiguo, renombrado)
- `id`: `el.id`
- `name_attr`: atributo `name`
- `classes`: `el.classList`
- `text`: innerText

Sin cambios en `observe.py` (ya era el consumidor correcto). El locators
derivados quedan distintos por elemento: `input#q` (id) vs `input.btn` (css).

## Archivos

- `src/computer_use_automation_system/discovery/selenium_driver.py` — OBSERVE_SCRIPT
- `tests/test_discovery_selenium_driver.py` — contrato de campos del script
- `tests/test_discovery_observe.py` — build_snapshot con la forma real del script

## Verificación

- Tests nuevos + suite completa en verde.
- Corrida real de discovery contra la proxy app: clic en Search navega a
  `/members/search`, goal alcanzada y artefacto emitido (evidencia Fase 9).

## Referencias

- Plan Fase 9: `docs/plans/fase_9/9.0_evidence_report_delivery.md` (Paso 5)
- Plan Fase 5: `docs/plans/fase_5/5.0_discovery_loop.md` (sección Correctivos)
