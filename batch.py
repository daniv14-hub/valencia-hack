"""Clasifica data/propuestas.csv y guarda data/clasificacion.json.

Uso:  python batch.py            (todas)
      python batch.py --limit 5  (prueba barata)
Si se corta, al relanzarlo continúa donde lo dejó.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from classify import classify

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "propuestas.csv"
OUT = ROOT / "data" / "clasificacion.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    df = pd.read_csv(CSV, dtype=str).fillna("")
    if args.limit:
        df = df.head(args.limit)
    previos = {str(c["id"]): c for c in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    pendientes = [r for r in df.to_dict("records") if str(r["id"]) not in previos]
    print(f"{len(previos)} ya clasificadas, {len(pendientes)} pendientes")

    def tarea(r):
        try:
            return classify(r)
        except Exception as e:  # una que falle no para el lote
            print(f"  ✗ {r['id']}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(tarea, pendientes):
            if res:
                previos[str(res["id"])] = res
                print(f"  ✓ {res['id']}: {res['estado_sugerido']}  ({res['coste_usd']:.5f} $)")
                OUT.write_text(json.dumps(list(previos.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(c.get("coste_usd", 0) for c in previos.values())
    print(f"\nGuardado {OUT} – {len(previos)} propuestas – coste total {total:.4f} $")

    # Aciertos frente a decisiones reales de los técnicos
    reales = df[df["decision_real"].isin(["viable", "rechazada"])]
    if len(reales):
        mapa = {"viable": "viable", "rechazo_sugerido": "rechazada", "revisar": "revisar"}
        aciertos = derivadas = 0
        for _, r in reales.iterrows():
            pred = mapa[previos[str(r["id"])]["estado_sugerido"]] if str(r["id"]) in previos else None
            if pred == "revisar":
                derivadas += 1
            elif pred == r["decision_real"]:
                aciertos += 1
        print(f"Casos reales: {len(reales)} | acierta {aciertos} | deriva al técnico {derivadas} | "
              f"falla {len(reales) - aciertos - derivadas}")


if __name__ == "__main__":
    main()
