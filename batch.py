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
from duplicates import agrupar

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
                print(f"  ✓ {res['id']}: {[a['tipo'] for a in res['alertas']] or 'sin alertas'}  ({res['coste_usd']:.5f} $)")
                OUT.write_text(json.dumps(list(previos.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(c.get("coste_usd", 0) for c in previos.values())
    print(f"\nGuardado {OUT} – {len(previos)} propuestas – coste total {total:.4f} $")

    # Coincidencia con los técnicos: rechazada con alguna alerta, o viable sin alertas
    reales = df[df["decision_real"].isin(["viable", "rechazada"])]
    if len(reales):
        dup = set(agrupar(df).dropna(subset=["grupo_duplicado"])["id"].astype(str))
        con_alerta = lambda i: bool(previos.get(i, {}).get("alertas")) or i in dup
        rech = [str(i) for i in reales[reales["decision_real"] == "rechazada"]["id"]]
        via = [str(i) for i in reales[reales["decision_real"] == "viable"]["id"]]
        c_rech = sum(con_alerta(i) for i in rech)
        c_via = sum(not con_alerta(i) for i in via)
        print(f"Coincidencia con técnicos: {c_rech + c_via}/{len(reales)} | "
              f"rechazadas con alerta {c_rech}/{len(rech)} | viables sin alertas {c_via}/{len(via)}")

if __name__ == "__main__":
    main()
