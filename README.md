# Copiloto VLCParticipa

Validación técnica asistida de propuestas de presupuestos participativos (ValènciaHack 2026, Reto 2).
**La IA propone, el técnico decide.**

## Arrancar
```bash
pip install -r requirements.txt
cp .env.example .env      # sin clave funciona en modo simulado
streamlit run app.py
```

## Archivos
| Archivo | Qué hace |
|---|---|
| `app.py` | Panel del técnico: indicadores, bandeja, detalle por criterio, duplicados, cartas es/va, vista vecino en vivo |
| `classify.py` | Clasifica una propuesta con el LLM (OpenRouter) o en modo simulado |
| `criterios.md` | Prompt de sistema: criterios de las bases y tabla de competencias |
| `duplicates.py` | Detección de duplicados en local (TF-IDF, sin coste) |
| `batch.py` | Clasifica `data/propuestas.csv` → `data/clasificacion.json` y mide aciertos frente a casos reales |

## Con la clave real
```bash
python batch.py --limit 3   # prueba barata
rm data/clasificacion.json && python batch.py
```
