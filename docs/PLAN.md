# Plan — Issue #2: dataset sintético y prompts del generador

> Plan de trabajo vivo. Cada sección tiene un estado: `[OPEN]` o `[RESOLVED]`. Una sección `[RESOLVED]` no se vuelve a mostrar salvo que se reabra.

## 1. Contexto [RESOLVED]

V0 necesita datos para probar extracción, almacenamiento, recuperación y chat. Este issue produce **solo archivos** (sin código de la app): una empresa ficticia, 25 documentos escritos por un chatbot externo (Gemini/ChatGPT) y la "clave de respuestas" de cada documento, para después comprobar si la extracción acierta.

## 2. Orden de trabajo y cómo se crean los compromisos [RESOLVED]

Los compromisos **los inventamos nosotros primero**; el chatbot después escribe textos que los contienen. Orden:

1. Catálogo: personas, proyectos, protagonista.
2. Diseñar, documento por documento, qué compromisos se "plantan" (quién, a quién, qué, para cuándo). Se diseñan hacia atrás desde las 5 preguntas de aceptación (ej. Q4 "compromisos con mi jefe" exige varios compromisos protagonista-jefe en más de un documento). Esto es la clave de respuestas (`expected`).
3. Escribir los prompts del generador. El prompt de cada tanda lleva la clave de respuestas: "escribí un mail donde Marcos le promete a Laura el presupuesto para el 18/09, sin listarlo".
4. Generar los 25 documentos en tandas chicas y revisar una muestra a mano.

Los prompts van **antes** de generar, siempre. Casos a cubrir al diseñar (paso 2): Q1 compromisos en ambos sentidos con una persona; Q2 vencimientos dentro, antes y después de la semana de referencia; Q3 una persona en varios compromisos; Q4 jefe en más de un documento; Q5 un documento reservado para ingerir al final y que cambie una respuesta; plazos relativos ("el viernes") y absolutos; compromisos sin fecha; documentos sin compromisos; reuniones de 3+ personas. Un mismo compromiso repetido entre documentos queda afuera (issue #4).

## 3. Estructura de carpetas [RESOLVED]

```text
data/
  generation/                 prompts del generador (compartidos por todas las empresas)
    base.md                   reglas generales (idioma, tono, formato del encabezado)
    types/email.md meeting.md chat.md      estilo por tipo de documento
    fields/commitments.md     cómo pedir que se incluyan compromisos
  <empresa>/                  ej. data/acme/ ; una segunda empresa = otra carpeta hermana
    company.json              datos de la empresa y id del protagonista
    people.jsonl              una persona por línea
    projects.jsonl            un proyecto por línea
    documents/acme-0004.md    encabezado + texto libre. Lo ÚNICO que lee el pipeline
    expected/acme-0004.json   clave de respuestas del documento con el mismo id
```

El nombre de la empresa se decide en el paso 1 del trabajo.

## 4. Nombre "documents" [RESOLVED]

Propuesta: **mantenerlo**. Es el término de la SPEC y del código (`Document`, `document_id`, `document_date`); cambiarlo en la carpeta rompería la trazabilidad con el código y las pruebas. Alternativas vistas: `sources` (choca con "fuentes" de la visión y con el issue #3), `inputs`/`items` (vagos), `corpus` (técnico y sin uso en el repo). La ambigüedad se resuelve por contexto: vive dentro de `data/<empresa>/` y la SPEC lo define como "cualquier pieza de entrada: mail, transcripción o chat".

El id es único entre empresas (`<empresa>-NNNN`, 4 dígitos), porque la ingesta es idempotente por id y dos empresas no deben colisionar.

## 5. Catálogo expandible: JSONL [RESOLVED]

Se evaluó JSON único vs JSONL. **JSONL**, un archivo por tipo de entidad:
- Agregar una persona o proyecto = agregar una línea (diffs limpios, sin editar un objeto gigante).
- Un campo nuevo no rompe líneas viejas, y un tipo de entidad nuevo (ej. clientes, equipos) = otro archivo `.jsonl`.
- Cada registro lleva `id` estable y `company`, lo que permite varias empresas y, más adelante, un archivo de vínculos entre ellas (no se diseña ahora).
- Costo: menos cómodo de leer que JSON indentado; las entidades son planas, así que es chico.

Ejemplo de línea de `people.jsonl`: `{"id":"acme-p03","company":"acme","name":"...","role":"...","area":"...","level":2,"reports_to":"acme-p01"}`. `company.json` es un único objeto (nombre, `user_id` del protagonista). El cargador (otro issue) traduce ids a los nombres que usa el modelo V0.

## 6. Clave de respuestas (`expected`) escalable y trazable [RESOLVED]

Un archivo por documento, mismo id que el documento, formato JSON:

```json
{
  "document_id": "acme-0004",
  "company": "acme",
  "type": "email",
  "date": "2026-09-14",
  "participants": ["Marcos Paz", "Laura Ríos"],
  "text_sha256": null,
  "extractions": {
    "commitments": [
      {"who": "Marcos Paz", "to_whom": "Laura Ríos", "what": "enviar el presupuesto revisado", "due": "2026-09-18", "project": "Portal Clientes"}
    ]
  }
}
```

- **Escalable:** cada campo a extraer es una clave dentro de `extractions`. Agregar "bloqueos" o "decisiones" = una clave nueva, sin tocar las existentes. Clave **ausente** = "no anotado, no evaluar". Lista **vacía** = "se anotó y no hay nada que extraer".
- **Doble chequeo de identidad** (nombre de archivo solo no alcanza): `document_id`, `type`, `date` y `participants` se repiten desde el encabezado del documento y deben coincidir. `text_sha256` guarda el hash del texto aceptado: si el documento se regenera o edita y la clave queda vieja, el chequeo lo detecta. Empieza en `null` y se completa al aceptar el documento.
- Los nombres de personas/proyectos coinciden con el catálogo y con `Commitment` (V0 vincula por nombre).

## 7. Script de verificación del dataset [RESOLVED]

`scripts/check_dataset.py` (solo librería estándar, sin dependencias nuevas): comprueba que cada documento tenga su `expected` y viceversa, que el id del archivo coincida con el del encabezado, que `type`/`date`/`participants` coincidan, que el hash coincida (con `--stamp` lo completa), y que los nombres usados existan en el catálogo. Justificación: protege la trazabilidad que pediste y escala a cientos o miles de documentos sin revisión manual de lo mecánico. Queda a revisión manual lo que el script no puede ver: que el texto realmente contenga el compromiso.

## 8. Prompts escalables [RESOLVED]

Prompt de una tanda = `base.md` + `types/<tipo>.md` + extracto del catálogo + clave de respuestas de los documentos de la tanda, con las instrucciones de `fields/<campo>.md`. Agregar un campo a extraer = un archivo nuevo en `fields/`; agregar un tipo de fuente = uno nuevo en `types/`. Se arma a mano (copiar y pegar) al principio; un script solo si resulta tedioso. Son archivos separados, igual que los prompts de la app (DECISIONS: "Prompts as separate files").

## 9. Archivos vs base de datos [RESOLVED]

Pregunta: ¿los JSONL tienen que migrar a una base de datos? **No hace falta migrar los archivos.** La app ya guarda todo en SQLite (DECISIONS: "Storage: SQLite"); el cargador del dataset lee estos archivos y los inserta en SQLite. Los archivos son la fuente del dataset de prueba (como un fixture), no el almacenamiento de la app. Empezar con base de datos ahora no conviene: (a) el módulo de almacenamiento todavía no existe, (b) un chatbot y vos tienen que poder crear, leer y revisar el dataset como texto, con diffs en git, y una base no sirve para eso. Por eso no se abre un issue de migración; el paso "archivos -> SQLite" ya es el issue del cargador (se propone al cierre). Si algún día el catálogo se edita desde la app, la base pasaría a ser la fuente: es una decisión de V1 y no se puede verificar desde hoy.

## 10. Sesiones e issues [OPEN]

No se hace todo en una sesión. Lo que no entra hoy se levanta como issue y va a `## Next` de `docs/PROGRESS.md` (con el hash actualizado). Etiqueta `type: feature` y milestone `V0` en todos (existen en el repo). Propuesta, a confirmar antes de correr `gh`:

- **#2 (existente)**: se acota a "Design the synthetic catalog and the dataset layout" (esta sesión): plan copiado a `docs/PLAN.md`, `data/<empresa>/company.json`, `people.jsonl`, `projects.jsonl`.
- **Nuevo A**: "Design the expected commitments for the 25 documents" (clave de respuestas + tabla pregunta de aceptación -> documentos).
- **Nuevo B**: "Write the generator prompts and the dataset check script" (`data/generation/`, `scripts/check_dataset.py`).
- **Nuevo C**: "Generate and review the 25 synthetic documents" (tandas de 5, revisión manual, hash).

`## Next` quedaría: 1. #2 · 2. A · 3. B · 4. C. Al cerrar C, `/close-feature`, se registran en `docs/DECISIONS.md` las decisiones de estructura (JSONL, expected separado, ids por empresa, hash), se agrega una nota de `data/` al README y se proponen los issues del cargador y del script de evaluación contra `expected/`.

## 11. Revisión del plan [RESOLVED]

- Supuesto no verificado: que el chatbot respete la clave de respuestas. Se mitiga con la revisión manual de cada tanda.
- No hay sobreingeniería de código: solo un script chico. Lo más "extra" son el hash y los ids por empresa, que responden a trazabilidad y a la segunda empresa que pediste.
- Seguridad: todo sintético; no hay datos reales, credenciales ni cambios en `.gitignore`.

## Verificación

- Para cada pregunta de aceptación hay una tabla con los documentos que la responden.
- `uv run scripts/check_dataset.py` sin errores.
- Muestra revisada a mano en cada tanda.
