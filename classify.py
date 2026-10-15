"""Clasificador de propuestas VLCParticipa.

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
from pydantic import BaseModel, ValidationError

load_dotenv()

ROOT = Path(__file__).parent
CRITERIOS = (ROOT / "criterios.md").read_text(encoding="utf-8")

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
# Precio por millón de tokens (solo se usa si OpenRouter no devuelve el coste)
PRICE_IN = float(os.getenv("PRICE_IN_PER_M", "0") or 0)
PRICE_OUT = float(os.getenv("PRICE_OUT_PER_M", "0") or 0)


# ---------- Esquema de salida ----------
class Criterio(BaseModel):
    ok: bool | None  # None = no se puede determinar (revisar)
    motivo: str
    norma: str


class Criterios(BaseModel):
    competencia: Criterio
    inversion: Criterio
    presupuesto: Criterio


class Clasificacion(BaseModel):
    estado_sugerido: Literal["viable", "revisar", "rechazo_sugerido"]
    criterios: Criterios
    confianza: float  # 0-1
    resumen: str
    borrador_carta_es: str = ""
    borrador_carta_va: str = ""


SCHEMA_TXT = """Devuelve SOLO un objeto JSON con esta forma exacta:
{
  "estado_sugerido": "viable" | "revisar" | "rechazo_sugerido",
  "criterios": {
    "competencia": {"ok": true|false|null, "motivo": "...", "norma": "..."},
    "inversion":   {"ok": true|false|null, "motivo": "...", "norma": "..."},
    "presupuesto": {"ok": true|false|null, "motivo": "...", "norma": "..."}
  },
  "confianza": 0.0-1.0,
  "resumen": "una frase para el técnico",
  "borrador_carta_es": "carta en castellano o vacío",
  "borrador_carta_va": "carta en valenciano o vacío"
}"""


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
            datos = Clasificacion(**_extraer_json(texto)).model_dump()
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
    comp = {"ok": True, "motivo": "Actuación en espacio público municipal.", "norma": "Art. 25 Ley 7/1985 LBRL"}
    for patron, (admin, norma) in AJENAS.items():
        if re.search(patron, texto, re.I):
            comp = {"ok": False, "motivo": f"Competencia de {admin}.", "norma": norma}
            break
    inv = {"ok": True, "motivo": "Bien construible/adquirible con vida útil > 1 año.", "norma": "Bases VLCParticipa – proyectos de inversión"}
    if re.search(NO_INVERSION, texto):
        inv = {"ok": False, "motivo": "Es gasto corriente o actividad, no una inversión.", "norma": "Bases VLCParticipa – proyectos de inversión"}
    try:
        euros = float(p.get("presupuesto_estimado") or 0)
    except ValueError:
        euros = 0
    if euros <= 0:
        pres = {"ok": None, "motivo": "Sin presupuesto estimado: el técnico debe valorarlo.", "norma": "Bases – presupuesto"}
    elif euros > 160000:
        pres = {"ok": None, "motivo": f"{euros:,.0f} € supera la asignación orientativa del distrito.", "norma": "Bases – asignación por distrito"}
    else:
        pres = {"ok": True, "motivo": f"{euros:,.0f} € dentro de la asignación del distrito.", "norma": "Bases – asignación por distrito"}

    if comp["ok"] is False or inv["ok"] is False:
        estado, conf = "rechazo_sugerido", 0.85
    elif pres["ok"] is None:
        estado, conf = "revisar", 0.6
    else:
        estado, conf = "viable", 0.8

    carta_es = carta_va = ""
    if estado == "rechazo_sugerido":
        motivo = comp["motivo"] if comp["ok"] is False else inv["motivo"]
        carta_es = (f"Estimado/a vecino/a:\n\nGracias por participar en VLCParticipa con la propuesta «{p.get('titulo')}». "
                    f"Tras su revisión técnica, no puede pasar a votación: {motivo} ({comp['norma'] if comp['ok'] is False else inv['norma']}). "
                    "Le animamos a seguir participando.\n\nServicio de Descentralización y Participación Ciudadana")
        carta_va = (f"Benvolgut/da veí/veïna:\n\nGràcies per participar en VLCParticipa amb la proposta «{p.get('titulo')}». "
                    f"Després de la revisió tècnica, no pot passar a votació: {motivo} "
                    "Vos animem a continuar participant.\n\nServici de Descentralització i Participació Ciutadana")
    return {
        "estado_sugerido": estado,
        "criterios": {"competencia": comp, "inversion": inv, "presupuesto": pres},
        "confianza": conf,
        "resumen": "Clasificación simulada (sin LLM).",
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
