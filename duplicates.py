"""Detección de propuestas duplicadas en local (sin API, sin coste).

MVP: TF-IDF de n-gramas de caracteres + similitud coseno + componentes conexas.
Proyecto real: embeddings multilingües (castellano/valenciano) en PostgreSQL + pgvector.
"""
from __future__ import annotations

import pandas as pd
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

UMBRAL = 0.35  # ajustar viendo los datos reales


def _textos(df: pd.DataFrame) -> list[str]:
    return (df["titulo"].fillna("") + ". " + df["descripcion"].fillna("")).str.lower().tolist()


def agrupar(df: pd.DataFrame, umbral: float = UMBRAL) -> pd.DataFrame:
    """Devuelve df con columnas grupo_duplicado (None si no tiene) y similar_a."""
    df = df.copy()
    if len(df) < 2:
        df["grupo_duplicado"] = None
        df["similar_a"] = ""
        return df
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
    sim = cosine_similarity(vec.fit_transform(_textos(df)))
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
                     umbral: float = UMBRAL, k: int = 3) -> pd.DataFrame:
    """Para el aviso al ciudadano: propuestas existentes parecidas a una nueva."""
    base = df[df["distrito"] == distrito] if distrito else df
    if base.empty:
        return base
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    m = vec.fit_transform(_textos(base) + [f"{titulo}. {descripcion}".lower()])
    sims = cosine_similarity(m[-1], m[:-1]).ravel()
    out = base.assign(similitud=sims)
    return out[out["similitud"] >= umbral].sort_values("similitud", ascending=False).head(k)
