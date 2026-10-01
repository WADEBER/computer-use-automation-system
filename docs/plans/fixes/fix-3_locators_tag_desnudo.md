# fix-3: el locator css de tag desnudo apuntaba al primer elemento de la pagina

- **Fecha**: 2026-10-01
- **Fase afectada**: 5 (discovery) — detectado al revisar los locators de los artefactos del T13.
- **Severidad**: media (clics ambiguos que resuelven al elemento equivocado en pages reales).

## Sintoma

El artefacto descubierto declara `css: a` como locator primario para el clic
de "View Detail". En la pagina de resultados sin registros (o en cualquier
pagina con otros links antes), `a` matchea el **primer** `<a>` de la pagina
("Back to search") y el clic resuelve al link equivocado — el mismo modo de
fallo que fix-1 corrigio en el submit (`css: input` sobre el campo de texto).

Un locator `a`/`input`/`button`/`div` sin atributos (sin id, name, class ni
role) no discrimina nada: para un tag generico hay N elementos en la pagina.

## Causa

`src/computer_use_automation_system/discovery/observe.py::_build_locators`
construia la lista de fallback sin filtrar el locator css cuando su selector
era un tag desnudo — el modelo lo emitia y se aceptaba tal cual como primario.

## Fix (test-first)

1. Tests rojos en `tests/test_discovery_observe.py`:
   - `test_bare_tag_css_is_omitted_when_it_cannot_discriminate`: un locator
     `css:a` sin predicados se omite de la lista cuando no aporta
     discriminacion.
   - `test_css_locator_is_kept_when_it_discriminates`: `css:form.login`,
     `css:input#q`, etc. se conservan (tienen atributos).
2. `_build_locators` descarta el css de tag desnudo cuando no puede
   discriminar; los locators role/text/xpath (que si llevan nombre) quedan
   como primarios, en su orden de prioridad.

## Impacto

- `uv run pytest`: +2 tests (452 en ese momento).
- Artefactos del T13 posteriores: el paso 4 declara
  `role:link::View Detail` / `text:View Detail` como primarios en vez de
  `css: a`.
- Comportamiento en CI: los fakes de replay (`tests/fakes.py`) no cambian;
  solo cambia la construccion de locators en el loop de discovery.

## Referencias

- Plan Fase 5: `docs/plans/fase_5/5.0_discovery_loop.md` (seccion Correctivos)
- Plan Fase 9: `docs/plans/fase_9/9.0_evidence_report_delivery.md` (seccion Correctivos)
