# CLAUDE.md – Pre-filtro de propuestas VLCParticipa

## Contexto (no repetir en respuestas)
- Hackathon ValènciaHack 2026 (Sigma Data Club, UPV, Cátedra Valent-IA, Ajuntament de València). Reto 2: modernizar la administración con tecnología. Jurado: personal del Ayuntamiento. Pitch de 2 min. Se valora más la idea que la ejecución; un chatbot NO vale.
- Producto: **Pre-filtro de propuestas VLCParticipa** 🔍, un pre-filtro de IA para la validación técnica de propuestas de VLCParticipa (presupuestos participativos, plataforma CONSUL). Edición 2025-26: 2.777 propuestas, 1.441 en validación técnica manual, 248 aprobadas.
- Principio: **la IA señala, el técnico decide**. La IA no decide nada: solo señala alertas. El técnico revisa todas las propuestas y toma todas las decisiones.
- Nombres únicos de alerta en todo el proyecto: 🔁 `duplicado` (la calcula la app con `duplicates.py`, no el LLM), 🏛️ `fuera_competencia` (otra administración), 💶 `fuera_presupuesto` (supera la partida oficial del distrito; sin presupuesto = nota informativa, no alerta), 🎉 `no_inversion` (actividad, gasto corriente, mantenimiento). Sin alertas = «Sin alertas · a priori viable».
- Objetivo de la demo: un panel web que muestre al funcionario las propuestas con sus alertas y agrupadas, más una vista del vecino con avisos en vivo.

## Estado actual (funciona)
- `app.py` (Streamlit): usa `classify_dict`. Las filas con `demo=si` no entran en la bandeja (se teclean en vivo en la vista del vecino). Indicadores (propuestas, sin/con alertas, una por tipo, grupos de duplicados, tiempo de cribado estimado ahorrado) y métricas de `batch.metricas`. Bandeja con una columna por alerta y «Decisión del técnico»; detalle con cada alerta + norma, `puntos_a_revisar`, edición y votos en las reales, botones Confirmar/Descartar alerta y Validar propuesta (session_state); borrador de carta es/va («revisar antes de enviar»); vista del vecino con avisos orientativos. No usa las palabras Aprobada/Rechazada/Viable/Rechazo.
- Métricas (`batch.metricas`, compartida por app y `batch.py`, sin filas demo, duplicados incluidos):
  - Reales: «Sin falsas alarmas en X de N aprobadas por los técnicos» + lista de falsas alarmas.
  - Sintéticas: «Alertas que coinciden con lo esperado: X/Y». `duplicado:A` acierta si está agrupada con todas las demás de la etiqueta A; con `|` deben estar todas; `sin_alertas` = ninguna alerta.
- `classify.py`: motor de C (`motor_C/classify.py`, probado con el lote real). `classify(titulo, descripcion, distrito, presupuesto_estimado)` llama a OpenRouter con `requests`, tipos en mayúsculas, caché en `cache_clasificacion.json`, regla fija: estimado > partida del distrito → `FUERA_PRESUPUESTO`. Cambios nuestros: lee `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` de `.env` (python-dotenv); distrito «Ciudad» sin regla de partida (solo desproporción > 5 M€); `classify_dict(p) -> dict` para la app (tipos en minúsculas, modo simulado sin clave, lanza excepción si el LLM falla).
- `criterios.md`: el de C (bases oficiales, partidas por distrito 2025-26).
- `duplicates.py`: TF-IDF de caracteres + coseno + componentes conexas, solo dentro del mismo distrito. TF-IDF ajustado una vez con el CSV sin filas demo; lo escrito en vivo se compara sin reentrenar. `UMBRAL` 0.38 para los grupos del panel (excluye R13/R18; S08 y el grupo A quedan fuera) y `UMBRAL_VECINO` 0.25 para los avisos al vecino (DEMO03 → S01, S02).
- `batch.py`: CSV → `data/clasificacion.json` con `classify_dict`, reanudable, 1 hilo (el caché no es seguro con hilos); imprime métricas y coste.
- `data/propuestas.csv`: CSV de B, 31 reales + 50 sintéticas + 3 demo. Último lote real: 0,084 $.
- `motor_C/`: copia de referencia del motor de C.

## Contratos de datos (NO cambiar sin avisar al equipo)
CSV: `id,titulo,descripcion,distrito,barrio,presupuesto_estimado,origen,decision_real,motivo_real,edicion,votos,demo,alerta_esperada`
- `origen` ∈ {real, sintetica}; `decision_real` ∈ {viable, rechazada, ""}; `demo` ∈ {si, no}; `alerta_esperada` = `sin_alertas` o tipos separados por `|` (`duplicado:<letra>` para grupos).
JSON por propuesta (`classify_dict`): `id, alertas: [{tipo ∈ {duplicado, fuera_competencia, fuera_presupuesto, no_inversion}, texto, mensaje, norma, administracion (solo en fuera_competencia)}], puntos_a_revisar, resumen, borrador_carta_es, borrador_carta_va, coste_usd, segundos, modelo, modo ∈ {llm, cache, mock}`.
- Lista vacía = «Sin alertas · a priori viable». El LLM nunca genera `duplicado`: la app lo añade desde `duplicates.py`.
- La carta es siempre un borrador que el técnico revisa.

## Reglas de trabajo
- Respuestas cortas. Cambios mínimos y localizados (Edit, no reescribir archivos). Sin refactors no pedidos.
- La demo nunca debe romperse: si falla el LLM, se usa el JSON guardado o el modo simulado.
- Nunca subir `.env` ni la clave. Gasto máximo de API: 4 $.
- No inventar datos oficiales; las cifras estimadas se etiquetan como estimación en la interfaz.
- Diseño sobrio e institucional, en castellano. Las cartas, también en valenciano.
- Probar con: `streamlit run app.py` o el test headless con `streamlit.testing.v1.AppTest`.

## Pendiente (en orden)
1. Pulir el diseño y congelar en el minuto 75. Grabar el vídeo de respaldo.
