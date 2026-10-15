"""Pre-filtro de propuestas VLCParticipa – panel del técnico municipal.

Ejecutar:  streamlit run app.py
"""
import html
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from batch import metricas
from classify import API_KEY, MODEL, classify_dict, presupuesto_del_distrito
from duplicates import agrupar, buscar_parecidas

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "propuestas.csv"
JSON = ROOT / "data" / "clasificacion.json"
MIN_POR_PROPUESTA = 20  # supuesto para estimar el tiempo ahorrado (decirlo en el pitch)

# ---------- Estilo ----------
MARINO, TEXTO, GRIS, BORDE, FONDO = "#1f3a5f", "#1f2933", "#66727f", "#dde2e8", "#f5f6f8"
COLOR = {"duplicado": "#4f7ca8", "fuera_competencia": "#6d5596", "fuera_presupuesto": "#c48a1c",
         "no_inversion": "#b0593b", "sin_alertas": "#5e8a6c"}
ICONO = {"duplicado": "content_copy", "fuera_competencia": "account_balance", "fuera_presupuesto": "euro",
         "no_inversion": "event_busy", "sin_alertas": "check_circle"}
NOMBRE = {"duplicado": "Duplicado", "fuera_competencia": "Fuera de competencia",
          "fuera_presupuesto": "Fuera de presupuesto", "no_inversion": "No inversión"}
SIN_ALERTAS = "Sin alertas · a priori viable"
AVISO_VECINO = "Puedes enviarla igualmente; un técnico la revisará."

st.set_page_config(page_title="Pre-filtro de propuestas VLCParticipa", page_icon=":material/search:", layout="wide")
st.markdown(f"""<style>
.stApp {{background:{FONDO};}}
[data-testid='stDecoration'] {{display:none;}}
.stTabs [data-baseweb='tab-highlight'] {{background:{MARINO};}}
.stTabs [aria-selected='true'] p {{color:{MARINO}; font-weight:600;}}
.stTabs [data-baseweb='tab'] p {{font-size:1rem;}}
button[kind='primary'], button[kind='primaryFormSubmit'] {{background:{MARINO}; border-color:{MARINO};}}
button[kind='primary']:hover {{background:#2c4f7c; border-color:#2c4f7c;}}
.block-container {{padding-top:2rem; max-width:1400px;}}
.mi {{font-family:'Material Symbols Rounded'; font-weight:400; font-style:normal; font-size:20px; line-height:1;
  display:inline-block; vertical-align:-4px; font-feature-settings:'liga'; -webkit-font-smoothing:antialiased;}}
.cab {{border-top:5px solid {MARINO}; background:#fff; border:1px solid {BORDE}; border-top:5px solid {MARINO};
  border-radius:6px; padding:18px 24px 14px; margin-bottom:18px;}}
.cab .t {{font-size:1.75rem; font-weight:700; color:{MARINO}; letter-spacing:-0.01em;}}
.cab .t .mi {{font-size:30px; vertical-align:-6px; margin-right:6px;}}
.cab .s {{color:{GRIS}; font-size:1rem; margin-top:4px;}}
.cab .s b {{color:{TEXTO};}}
.kpis {{display:grid; grid-template-columns:repeat(4, 1fr); gap:14px; margin-bottom:10px;}}
@media (max-width:900px) {{.kpis {{grid-template-columns:repeat(2, 1fr);}}}}
.kpi {{background:#fff; border:1px solid {BORDE}; border-radius:8px; padding:14px 18px;}}
.kpi .mi {{font-size:24px; color:{MARINO};}}
.kpi .n {{font-size:2.3rem; font-weight:700; color:{TEXTO}; line-height:1.15; margin-top:6px;}}
.kpi .l {{color:{TEXTO}; font-size:0.95rem; font-weight:600;}}
.kpi .x {{color:{GRIS}; font-size:0.8rem; margin-top:2px;}}
.nota {{color:{GRIS}; font-size:0.85rem;}}
.pill {{display:inline-block; padding:2px 10px 2px 7px; margin:1px 4px 1px 0; border-radius:999px; font-size:0.8rem;
  font-weight:600; border:1px solid; white-space:nowrap;}}
.pill .mi {{font-size:15px; vertical-align:-3px; margin-right:3px;}}
.tabla {{max-height:430px; overflow:auto; background:#fff; border:1px solid {BORDE}; border-radius:8px;}}
.tabla table {{width:100%; border-collapse:collapse; font-size:0.9rem;}}
.tabla th {{position:sticky; top:0; background:#eef1f5; color:{TEXTO}; text-align:left; padding:8px 10px;
  font-weight:600; border-bottom:1px solid {BORDE};}}
.tabla td {{padding:7px 10px; border-bottom:1px solid #eef0f3; color:{TEXTO}; vertical-align:top;}}
.tarjeta {{background:#fff; border:1px solid {BORDE}; border-radius:6px;
  padding:10px 14px; margin:8px 0 6px;}}
.tarjeta .h {{font-weight:700;}}
.tarjeta .m {{color:{TEXTO}; margin-top:3px;}}
.tarjeta .r {{color:{GRIS}; font-size:0.83rem; margin-top:4px;}}
.estado {{float:right; font-size:0.75rem; color:{GRIS}; border:1px solid {BORDE}; border-radius:4px; padding:0 6px;}}
.caja {{background:#fff; border:1px solid {BORDE}; border-radius:8px; padding:12px 16px; margin:8px 0;}}
.caja .h {{font-size:0.75rem; font-weight:700; letter-spacing:0.06em; color:{GRIS}; text-transform:uppercase;}}
.titulo {{font-size:1.35rem; font-weight:700; color:{MARINO}; margin:4px 0 6px;}}
.barra {{background:#e6e9ee; border-radius:4px; height:12px; margin:6px 0 4px;}}
.barra div {{background:{MARINO}; height:12px; border-radius:4px;}}
.met .v {{font-size:1.6rem; font-weight:700; color:{TEXTO};}}
.met .l {{color:{TEXTO}; font-weight:600;}}
.borrador {{display:inline-block; font-size:0.75rem; font-weight:700; letter-spacing:0.06em; color:{COLOR["fuera_presupuesto"]};
  border:1px solid {COLOR["fuera_presupuesto"]}; border-radius:4px; padding:1px 8px; margin-bottom:6px;}}
</style>""", unsafe_allow_html=True)


def mi(nombre):
    return f"<span class='mi'>{nombre}</span>"


def pill(t, extra=""):
    texto = NOMBRE.get(t, "Sin alertas") + extra
    return (f"<span class='pill' style='color:{COLOR[t]}; border-color:{COLOR[t]}55; background:{COLOR[t]}12'>"
            f"{mi(ICONO[t])}{texto}</span>")


def tarjeta(t, cabecera, mensaje, resto="", estado=""):
    est = f"<span class='estado'>{html.escape(estado)}</span>" if estado else ""
    r = f"<div class='r'>{resto}</div>" if resto else ""
    return (f"<div class='tarjeta' style='border-left:5px solid {COLOR[t]}'>{est}"
            f"<div class='h' style='color:{COLOR[t]}'>{mi(ICONO[t])} {html.escape(cabecera)}</div>"
            f"<div class='m'>{html.escape(mensaje)}</div>{r}</div>")


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
st.markdown(f"<div class='cab'><div class='t'>{mi('search')}Pre-filtro de propuestas VLCParticipa</div>"
            "<div class='s'>Asistente para la validación técnica de los presupuestos participativos de València · "
            "<b>La IA señala, el técnico decide</b></div></div>", unsafe_allow_html=True)

n = len(df)
con = df["tipos"].map(bool)
n_sin, n_con = int((~con).sum()), int(con.sum())
costes = [c.get("coste_usd", 0) for c in cls.values()]
coste_medio = sum(costes) / len(costes) if costes else 0
m = metricas(df)


def kpi(icono, num, etiqueta, extra="", color=MARINO):
    x = f"<div class='x'>{extra}</div>" if extra else ""
    return (f"<div class='kpi'><span class='mi' style='color:{color}'>{icono}</span>"
            f"<div class='n'>{num}</div><div class='l'>{etiqueta}</div>{x}</div>")


st.markdown("<div class='kpis'>"
            + kpi("inbox", n, "Propuestas")
            + kpi("check_circle", n_sin, "Sin alertas", color=COLOR["sin_alertas"])
            + kpi("flag", n_con, "Con alertas", color=COLOR["fuera_presupuesto"])
            + kpi("schedule", f"{n * MIN_POR_PROPUESTA / 60 * 0.6:.0f} h", "Tiempo de cribado estimado ahorrado",
                  f"Estimación: {MIN_POR_PROPUESTA} min por propuesta, 60 % del cribado asistido")
            + "</div>", unsafe_allow_html=True)
st.markdown(f"<span class='nota'>Coste IA medio: {coste_medio:.4f} $/propuesta · "
            f"modelo: {MODEL if API_KEY else 'simulado (sin clave)'}</span>", unsafe_allow_html=True)

tab_resumen, tab_bandeja, tab_dup, tab_nueva = st.tabs([
    ":material/insights: Resumen", ":material/inbox: Bandeja de revisión",
    ":material/content_copy: Duplicados", ":material/edit_note: Nueva propuesta (vista vecino)"])


# ---------- Gráficos (Altair) ----------
def titulo(texto, sub=""):
    return alt.TitleParams(texto, subtitle=sub, anchor="start", fontSize=18, color=MARINO, subtitleColor=GRIS,
                           subtitleFontSize=13, offset=12)


def estilo(chart):
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(grid=False, domain=False, ticks=False, labelColor=TEXTO, labelFontSize=13, labelLimit=220)
            .configure_legend(labelFontSize=13, labelColor=TEXTO, symbolType="square")
            .configure(background="#ffffff", padding=14))


def dibujar(chart):
    st.altair_chart(estilo(chart), use_container_width=True, theme=None)


ORDEN_TIPOS = ["fuera_competencia", "fuera_presupuesto", "no_inversion", "duplicado"]

with tab_resumen:
    # 1. Sin alertas frente a cada tipo (cada propuesta, una vez: por su alerta principal)
    principal = df.tipos.map(lambda s: next((t for t in ORDEN_TIPOS if t in s), "sin_alertas"))
    c1 = principal.value_counts().rename_axis("cat").reset_index(name="n").sort_values("n", ascending=False)
    c1["nombre"] = c1.cat.map(lambda t: NOMBRE.get(t, "Sin alertas"))
    c1["fin"] = c1.n.cumsum()
    c1["ini"] = c1.fin - c1.n
    c1["medio"] = (c1.ini + c1.fin) / 2
    c1["pct"] = c1.n / n
    dom = c1.nombre.tolist()
    escala = alt.Scale(domain=dom, range=[COLOR[t] for t in c1.cat])
    base = alt.Chart(c1)
    barras = base.mark_bar(height=48).encode(
        x=alt.X("ini:Q", axis=None, scale=alt.Scale(domain=[0, n], nice=False)), x2="fin:Q",
        color=alt.Color("nombre:N", scale=escala, sort=dom, legend=None),
        tooltip=[alt.Tooltip("nombre:N", title="Categoría"), alt.Tooltip("n:Q", title="Propuestas"),
                 alt.Tooltip("pct:Q", title="Del total", format=".0%")])
    etiquetas = base.transform_filter("datum.n >= 3").mark_text(color="white", fontSize=16, fontWeight="bold").encode(
        x="medio:Q", text="n:Q")
    dibujar((barras + etiquetas).properties(
        height=110, title=titulo(f"{n_sin} de {n} propuestas no necesitan análisis profundo",
                                "Cada propuesta se cuenta una vez, por su alerta principal")))
    st.markdown("<div style='margin:-6px 0 10px'>" + "".join(pill(r.cat, f" · {r.n}") for r in c1.itertuples())
                + "</div>", unsafe_allow_html=True)

    clave_d = df.distrito.str.strip().str.lower()
    nombre_d = df.groupby(clave_d).distrito.agg(lambda x: x.value_counts().index[0])
    df_g = df.assign(distrito=clave_d.map(nombre_d))  # solo para los gráficos

    izq, der = st.columns(2)
    with izq:
        # 2. Presupuesto solicitado frente a partida por distrito (sin «Ciudad»)
        d2 = df_g[df_g.distrito.str.strip().str.lower() != "ciudad"].assign(
            euros=lambda x: pd.to_numeric(x.presupuesto_estimado, errors="coerce").fillna(0))
        d2 = d2.groupby("distrito", as_index=False).euros.sum()
        d2["partida"] = d2.distrito.map(presupuesto_del_distrito)
        d2 = d2.dropna(subset=["partida"])
        d2["pct"] = d2.euros / d2.partida
        d2["supera"] = d2.pct > 1
        orden = d2.sort_values("pct", ascending=False).distrito.tolist()
        tope = float(d2.partida.max()) * 1.4  # escala recortada: las barras que la superan se cortan
        d2["barra"] = d2.euros.clip(upper=tope)
        d2["pos"] = d2.barra
        escala_eur = alt.Scale(domain=[0, tope * 1.18])
        y = alt.Y("distrito:N", sort=orden, title=None)
        eje_eur = alt.Axis(labelExpr="format(datum.value / 1e6, '.1f') + ' M€'", tickCount=4, labelFontSize=12)
        tip = [alt.Tooltip("distrito:N", title="Distrito"), alt.Tooltip("euros:Q", title="Solicitado (€)", format=",.0f"),
               alt.Tooltip("partida:Q", title="Partida (€)", format=",.0f"), alt.Tooltip("pct:Q", title="% de la partida", format=".0%")]
        b2 = alt.Chart(d2).mark_bar(height=16).encode(
            x=alt.X("barra:Q", axis=eje_eur, scale=escala_eur, title=None), y=y, tooltip=tip,
            color=alt.condition("datum.supera", alt.value(COLOR["fuera_presupuesto"]), alt.value(MARINO)))
        t2 = alt.Chart(d2).mark_tick(color=TEXTO, thickness=2.5, size=24).encode(
            x=alt.X("partida:Q", scale=escala_eur, title=None), y=y, tooltip=tip)
        l2 = alt.Chart(d2).mark_text(align="left", dx=6, fontSize=12, color=TEXTO).encode(
            x=alt.X("pos:Q", scale=escala_eur, title=None), y=y, text=alt.Text("pct:Q", format=".0%"))
        dibujar((b2 + t2 + l2).properties(height=max(260, 26 * len(d2)), title=titulo(
            "Presupuesto solicitado frente a partida disponible por distrito",
            ["Barra: suma solicitada · Marca: partida oficial 2025-26 · Ámbar: supera la partida",
             "Etiqueta: % de la partida solicitado · Escala recortada en los distritos que la superan mucho"])))
    with der:
        # 3. A qué administración redirigir
        adm = [a.get("administracion") or "Sin especificar" for al in df.alertas for a in al
               if a["tipo"] == "fuera_competencia"]
        if adm:
            d3 = pd.Series(adm).value_counts().rename_axis("adm").reset_index(name="n")
            y3 = alt.Y("adm:N", sort="-x", title=None)
            b3 = alt.Chart(d3).mark_bar(height=18, color=COLOR["fuera_competencia"]).encode(
                x=alt.X("n:Q", axis=None), y=y3,
                tooltip=[alt.Tooltip("adm:N", title="Administración"), alt.Tooltip("n:Q", title="Alertas")])
            l3 = b3.mark_text(align="left", dx=6, fontSize=13, color=TEXTO).encode(text="n:Q")
            dibujar((b3 + l3).properties(height=max(110, 34 * len(d3)), title=titulo(
                "A qué administración redirigir", "Alertas de fuera de competencia por administración")))
        else:
            st.caption("No hay alertas de fuera de competencia.")

        # 4. Dónde se concentran las alertas
        filas = [(r.distrito, t) for r in df_g.itertuples() for t in r.tipos]
        if filas:
            d4 = pd.DataFrame(filas, columns=["distrito", "tipo"]).value_counts().reset_index(name="n")
            dists = d4.groupby("distrito").n.sum().sort_values(ascending=False).index.tolist()
            rejilla = pd.MultiIndex.from_product([dists, ORDEN_TIPOS], names=["distrito", "tipo"]).to_frame(index=False)
            d4 = rejilla.merge(d4, how="left").fillna({"n": 0})
            d4["nombre"] = d4.tipo.map(NOMBRE)
            d4["n"] = d4.n.astype(int)
            x4 = alt.X("nombre:N", sort=[NOMBRE[t] for t in ORDEN_TIPOS], title=None,
                       axis=alt.Axis(orient="top", labelAngle=0, labelFontSize=12))
            y4 = alt.Y("distrito:N", sort=dists, title=None)
            tip4 = [alt.Tooltip("distrito:N", title="Distrito"), alt.Tooltip("nombre:N", title="Alerta"),
                    alt.Tooltip("n:Q", title="Propuestas")]
            fondo = alt.Chart(d4).mark_rect(color="#f0f2f5", stroke="white", strokeWidth=2).encode(x=x4, y=y4, tooltip=tip4)
            celdas = alt.Chart(d4).transform_filter("datum.n > 0").mark_rect(stroke="white", strokeWidth=2).encode(
                x=x4, y=y4, tooltip=tip4,
                color=alt.Color("nombre:N", scale=alt.Scale(domain=[NOMBRE[t] for t in ORDEN_TIPOS],
                                                            range=[COLOR[t] for t in ORDEN_TIPOS]), legend=None),
                opacity=alt.Opacity("n:Q", scale=alt.Scale(range=[0.45, 1]), legend=None))
            numeros = alt.Chart(d4).transform_filter("datum.n > 0").mark_text(fontSize=14, fontWeight="bold",
                                                                               color="white").encode(x=x4, y=y4, text="n:Q")
            dibujar((fondo + celdas + numeros).properties(height=max(200, 28 * len(dists)), title=titulo(
                "Dónde se concentran las alertas", "Propuestas con cada alerta, por distrito")))

    # Coincidencia con los técnicos
    st.markdown("<div class='titulo'>Coincidencia con los técnicos</div>", unsafe_allow_html=True)

    def medidor(valor, total, texto, sub):
        pct = valor / total if total else 0
        return (f"<div class='caja met'><div class='v'>{valor} / {total}</div><div class='l'>{texto}</div>"
                f"<div class='barra'><div style='width:{pct:.0%}'></div></div><div class='nota'>{sub}</div></div>")

    m1, m2 = st.columns(2)
    m1.markdown(medidor(m["sin_falsas"], m["aprobadas"],
                        f"Sin falsas alarmas en {m['sin_falsas']} de {m['aprobadas']} aprobadas por los técnicos",
                        "Propuestas reales de ediciones anteriores"), unsafe_allow_html=True)
    m2.markdown(medidor(m["sint_ok"], m["sint_total"],
                        f"Alertas que coinciden con lo esperado: {m['sint_ok']}/{m['sint_total']}",
                        "Propuestas sintéticas con la alerta esperada etiquetada"), unsafe_allow_html=True)
    if len(m["falsas"]):
        with m1.expander(f"Ver las {len(m['falsas'])} falsas alarmas"):
            st.markdown("".join(
                f"<div style='margin:4px 0'><b>#{r.id}</b> {html.escape(r.titulo)}<br>"
                + "".join(pill(t) for t in sorted(r.tipos)) + "</div>" for r in m["falsas"].itertuples()),
                unsafe_allow_html=True)

# ---------- Bandeja ----------
with tab_bandeja:
    f1, f2, f3 = st.columns([2, 2, 3])
    distritos = f1.multiselect("Distrito", sorted(df.distrito.unique()), placeholder="Todos")
    filtro = f2.multiselect("Alertas", ["sin_alertas", *NOMBRE], format_func=lambda t: NOMBRE.get(t, "Sin alertas"),
                            placeholder="Todas")
    texto = f3.text_input("Buscar", placeholder="palabra clave…")
    vista = df.copy()
    if distritos:
        vista = vista[vista.distrito.isin(distritos)]
    if filtro:
        vista = vista[vista.tipos.map(lambda s: bool(s & set(filtro)) or (not s and "sin_alertas" in filtro))]
    if texto:
        vista = vista[vista.titulo.str.contains(texto, case=False) | vista.descripcion.str.contains(texto, case=False)]

    filas = "".join(
        f"<tr><td>{html.escape(str(r.id))}</td><td>{html.escape(r.titulo)}</td><td>{html.escape(r.distrito)}</td>"
        f"<td>{''.join(pill(t) for t in ORDEN_TIPOS[::-1] if t in r.tipos) or pill('sin_alertas')}</td>"
        f"<td>{html.escape(r.decision)}</td></tr>" for r in vista.itertuples())
    st.markdown(f"<div class='tabla'><table><thead><tr><th>ID</th><th>Título</th><th>Distrito</th><th>Alertas</th>"
                f"<th>Decisión del técnico</th></tr></thead><tbody>{filas}</tbody></table></div>"
                f"<div class='nota' style='margin-top:4px'>{len(vista)} propuestas</div>", unsafe_allow_html=True)

    st.markdown("<div class='titulo' style='margin-top:18px'>Detalle de la propuesta</div>", unsafe_allow_html=True)
    if vista.empty:
        st.markdown("<span class='nota'>No hay propuestas con estos filtros.</span>", unsafe_allow_html=True)
    else:
        sel = st.selectbox("Selecciona una propuesta", vista["id"].tolist(),
                           format_func=lambda i: f"#{i} · {df.loc[df.id == i, 'titulo'].iloc[0]}")
        p = df[df.id == sel].iloc[0]
        c = cls.get(str(sel), {})
        izq, der = st.columns([3, 2])
        with izq:
            etiquetas = "".join(pill(a["tipo"]) for a in p.alertas) or pill("sin_alertas")
            meta = f"{html.escape(p.distrito)} · {html.escape(p.barrio)} · {f'{float(p.presupuesto_estimado or 0):,.0f}'.replace(',', '.')} €"
            if p.origen == "real":
                meta += f" · Propuesta real · edición {html.escape(p.edicion)} · {html.escape(p.votos)} votos"
            st.markdown(f"<div class='caja'><div class='titulo'>{html.escape(p.titulo)}</div>{etiquetas}"
                        f"<div class='nota' style='margin-top:6px'>{meta} · Decisión del técnico: "
                        f"<b>{html.escape(p.decision)}</b></div>"
                        f"<div style='margin-top:10px; color:{TEXTO}'>{html.escape(p.descripcion)}</div>"
                        + ("<div class='nota' style='margin-top:6px'>" + mi("info") + " Sin presupuesto estimado</div>"
                           if not float(p.presupuesto_estimado or 0) else "")
                        + "</div>", unsafe_allow_html=True)
            if c.get("resumen"):
                st.markdown(f"<div class='caja'><div class='h'>Resumen IA</div>{html.escape(c['resumen'])}</div>",
                            unsafe_allow_html=True)
            if c.get("puntos_a_revisar"):
                st.markdown("<div class='caja'><div class='h'>Puntos a revisar por el técnico</div><ul style='margin:4px 0 0'>"
                            + "".join(f"<li>{html.escape(x)}</li>" for x in c["puntos_a_revisar"]) + "</ul></div>",
                            unsafe_allow_html=True)
        with der:
            st.markdown("<div class='h nota' style='font-weight:700'>ALERTAS DEL PRE-FILTRO</div>", unsafe_allow_html=True)
            if not p.alertas:
                st.markdown(tarjeta("sin_alertas", SIN_ALERTAS, "El técnico revisa igualmente la propuesta."),
                            unsafe_allow_html=True)
            for a in p.alertas:
                t, clave = a["tipo"], (str(sel), a["tipo"])
                resto = mi("gavel") + " " + html.escape(a.get("norma") or "—")
                if a.get("administracion"):
                    resto += f"<br>Administración competente: {html.escape(a['administracion'])}"
                if a.get("confianza") is not None:
                    resto += f" · confianza {a['confianza']:.0%}"
                estado = st.session_state.alertas_dec.get(clave, "")
                st.markdown(tarjeta(t, NOMBRE[t], a["mensaje"], resto, f"Alerta {estado}" if estado else ""),
                            unsafe_allow_html=True)
                x, y = st.columns(2)
                if x.button("Confirmar alerta", key=f"conf{sel}{t}", icon=":material/check:", use_container_width=True):
                    st.session_state.alertas_dec[clave] = "confirmada"
                    st.rerun()
                if y.button("Descartar alerta", key=f"desc{sel}{t}", icon=":material/close:", use_container_width=True):
                    st.session_state.alertas_dec[clave] = "descartada"
                    st.rerun()
        if st.button("Validar propuesta", icon=":material/task_alt:", type="primary", use_container_width=True):
            st.session_state.decisiones[str(sel)] = "validada"
            st.rerun()

        if c.get("borrador_carta_es") or c.get("borrador_carta_va"):
            with st.container(border=True):
                st.markdown("<span class='borrador'>BORRADOR – revisar antes de enviar</span>", unsafe_allow_html=True)
                t_es, t_va = st.tabs(["Castellano", "Valencià"])
                t_es.text_area("es", c.get("borrador_carta_es", ""), height=180, label_visibility="collapsed", key=f"es{sel}")
                t_va.text_area("va", c.get("borrador_carta_va", ""), height=180, label_visibility="collapsed", key=f"va{sel}")

# ---------- Duplicados ----------
with tab_dup:
    dups = df[df.grupo_duplicado.notna()]
    if dups.empty:
        st.markdown("<span class='nota'>No se han detectado duplicados.</span>", unsafe_allow_html=True)
    for g, grupo in dups.groupby("grupo_duplicado"):
        with st.expander(f"{g} · {len(grupo)} propuestas · {grupo.distrito.iloc[0]} — «{grupo.titulo.iloc[0]}»",
                         expanded=True, icon=":material/content_copy:"):
            st.dataframe(grupo[["id", "titulo", "descripcion", "barrio", "presupuesto_estimado"]],
                         hide_index=True, use_container_width=True)
            st.button(f"Fusionar en una propuesta y avisar a los {len(grupo)} autores", key=f"fus{g}",
                      icon=":material/merge:")

# ---------- Nueva propuesta (vista vecino) ----------
with tab_nueva:
    st.markdown("Así vería el vecino los avisos **antes de enviar** su propuesta.")
    with st.form("nueva"):
        titulo_n = st.text_input("Título")
        desc = st.text_area("Descripción")
        a, b, cc = st.columns(3)
        distrito = a.selectbox("Distrito", sorted(df_base.distrito.unique()))
        barrio = b.text_input("Barrio")
        pres = cc.number_input("Presupuesto estimado (€)", min_value=0, step=1000)
        enviar = st.form_submit_button("Revisar propuesta", icon=":material/search:", type="primary")
    if enviar and titulo_n:
        parecidas = buscar_parecidas(df, titulo_n, desc, distrito)
        if not parecidas.empty:
            lista = "".join(f"<br>#{r.id} <b>{html.escape(r.titulo)}</b> ({r.similitud:.0%} parecida)"
                            for _, r in parecidas.iterrows())
            st.markdown(tarjeta("duplicado", "Hay propuestas parecidas en tu distrito",
                                "Si quieres, puedes apoyarlas en lugar de crear otra.", lista[4:] + f"<br>{AVISO_VECINO}"),
                        unsafe_allow_html=True)
        nueva = {"id": str(1000 + len(st.session_state.extra) + 1), "titulo": titulo_n, "descripcion": desc,
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
                st.markdown(tarjeta(a["tipo"], f"Aviso orientativo · {NOMBRE[a['tipo']]}", a["mensaje"], AVISO_VECINO),
                            unsafe_allow_html=True)
            if not res["alertas"]:
                st.markdown(tarjeta("sin_alertas", SIN_ALERTAS, "Un técnico la revisará igualmente."),
                            unsafe_allow_html=True)
            st.markdown(f"<span class='nota'>{res.get('segundos', 0)} s · coste {res.get('coste_usd', 0):.5f} $ · "
                        f"{res.get('modelo')} · La propuesta ya aparece en la bandeja del técnico.</span>",
                        unsafe_allow_html=True)
            st.session_state.extra.append((nueva, res))
