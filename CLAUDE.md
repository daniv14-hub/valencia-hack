# CLAUDE.md – Copiloto VLCParticipa

## Contexto (no repetir en respuestas)
- Hackathon ValènciaHack 2026 (Sigma Data Club, UPV, Cátedra Valent-IA, Ajuntament de València). Reto 2: modernizar la administración con tecnología. Jurado: personal del Ayuntamiento. Pitch de 2 min. Se valora más la idea que la ejecución; un chatbot NO vale.
- Producto: copiloto de IA para la **validación técnica** de propuestas de VLCParticipa (presupuestos participativos, plataforma CONSUL). Edición 2025-26: 2.777 propuestas, 1.441 en validación técnica manual, 248 aprobadas.
- Principio: **la IA propone, el técnico decide**. Nada se rechaza automáticamente.
- Objetivo de la demo: un panel web que muestre al funcionario las propuestas clasificadas y agrupadas, más una vista del vecino con avisos en vivo.

## Estado actual (funciona)
- `app.py` (Streamlit): indicadores, bandeja filtrable, detalle con los 3 criterios ✅/❌/❔ + norma, botones de decisión (session_state), duplicados, carta de rechazo es/va, pestaña "Nueva propuesta" que clasifica en vivo y la añade a la bandeja.
- `classify.py`: `classify(dict)->dict`. Con `OPENROUTER_API_KEY` en `.env` usa OpenRouter (SDK de OpenAI, `base_url=https://openrouter.ai/api/v1`, `OPENROUTER_MODEL`, temperature 0, JSON validado con Pydantic, 1 reintento, coste desde `usage`). Sin clave usa el **modo simulado** con regex.
- `criterios.md`: prompt de sistema (criterios y tabla de competencias). BORRADOR pendiente de validar con las bases oficiales.
- `duplicates.py`: TF-IDF de caracteres + coseno + componentes conexas, solo dentro del mismo distrito. Umbral 0.35.
- `batch.py`: CSV → `data/clasificacion.json`, reanudable; mide aciertos frente a `decision_real`.
- `data/propuestas.csv`: 18 filas sintéticas de ejemplo (se sustituyen por las de B).

## Contratos de datos (NO cambiar sin avisar al equipo)
CSV: `id,titulo,descripcion,distrito,barrio,presupuesto_estimado,origen,decision_real,motivo_real`
- `origen` ∈ {real, sintetica}; `decision_real` ∈ {viable, rechazada, ""}.
JSON por propuesta: `id, estado_sugerido ∈ {viable, revisar, rechazo_sugerido}, criterios.{competencia,inversion,presupuesto}.{ok: bool|null, motivo, norma}, confianza, resumen, borrador_carta_es, borrador_carta_va, tokens_in, tokens_out, coste_usd, segundos, modelo, modo`.

## Reglas de trabajo
- Respuestas cortas. Cambios mínimos y localizados (Edit, no reescribir archivos). Sin refactors no pedidos.
- La demo nunca debe romperse: si falla el LLM, se usa el JSON guardado o el modo simulado.
- Nunca subir `.env` ni la clave. Gasto máximo de API: 4 $.
- No inventar datos oficiales; las cifras estimadas se etiquetan como estimación en la interfaz.
- Diseño sobrio e institucional, en castellano. Las cartas, también en valenciano.
- Probar con: `streamlit run app.py` o el test headless con `streamlit.testing.v1.AppTest`.

## Pendiente (en orden)
1. Clave y modelo de C → `.env` → `python classify.py` (1 llamada de prueba).
2. CSV de B → `rm data/clasificacion.json && python batch.py --limit 3`, revisar, y luego el lote completo.
3. Ajustar `UMBRAL` de duplicados con los datos reales.
4. Pulir el diseño y congelar en el minuto 75. Grabar el vídeo de respaldo.
