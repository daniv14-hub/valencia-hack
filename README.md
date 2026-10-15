# 🔍 Garbell · Pre-filtro de propuestas VLCParticipa

Asistente para la validación técnica de los presupuestos participativos de València ·
**La IA señala, el técnico decide.** (ValènciaHack 2026, Reto 2)

## Cómo ejecutar la app

Para que funcione en otro ordenador, ejecuta estos comandos en el terminal, en orden:

```bash
# 1. Descarga el proyecto y entra en su carpeta
git clone https://github.com/daniv14-hub/valencia-hack.git && cd valencia-hack

# 2. Crea un entorno virtual de Python y actívalo (las librerías se instalan ahí, no en el sistema)
python3 -m venv .venv && source .venv/bin/activate

# 3. Instala las librerías que necesita la app
pip install -r requirements.txt

# 4. Crea tu archivo de configuración a partir de la plantilla
cp .env.example .env

# 5. Arranca la app; se abre en el navegador (http://localhost:8501)
streamlit run app.py
```

- **Sin clave:** el panel funciona con los resultados guardados en `data/clasificacion.json`,
  y la vista del vecino usa el modo simulado (reglas sencillas, sin coste).
- **Con clave:** pon `OPENROUTER_API_KEY` y `OPENROUTER_MODEL` en `.env`.
  **Nunca subas ese archivo** al repositorio (ya está en `.gitignore`).
- **La próxima vez** basta con: `source .venv/bin/activate && streamlit run app.py`
- Si `pip install` da el error **“externally managed environment”**, es porque falta el
  paso 2 (crear y activar el entorno virtual).

## Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` | Panel del técnico (Streamlit): indicadores, bandeja con alertas, detalle, duplicados, borradores de carta es/va y vista del vecino en vivo |
| `classify.py` | Pre-filtro con el LLM vía OpenRouter (`classify_dict` para la app) o modo simulado sin clave |
| `criterios.md` | Criterios de las bases oficiales que usa el modelo |
| `duplicates.py` | Detección local de propuestas parecidas (TF-IDF, sin coste) |
| `batch.py` | Pasa `data/propuestas.csv` por el pre-filtro → `data/clasificacion.json` y calcula las métricas |
| `data/propuestas.csv` | Propuestas reales y sintéticas de prueba |
| `data/clasificacion.json` | Resultados guardados del pre-filtro (los lee la app) |
| `motor_C/` | Copia de referencia del motor original |
