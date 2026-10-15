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

from classify import classify_dict
from duplicates import agrupar

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "propuestas.csv"
OUT = ROOT / "data" / "clasificacion.json"


def metricas(df):
    """df: sin filas demo, con grupo_duplicado (duplicates.agrupar) y tipos (set de alertas, duplicado incluido)."""
    aprob = df[(df.origen == "real") & (df.decision_real == "viable")]
    falsas = aprob[aprob.tipos.map(bool)]
    sint = df[(df.origen == "sintetica") & (df.alerta_esperada != "")]
    grupo = {str(i): g if isinstance(g, str) and g else None for i, g in zip(df.id, df.grupo_duplicado)}

    def acierta(r):
        for e in r.alerta_esperada.split("|"):
            if e == "sin_alertas":
                if r.tipos:
                    return False
            elif e.startswith("duplicado:"):  # agrupada con todas las demás de la misma etiqueta
                otros = [str(i) for i, esp in zip(sint.id, sint.alerta_esperada)
                         if e in esp.split("|") and str(i) != str(r.id)]
                g = grupo[str(r.id)]
                if not g or any(grupo[o] != g for o in otros):
                    return False
            elif e not in r.tipos:
                return False
        return True

    fallos = sint[[not acierta(r) for r in sint.itertuples()]]
    return {"aprobadas": len(aprob), "sin_falsas": len(aprob) - len(falsas), "falsas": falsas,
            "sint_total": len(sint), "sint_ok": len(sint) - len(fallos), "sint_fallos": fallos}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1)  # el caché de classify.py no es seguro con hilos
    args = ap.parse_args()

    df = pd.read_csv(CSV, dtype=str).fillna("")
    if args.limit:
        df = df.head(args.limit)
    previos = {str(c["id"]): c for c in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    pendientes = [r for r in df.to_dict("records") if str(r["id"]) not in previos]
    print(f"{len(previos)} ya clasificadas, {len(pendientes)} pendientes")

    def tarea(r):
        try:
            return classify_dict(r)
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

    # Métricas sobre lo que ve el técnico (sin filas demo), duplicados incluidos
    base = agrupar(df[df["demo"] != "si"])
    base["tipos"] = [{a["tipo"] for a in previos.get(str(r.id), {}).get("alertas", [])}
                     | ({"duplicado"} if isinstance(r.grupo_duplicado, str) else set()) for r in base.itertuples()]
    m = metricas(base)
    print(f"Reales: sin falsas alarmas en {m['sin_falsas']} de {m['aprobadas']} aprobadas por los técnicos")
    for r in m["falsas"].itertuples():
        print(f"   ! {r.id} {r.titulo[:60]} -> {sorted(r.tipos)}")
    print(f"Sintéticas: alertas que coinciden con lo esperado: {m['sint_ok']}/{m['sint_total']}")
    for r in m["sint_fallos"].itertuples():
        print(f"   - {r.id} esperada {r.alerta_esperada} | obtenida {sorted(r.tipos) or 'sin alertas'}")

if __name__ == "__main__":
    main()
