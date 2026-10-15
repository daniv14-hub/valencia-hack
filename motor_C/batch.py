"""Garbell: pasa el pre-filtro a todo data/propuestas.csv -> clasificacion.json + número del pitch.

Uso:  python batch.py              (lee data/propuestas.csv)
      python batch.py ruta.csv

Número del pitch: en cuántas propuestas REALES coinciden nuestras alertas con lo que
decidieron los técnicos (no "cuánto acierta la IA decidiendo": la IA no decide).
"""
import csv
import json
import sys

from classify import classify

ruta = sys.argv[1] if len(sys.argv) > 1 else "data/propuestas.csv"
with open(ruta, encoding="utf-8-sig") as f:
    filas = list(csv.DictReader(f))

salida, coste = [], 0.0
for i, p in enumerate(filas, 1):
    r = classify(p["titulo"], p["descripcion"], p.get("distrito", ""), p.get("presupuesto_estimado", ""))
    coste += r.get("_coste_usd") or 0
    salida.append({**p, "ia": r})
    print(f"[{i}/{len(filas)}] {r.get('etiqueta', '')[:45]:<45} | {p['titulo'][:50]}")

with open("clasificacion.json", "w", encoding="utf-8") as f:
    json.dump(salida, f, ensure_ascii=False, indent=2)

# --- Coincidencia con las decisiones reales de los técnicos ---
reales = [s for s in salida if s.get("origen", "").strip() == "real" and s.get("decision_real", "").strip()]
rech = [s for s in reales if s["decision_real"].strip().lower().startswith("rechaz")]
viab = [s for s in reales if s["decision_real"].strip().lower().startswith("viable")]
con_alerta = lambda s: s["ia"].get("estado") == "con_alertas"  # noqa: E731

coinc_rech = [s for s in rech if con_alerta(s)]
coinc_viab = [s for s in viab if not con_alerta(s)]
falsas = [s for s in viab if con_alerta(s)]
no_vistas = [s for s in rech if not con_alerta(s)]

print("\n===== NÚMERO DEL PITCH (solo propuestas reales) =====")
print(f"Reales con decisión del técnico: {len(reales)}  (rechazadas {len(rech)}, viables {len(viab)})")
total = len(coinc_rech) + len(coinc_viab)
if reales:
    print(f"Nuestras alertas coinciden con el técnico en {total}/{len(reales)} = {total/len(reales):.0%}")
if rech:
    print(f"  - Rechazos reales que ya tenían alerta: {len(coinc_rech)}/{len(rech)}")
if viab:
    print(f"  - Viables reales que salieron sin alertas: {len(coinc_viab)}/{len(viab)}")
print(f"Falsas alarmas (viable real con alerta): {len(falsas)}")
for s in falsas:
    print(f"   ! {s['titulo']} -> {s['ia'].get('etiqueta')}")
print("Rechazos sin alerta (normalmente conocimiento interno: solar, obra ya prevista...):")
for s in no_vistas:
    print(f"   - {s['titulo']} | motivo real: {s.get('motivo_real', '')}")
print(f"\nCoste total: {coste:.4f} USD | por propuesta: {coste/max(len(filas), 1):.4f} USD")
