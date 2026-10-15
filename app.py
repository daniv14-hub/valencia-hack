"""Copiloto VLCParticipa – panel del técnico municipal.

Ejecutar:  streamlit run app.py
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from classify import API_KEY, MODEL, classify
from duplicates import agrupar, buscar_parecidas

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "propuestas.csv"
JSON = ROOT / "data" / "clasificacion.json"
MIN_POR_PROPUESTA = 20  # supuesto para estimar horas ahorradas (decirlo en el pitch)

st.set_page_config(page_title="Copiloto VLCParticipa", page_icon="🏛️", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.5rem;}
  h1, h2, h3 {color: #1f3b57;}
  .badge {padding: 2px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600;}
  .viable {background:#e3f4e8; color:#1e6b34;}
  .revisar {background:#fff4d6; color:#8a6100;}
  .rechazo_sugerido {background:#fde4e4; color:#9b1c1c;}
  .nota {color:#5b6b7b; font-size:0.85rem;}
</style>""", unsafe_allow_html=True)

ICONO = {"viable": "🟢 Viable", "revisar": "🟡 Revisar", "rechazo_sugerido": "🔴 Rechazo sugerido"}
CRIT = {"competencia": "Competencia municipal", "inversion": "Es inversión", "presupuesto": "Presupuesto"}


# ---------- Carga de datos ----------
@st.cache_data
def cargar():
    df = pd.read_csv(CSV, dtype=str).fillna("")
    cls = {str(c["id"]): c for c in json.loads(JSON.read_text(encoding="utf-8"))} if JSON.exists() else {}
    # Si falta alguna clasificación, se completa en modo simulado para que el panel nunca se rompa
    for r in df.to_dict("records"):
        if str(r["id"]) not in cls:
            c = classify(r) if not API_KEY else None
            if c:
                cls[str(r["id"])] = c
    return df, cls


if "extra" not in st.session_state:
    st.session_state.extra = []        # propuestas nuevas de la demo en vivo
    st.session_state.decisiones = {}   # id -> decisión del técnico

df_base, cls = cargar()
cls = dict(cls)
for p, c in st.session_state.extra:
    cls[str(p["id"])] = c
df = pd.concat([df_base, pd.DataFrame([p for p, _ in st.session_state.extra])], ignore_index=True) \
    if st.session_state.extra else df_base.copy()
df = agrupar(df)
df["estado"] = df["id"].map(lambda i: cls.get(str(i), {}).get("estado_sugerido", "revisar"))
df["confianza"] = df["id"].map(lambda i: cls.get(str(i), {}).get("confianza", 0))
df["decision"] = df["id"].map(lambda i: st.session_state.decisiones.get(str(i), "—"))

# ---------- Cabecera ----------
st.title("🏛️ Copiloto VLCParticipa")
st.caption("Validación técnica asistida de propuestas · Ajuntament de València · "
           "**La IA propone, el técnico decide**")

n = len(df)
grupos = df["grupo_duplicado"].dropna().nunique()
redundantes = df["grupo_duplicado"].notna().sum() - grupos
costes = [c.get("coste_usd", 0) for c in cls.values()]
coste_medio = sum(costes) / len(costes) if costes else 0
k = st.columns(6)
k[0].metric("Propuestas recibidas", n)
k[1].metric("Grupos de duplicados", grupos, f"{redundantes} redundantes", delta_color="off")
k[2].metric("🟢 Viables", (df.estado == "viable").sum())
k[3].metric("🟡 A revisar", (df.estado == "revisar").sum())
k[4].metric("🔴 Rechazo sugerido", (df.estado == "rechazo_sugerido").sum())
k[5].metric("Horas de técnico ahorradas*", f"{n * MIN_POR_PROPUESTA / 60 * 0.6:.0f} h")
st.markdown(f"<span class='nota'>* Estimación: {MIN_POR_PROPUESTA} min por propuesta y 60 % del trabajo "
            f"de cribado asistido. Coste IA medio: {coste_medio:.4f} $/propuesta · "
            f"modelo: {MODEL if API_KEY else 'simulado (sin clave)'}</span>", unsafe_allow_html=True)

tab_bandeja, tab_dup, tab_nueva = st.tabs(["📥 Bandeja de validación", "🔁 Duplicados", "✍️ Nueva propuesta (vista vecino)"])

# ---------- Bandeja ----------
with tab_bandeja:
    f1, f2, f3 = st.columns([2, 2, 3])
    distritos = f1.multiselect("Distrito", sorted(df.distrito.unique()))
    estados = f2.multiselect("Estado sugerido", list(ICONO), format_func=ICONO.get)
    texto = f3.text_input("Buscar", placeholder="palabra clave…")
    vista = df.copy()
    if distritos:
        vista = vista[vista.distrito.isin(distritos)]
    if estados:
        vista = vista[vista.estado.isin(estados)]
    if texto:
        vista = vista[vista.titulo.str.contains(texto, case=False) | vista.descripcion.str.contains(texto, case=False)]

    tabla = vista[["id", "titulo", "distrito", "estado", "confianza", "grupo_duplicado", "decision"]].copy()
    tabla["estado"] = tabla["estado"].map(ICONO)
    tabla["grupo_duplicado"] = tabla["grupo_duplicado"].fillna("")
    st.dataframe(tabla, hide_index=True, use_container_width=True,
                 column_config={"confianza": st.column_config.ProgressColumn("Confianza", min_value=0, max_value=1),
                                "grupo_duplicado": "Duplicado", "decision": "Decisión técnico"})

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
            st.markdown(f"<span class='badge {p.estado}'>{ICONO[p.estado]}</span> &nbsp; "
                        f"{p.distrito} · {p.barrio} · {float(p.presupuesto_estimado or 0):,.0f} €",
                        unsafe_allow_html=True)
            st.write(p.descripcion)
            if c.get("resumen"):
                st.info(f"**Resumen IA:** {c['resumen']}")
            if isinstance(p.grupo_duplicado, str) and p.grupo_duplicado:
                st.warning(f"🔁 Posible duplicado ({p.grupo_duplicado}) de: #{p.similar_a}")
        with der:
            st.markdown("**Criterios de viabilidad**")
            for clave, nombre in CRIT.items():
                cr = c.get("criterios", {}).get(clave, {})
                ok = cr.get("ok")
                icono = "✅" if ok is True else "❌" if ok is False else "❔"
                st.markdown(f"{icono} **{nombre}** — {cr.get('motivo', '')}  \n"
                            f"<span class='nota'>📜 {cr.get('norma', '')}</span>", unsafe_allow_html=True)
        b1, b2, b3 = st.columns(3)
        if b1.button("✔️ Aceptar sugerencia", use_container_width=True):
            st.session_state.decisiones[str(sel)] = f"Aceptada ({ICONO[p.estado]})"
            st.rerun()
        if b2.button("✏️ Marcar viable", use_container_width=True):
            st.session_state.decisiones[str(sel)] = "Cambiada → viable"
            st.rerun()
        if b3.button("✏️ Marcar rechazo", use_container_width=True):
            st.session_state.decisiones[str(sel)] = "Cambiada → rechazo"
            st.rerun()

        if c.get("borrador_carta_es") or c.get("borrador_carta_va"):
            st.markdown("**Borrador de notificación al vecino** (editable antes de enviar)")
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
            st.warning("🔁 **Ya hay propuestas parecidas en tu distrito.** Puedes apoyarlas en lugar de crear otra:")
            for _, r in parecidas.iterrows():
                st.markdown(f"- #{r.id} **{r.titulo}** ({r.similitud:.0%} parecida)")
        nueva = {"id": str(1000 + len(st.session_state.extra) + 1), "titulo": titulo, "descripcion": desc,
                 "distrito": distrito, "barrio": barrio, "presupuesto_estimado": str(pres),
                 "origen": "demo", "decision_real": "", "motivo_real": ""}
        with st.spinner("Analizando con IA…"):
            try:
                res = classify(nueva)
            except Exception as e:
                st.error(f"No se pudo clasificar en vivo: {e}")
                res = None
        if res:
            if res["estado_sugerido"] == "rechazo_sugerido":
                st.error("⚠️ " + " ".join(cr["motivo"] for cr in res["criterios"].values() if cr.get("ok") is False))
            elif res["estado_sugerido"] == "revisar":
                st.warning("ℹ️ Un técnico revisará algún aspecto: " + res.get("resumen", ""))
            else:
                st.success("✅ Tu propuesta cumple los requisitos básicos.")
            st.caption(f"⏱ {res.get('segundos', 0)} s · coste {res.get('coste_usd', 0):.5f} $ · {res.get('modelo')}")
            st.session_state.extra.append((nueva, res))
            st.info("La propuesta ya aparece en la bandeja del técnico.")
