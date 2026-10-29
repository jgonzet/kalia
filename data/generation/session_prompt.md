---
version: v0
---

# Prompt de la sesión generadora

Versión v0: línea base. Para compararla con una v1, correr las mismas tandas y contar por tanda los hallazgos de la revisión manual (compromisos faltantes o sobrantes, `due_text` alterado, compromisos en forma de lista, contradicciones con `story.md`). Se pega entero al abrir la sesión, con la tanda completada al final.

---

Sos la sesión que **genera** los documentos sintéticos de `data/lamanija/`. Otra sesión los revisa y los acepta. Vos no revisás, no aceptás y no tocás ningún otro archivo que los documentos.

**Tanda a escribir:** `lamanija-____` a `lamanija-____`.

## Qué hacer

1. Leé `CLAUDE.md` y la sección "Generating documents" de `docs/DATASET.md`, y seguí ese procedimiento: `data/generation/base.md`, el `types/` de cada documento, todos los `fields/`, el catálogo de `data/lamanija/`, `story.md` entero y los `expected` de la tanda. Por cada id en `mentions`, leé también ese compromiso en su `expected` y, si ya existe, el texto de su documento.
2. Antes de generar documentos nuevos, releé los que ya existen en `data/lamanija/documents/` para mantener la coherencia de las historias.
3. Escribí `data/lamanija/documents/<id>.md` para cada documento de la tanda, en orden de id.
4. Corré `uv run scripts/dataset/check_dataset.py --allow-pending` y arreglá lo que marque en tus textos.
5. Releé cada texto contra su `expected`: que contenga exactamente sus compromisos, con el plazo escrito como el `due_text`, sin listas.

## Qué no hacer

- No modifiques `expected/`, `story.md`, el catálogo ni `data/generation/`. Si algo no se puede escribir tal como está (un compromiso contradice un hecho de `story.md`, una fecha no cierra con el calendario, un `brief` es ambiguo), **pará y avisá** en vez de improvisar.
- No corras `--stamp`, no hagas commit ni push.

## Qué reportar al terminar

Por cada documento: una línea con lo raro que viste (o "nada"), y cuáles textos conviene mirar primero. Sin resumir el contenido de los textos.
