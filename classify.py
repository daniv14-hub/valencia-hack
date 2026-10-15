"""Garbell: pre-filtro de propuestas VLCParticipa (señala alertas, no decide).

- Con OPENROUTER_API_KEY en .env -> llama al LLM vía OpenRouter (API compatible con OpenAI).
- Sin clave -> modo simulado con reglas sencillas, para poder desarrollar la app sin gastar.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

ROOT = Path(__file__).parent
CRITERIOS = (ROOT / "criterios.md").read_text(encoding="utf-8")

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
# Precio por millón de tokens (solo se usa si OpenRouter no devuelve el coste)
PRICE_IN = float(os.getenv("PRICE_IN_PER_M", "0") or 0)
PRICE_OUT = float(os.getenv("PRICE_OUT_PER_M", "0") or 0)


# ---------- Esquema de salida ----------
class Alerta(BaseModel):
    tipo: Literal["duplicado", "competencia", "presupuesto", "no_inversion"]
    mensaje: str
    norma: str = ""
    administracion: str | None = None  # solo en alertas de competencia
    confianza: float = Field(ge=0, le=1)


class Clasificacion(BaseModel):
    alertas: list[Alerta] = []  # vacía = "Sin alertas · a priori viable"
    resumen: str
    borrador_carta_es: str = ""
    borrador_carta_va: str = ""


def _limpiar(c: Clasificacion) -> dict:
    datos = c.model_dump()
    alertas = []
    for a in datos["alertas"]:
        if a["tipo"] == "duplicado":  # los duplicados los añade la app (duplicates.py)
            continue
        if a["tipo"] != "competencia" or not a["administracion"]:
            a.pop("administracion")
        alertas.append(a)
    datos["alertas"] = alertas
    return datos


SCHEMA_TXT = """Devuelve SOLO un objeto JSON con esta forma exacta:
{
  "alertas": [
    {"tipo": "competencia" | "presupuesto" | "no_inversion",
     "mensaje": "...", "norma": "...",
     "administracion": "solo en alertas de competencia",
     "confianza": 0.0-1.0}
  ],
  "resumen": "una frase para el técnico",
  "borrador_carta_es": "borrador en castellano o vacío",
  "borrador_carta_va": "borrador en valenciano o vacío"
}
Si no hay indicios claros de ningún problema, "alertas" es una lista vacía []."""


def _prompt_usuario(p: dict) -> str:
    return (
        f"Propuesta nº {p.get('id')}\n"
        f"Título: {p.get('titulo')}\n"
        f"Descripción: {p.get('descripcion')}\n"
        f"Distrito: {p.get('distrito')} | Barrio: {p.get('barrio')}\n"
        f"Presupuesto estimado: {p.get('presupuesto_estimado')} €\n\n{SCHEMA_TXT}"
    )


def _extraer_json(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
    i, j = texto.find("{"), texto.rfind("}")
    return json.loads(texto[i : j + 1])


# ---------- Modo LLM ----------
def _classify_llm(p: dict) -> dict:
    from openai import OpenAI

    if not MODEL:
        raise RuntimeError("Falta OPENROUTER_MODEL en .env")
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)
    mensajes = [
        {"role": "system", "content": CRITERIOS},
        {"role": "user", "content": _prompt_usuario(p)},
    ]
    ultimo_error = None
    for intento in range(2):  # 1 reintento si el JSON no es válido
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=mensajes,
            temperature=0,
            response_format={"type": "json_object"},
            extra_body={"usage": {"include": True}},
        )
        texto = resp.choices[0].message.content or ""
        try:
            datos = _limpiar(Clasificacion(**_extraer_json(texto)))
        except (ValueError, ValidationError) as e:
            ultimo_error = e
            mensajes.append({"role": "assistant", "content": texto})
            mensajes.append({"role": "user", "content": "JSON inválido. Repite SOLO el JSON correcto."})
            continue
        u = resp.usage
        tin, tout = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
        coste = getattr(u, "cost", None) if u else None
        if coste is None:
            coste = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
        datos.update(
            tokens_in=tin, tokens_out=tout, coste_usd=round(float(coste), 6),
            segundos=round(time.time() - t0, 2), modelo=MODEL, modo="llm",
        )
        return datos
    raise RuntimeError(f"El modelo no devolvió JSON válido: {ultimo_error}")


# ---------- Modo simulado (sin clave) ----------
AJENAS = {
    r"playa|arena|chiringuito|duchas? en la playa": ("Estado (Demarcación de Costas)", "Ley 22/1988 de Costas"),
    r"colegio|instituto|\bIES\b|\bCEIP\b|aula": ("Generalitat (Conselleria de Educación)", "Competencia autonómica en educación"),
    r"centro de salud|hospital|ambulatorio": ("Generalitat (Conselleria de Sanidad)", "Competencia autonómica en sanidad"),
    r"metro|tranv[ií]a|\bFGV\b": ("Generalitat (FGV)", "Ley 4/2004 de FGV"),
    r"renfe|adif|v[ií]as? del tren|cercan[ií]as": ("Estado (Adif/Renfe)", "Ley 38/2015 del Sector Ferroviario"),
}
NO_INVERSION = r"fiesta|concierto|festival|taller|curso|campa[ñn]a|contratar|monitor|limpieza|vigilancia|pintar|podar|reparar|mantenimiento|subvenci"


def _classify_mock(p: dict) -> dict:
    texto = f"{p.get('titulo', '')} {p.get('descripcion', '')}".lower()
    alertas = []
    for patron, (admin, norma) in AJENAS.items():
        if re.search(patron, texto, re.I):
            alertas.append({"tipo": "competencia", "mensaje": f"Parece competencia de {admin}.",
                            "norma": norma, "administracion": admin, "confianza": 0.85})
            break
    if re.search(NO_INVERSION, texto):
        alertas.append({"tipo": "no_inversion", "mensaje": "Parece gasto corriente o actividad, no una inversión.",
                        "norma": "Bases VLCParticipa – proyectos de inversión", "confianza": 0.8})
    try:
        euros = float(p.get("presupuesto_estimado") or 0)
    except ValueError:
        euros = 0
    if euros <= 0:
        alertas.append({"tipo": "presupuesto", "mensaje": "Sin presupuesto estimado.",
                        "norma": "Bases – presupuesto", "confianza": 0.9})
    elif euros > 160000:  # [VERIFICAR C] umbral provisional
        alertas.append({"tipo": "presupuesto", "mensaje": f"{euros:,.0f} € supera el umbral orientativo de 160.000 €.",
                        "norma": "Bases – asignación por distrito", "confianza": 0.7})

    carta_es = carta_va = ""
    motivo = next((a for a in alertas if a["tipo"] in ("competencia", "no_inversion")), None)
    if motivo:
        admin = motivo.get("administracion")
        razon_es = f"es competencia de {admin}" if admin else "no es un proyecto de inversión"
        razon_va = f"és competència de {admin}" if admin else "no és un projecte d'inversió"
        carta_es = (f"Estimado/a vecino/a:\n\nGracias por participar en VLCParticipa con la propuesta «{p.get('titulo')}». "
                    f"Tras su revisión técnica, no puede pasar a votación porque {razon_es} ({motivo['norma']}). "
                    "Le animamos a seguir participando.\n\nServicio de Descentralización y Participación Ciudadana")
        carta_va = (f"Benvolgut/da veí/veïna:\n\nGràcies per participar en VLCParticipa amb la proposta «{p.get('titulo')}». "
                    f"Després de la revisió tècnica, no pot passar a votació perquè {razon_va} ({motivo['norma']}). "
                    "Vos animem a continuar participant.\n\nServici de Descentralització i Participació Ciutadana")
    return {
        "alertas": alertas,
        "resumen": "Pre-filtro simulado (sin LLM).",
        "borrador_carta_es": carta_es,
        "borrador_carta_va": carta_va,
        "tokens_in": 0, "tokens_out": 0, "coste_usd": 0.0, "segundos": 0.0,
        "modelo": "simulado", "modo": "mock",
    }


def classify(propuesta: dict) -> dict:
    """Clasifica una propuesta. Usa el LLM si hay clave; si no, el modo simulado."""
    out = _classify_llm(propuesta) if API_KEY else _classify_mock(propuesta)
    out["id"] = propuesta.get("id")
    return out


if __name__ == "__main__":
    ejemplo = {"id": 1, "titulo": "Lavabos en la playa de la Malvarrosa",
               "descripcion": "Instalar lavabos públicos en la arena", "distrito": "Poblats Marítims",
               "barrio": "Malvarrosa", "presupuesto_estimado": 40000}
    print("Modo:", "LLM" if API_KEY else "simulado")
    print(json.dumps(classify(ejemplo), ensure_ascii=False, indent=2))
