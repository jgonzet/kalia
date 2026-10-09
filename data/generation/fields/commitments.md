# Campo: compromisos

Un compromiso es: alguien (`who`) le promete a otro (`to_whom`) hacer algo (`what`), con o sin fecha (`due`/`due_text`), y lo acepta en el texto. La clave de respuestas (`extractions.commitments`) trae la lista completa de cada documento.

- Cada compromiso se puede leer del texto, con `who`, `to_whom` y `what`. No hay ninguno más: nada de "después te aviso" ni "lo miro" con dueño y acción claros.
- Aparecen en texto natural, dentro de la conversación. Nunca como lista, viñetas ni tabla de tareas.
- El plazo se escribe tal como el `due_text`, sin convertirlo a fecha absoluta, y es coherente con la fecha del documento y con el `due` real. Si `due_text` es `null`, no pongas plazo.
- Quien asume el compromiso lo acepta en el texto. En un mail, la respuesta va dentro del mismo documento (mail citado o respuesta debajo).
- Un compromiso de `mentions` se nombra ("lo que quedó con Frink", "como dijo Marge") sin volver a prometerlo ni darle un plazo nuevo.
- `not_commitments` describe una idea (por ejemplo, un condicional o una intención vaga). Escribila con palabras naturales, bien reconocible y sin que nadie se obligue. Nunca copies la descripción ni su aclaración entre paréntesis.
- Si la lista del `expected` está vacía, el documento no contiene ningún compromiso.
