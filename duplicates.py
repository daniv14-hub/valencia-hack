"""Detección de propuestas duplicadas en local (sin API, sin coste).

MVP: TF-IDF de n-gramas de caracteres + similitud coseno + componentes conexas.
Proyecto real: embeddings multilingües (castellano/valenciano) en PostgreSQL + pgvector.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

CSV = Path(__file__).parent / "data" / "propuestas.csv"
# Ajustados con data/propuestas.csv (modelo fijo):
UMBRAL = 0.38  # grupos del panel: R13-R18 = 0.337 queda fuera; B se une por S04-S05 = 0.419
UMBRAL_VECINO = 0.25  # avisos orientativos al vecino: DEMO03-S02 = 0.314; ruido máximo de DEMO01-03 = 0.137


def _textos(df: pd.DataFrame) -> list[str]:
    return (df["titulo"].fillna("") + ". " + df["descripcion"].fillna("")).str.lower().tolist()


@lru_cache(maxsize=1)
def _modelo() -> TfidfVectorizer:
    """TF-IDF ajustado una sola vez con el CSV (sin filas demo). Lo que se escribe en vivo
    se compara contra este modelo sin reentrenarlo, para que las similitudes no se muevan."""
    df = pd.read_csv(CSV, dtype=str).fillna("")
    df = df[df["demo"] != "si"]
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(_textos(df))


def agrupar(df: pd.DataFrame, umbral: float = UMBRAL) -> pd.DataFrame:
    """Devuelve df con columnas grupo_duplicado (None si no tiene) y similar_a."""
    df = df.copy()
    if len(df) < 2:
        df["grupo_duplicado"] = None
        df["similar_a"] = ""
        return df
    sim = cosine_similarity(_modelo().transform(_textos(df)))
    # Mismo distrito pesa más: dos propuestas iguales en distritos distintos no son duplicado
    d = df["distrito"].to_numpy(dtype=object)
    mismo = d[:, None] == d[None, :]
    adj = (sim >= umbral) & mismo
    _, etiquetas = connected_components(adj, directed=False)
    tam = pd.Series(etiquetas).value_counts()
    ids = df["id"].tolist()
    grupos, similares, n = [], [], 0
    mapa = {}
    for i, e in enumerate(etiquetas):
        if tam[e] > 1:
            if e not in mapa:
                n += 1
                mapa[e] = f"G{n}"
            grupos.append(mapa[e])
            otros = [str(ids[j]) for j in range(len(ids)) if etiquetas[j] == e and j != i]
            similares.append(", ".join(otros))
        else:
            grupos.append(None)
            similares.append("")
    df["grupo_duplicado"] = grupos
    df["similar_a"] = similares
    return df


def buscar_parecidas(df: pd.DataFrame, titulo: str, descripcion: str, distrito: str,
                     umbral: float = UMBRAL_VECINO, k: int = 3) -> pd.DataFrame:
    """Para el aviso al ciudadano: propuestas existentes parecidas a una nueva."""
    base = df[df["distrito"] == distrito] if distrito else df
    if base.empty:
        return base
    vec = _modelo()
    sims = cosine_similarity(vec.transform([f"{titulo}. {descripcion}".lower()]),
                             vec.transform(_textos(base))).ravel()
    out = base.assign(similitud=sims)
    return out[out["similitud"] >= umbral].sort_values("similitud", ascending=False).head(k)
