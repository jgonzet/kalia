# KALIA — Visión del producto

> Documento de dirección: hacia dónde va el producto y por qué. No es una lista de tareas: el trabajo pendiente vive en GitHub Issues y el alcance de V0 vive en `docs/SPEC.md`.
> Leer antes de proponer arquitectura o alcance. Lo que no está escrito acá no forma parte de la visión. Documento vivo: se agregan ideas a medida que se definen.

## Qué es KALIA

Un copiloto, o avatar, que actúa como el subconsciente del usuario. Capta toda la información que el usuario recibe (mails, chats, agendas, transcripciones de reuniones, documentos), la destila y con eso construye y mantiene el contexto del usuario: vínculos, proyectos, deadlines, agenda, el tipo de vínculo con cada stakeholder en cada proyecto (jefes, proveedores, pares) y los avatares de otros usuarios. Reside en segundo plano en la PC del usuario.

No es un gestor de tareas, ni un dashboard empresarial, ni un chatbot genérico. Es un copiloto contextual con memoria organizacional persistente que reduce la carga cognitiva del usuario: ya no tiene que reconstruir mentalmente el caos de su trabajo.

## Usuarios

Managers, PMs, tech leads y roles de founder/operador. Contexto típico: múltiples proyectos, exceso de reuniones, stakeholders complejos, burocracia y cambio constante de contexto, en empresas medianas o grandes o en entornos operativos caóticos.

## Qué extrae el avatar de la información

Fuentes: mails, transcripciones de reuniones, chats (por ejemplo Teams) y el resto de la información que el usuario recibe. De cada una extrae, entre otras cosas (ejemplos, no una lista cerrada):

- Las personas que participan.
- El cargo de cada una.
- La relación de cada una con el usuario (par del mismo nivel, jefe, etc.).
- Los compromisos.
- El contexto del vínculo: si es cálido, frío, autoritario, etc.

## Comportamiento: activo, no reactivo

En todo lo que sigue, el avatar propone y el usuario decide. Son ejemplos, no una lista cerrada:

- Propone enviar mails, mostrando antes un borrador que usa el contexto completo del mail a enviar.
- Sugiere reservar espacios en la agenda o enviar invitaciones a reuniones con personas específicas.
- Propone minutas de reuniones.
- Escucha activamente durante las reuniones: avisa al usuario cuando se habla de algo importante y le sugiere preguntas para intervenir.

## Aprendizaje e incertidumbre

- Consume diariamente toda la información que va llegando.
- Le pregunta al usuario lo que no sabe, en vez de arriesgarse a inferirlo.
- Aprende cómo trabajar con cada usuario.

## Red de avatares

Los avatares de distintos usuarios pueden hablar entre sí e intercambiar información para enriquecer el contexto de cada uno. El intercambio es muy controlado y no bidireccional: los privilegios dependen de la jerarquía. Por ejemplo, un jefe puede consultar información de los avatares de las personas a su cargo; a la inversa no funciona igual.

## Requisitos de diseño

- Modular: cada módulo puede escalar y evolucionar por separado.
- Las piezas clave están pensadas para durar mucho tiempo. El producto crece a partir de una primera versión chica, manteniendo siempre un producto funcionando mientras se refactoriza y se amplía.

## Posibles expansiones

Solo temas: sin orden y sin estado. El trabajo concreto pasa a ser GitHub Issues cuando está listo para encararse.

- Conectores para cada fuente real (mail, chat, transcripciones).
- Calendario y dimensión temporal.
- Vínculos inferidos por stakeholder y por proyecto (cargo, relación jerárquica, tono del vínculo).
- Sugerencias proactivas y priorización.
- Redacción y acciones de reuniones (mails, invitaciones, minutas).
- Escucha de reuniones en vivo.
- Preguntas de aclaración y aprendizaje por usuario.
- Red de avatares con privilegios jerárquicos.
- Proceso residente en segundo plano en la PC del usuario.

## V0 como primer paso

V0 valida el pipeline base para un solo usuario: los documentos se convierten en contexto estructurado, se guardan y se usan para responder preguntas. No tiene comportamiento proactivo. Su alcance y sus restricciones están definidos en `docs/SPEC.md`.
