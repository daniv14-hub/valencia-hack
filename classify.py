"""Garbell - pre-filtro de propuestas VLCParticipa (OpenRouter).

LA IA SEÑALA, EL TÉCNICO DECIDE. Este módulo NO aprueba ni rechaza nada:
solo devuelve alertas para que el técnico revise más rápido.

Alertas que genera este módulo:
  FUERA_COMPETENCIA, FUERA_PRESUPUESTO, NO_INVERSION
La alerta POSIBLE_DUPLICADO se calcula aparte, en local, comparando textos (parte de la app).

Uso:
    python classify.py            # prueba con 5 propuestas inventadas
Desde la app:
    from classify import classify
    r = classify(titulo, descripcion, distrito, presupuesto_estimado)
"""
import hashlib
import json
import os
import pathlib
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
_KEY_FILE = pathlib.Path(__file__).with_name("clave.txt")
API_KEY = os.environ.get("OPENROUTER_API_KEY") or (
    _KEY_FILE.read_text(encoding="utf-8").strip() if _KEY_FILE.exists() else "")
CRITERIOS = pathlib.Path(__file__).with_name("criterios.md").read_text(encoding="utf-8")
CACHE_FILE = pathlib.Path(__file__).with_name("cache_clasificacion.json")

# Presupuesto oficial por distrito VLCParticipa 2025-26 (vlcparticipa.valencia.es/help)
PRESUPUESTO_DISTRITO = {
    "ciutat vella": 395154, "eixample": 485894, "extramurs": 640588, "campanar": 623387,
    "saidia": 921957, "pla del real": 380571, "olivereta": 1183678, "patraix": 1012058,
    "jesus": 1157550, "quatre carreres": 1475031, "poblats maritims": 1205469,
    "camins al grau": 1098609, "algiros": 586341, "benimaclet": 510618, "rascanya": 1256663,
    "benicalap": 1103863, "pobles del nord": 373506, "pobles de l'oest": 692676,
    "pobles del sud": 896387,
}

SYSTEM = f"""Eres "Garbell", un PRE-FILTRO de ayuda para el técnico del Servicio de Descentralización y Participación Ciudadana del Ayuntamiento de València (presupuestos participativos VLCParticipa).

NO DECIDES NADA. No apruebas, no rechazas, no descartas. Solo señalas POSIBLES alertas para que el técnico revise más rápido. El técnico revisa siempre todas las propuestas y toma todas las decisiones.

Bases oficiales:
{CRITERIOS}

Solo puedes señalar estos 3 tipos de alerta:
- FUERA_COMPETENCIA: parece competencia de otra administración (Costas/Estado, Generalitat, FGV, Adif, Autoridad Portuaria...) o requiere implicar a otras administraciones.
- FUERA_PRESUPUESTO: idea claramente desproporcionada para el presupuesto del distrito (p. ej. una línea de metro, un polideportivo grande en un distrito pequeño).
- NO_INVERSION: actividades, fiestas, talleres, cursos, contratar personal, servicios, subvenciones, alquileres, mantenimiento o limpieza ordinarios.

Reglas:
- Usa SIEMPRE lenguaje de posibilidad: "posible", "parece". Nunca "rechazada", "aprobada", "inviable" ni "desestimada".
- Señala una alerta solo si hay base clara en el texto; ante la duda, no la pongas y anótalo en "puntos_a_revisar".
- Cada alerta cita la regla concreta de las bases en una frase.
- "puntos_a_revisar": cosas que la IA no puede saber y el técnico debe comprobar (titularidad del solar, si ya está prevista, viabilidad técnica del sitio...). Máximo 2.
- Si hay alertas, escribe un BORRADOR de carta al vecino en castellano y en valenciano: breve, amable, en condicional ("podría no ser competencia municipal..."), explicando el posible motivo y cómo reformularla. Si no hay alertas, deja las cartas vacías.
- Responde SOLO con JSON válido, sin texto adicional, con este esquema exacto:
{{
  "alertas": [
    {{"tipo": "FUERA_COMPETENCIA|FUERA_PRESUPUESTO|NO_INVERSION",
      "texto": "Posible ... (frase corta para la etiqueta)",
      "motivo": "por qué, en una frase",
      "regla": "regla de las bases que lo respalda",
      "administracion": "solo si FUERA_COMPETENCIA: Estado-Costas|Generalitat|FGV|Adif|Autoridad Portuaria|Otra"}}
  ],
  "puntos_a_revisar": ["..."],
  "resumen": "una frase para el técnico, en lenguaje de posibilidad",
  "borrador_carta_es": "",
  "borrador_carta_va": ""
}}"""

PROMPT_VERSION = hashlib.sha256(SYSTEM.encode()).hexdigest()[:8]


def _norm(s):
    s = (s or "").lower()
    for a, b in (("à", "a"), ("á", "a"), ("è", "e"), ("é", "e"), ("í", "i"), ("ï", "i"),
                 ("ò", "o"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("l'", ""), ("la ", ""), ("el ", "")):
        s = s.replace(a, b)
    return s.strip()


def presupuesto_del_distrito(distrito):
    d = _norm(distrito)
    for k, v in PRESUPUESTO_DISTRITO.items():
        if _norm(k) in d or d in _norm(k):
            return v
    return None


def _numero(x):
    digits = re.sub(r"[^\d]", "", str(x or ""))
    return int(digits) if digits else None


def _load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_json(text):
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def _alerta_presupuesto_regla(distrito, presupuesto_estimado, alertas):
    """Regla determinista: si el vecino estima más que la partida del distrito."""
    tope, est = presupuesto_del_distrito(distrito), _numero(presupuesto_estimado)
    if tope and est and est > tope and not any(a.get("tipo") == "FUERA_PRESUPUESTO" for a in alertas):
        alertas.append({
            "tipo": "FUERA_PRESUPUESTO",
            "texto": "Posible fuera de presupuesto",
            "motivo": f"El coste estimado ({est:,} €) supera la partida del distrito ({tope:,} €).".replace(",", "."),
            "regla": "Bases: se excluyen las propuestas con coste superior a la cuantía asignada al distrito.",
            "administracion": "",
        })


ETIQUETAS = {
    "FUERA_COMPETENCIA": "Posible fuera de competencia",
    "FUERA_PRESUPUESTO": "Posible fuera de presupuesto",
    "NO_INVERSION": "Posible no inversión",
}


def _etiquetar(result):
    """Etiquetas fijas (no las escribe la IA) para que el panel sea consistente."""
    alertas = result.get("alertas", [])
    for a in alertas:
        a["texto"] = ETIQUETAS.get(a.get("tipo"), a.get("texto", ""))
        if a.get("tipo") == "FUERA_COMPETENCIA" and a.get("administracion"):
            a["texto"] += f" ({a['administracion']})"
    result["estado"] = "con_alertas" if alertas else "sin_alertas"
    result["etiqueta"] = " · ".join(a["texto"] for a in alertas) if alertas else "Sin alertas, a priori viable"
    return result


def classify(titulo, descripcion, distrito="", presupuesto_estimado="", use_cache=True):
    """Devuelve alertas (nunca una decisión). Campos clave:
    estado: "con_alertas" | "sin_alertas"   ->  etiqueta: "Alerta: posible..." | "Sin alertas, a priori viable"
    alertas: lista de {tipo, texto, motivo, regla, administracion}
    puntos_a_revisar, resumen, borrador_carta_es, borrador_carta_va, _coste_usd
    """
    ciudad = _norm(distrito) == "ciudad"
    tope = presupuesto_del_distrito(distrito)
    linea_tope = ("Edición de ámbito ciudad: sin partida por distrito; no señales fuera_presupuesto "
                  "salvo si es desproporcionado (más de 5 M€)") if ciudad else \
        f"Presupuesto disponible del distrito: {tope if tope else 'desconocido'} €"
    user = (f"Título: {titulo}\nDescripción: {descripcion}\nDistrito: {distrito}\n{linea_tope}\n"
            f"Presupuesto estimado por el vecino: {presupuesto_estimado or 'no indicado'}")
    key = hashlib.sha256(f"{MODEL}|{PROMPT_VERSION}|{user}".encode()).hexdigest()
    cache = _load_cache() if use_cache else {}
    if use_cache and key in cache:
        return _etiquetar({**cache[key], "_cache": True})

    t0 = time.time()
    last_err = None
    for _ in range(2):  # un reintento si el JSON sale mal
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "usage": {"include": True},
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            result = _parse_json(data["choices"][0]["message"]["content"])
            alertas = [a for a in result.get("alertas", [])
                       if a.get("tipo") in ("FUERA_COMPETENCIA", "FUERA_PRESUPUESTO", "NO_INVERSION")]
            if not ciudad:
                _alerta_presupuesto_regla(distrito, presupuesto_estimado, alertas)
            result["alertas"] = alertas
            result = _etiquetar(result)
            if not alertas:
                result["borrador_carta_es"] = result["borrador_carta_va"] = ""
            result["decision_tecnico"] = "pendiente"  # la decide SIEMPRE el técnico
            usage = data.get("usage", {})
            result["_coste_usd"] = usage.get("cost")
            result["_segundos"] = round(time.time() - t0, 2)
            result["_modelo"] = MODEL
            if use_cache:
                cache[key] = result
                _save_cache(cache)
            return result
        except Exception as e:  # noqa: BLE001
            last_err = e
    return {"estado": "error", "alertas": [], "etiqueta": "Sin analizar: revisión manual",
            "resumen": f"Error del pre-filtro: {last_err}", "decision_tecnico": "pendiente", "_error": True}


# ---------- Adaptador para la app (contrato JSON de CLAUDE.md) ----------
# Modo simulado sin clave: reglas sencillas para desarrollar la app sin gastar.
AJENAS = {
    r"playa|arena|chiringuito|duchas? en la playa": "Estado-Costas",
    r"colegio|instituto|\bIES\b|\bCEIP\b|aula": "Generalitat",
    r"centro de salud|hospital|ambulatorio": "Generalitat",
    r"metro|tranv[ií]a|\bFGV\b": "FGV",
    r"renfe|adif|v[ií]as? del tren|cercan[ií]as": "Adif",
    r"puerto|portuari": "Autoridad Portuaria",
}
NO_INVERSION = r"fiesta|concierto|festival|taller|curso|clases|campa[ñn]a|contratar|monitor|limpieza|vigilancia|patrulla|pintar|repintar|podar|poda\b|reparar|arreglar|mantenimiento|subvenci"


def _classify_mock(p):
    texto = f"{p.get('titulo', '')} {p.get('descripcion', '')}"
    alertas = []
    for patron, admin in AJENAS.items():
        if re.search(patron, texto, re.I):
            alertas.append({"tipo": "FUERA_COMPETENCIA", "motivo": f"Parece competencia de {admin}.",
                            "regla": "Bases: fuera de competencia municipal.", "administracion": admin})
            break
    if re.search(NO_INVERSION, texto, re.I):
        alertas.append({"tipo": "NO_INVERSION", "motivo": "Parece una actividad, servicio o mantenimiento, no una inversión.",
                        "regla": "Bases: solo proyectos de inversión.", "administracion": ""})
    if _norm(p.get("distrito")) == "ciudad":
        est = _numero(p.get("presupuesto_estimado"))
        if est and est > 5_000_000:
            alertas.append({"tipo": "FUERA_PRESUPUESTO", "motivo": "Coste desproporcionado (más de 5 M€).",
                            "regla": "Bases: presupuesto.", "administracion": ""})
    else:
        _alerta_presupuesto_regla(p.get("distrito"), p.get("presupuesto_estimado"), alertas)
    r = _etiquetar({"alertas": alertas, "puntos_a_revisar": [], "resumen": "Pre-filtro simulado (sin LLM).",
                    "borrador_carta_es": "", "borrador_carta_va": ""})
    if alertas:
        a = alertas[0]
        r["borrador_carta_es"] = (f"Estimado/a vecino/a:\n\nGracias por participar en VLCParticipa con la propuesta "
                                  f"«{p.get('titulo')}». Tras una primera revisión, podría no cumplir las bases: "
                                  f"{a['motivo']} ({a['regla']}) Un técnico la revisará.\n\n"
                                  "Servicio de Descentralización y Participación Ciudadana")
        r["borrador_carta_va"] = (f"Benvolgut/da veí/veïna:\n\nGràcies per participar en VLCParticipa amb la proposta "
                                  f"«{p.get('titulo')}». Després d'una primera revisió, podria no complir les bases "
                                  f"({a['regla']}). Un tècnic la revisarà.\n\n"
                                  "Servici de Descentralització i Participació Ciutadana")
    return r


def classify_dict(p: dict) -> dict:
    """Para la app: recibe una fila del CSV y devuelve el contrato JSON con tipos en minúsculas
    (fuera_competencia, fuera_presupuesto, no_inversion). Sin clave usa el modo simulado."""
    r = classify(p.get("titulo", ""), p.get("descripcion", ""), p.get("distrito", ""),
                 p.get("presupuesto_estimado", "")) if API_KEY else _classify_mock(p)
    if r.get("_error"):
        raise RuntimeError(r.get("resumen"))
    alertas = []
    for a in r.get("alertas", []):
        al = {"tipo": a["tipo"].lower(), "texto": a.get("texto", ""), "mensaje": a.get("motivo", ""),
              "norma": a.get("regla", "")}
        if a["tipo"] == "FUERA_COMPETENCIA" and a.get("administracion"):
            al["administracion"] = a["administracion"]
        alertas.append(al)
    return {
        "id": p.get("id"), "alertas": alertas, "puntos_a_revisar": r.get("puntos_a_revisar", []),
        "resumen": r.get("resumen", ""), "borrador_carta_es": r.get("borrador_carta_es", ""),
        "borrador_carta_va": r.get("borrador_carta_va", ""),
        "coste_usd": r.get("_coste_usd") or 0.0, "segundos": r.get("_segundos", 0.0),
        "modelo": r.get("_modelo", MODEL) if API_KEY else "simulado",
        "modo": ("cache" if r.get("_cache") else "llm") if API_KEY else "mock",
    }


if __name__ == "__main__":
    pruebas = [
        ("Lavabos en la playa de la Malva-rosa", "Instalar baños públicos en la arena de la playa.", "Poblats Marítims", "30000", {"FUERA_COMPETENCIA"}),
        ("Bancos y sombra en la plaza", "Poner 6 bancos y un toldo fijo en la plaza del barrio.", "Benimaclet", "15000", set()),
        ("Fiesta de barrio anual", "Organizar una fiesta con música cada verano.", "Patraix", "5000", {"NO_INVERSION"}),
        ("Ampliar la línea de metro", "Que el metro llegue hasta nuestro barrio.", "Benicalap", "2000000", {"FUERA_COMPETENCIA", "FUERA_PRESUPUESTO"}),
        ("Más limpieza en las calles", "Contratar más personal de limpieza.", "Ciutat Vella", "", {"NO_INVERSION"}),
    ]
    ok_total = 0
    for t, d, dist, pres, esperadas in pruebas:
        r = classify(t, d, dist, pres)
        tipos = {a["tipo"] for a in r.get("alertas", [])}
        ok = (tipos & esperadas) if esperadas else not tipos
        ok_total += bool(ok)
        print(f"{'OK ' if ok else 'MAL'} | {t:<35} | {r.get('etiqueta')} | coste: {r.get('_coste_usd')} $")
    print(f"\nRESULTADO: {ok_total}/5 alertas como se esperaba. Modelo: {MODEL}")
