---
id: lamanija-0009
type: meeting
date: 2026-09-24
participants: Lalo Landa, Seymour Skinner, Profesor Frink, Edna Krabappel, Manjula Nahasapeemapetilon
---
Skinner: Vamos al grano que hay mucho para ver. Netcode cooperativo de Choripixels, reconexiones y sincronización. Frink, vos primero, que tenés el resumen.

Frink: Sí. Con lo que armé en el resumen de la sincronización para hoy, el problema grande es la reconexión. Cuando alguien se cae y vuelve, el cliente queda con un estado viejo y el servidor tarda en darse cuenta. En la alpha del 18 con dos jugadores se vio clarísimo.

Skinner: Y hoy, cuando se cae uno, el otro se queda esperando.

Frink: Peor. Se rompe la partida. Lo que habría que hacer es dar un tiempo de gracia: si volvés dentro de unos segundos, retomás donde estabas. Eso en principio no es complicado, pero toca varias cosas.

Skinner: ¿Podés armar esa propuesta?

Frink: Dale, armo la propuesta de reconexión con tiempo de gracia en tres semanas.

Skinner: Perfecto.

Edna: Yo tengo una duda sobre eso. Para que el servidor sincronice el movimiento, los eventos de movimiento tienen que ser algo que se pueda leer desde afuera. Ahora están metidos dentro del controlador del personaje.

Frink: Es verdad, sin eso no puedo sincronizar nada.

Edna: Entonces expongo los eventos de movimiento para que puedas sincronizarlos el martes 13.

Frink: Dale, gracias. Con eso me desbloqueás.

Skinner: Hay otra cosa. No podemos probar las reconexiones bien si no tenemos una forma de forzar problemas de red. Manjula, ¿eso es algo que puedas hacer?

Manjula: Una herramienta que simule pérdida de paquetes, sí. No es difícil, pero tengo que ver cómo engancharla al juego. Te la armo para el 20 de octubre.

Skinner: Me sirve.

Lalo: Yo en todo esto no toco código, pero me preocupa la parte de las pruebas. Con tantas cosas nuevas, QA tiene que dedicarle tiempo en serio. Skinner, yo coordino con Milhouse horas de QA para probar el netcode, así cuando estén las piezas ya tienen gente probando.

Skinner: Buenísimo. Es lo que me faltaba.

Frink: Una cosa más, ¿vamos a querer jugar con más de dos jugadores?

Skinner: Por ahora el objetivo es dos, después vemos. No hay que abrir otro frente.

Edna: Mejor. Con dos ya tenemos bastante lío.

Manjula: Eso mismo.

Skinner: Bueno, entonces estamos. Gracias a todos.
