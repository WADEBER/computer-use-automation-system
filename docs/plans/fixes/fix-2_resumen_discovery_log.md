# fix-2: el resumen del discovery no se escribia en el log JSONL

- **Fecha**: 2026-10-01
- **Fase afectada**: 5 (discovery) — detectado al verificar el CA 1.3 de Fase 9.
- **Severidad**: menor (evidencia incompleta, sin impacto en ejecucion).

## Sintoma

`evidence/discovery_run.log` (y cualquier `--log-out` de `discover`) solo contiene
una linea JSON por paso. El evento final `{"event": "summary", "status": ...,
"steps": ...}` se imprimia unicamente en stdout (`StepLogger.write_summary`).

El CA 1.3 de Fase 9 exige: *"`discovery_run.log`: JSONL estructurado (un evento
por paso + resumen)"*. El archivo no era autocontenido.

## Causa

`src/computer_use_automation_system/discovery/logging_runner.py`:
`write_summary()` hacia `self._stdout.write(...)` sin persistir en `log_path`,
a diferencia de `write_step()` que escribe en archivo y stdout. Decision de
diseno de Fase 5 ("The summary event goes to stdout only") que quedo obsoleta
al requerir Fase 9 que el log entregable lleve el resumen.

## Fix (test-first)

1. Test rojo: `test_summary_is_appended_to_the_log_file` y
   `test_summary_file_line_is_redacted` en `tests/test_discovery_logging.py`.
2. `write_summary()` ahora construye el payload, lo pasa por
   `redact_mapping` (misma capa de escritura que `write_step`), lo anade al
   archivo y lo escribe en stdout. Docstring actualizado.
3. Ajuste de contrato en
   `tests/test_discovery_runner.py::test_goal_reached_writes_valid_artifact_and_evidence`:
   el log ahora termina con la linea de resumen (2 pasos + 1 resumen = 3 lineas).

## Impacto

- `uv run pytest`: 450 verdes (2 tests nuevos).
- Evidencia de Fase 9: `discovery_run.log` regenerado con resumen incluido.
- Compatibilidad: stdout no cambia (mismas lineas, mismo orden); solo se anade
  la persistencia del resumen en disco.
