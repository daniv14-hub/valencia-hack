"""Pre-filtro de propuestas VLCParticipa – panel del técnico municipal.

Ejecutar:  streamlit run app.py
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from batch import metricas
from classify import API_KEY, MODEL, classify_dict
from duplicates import agrupar, buscar_parecidas

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "propuestas.csv"
JSON = ROOT / "data" / "clasificacion.json"
MIN_POR_PROPUESTA = 20  # supuesto para estimar el tiempo ahorrado (decirlo en el pitch)

st.set_page_config(page_title="Pre-filtro de propuestas VLCParticipa", page_icon="🔍", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.5rem;}
  h1, h2, h3 {color: #1f3b57;}
  .badge {padding: 2px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600;}
  .sin {background:#e3f4e8; color:#1e6b34;}
  .con {background:#fff4d6; color:#8a6100;}
  .nota {color:#5b6b7b; font-size:0.85rem;}
</style>""", unsafe_allow_html=True)

ICONO = {"duplicado": "🔁", "fuera_competencia": "🏛️", "fuera_presupuesto": "💶", "no_inversion": "🎉"}
NOMBRE = {"duplicado": "Duplicado", "fuera_competencia": "Fuera de competencia",
          "fuera_presupuesto": "Fuera de presupuesto", "no_inversion": "No inversión"}
SIN_ALERTAS = "Sin alertas · a priori viable"


# ---------- Carga de datos ----------
@st.cache_data
def cargar():
    df = pd.read_csv(CSV, dtype=str).fillna("")
    df = df[df.demo != "si"].reset_index(drop=True)  # las filas demo se teclean en vivo en la vista del vecino
    cls = {str(c["id"]): c for c in json.loads(JSON.read_text(encoding="utf-8"))} if JSON.exists() else {}
    # Si falta alguna clasificación, se completa en modo simulado para que el panel nunca se rompa
    for r in df.to_dict("records"):
        if str(r["id"]) not in cls:
            c = classify_dict(r) if not API_KEY else None
            if c:
                cls[str(r["id"])] = c
    return df, cls


if "extra" not in st.session_state:
    st.session_state.extra = []        # propuestas nuevas de la demo en vivo
    st.session_state.decisiones = {}   # id -> "validada"
    st.session_state.alertas_dec = {}  # (id, tipo) -> "confirmada" | "descartada"

df_base, cls = cargar()
cls = dict(cls)
for p, c in st.session_state.extra:
    cls[str(p["id"])] = c
df = pd.concat([df_base, pd.DataFrame([p for p, _ in st.session_state.extra])], ignore_index=True) \
    if st.session_state.extra else df_base.copy()
df = agrupar(df)


def alertas_de(r):
    """Alertas del LLM + alerta de duplicado calculada aquí con duplicates.py."""
    al = list(cls.get(str(r.id), {}).get("alertas", []))
    if isinstance(r.grupo_duplicado, str) and r.grupo_duplicado:
        al.insert(0, {"tipo": "duplicado", "mensaje": f"Posible duplicado ({r.grupo_duplicado}) de: #{r.similar_a}",
                      "norma": "", "confianza": None})
    return al


def decision(r):
    if st.session_state.decisiones.get(str(r.id)) != "validada":
        return "Pendiente"
    n_conf = sum(st.session_state.alertas_dec.get((str(r.id), a["tipo"])) == "confirmada" for a in r.alertas)
    return f"Validada · {n_conf} alerta(s) confirmada(s)" if n_conf else "Validada"


df["alertas"] = [alertas_de(r) for r in df.itertuples()]
df["tipos"] = df["alertas"].map(lambda al: {a["tipo"] for a in al})
df["decision"] = [decision(r) for r in df.itertuples()]

# ---------- Cabecera ----------
st.title("🔍 Pre-filtro de propuestas VLCParticipa")
st.caption("Asistente para la validación técnica de los presupuestos participativos de València · "
           "**La IA señala, el técnico decide**")

n = len(df)
con = df["tipos"].map(bool)
grupos = df["grupo_duplicado"].dropna().nunique()
costes = [c.get("coste_usd", 0) for c in cls.values()]
coste_medio = sum(costes) / len(costes) if costes else 0
m = metricas(df)
k = st.columns(5)
k[0].metric("Propuestas", n)
k[1].metric("Sin alertas", int((~con).sum()))
k[2].metric("Con alertas", int(con.sum()))
k[3].metric("Grupos de duplicados", grupos)
k[4].metric("Tiempo de cribado estimado ahorrado", f"{n * MIN_POR_PROPUESTA / 60 * 0.6:.0f} h")
k[4].markdown(f"<span class='nota'>Estimación: {MIN_POR_PROPUESTA} min por propuesta, "
              "60 % del cribado asistido</span>", unsafe_allow_html=True)
k2 = st.columns(4)
for col, (t, nombre) in zip(k2, NOMBRE.items()):
    col.metric(f"{ICONO[t]} {nombre}", int(df.tipos.map(lambda s: t in s).sum()))
k3 = st.columns(2)
k3[0].markdown(f"**Sin falsas alarmas en {m['sin_falsas']} de {m['aprobadas']} aprobadas por los técnicos** "
               "(propuestas reales)")
if len(m["falsas"]):
    k3[0].markdown("<span class='nota'>Falsas alarmas:<br>" + "<br>".join(
        f"#{r.id} {r.titulo} → {', '.join(NOMBRE[t] for t in sorted(r.tipos))}" for r in m["falsas"].itertuples())
        + "</span>", unsafe_allow_html=True)
k3[1].markdown(f"**Alertas que coinciden con lo esperado: {m['sint_ok']}/{m['sint_total']}** (propuestas sintéticas)")
st.markdown(f"<span class='nota'>Coste IA medio: {coste_medio:.4f} $/propuesta · "
            f"modelo: {MODEL if API_KEY else 'simulado (sin clave)'}</span>", unsafe_allow_html=True)

tab_bandeja, tab_dup, tab_nueva = st.tabs(["📥 Bandeja de revisión", "🔁 Duplicados", "✍️ Nueva propuesta (vista vecino)"])

# ---------- Bandeja ----------
with tab_bandeja:
    f1, f2, f3 = st.columns([2, 2, 3])
    distritos = f1.multiselect("Distrito", sorted(df.distrito.unique()))
    filtro = f2.multiselect("Alertas", ["sin_alertas", *NOMBRE],
                            format_func=lambda t: f"{ICONO[t]} {NOMBRE[t]}" if t in NOMBRE else "Sin alertas")
    texto = f3.text_input("Buscar", placeholder="palabra clave…")
    vista = df.copy()
    if distritos:
        vista = vista[vista.distrito.isin(distritos)]
    if filtro:
        vista = vista[vista.tipos.map(lambda s: bool(s & set(filtro)) or (not s and "sin_alertas" in filtro))]
    if texto:
        vista = vista[vista.titulo.str.contains(texto, case=False) | vista.descripcion.str.contains(texto, case=False)]

    tabla = vista[["id", "titulo", "distrito"]].copy()
    for t, nombre in NOMBRE.items():
        tabla[nombre] = vista.tipos.map(lambda s, t=t: ICONO[t] if t in s else "")
    tabla["Decisión del técnico"] = vista.decision
    st.dataframe(tabla, hide_index=True, use_container_width=True)

    st.subheader("Detalle de la propuesta")
    if vista.empty:
        st.info("No hay propuestas con estos filtros.")
    else:
        sel = st.selectbox("Selecciona una propuesta", vista["id"].tolist(),
                           format_func=lambda i: f"#{i} · {df.loc[df.id == i, 'titulo'].iloc[0]}")
        p = df[df.id == sel].iloc[0]
        c = cls.get(str(sel), {})
        izq, der = st.columns([3, 2])
        with izq:
            st.markdown(f"### {p.titulo}")
            etiqueta = f"{len(p.alertas)} alerta(s)" if p.alertas else SIN_ALERTAS
            st.markdown(f"<span class='badge {'con' if p.alertas else 'sin'}'>{etiqueta}</span> &nbsp; "
                        f"{p.distrito} · {p.barrio} · {float(p.presupuesto_estimado or 0):,.0f} € · "
                        f"Decisión del técnico: <b>{p.decision}</b>", unsafe_allow_html=True)
            st.write(p.descripcion)
            if p.origen == "real":
                st.caption(f"Propuesta real · edición {p.edicion} · {p.votos} votos")
            if not float(p.presupuesto_estimado or 0):
                st.caption("ℹ️ Sin presupuesto estimado")
            if c.get("resumen"):
                st.info(f"**Resumen IA:** {c['resumen']}")
            if c.get("puntos_a_revisar"):
                st.markdown("**Puntos a revisar por el técnico**\n" + "".join(f"\n- {x}" for x in c["puntos_a_revisar"]))
        with der:
            st.markdown("**Alertas del pre-filtro**")
            if not p.alertas:
                st.success(SIN_ALERTAS)
            for a in p.alertas:
                t, clave = a["tipo"], (str(sel), a["tipo"])
                admin = f"<br>Administración competente: {a['administracion']}" if a.get("administracion") else ""
                conf = f" · confianza {a['confianza']:.0%}" if a.get("confianza") is not None else ""
                st.markdown(f"{ICONO[t]} **{NOMBRE[t]}** — {a['mensaje']}  \n"
                            f"<span class='nota'>📜 {a.get('norma') or '—'}{conf}{admin}</span>",
                            unsafe_allow_html=True)
                if clave in st.session_state.alertas_dec:
                    st.caption(f"Alerta {st.session_state.alertas_dec[clave]} por el técnico")
                x, y = st.columns(2)
                if x.button("Confirmar alerta", key=f"conf{sel}{t}", use_container_width=True):
                    st.session_state.alertas_dec[clave] = "confirmada"
                    st.rerun()
                if y.button("Descartar alerta", key=f"desc{sel}{t}", use_container_width=True):
                    st.session_state.alertas_dec[clave] = "descartada"
                    st.rerun()
        if st.button("✔️ Validar propuesta", use_container_width=True):
            st.session_state.decisiones[str(sel)] = "validada"
            st.rerun()

        if c.get("borrador_carta_es") or c.get("borrador_carta_va"):
            st.markdown("**Borrador – revisar antes de enviar**")
            t_es, t_va = st.tabs(["Castellano", "Valencià"])
            t_es.text_area("es", c.get("borrador_carta_es", ""), height=180, label_visibility="collapsed", key=f"es{sel}")
            t_va.text_area("va", c.get("borrador_carta_va", ""), height=180, label_visibility="collapsed", key=f"va{sel}")

# ---------- Duplicados ----------
with tab_dup:
    dups = df[df.grupo_duplicado.notna()]
    if dups.empty:
        st.info("No se han detectado duplicados.")
    for g, grupo in dups.groupby("grupo_duplicado"):
        with st.expander(f"{g} · {len(grupo)} propuestas · {grupo.distrito.iloc[0]} — «{grupo.titulo.iloc[0]}»", expanded=True):
            st.dataframe(grupo[["id", "titulo", "descripcion", "barrio", "presupuesto_estimado"]],
                         hide_index=True, use_container_width=True)
            st.button(f"Fusionar en una propuesta y avisar a los {len(grupo)} autores", key=f"fus{g}")

# ---------- Nueva propuesta (vista vecino) ----------
with tab_nueva:
    st.markdown("Así vería el vecino los avisos **antes de enviar** su propuesta.")
    with st.form("nueva"):
        titulo = st.text_input("Título")
        desc = st.text_area("Descripción")
        a, b, cc = st.columns(3)
        distrito = a.selectbox("Distrito", sorted(df_base.distrito.unique()))
        barrio = b.text_input("Barrio")
        pres = cc.number_input("Presupuesto estimado (€)", min_value=0, step=1000)
        enviar = st.form_submit_button("Revisar propuesta")
    if enviar and titulo:
        parecidas = buscar_parecidas(df, titulo, desc, distrito)
        if not parecidas.empty:
            st.info("🔁 **Hay propuestas parecidas en tu distrito.** Si quieres, puedes apoyarlas:")
            for _, r in parecidas.iterrows():
                st.markdown(f"- #{r.id} **{r.titulo}** ({r.similitud:.0%} parecida)")
        nueva = {"id": str(1000 + len(st.session_state.extra) + 1), "titulo": titulo, "descripcion": desc,
                 "distrito": distrito, "barrio": barrio, "presupuesto_estimado": str(pres),
                 "origen": "demo", "decision_real": "", "motivo_real": "",
                 "edicion": "", "votos": "", "demo": "no", "alerta_esperada": ""}
        with st.spinner("Analizando con IA…"):
            try:
                res = classify_dict(nueva)
            except Exception as e:
                st.error(f"No se pudo clasificar en vivo: {e}")
                res = None
        if res:
            for a in res["alertas"]:
                st.info(f"{ICONO[a['tipo']]} **Aviso orientativo:** {a['mensaje']}")
            if not res["alertas"]:
                st.success(f"✅ {SIN_ALERTAS}")
            if res["alertas"] or not parecidas.empty:
                st.markdown("**Puedes enviarla igualmente; un técnico la revisará.**")
            st.caption(f"⏱ {res.get('segundos', 0)} s · coste {res.get('coste_usd', 0):.5f} $ · {res.get('modelo')}")
            st.session_state.extra.append((nueva, res))
            st.info("La propuesta ya aparece en la bandeja del técnico.")
