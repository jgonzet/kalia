# Reglas generales de generación

Vas a escribir documentos de trabajo de una empresa ficticia. Cada documento tiene una clave de respuestas (`expected`) que dice qué compromisos contiene. Escribís el texto; la clave ya está hecha y no se modifica.

## Reglas

- Respetá `data/<empresa>/story.md`: sus hechos son verdad en todos los documentos. No los contradigas ni inventes fechas o compromisos que choquen con ellos.
- Español rioplatense, informal y plano, como se escribe en el trabajo. Sin emojis salvo que el tipo de documento lo pida.
- No inventes hechos que otro documento pueda contradecir: cifras, fechas, decisiones. Si un documento los necesita, se agregan primero a `story.md`.
- Coherencia temporal: no hables como ya ocurrido de nada fechado después del documento. Todo el documento (incluidas las respuestas de un mail) ocurre en la fecha del `expected`, y los días de la semana que nombres tienen que coincidir con el calendario real.
- Usá solo las personas y los proyectos del catálogo; no agregues personas. Solo los participantes escriben, hablan o asumen compromisos; otros pueden ser nombrados. En `De:`, `Para:` y `Cc:` va el nombre completo del catálogo; en el cuerpo y en las etiquetas de turno, el nombre corto habitual (Lalo, Smithers, Frink), nunca "Bouvier" solo porque hay dos.
- Largo: el que indica el `brief`; si no dice nada, corto. El texto tiene que alcanzar para que entren todos sus compromisos.
- El texto contiene solo lo que su `expected` indica, y nada más. Quien recibe cada compromiso (`to_whom`) tiene que ser identificable en el texto.
- Sin direcciones de mail, teléfonos ni URLs, y sin comentarios tuyos antes ni después del texto.

## Qué más leer

- `types/<tipo>.md`: cómo se ve el tipo de documento (`email`, `meeting`, `chat`). Leé el del documento que escribís.
- `fields/*.md`: qué tiene que contener el texto por cada campo que la app extrae (hoy, `commitments.md`). Leelos todos.

## Formato del archivo

`data/<empresa>/documents/<id>.md`, con el encabezado definido en `docs/DATASET.md` (`id`, `type`, `date`, `participants`, copiados del `expected`) y después el texto libre. El texto de un mail incluye `De:`, `Para:`, `Cc:` (si hay) y `Asunto:`.
