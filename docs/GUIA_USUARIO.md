# computer-use-automation-system — Guía de Usuario

> Esta guía te enseña a usar **MemberServ Console**, la consola bancaria simulada incluida en el proyecto, paso a paso: buscar miembros, consultar sus cuentas y registrar un préstamo con su confirmación.

---

## 📋 Índice

- [Primeros pasos](#-primeros-pasos)
- [Buscar miembros](#-buscar-miembros)
- [Ver la ficha de un miembro](#-ver-la-ficha-de-un-miembro)
- [Registrar un préstamo](#-registrar-un-préstamo)
- [Automatizar tareas con discover](#-automatizar-tareas-con-discover)
- [Repetir una tarea con replay](#-repetir-una-tarea-con-replay)
- [Intervención humana con --interactive](#-intervención-humana-con---interactive)
- [Avisos y errores que puedes ver](#-avisos-y-errores-que-puedes-ver)
- [Preguntas frecuentes](#-preguntas-frecuentes)
- [Problemas conocidos](#️-problemas-conocidos)

---

## 🚀 Primeros pasos

1. Instala [uv](https://docs.astral.sh/uv/) (el gestor de dependencias del proyecto).
2. Abre una terminal en la carpeta del proyecto y ejecuta `uv sync` (instala todo lo necesario).
3. Arranca la consola con `uv run python -m proxy_app.app`.
4. Abre el navegador en `http://127.0.0.1:5000/`. Verás la pantalla **Member Search** con el banner azul "MemberServ Console v4.2".
5. Escribe `M-1001` en el campo **Member ID or Name** y pulsa **Search** para probar.

La consola funciona 100% en local: no toca ninguna cuenta ni sistema real.

---

## 🔍 Buscar miembros

Encuentra a un miembro por número de identificación o por nombre.

### Cómo buscar

1. En la pantalla principal, escribe en **Member ID or Name** un ID (por ejemplo: `M-1001`), un nombre completo (`Alice Hartwell`) o una parte del nombre (`alice`).
2. Pulsa **Search**.
3. Si hay coincidencias, verás la tabla **Search Results** con el ID y el nombre de cada miembro.
4. Pulsa **View Detail** en la fila del miembro que te interesa.

### Lo que debes saber

- La búsqueda ignora mayúsculas/minúsculas y espacios de sobra.
- Puedes buscar por ID completo (`M-1002`) o por fragmento de nombre (`brian`).
- Con la búsqueda vacía no aparece ningún resultado.
- Si no hay coincidencias verás: `No records found. Member not found for "..."` (es el resultado normal de una búsqueda sin resultados, no una avería).

### Ejemplo

> Escribe `carla` y pulsa **Search**: aparece `M-1003 — Carla Mendes`. Pulsa **View Detail** para abrir su ficha.

---

## 👤 Ver la ficha de un miembro

Consulta los datos del miembro y el estado de sus cuentas.

### Lo que encuentras en la pantalla

- **Member ID**, **Full Name** y **Credit Limit** del miembro.
- La tabla **Accounts**: cada cuenta con su número, tipo (`checking`/`savings`) y saldo.
- El botón **New Loan Disbursement** para registrar un préstamo.
- El enlace **Back to results** para volver a la búsqueda.

### Miembros disponibles en los datos de ejemplo

| Member ID | Nombre | Cuentas | Límite de crédito |
|-----------|--------|---------|-------------------|
| `M-1001` | Alice Hartwell | `CHK-2201` (4250.75) · `SAV-5101` (15200.00) | 10000.00 |
| `M-1002` | Brian Okafor | `CHK-2202` (980.40) | 2500.00 |
| `M-1003` | Carla Mendes | `CHK-2203` (312.00) · `SAV-5103` (8700.50) | 500.00 |

---

## 💰 Registrar un préstamo

Flujo completo de desembolso de préstamo en tres pantallas: formulario, confirmación y recibo.

### Cómo hacerlo

1. Abre la ficha del miembro y pulsa **New Loan Disbursement**.
2. En **Disbursement account**, selecciona la cuenta de destino (verás el número, el tipo y el saldo actual).
3. Escribe el importe en **Amount**, por ejemplo: `250.50`.
4. Pulsa **Review Disbursement**. Si los datos son válidos, pasas a la pantalla de confirmación; si no, verás la lista de errores en rojo (más abajo).
5. Revisa el resumen: miembro, cuenta e importe.
   - Para ejecutar: pulsa **Confirm Disbursement**.
   - Para volver atrás: pulsa **Cancel** (el préstamo no se registra).
6. Al confirmar aparece el **recibo** con: número de desembolso (`DISB-0001`, `DISB-0002`...), miembro, cuenta, importe y el **saldo resultante** de la cuenta.

### Lo que debes saber

- **El importe debe ser mayor que 0** y **nunca superar el límite de crédito** del miembro (aparece en la ficha y en el formulario).
- El importe debe ser un número (acepta decimales con punto: `150.75`).
- Debes seleccionar una cuenta válida de ese miembro.
- La confirmación es obligatoria: nada se registra hasta pulsar **Confirm Disbursement**.
- La numeración de recibos (`DISB-0001`, `DISB-0002`...) avanza con cada desembolso de la sesión.
- El saldo resultante suma el saldo actual más los desembolos ya hechos a esa cuenta en la sesión.

### Ejemplo

> Con `M-1001`: selecciona `SAV-5101 (savings) - 15200.00`, escribe `250.50`, **Review Disbursement** -> **Confirm Disbursement**. El recibo muestra `Resulting Balance: 15450.50`.

---

## 🤖 Automatizar tareas con `discover`

El proyecto incluye un asistente que realiza una tarea en la consola por ti: le dices **qué quieres conseguir** en lenguaje normal y él va leyendo la pantalla, decidiendo el siguiente paso y ejecutándolo hasta lograrlo.

### Qué necesitas antes

1. La consola arrancada: `uv run python -m proxy_app.app` (sin reiniciar a mitad de tarea).
2. [Ollama](https://ollama.com/) funcionando en local con el modelo `qwen2.5-coder:7b`.
3. Google Chrome instalado.

### Cómo se usa

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta (poniendo tu meta y la dirección de inicio):

   ```bash
   uv run computer-use-automation-system discover --goal "Find the balance of member M-1001" --entry http://127.0.0.1:5000/
   ```

3. Mira el navegador: el asistente navega solo (busca, abre fichas, rellena formularios...).
4. Al terminar guarda dos archivos en `evidence/discovery/`:
   - `artifact.json` — el "plano" reutilizable de lo aprendido (lo que después podrá repetirse sin IA).
   - `steps.jsonl` — el registro paso a paso: qué hizo, por qué y con qué resultado.

### Opciones disponibles

| Opción | Qué hace | Por defecto |
|--------|----------|-------------|
| `--goal` | La tarea en lenguaje natural (obligatoria) | — |
| `--entry` | URL de inicio; tiene que empezar por `http://` o `https://` (obligatoria) | — |
| `--max-steps` | Pasos máximos antes de parar (número entero mayor que 0) | `15` |
| `--artifact-out` | Dónde guardar el artefacto JSON | `evidence/discovery/artifact.json` |
| `--log-out` | Dónde guardar el registro de pasos | `evidence/discovery/steps.jsonl` |

### Códigos de salida del comando

| Código | Significado |
|--------|-------------|
| `0` | Tarea completada con éxito |
| `10` | Bloqueado por la política de seguridad |
| `11` | Requiere aprobación de una persona |
| `12` | Se alcanzó el máximo de pasos |
| `13` | Se agotó el tiempo total |
| `14` | No encontró camino (dead-end) |
| `15` | Error del modelo de IA |
| `2` | Error de uso (argumentos mal escritos) |
| `130` | Interrumpido a mano con Ctrl+C |

### Lo que debes saber

- **No puede salirse de la consola**: la política de seguridad solo permite navegar dentro de `http://127.0.0.1:5000/`.
- **Los datos sensibles se enmascaran** (cifras, números de cuenta, nombres) en los archivos que guarda.
- Reinicia la consola antes de cada corrida si quieres partir de datos limpios.
- Si usas otro modelo u Ollama en otro puerto, ajusta `OLLAMA_MODEL` y `OLLAMA_BASE_URL` en el archivo `.env`.
- Las acciones irreversibles (como ejecutar un desembolso) se detienen y piden aprobación antes de pulsarse.

---

## 🔁 Repetir una tarea con `replay`

Cuando ya tienes un "plano" guardado (`evidence/artifact_example.json`, incluido en el proyecto, o uno que tú guardes con `discover`), puedes **repetirlo exactamente igual** cuantas veces quieras — sin inteligencia artificial, sin sorpresas y mucho más rápido.

### Qué necesitas antes

1. La consola arrancada: `uv run python -m proxy_app.app`.
2. Google Chrome instalado.
3. **No hace falta Ollama**: este comando no usa IA.

### Cómo se usa

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta indicando el plano y los datos de entrada (uno o varios `clave=valor`):

   ```bash
   uv run computer-use-automation-system replay --artifact evidence/artifact_example.json --input q=M-1001
   ```

3. Al terminar imprime un resumen: la capacidad, la versión, los datos extraídos (`outputs`) y cuántos pasos ejecutó.

### Opciones disponibles

| Opción | Qué hace | Por defecto |
|--------|----------|-------------|
| `--artifact` | Ruta al plano JSON (obligatoria) | — |
| `--input` | Dato de entrada como `clave=valor`; repítelo si son varios (mínimo uno, obligatorio) | — |
| `--approved` | Autoriza las acciones que normalmente esperan confirmación (como ejecutar un desembolso) | desactivado |
| `--max-timeout-ms` | Tiempo total máximo en milisegundos (número entero mayor que 0) | sin límite |
| `--interactive` | Si algo se atasca, pausa y te pregunta en la terminal qué hacer (ver [Intervención humana](#-intervención-humana-con---interactive)) | desactivado |

### Códigos de salida del comando

| Código | Significado |
|--------|-------------|
| `0` | Terminó con éxito (verificó la pantalla final y los datos pedidos) |
| `10` | Bloqueado por la política de seguridad |
| `11` | Necesita aprobación: vuelve a ejecutar con `--approved` (también si pausas con `--interactive` y eliges `abort` en una aprobación) |
| `1` | Falló en algún paso (datos de entrada, elemento no encontrado, pantalla final...) |
| `2` | Error de uso, el archivo del plano no existe / no es válido, o `config/taxonomy.json` o `config/policy.json` no son válidos |
| `130` | Interrumpido a mano con Ctrl+C |

### Lo que debes saber

- **Es determinista**: con el mismo plano y los mismos datos, siempre hace exactamente lo mismo.
- **Respeta la misma seguridad que `discover`**: no puede salirse de `http://127.0.0.1:5000/` y las acciones peligrosas siguen pidiendo `--approved`.
- **Si falla, te dice en qué punto**: el mensaje indica la etapa (`step`, `checkpoint`...) y el paso concreto, sin listados técnicos largos.
- **Los fallos llevan una categoría** (la palabra entre el paso y el motivo) para saber de un vistozo qué hacer:
  - `business_outcome`: la aplicación respondió bien y la respuesta *es* el resultado (por ejemplo, "No records found"). No es un fallo del sistema: no investigues nada.
  - `recoverable`: algo transitorio (la página tardó, un mensaje temporal). El sistema ya lo reintentó solo hasta 3 veces; si se agota, vuelve a ejecutar el comando más tarde.
  - `hard`: fallo real. Revisa la etapa y el paso que indica el mensaje.
- **Los avisos se ajustan a la aplicación sin tocar código**: si la consola cambia sus textos, actualiza los patrones en `config/taxonomy.json`.
- **Solo se muestran los resultados pedidos**: el resumen imprime los datos extraídos (`outputs`); los valores intermedios no se imprimen.

### Ejemplo

> `uv run computer-use-automation-system replay --artifact evidence/artifact_example.json --input q=M-1001`
> -> imprime `replay success: <capacidad> v1.0.0` y resume los pasos ejecutados (más los datos extraídos `outputs`, si el plano los define).
>
> Si el miembro no existe (`--input q=M-9999`), imprime algo como:
> `replay failure: stage=step step=5 business_outcome step 5 (click) failed: element_not_found; classified business_outcome: page pattern: No records found`
> -> no es un error del sistema: la aplicación respondió y su respuesta es "no hay registros".

---

## ⏸️ Intervención humana con `--interactive`

Cuando la repetición se atasca, en vez de terminar con error puedes pedir que **se pause y te pregunte**: decides tú, en la misma ventana del navegador, sin perder la sesión ni empezar de cero.

### Cómo se usa

1. Añade `--interactive` a cualquier comando `replay`:

   ```bash
   uv run computer-use-automation-system replay --artifact evidence/handoff_artifact.json --input member_id=M-1001 --interactive
   ```

2. Si algo se atasca, la terminal muestra el aviso con el contexto y la pregunta:

   ```
   handoff pause: trigger=hard_failure stage=step
   capability=lookup_member_balance v1.0.0 step=2 action=click
   reason=step 2 (click) failed: element_not_found; classified hard: page pattern: ...
   observed elements=42
   decision [resume|finish|abort]:
   ```

3. Mientras espera, **puedes usar tú el navegador**: la automatización no toca la página hasta que respondas.
4. Escribe la decisión y pulsa Enter.

### Las tres decisiones

- **`resume`** — la tarea sigue desde el mismo paso: reintentándolo, o ejecutando la acción pendiente si la pausa era una aprobación (equivale a `--approved`, pero solo para ese paso).
- **`finish`** — has terminado tú a mano lo que faltaba: se comprueba solo la pantalla final. Si está bien, termina con éxito; si no, falla (nunca da un éxito falso).
- **`abort`** — se detiene y termina con error: código `11` si la pausa era una aprobación, `1` si era un fallo.

### Lo que debes saber

- La pausa ocurre en 4 situaciones: **fallo duro**, **reintentos agotados**, **acción que necesita aprobación** y **paso riesgoso detectado antes de ejecutarse**.
- Sin `--interactive` nada cambia: el comando termina con error como siempre.
- Un bloqueo de seguridad (la política dice "no") **nunca** se pausa para preguntar: detiene la acción directamente.
- Cada paso se pausa como máximo una vez: si tras `resume` vuelve a fallar igual, el comando termina con error (no entra en bucle de pausas).
- Entrada vacía, cualquier texto distinto de `resume`/`finish`/`abort` (mayúsculas y espacios de sobra dan igual) o fin de entrada se interpreta como `abort`: nunca asume que dijiste que sí.
- Ctrl+C en el prompt aborta la tarea; Ctrl+C en cualquier otro momento interrumpe el comando (código `130`) y el navegador se cierra correctamente.
- Los textos del aviso (motivo, página observada) aparecen con los datos sensibles enmascarados.

### Ejemplo

> Una acción de desembolso necesita aprobación y no has pasado `--approved`:
> -> la corrida pausa con `trigger=risky_step` (el paso se detecta antes de ejecutarse), escribes `resume` y el desembolso se ejecuta ese único paso.
> -> si escribes `abort`, termina con código `11`, igual que sin `--interactive`.

---

## ⚠️ Avisos y errores que puedes ver

- **Caja roja "The form contains errors"** (formulario): aparece en el paso 2 del préstamo si el importe o la cuenta no son válidos. Corrige lo marcado y vuelve a pulsar **Review Disbursement**.
- **Caja amarilla "No records found..."** (búsqueda): no hay ningún miembro que coincida con lo escrito.
- **Línea `handoff pause:` en la terminal** (solo con `--interactive`): la tarea se ha pausado y espera tu decisión `resume`/`finish`/`abort` (ver [Intervención humana](#-intervención-humana-con---interactive)).
- **Línea `replay failure:` en la terminal**: el comando `replay` no ha terminado bien. La línea lleva la etapa (`stage`), el paso, la categoría del fallo (`business_outcome`, `recoverable` o `hard`) y el motivo; el código de salida es `1` (o `2` si el problema es la configuración).
- **Página "Page Not Found"** (404): has abierto la ficha o el formulario de un miembro que no existe (por ejemplo, un ID mal escrito a mano en la dirección). Verifica el ID y vuelve a la búsqueda.

---

## ❓ Preguntas frecuentes

**¿Los datos son reales?**
No. MemberServ es una simulación local con datos de ejemplo; no hay cuentas ni dinero reales.

**¿Puedo deshacer un préstamo?**
No hay botón de deshacer. Reinicia la aplicación y todo vuelve al estado inicial.

**¿Cuántos préstamos puedo registrar?**
Los que quieras. La numeración de recibos sigue `DISB-0001`, `DISB-0002`... mientras dure la sesión.

**¿Por qué no encuentro a un miembro?**
Comprueba el ID (los de ejemplo son `M-1001`, `M-1002` y `M-1003`) o busca por una parte del nombre, por ejemplo `alice`.

**¿Se guarda algo en un archivo o base de datos?**
No. Todo vive en memoria mientras la aplicación está abierta.

**¿La interfaz está en español?**
No, la consola MemberServ está en inglés (así la diseñó el sistema que simula). Esta guía te traduce lo importante.

---

## ⚠️ Problemas conocidos

- **Todo se reinicia al cerrar la aplicación**: saldos, desembolsos y numeración de recibos vuelven al estado inicial. Es intencionado (datos de ejemplo deterministas).
- **El puerto 5000 debe estar libre**: si otro programa lo usa, arranca con otro puerto: `$env:PROXY_APP_PORT=50000; uv run python -m proxy_app.app` (PowerShell) y abre ese puerto en el navegador.
- **Solo funciona en local**: la consola está pensada para `127.0.0.1` en tu equipo.
- **Los saldos mostrados en las cuentas no cambian al desembolsar**: el recibo sí calcula el saldo resultante, pero la ficha muestra siempre el saldo inicial de la sesión (limitación de la simulación actual).
