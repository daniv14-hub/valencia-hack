# Qué estamos haciendo y qué hace cada uno

## La idea en una frase
Cuando los vecinos de València proponen obras para su barrio (VLCParticipa), un técnico del
Ayuntamiento tiene que leerlas una a una para ver si son viables. En la última edición fueron
1.441 propuestas, y la fase tuvo que alargarse. Nuestro programa las lee primero, las ordena y
le dice al técnico: "estas 3 son la misma idea", "esta es de Costas, no nuestra", "esta es una
fiesta, no una obra". Y le deja escrita la carta para el vecino. **El técnico siempre decide.**

## Ejemplo real
Un vecino propone "lavabos en la playa de la Malvarrosa". Hoy un técnico lo lee, busca la
norma, decide que es competencia de Costas (Estado) y redacta la explicación. Con nuestro
panel aparece en rojo: "Competencia del Estado (Costas) – Ley de Costas", con la carta ya
escrita en castellano y valenciano. El técnico solo revisa y pulsa aceptar.

Y el vecino, antes de enviar, ya ve el aviso: "esto no lo puede hacer el Ayuntamiento"
o "ya hay 2 propuestas iguales en tu distrito, apóyalas".

## Cómo funciona por dentro (versión sencilla)
1. **Datos**: una lista de propuestas (archivo CSV, como un Excel).
2. **IA**: le pasamos cada propuesta a un modelo de lenguaje con las reglas de las bases.
   Devuelve para cada criterio sí, no o "que lo mire un técnico", y por qué.
3. **Duplicados**: comparamos textos en el ordenador, sin IA de pago.
4. **Panel**: una web (Streamlit) donde el técnico ve todo y decide.

## Tareas

### B — Datos (entrega en el minuto 30)
Rellenar `data/propuestas.csv` con estas columnas exactas:
`id,titulo,descripcion,distrito,barrio,presupuesto_estimado,origen,decision_real,motivo_real`
- **Unas 20 reales** copiadas a mano de vlcparticipa.valencia.es. `origen=real`. Si la web dice
  si se aprobó o se rechazó, ponlo en `decision_real` (viable / rechazada) y el motivo en `motivo_real`.
- **Unas 50 sintéticas** generadas con Claude. `origen=sintetica`. Mezcla:
  - 3–4 ideas repetidas por distintos vecinos en el mismo distrito.
  - Propuestas que no son del Ayuntamiento: playa (Costas), colegio o centro de salud
    (Generalitat), metro (FGV), tren (Adif).
  - Propuestas que no son obra: fiestas, talleres, contratar personal, pintar o reparar.
  - Muchas viables: bancos, sombras, juegos, carril bici, fuentes, iluminación.
- Además, 3 propuestas de exhibición para la demo en vivo: una viable, una de playa y una
  repetida de otra que ya esté en la lista.

### C — Motor de IA (no programa)
1. Ya: crear la clave en openrouter.ai con **límite de gasto de 4 $**. Elegir un modelo barato y
   rápido. Pasar a Dani el identificador exacto y el precio.
2. Ya: leer las bases oficiales (vlcparticipa.valencia.es/help) y corregir `criterios.md`:
   qué cuenta como inversión, el presupuesto por distrito y si hay un máximo por propuesta.
3. Minuto 30: con el CSV de B, revisar los resultados del lote. ¿Tienen sentido los motivos?
   Contar en cuántas propuestas reales acierta la IA: ese es nuestro número del pitch.

### D — Pitch (lo que más puntúa)
- Guion de 2 min: problema (cifras oficiales) → demo de 30–40 s → cómo se implantaría → impacto
  → "la IA propone, el técnico decide".
- Antes de ponerlas en una diapositiva, comprobar en fuentes oficiales: si la validación se
  amplió 3 semanas, si hubo unas 980 descartadas, el mínimo de apoyos y los 16 M€.
- Preparar respuestas: ¿y si la IA se equivoca? (no decide, solo sugiere). ¿Y los datos
  personales? (no se envían datos del vecino, solo el texto de la propuesta). ¿Cuánto cuesta?
  (céntimos por propuesta, se ve en el panel).

### Dani — App (Claude Code)
Integrar todo, pulir el panel, preparar la demo en vivo y grabar el vídeo de respaldo.

## Horario
| Minuto | Hito |
|---|---|
| 30 | CSV de B, clave y modelo de C |
| 50 | Lote clasificado y revisado |
| 75 | Se congela el código |
| 75–90 | Ensayo y vídeo de respaldo |
