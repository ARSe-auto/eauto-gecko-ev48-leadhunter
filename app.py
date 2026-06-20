# -*- coding: utf-8 -*-
"""
E-Auto Global · Gecko EV48 — Lead Hunter (RM)
Dashboard de cacería de leads con acceso restringido.
Ejecutar:  streamlit run app.py
"""
import hmac
import os

import altair as alt
import pandas as pd
import streamlit as st

import data as datamod
import scoring
from scoring import LABELS, NIVEL_LABEL
import lib
from lib import (fmt_clp, tco_por_vehiculo, ahorro_estimado_empresa, plan_ataque,
                 apollo_query, top_inmediatas, top_faciles, top_volumen, top_piloto,
                 TIER_COLOR, PROB_EMOJI)
from report import generar_informe
import apollo_client as apollo

st.set_page_config(page_title="E-Auto · Gecko EV48 Lead Hunter",
                   page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1400px;}
[data-testid="stMetric"] {background:#1A1F2B; border:1px solid #283041; border-radius:12px; padding:14px;}
.badge {display:inline-block; padding:2px 9px; border-radius:9px; font-size:0.72rem; font-weight:700; color:#0E1117;}
.tA{background:#00B86B;} .tB{background:#3DA5FF;} .tC{background:#F5A623;} .tD{background:#9AA0A6;}
.pill {display:inline-block;padding:2px 8px;border-radius:8px;font-size:0.7rem;background:#283041;color:#C9D2E0;margin:1px;}
.hero {background:linear-gradient(110deg,#062a1c,#0E1117 60%);border:1px solid #134;border-radius:16px;padding:18px 22px;margin-bottom:8px;}
.hero h1{margin:0;font-size:1.5rem;} .hero p{margin:4px 0 0;color:#9fb3c8;}
small.src{color:#7d8aa0;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ───────────────────────── AUTENTICACIÓN ─────────────────────────
def _expected_password() -> str:
    try:
        if "password" in st.secrets:
            return str(st.secrets["password"])
    except Exception:
        pass
    return os.environ.get("EAUTO_DASH_PASSWORD", "ev48-rm-2026")


def check_password() -> bool:
    if st.session_state.get("auth_ok"):
        return True
    st.markdown("<div class='hero'><h1>⚡ E-Auto Global · Gecko EV48</h1>"
                "<p>Lead Hunter — acceso restringido</p></div>", unsafe_allow_html=True)
    with st.form("login"):
        st.text_input("Contraseña de acceso", type="password", key="pwd")
        ok = st.form_submit_button("Ingresar", type="primary")
    if ok:
        if hmac.compare_digest(st.session_state.get("pwd", ""), _expected_password()):
            st.session_state["auth_ok"] = True
            st.session_state.pop("pwd", None)
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.caption("Acceso solo para el equipo comercial de E-Auto Global. "
               "Define la contraseña en `.streamlit/secrets.toml` (clave `password`) o la variable "
               "de entorno `EAUTO_DASH_PASSWORD`.")
    return False


if not check_password():
    st.stop()


# ───────────────────────── DATOS ─────────────────────────
@st.cache_data(show_spinner=False)
def load():
    return scoring.enrich_all(datamod.EMPRESAS_ALL)


EMP = load()
PRODUCTO = datamod.PRODUCTO
N = len(EMP)
RM = [c for c in EMP if c.get("foco_rm")]


def df_from(emp, cols=None):
    rows = []
    for c in emp:
        rows.append({
            "#": c["rank"], "Empresa": c["nombre"], "Industria": c["industria"],
            "Nivel": c["nivel"], "Ubicación": c["ubicacion"], "Score": c["score"],
            "Tier": c["tier"], "Prob. compra": c["prob_compra"],
            "Flota": LABELS["flota_band"].get(c.get("flota_band"), "—"),
            "Urbano": LABELS["urbano_level"].get(c.get("urbano_level"), "—"),
            "ESG": LABELS["esg_level"].get(c.get("esg_level"), "—"),
            "Canal": LABELS["canal_compra"].get(c.get("canal_compra"), "—"),
            "Competidor EV": LABELS["competidor_ev"].get(c.get("competidor_ev"), "—"),
            "Fac. cierre": c["facilidad_cierre"], "Impacto vol.": c["impacto_volumen"],
            "Apt. piloto": c["aptitud_piloto"],
            "Dato": "✔ Investigado" if c.get("origen") == "investigado" else "⚙ Mapeo (validar)",
            "RM": "Sí" if c.get("foco_rm") else "No",
        })
    df = pd.DataFrame(rows)
    return df[cols] if cols else df


def matrix_chart(emp, x="facilidad_cierre", y="impacto_volumen",
                 xt="Facilidad de cierre →", yt="Impacto en volumen →"):
    d = pd.DataFrame([{
        "Empresa": c["nombre"], "Industria": c["industria"], x: c[x], y: c[y],
        "Score": c["score"], "Tier": c["tier"], "Prob": c["prob_compra"],
    } for c in emp])
    return (alt.Chart(d).mark_circle(opacity=0.8).encode(
        x=alt.X(f"{x}:Q", title=xt, scale=alt.Scale(zero=False)),
        y=alt.Y(f"{y}:Q", title=yt, scale=alt.Scale(zero=False)),
        size=alt.Size("Score:Q", scale=alt.Scale(range=[40, 500]), legend=None),
        color=alt.Color("Tier:N", scale=alt.Scale(
            domain=["A", "B", "C", "D"], range=["#00B86B", "#3DA5FF", "#F5A623", "#9AA0A6"])),
        tooltip=["Empresa", "Industria", "Tier", "Score", "Prob", x, y],
    ).properties(height=460).interactive())


def tier_badge(t):
    return f"<span class='badge t{t}'>Tier {t}</span>"


def render_apollo_block(company_query_name, titulos_iniciales, dominio_inicial, key_prefix):
    """UI reutilizable: búsqueda + enriquecimiento de decisores en Apollo."""
    key = apollo.get_api_key()
    if not key:
        st.info("Configura `apollo_api_key` en secrets/entorno para traer contactos desde Apollo "
                "(Apollo → Settings → Integrations → API). La búsqueda/enriquecimiento consume créditos.")
        return
    titulos = st.text_area("Cargos objetivo (uno por línea)", "\n".join(titulos_iniciales),
                           height=120, key=f"{key_prefix}_tit")
    cc = st.columns(3)
    dominio = cc[0].text_input("Dominio (opcional, mejora precisión)", dominio_inicial, key=f"{key_prefix}_dom")
    loc = cc[1].text_input("Ubicación", "Chile", key=f"{key_prefix}_loc")
    per_page = cc[2].slider("N° resultados", 1, 25, 10, key=f"{key_prefix}_pp")
    if st.button("🔎 Buscar decisores en Apollo", type="primary", key=f"{key_prefix}_btn"):
        try:
            res = apollo.ApolloClient(key).search_people(
                titles=[t.strip() for t in titulos.splitlines() if t.strip()],
                locations=[loc] if loc else ["Chile"],
                org_domains=[dominio] if dominio else None,
                org_name=None if dominio else company_query_name, per_page=per_page)
            st.session_state[f"{key_prefix}_res"] = res
        except apollo.ApolloError as e:
            st.error(str(e))
            st.session_state.pop(f"{key_prefix}_res", None)
    res = st.session_state.get(f"{key_prefix}_res")
    if res:
        people = res["people"]
        st.caption(f"{len(people)} contactos · total estimado en Apollo: {res.get('total','?')} "
                   "· (emails ocultos en la búsqueda; se revelan al enriquecer)")
        if people:
            df = pd.DataFrame([{
                "Nombre": p["nombre"], "Cargo": p["cargo"],
                "Email": p["email"] or f"({p['email_status'] or 'oculto'})",
                "Teléfono": p["telefono"], "LinkedIn": p["linkedin"], "Ciudad": p["ciudad"],
            } for p in people])
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.download_button("⬇️ Descargar contactos (CSV)", df.to_csv(index=False).encode("utf-8"),
                               f"apollo_{key_prefix}.csv", "text/csv", key=f"{key_prefix}_dl")
            etiquetas = [f"{p['nombre']} — {p['cargo']}" for p in people]
            who = st.selectbox("Revelar email/teléfono de:", etiquetas, key=f"{key_prefix}_who")
            if st.button("✨ Enriquecer contacto (consume 1 crédito)", key=f"{key_prefix}_enr"):
                pp = people[etiquetas.index(who)]
                try:
                    e = apollo.ApolloClient(key).enrich_person(
                        apollo_id=pp.get("id"), first_name=pp["first_name"], last_name=pp["last_name"],
                        org_name=pp["empresa"] or company_query_name, domain=dominio or pp["dominio"])
                    est = {"verified": "✅ verificado", "extrapolated": "≈ extrapolado",
                           "unavailable": "🔒 no disponible en Apollo", "": "—"}.get(
                               e["email_status"], e["email_status"])
                    st.success(f"**{e['nombre'] or pp['nombre']}** — {e['cargo'] or pp['cargo']}")
                    st.markdown(f"📧 **{e['email'] or '— (sin email)'}** ({est}) · "
                                f"📞 {e['telefono'] or '—'} · 🔗 {e['linkedin'] or '—'}")
                except apollo.ApolloError as ex:
                    st.error(str(ex))
        else:
            st.info("Sin resultados. Ajusta el dominio o usa cargos más amplios.")


# ───────────────────────── SIDEBAR ─────────────────────────
with st.sidebar:
    st.markdown("### ⚡ E-Auto · Gecko EV48")
    st.caption("Lead Hunter — Región Metropolitana")
    PAGES = ["🏠 Resumen ejecutivo", "🎯 Base de datos", "🔎 Evaluar empresa nueva", "🏆 Rankings",
             "🧮 Modelo de scoring", "📈 Matriz de priorización", "⚔️ Plan de ataque (Top 20)",
             "💰 Calculadora TCO & CO₂", "🔍 Playbook Apollo", "🔌 Apollo en vivo",
             "📄 Informe ejecutivo", "ℹ️ Metodología"]
    page = st.radio("Navegación", PAGES, label_visibility="collapsed")
    st.divider()
    st.metric("Cuentas en base", N)
    st.metric("Foco RM", len(RM))
    st.caption(f"Tier A: {sum(c['tier']=='A' for c in EMP)} · "
               f"B: {sum(c['tier']=='B' for c in EMP)} · "
               f"C: {sum(c['tier']=='C' for c in EMP)}")
    if st.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()


# ───────────────────────── PÁGINAS ─────────────────────────
def page_resumen():
    st.markdown(f"<div class='hero'><h1>⚡ Cacería de leads · Gecko EV48</h1>"
                f"<p>{PRODUCTO['empresa']} · {PRODUCTO['tipo']} · Foco Región Metropolitana</p></div>",
                unsafe_allow_html=True)
    c = st.columns(5)
    c[0].metric("Cuentas totales", N)
    c[1].metric("Foco RM", len(RM))
    c[2].metric("Tier A", sum(x["tier"] == "A" for x in EMP))
    c[3].metric("Prob. compra Alta/Muy Alta", sum(x["prob_compra"] in ("Alta", "Muy Alta") for x in EMP))
    c[4].metric("Investigadas c/fuente", sum(x["origen"] == "investigado" for x in EMP))

    a, b = st.columns([1, 1])
    with a:
        st.subheader("Distribución por Tier")
        dt = pd.DataFrame(
            [{"Tier": t, "Cuentas": sum(x["tier"] == t for x in EMP)} for t in ["A", "B", "C", "D"]])
        ch = alt.Chart(dt).mark_bar().encode(
            x=alt.X("Tier:N", sort=["A", "B", "C", "D"]),
            y="Cuentas:Q",
            color=alt.Color("Tier:N", scale=alt.Scale(
                domain=["A", "B", "C", "D"], range=["#00B86B", "#3DA5FF", "#F5A623", "#9AA0A6"]),
                legend=None),
            tooltip=["Tier", "Cuentas"]).properties(height=260)
        st.altair_chart(ch, use_container_width=True)
    with b:
        st.subheader("Cuentas por nivel de industria")
        dn = pd.DataFrame([{"Nivel": f"Nivel {k}", "Cuentas": sum(x["nivel"] == k for x in EMP)}
                           for k in (1, 2, 3)])
        ch = alt.Chart(dn).mark_bar(color="#00B86B").encode(
            x="Nivel:N", y="Cuentas:Q", tooltip=["Nivel", "Cuentas"]).properties(height=260)
        st.altair_chart(ch, use_container_width=True)

    st.subheader("Top 10 oportunidades inmediatas (RM)")
    st.dataframe(df_from(top_inmediatas(EMP, 10),
                 ["#", "Empresa", "Industria", "Score", "Tier", "Prob. compra", "Fac. cierre", "Dato"]),
                 hide_index=True, use_container_width=True)
    st.info("Las cuentas marcadas **⚙ Mapeo (validar)** provienen del mapeo automático y deben "
            "verificarse (y enriquecerse con contactos) en Apollo antes de comprometer recursos.")


def page_base():
    st.header("🎯 Base de datos de prospectos")
    f = st.columns(5)
    niveles = f[0].multiselect("Nivel", [1, 2, 3], default=[1, 2, 3])
    tiers = f[1].multiselect("Tier", ["A", "B", "C", "D"], default=["A", "B", "C", "D"])
    solo_rm = f[2].selectbox("Foco", ["Todas", "Solo RM", "Fuera de RM"])
    origen = f[3].selectbox("Origen del dato", ["Todos", "Investigado", "Mapeo (validar)"])
    txt = f[4].text_input("Buscar empresa / industria")

    sel = []
    for c in EMP:
        if c["nivel"] not in niveles or c["tier"] not in tiers:
            continue
        if solo_rm == "Solo RM" and not c.get("foco_rm"):
            continue
        if solo_rm == "Fuera de RM" and c.get("foco_rm"):
            continue
        if origen == "Investigado" and c["origen"] != "investigado":
            continue
        if origen == "Mapeo (validar)" and c["origen"] == "investigado":
            continue
        if txt and txt.lower() not in (c["nombre"] + " " + c["industria"]).lower():
            continue
        sel.append(c)

    st.caption(f"{len(sel)} cuentas · ordenadas por score")
    df = df_from(sel)
    st.dataframe(df, hide_index=True, use_container_width=True, height=380,
                 column_config={"Score": st.column_config.ProgressColumn(
                     "Score", min_value=0, max_value=100, format="%.1f")})
    st.download_button("⬇️ Descargar CSV", df.to_csv(index=False).encode("utf-8"),
                       "eauto_leads_ev48.csv", "text/csv")

    st.divider()
    st.subheader("Ficha de empresa")
    nombres = [c["nombre"] for c in sel] or [c["nombre"] for c in EMP]
    pick = st.selectbox("Selecciona una cuenta", nombres)
    c = next(x for x in EMP if x["nombre"] == pick)
    ficha(c)


def ficha(c):
    h = st.columns([3, 1, 1, 1])
    h[0].markdown(f"### {c['nombre']}")
    h[0].markdown(tier_badge(c["tier"]) + f" &nbsp; <span class='pill'>{c['industria']}</span> "
                  f"<span class='pill'>{c['ubicacion']}</span> "
                  f"<span class='pill'>{NIVEL_LABEL.get(c['nivel']).split('—')[0].strip()}</span>",
                  unsafe_allow_html=True)
    h[1].metric("Lead Score", c["score"])
    h[2].metric("Prob. compra", c["prob_compra"])
    h[3].metric("Dato", "Investigado" if c["origen"] == "investigado" else "Validar")

    sub = c["sub"]
    dd = pd.DataFrame([{"Dimensión": k.capitalize(), "Puntaje": v} for k, v in {
        "flota": sub["flota"], "urbano": sub["urbano"], "esg": sub["esg"],
        "financiero": sub["financiero"], "adopción": sub["adopcion"], "acceso": sub["acceso"]}.items()])
    ch = alt.Chart(dd).mark_bar(color="#00B86B").encode(
        x=alt.X("Puntaje:Q", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("Dimensión:N", sort="-x"), tooltip=["Dimensión", "Puntaje"]).properties(height=200)
    cols = st.columns([1, 1])
    cols[0].altair_chart(ch, use_container_width=True)
    with cols[1]:
        st.markdown(f"**Flota estimada:** {c.get('veh_estimados','—')}  \n"
                    f"**Vans estimadas:** {c.get('vans_estimadas','—')}  \n"
                    f"**Madurez ESG:** {LABELS['esg_level'].get(c.get('esg_level'),'—')}  \n"
                    f"**Potencial de electrificación:** {LABELS['potencial_elect'].get(c.get('potencial_elect'),'—')}  \n"
                    f"**Canal de compra:** {LABELS['canal_compra'].get(c.get('canal_compra'),'—')}  \n"
                    f"**Competidor EV:** {LABELS['competidor_ev'].get(c.get('competidor_ev'),'—')}")
    st.markdown(f"**🩹 Dolor operacional:** {c.get('dolor','—')}")
    st.markdown(f"**✅ Beneficio con EV48:** {c.get('beneficio_ev48','—')}")
    if c.get("compromiso_carbono"):
        st.markdown(f"**🌱 Compromiso de carbono:** {c['compromiso_carbono']}")
    if c.get("programas_sost"):
        st.markdown(f"**♻️ Programas de sostenibilidad:** {c['programas_sost']}")
    st.markdown(f"**🧭 Justificación:** {c.get('justificacion','—')}")
    if c.get("senales"):
        st.markdown("**📡 Señales de compra:** " +
                    " ".join(f"<span class='pill'>{s}</span>" for s in c["senales"]),
                    unsafe_allow_html=True)
    st.markdown("**👤 Decisores objetivo (cargos — verificar nombres en Apollo):** " +
                " ".join(f"<span class='pill'>{t}</span>" for t in c.get("decisores_titulos", [])),
                unsafe_allow_html=True)
    if c.get("fuentes"):
        st.markdown("<small class='src'>Fuentes: " + " · ".join(c["fuentes"]) + "</small>",
                    unsafe_allow_html=True)


def page_rankings():
    st.header("🏆 Rankings")
    tabs = st.tabs(["Top 100", "Top 20 inmediatas", "Top 10 fáciles de cerrar",
                    "Top 10 volumen", "Top 10 piloto"])
    with tabs[0]:
        st.caption("Universo completo ordenado por Lead Score (Top 100 de la base).")
        st.dataframe(df_from(EMP[:100]), hide_index=True, use_container_width=True, height=560,
                     column_config={"Score": st.column_config.ProgressColumn(
                         "Score", min_value=0, max_value=100, format="%.1f")})
    with tabs[1]:
        st.caption("Mayor score con foco RM y facilidad de cierre — el pipeline de ataque inmediato.")
        st.dataframe(df_from(top_inmediatas(EMP, 20),
                     ["#", "Empresa", "Industria", "Score", "Tier", "Prob. compra", "Fac. cierre", "Dato"]),
                     hide_index=True, use_container_width=True, height=560)
    with tabs[2]:
        st.caption("Mayor facilidad de cierre (adopción + acceso + canal directo + sin competidor).")
        st.dataframe(df_from(top_faciles(EMP, 10),
                     ["#", "Empresa", "Industria", "Fac. cierre", "Score", "Prob. compra", "Canal"]),
                     hide_index=True, use_container_width=True)
    with tabs[3]:
        st.caption("Mayor impacto en volumen de vans (tamaño de flota × intensidad urbana).")
        st.dataframe(df_from(top_volumen(EMP, 10),
                     ["#", "Empresa", "Industria", "Impacto vol.", "Flota", "Score", "Prob. compra"]),
                     hide_index=True, use_container_width=True)
    with tabs[4]:
        st.caption("Mejor aptitud para un piloto en RM (ESG + adopción + urbano + acceso).")
        st.dataframe(df_from(top_piloto(EMP, 10),
                     ["#", "Empresa", "Industria", "Apt. piloto", "Score", "Prob. compra", "ESG"]),
                     hide_index=True, use_container_width=True)


def page_scoring():
    st.header("🧮 Modelo de scoring")
    st.markdown(
        "El **Lead Score (0–100)** pondera seis dimensiones evaluadas con categorías auditables. "
        "Tier **A** > 80 · **B** 60–80 · **C** 40–59 · **D** < 40.")
    pesos = pd.DataFrame([
        {"Dimensión": "Flota", "Peso": "25%", "Qué mide": "Tamaño y propiedad de la flota (propia > tercerizada)"},
        {"Dimensión": "Recorridos urbanos", "Peso": "20%", "Qué mide": "Intensidad de uso urbano repetitivo en RM"},
        {"Dimensión": "Compromisos ESG", "Peso": "15%", "Qué mide": "Metas de carbono / madurez de sostenibilidad"},
        {"Dimensión": "Capacidad financiera", "Peso": "15%", "Qué mide": "Músculo para invertir en flota"},
        {"Dimensión": "Facilidad de adopción", "Peso": "15%", "Qué mide": "Apetito EV + rapidez + ajuste operacional"},
        {"Dimensión": "Acceso a decisores", "Peso": "10%", "Qué mide": "Organigrama claro / presencia en Apollo"},
    ])
    st.table(pesos)
    st.subheader("Score vs. Facilidad de adopción")
    d = pd.DataFrame([{"Empresa": c["nombre"], "Score": c["score"],
                       "Adopción": c["sub"]["adopcion"], "Tier": c["tier"],
                       "Industria": c["industria"]} for c in EMP])
    ch = alt.Chart(d).mark_circle(opacity=0.8).encode(
        x=alt.X("Adopción:Q", title="Facilidad de adopción →", scale=alt.Scale(zero=False)),
        y=alt.Y("Score:Q", scale=alt.Scale(zero=False)),
        color=alt.Color("Tier:N", scale=alt.Scale(
            domain=["A", "B", "C", "D"], range=["#00B86B", "#3DA5FF", "#F5A623", "#9AA0A6"])),
        tooltip=["Empresa", "Industria", "Tier", "Score"]).properties(height=420).interactive()
    st.altair_chart(ch, use_container_width=True)


def page_matriz():
    st.header("📈 Matriz de priorización")
    st.caption("Eje X: facilidad de cierre · Eje Y: impacto en volumen · Tamaño: Lead Score · Color: Tier. "
               "El cuadrante superior derecho son las apuestas ideales (fácil de cerrar y alto volumen).")
    foco = st.radio("Universo", ["Solo RM", "Todas"], horizontal=True)
    base = RM if foco == "Solo RM" else EMP
    st.altair_chart(matrix_chart(base), use_container_width=True)
    st.subheader("Score vs. Impacto en volumen")
    st.altair_chart(matrix_chart(base, x="score", y="impacto_volumen",
                                 xt="Lead Score →", yt="Impacto en volumen →"),
                    use_container_width=True)


def page_plan():
    st.header("⚔️ Plan de ataque comercial — Top 20")
    st.caption("Plan accionable por cuenta. Las probabilidades y el ahorro son estimaciones del modelo; "
               "el ahorro asume una flota convertible ilustrativa por banda de tamaño.")
    p = datamod.TCO_DEFAULTS
    top = top_inmediatas(EMP, 20)
    resumen = pd.DataFrame([{
        "#": i + 1, "Empresa": c["nombre"], "Tier": c["tier"],
        "P. reunión": c["prob_reunion"], "P. piloto": c["prob_piloto"], "P. compra": c["prob_compra"],
    } for i, c in enumerate(top)])
    st.dataframe(resumen, hide_index=True, use_container_width=True)
    st.divider()
    for i, c in enumerate(top):
        pl = plan_ataque(c, p)
        with st.expander(f"{i+1}. {c['nombre']}  ·  Score {c['score']} ({c['tier']})  ·  "
                         f"compra {PROB_EMOJI.get(c['prob_compra'],'')} {c['prob_compra']}"):
            cc = st.columns([2, 1])
            with cc[0]:
                st.markdown(f"**🎯 Argumento de venta:** {pl['argumento']}")
                st.markdown(f"**💰 Ahorro esperado:** {pl['ahorro_esperado']}")
                st.markdown(f"**🧗 Estrategia de acercamiento:** {pl['estrategia']}")
                st.markdown(f"**👤 Primer contacto ideal:** {pl['primer_contacto']}")
            with cc[1]:
                st.metric("Prob. reunión", pl["prob_reunion"])
                st.metric("Prob. piloto", pl["prob_piloto"])
                st.metric("Prob. compra", pl["prob_compra"])
            st.markdown("**⚠️ Riesgos de adopción:**")
            for r in pl["riesgos"]:
                st.markdown(f"- {r}")
            st.markdown("**🛡️ Objeciones probables:**")
            for o in pl["objeciones"]:
                st.markdown(f"- {o}")


def page_tco():
    st.header("💰 Calculadora de TCO y CO₂")
    st.caption("Ajusta los supuestos y compara van diésel vs. Gecko EV48. Cifras ilustrativas en CLP.")
    p = dict(datamod.TCO_DEFAULTS)
    c = st.columns(4)
    p["km_anio"] = c[0].slider("km/año por van", 10000, 80000, p["km_anio"], 1000)
    p["precio_diesel"] = c[1].slider("Precio diésel (CLP/L)", 700, 1500, p["precio_diesel"], 10)
    p["precio_kwh"] = c[2].slider("Precio electricidad (CLP/kWh)", 80, 300, p["precio_kwh"], 5)
    n_vans = c[3].slider("N° de vans en la flota", 1, 300, 60, 1)
    c2 = st.columns(4)
    p["diesel_l_100"] = c2[0].slider("Consumo diésel (L/100km)", 8.0, 18.0, p["diesel_l_100"], 0.5)
    p["ev_kwh_100"] = c2[1].slider("Consumo EV (kWh/100km)", 15.0, 35.0, p["ev_kwh_100"], 1.0)
    p["mant_diesel_km"] = c2[2].slider("Mantención diésel (CLP/km)", 30, 150, p["mant_diesel_km"], 5)
    p["mant_ev_km"] = c2[3].slider("Mantención EV (CLP/km)", 10, 100, p["mant_ev_km"], 5)
    sobreprecio = st.slider("Sobreprecio inicial EV vs diésel por van (CLP)", 0, 20_000_000, 8_000_000, 500_000)

    t = tco_por_vehiculo(p)
    m = st.columns(4)
    m[0].metric("Costo anual diésel/van", fmt_clp(t["total_diesel"]))
    m[1].metric("Costo anual EV/van", fmt_clp(t["total_ev"]))
    m[2].metric("Ahorro anual/van", fmt_clp(t["ahorro_anual"]))
    payback = sobreprecio / t["ahorro_anual"] if t["ahorro_anual"] > 0 else None
    m[3].metric("Payback del sobreprecio", f"{payback:.1f} años" if payback else "—")

    st.subheader(f"A nivel de flota ({n_vans} vans)")
    f = st.columns(3)
    f[0].metric("Ahorro operacional/año", fmt_clp(t["ahorro_anual"] * n_vans))
    f[1].metric("CO₂ evitado/año", f"{t['co2_ahorro_t'] * n_vans:,.0f} t".replace(",", "."))
    f[2].metric("Ahorro a 5 años", fmt_clp(t["ahorro_anual"] * n_vans * 5))

    comp = pd.DataFrame([
        {"Concepto": "Energía", "Diésel": t["energia_diesel"], "EV48": t["energia_ev"]},
        {"Concepto": "Mantención", "Diésel": t["mant_diesel"], "EV48": t["mant_ev"]},
    ]).melt("Concepto", var_name="Tecnología", value_name="CLP/año")
    ch = alt.Chart(comp).mark_bar().encode(
        x=alt.X("Tecnología:N", title=None), y="CLP/año:Q",
        color=alt.Color("Tecnología:N", scale=alt.Scale(
            domain=["Diésel", "EV48"], range=["#9AA0A6", "#00B86B"]), legend=None),
        column=alt.Column("Concepto:N", title=None),
        tooltip=["Tecnología", "CLP/año"]).properties(height=260, width=180)
    st.altair_chart(ch)
    st.caption("Modelo simplificado (no incluye incentivos tributarios, residual ni costo financiero). "
               "Úsalo como base para el caso de negocio de cada cuenta.")


def page_apollo():
    st.header("🔍 Playbook de Apollo Professional")
    st.markdown(
        "Esta base define el **ICP y las búsquedas**; la extracción de contactos verificados "
        "(nombres, correos, teléfonos, LinkedIn) se ejecuta en **Apollo Professional**, la cuenta "
        "contratada por E-Auto. No inventamos datos de personas — Apollo los entrega verificados.")

    st.subheader("1) Definición de ICP (filtros base en Apollo)")
    st.markdown("""
- **Ubicación (persona):** Chile · *Santiago, Chile* · *Región Metropolitana* (RM-first).
- **Tamaño de empresa (empleados):** 200+ para corporativos; 50+ para operadores logísticos.
- **Industrias (Apollo):** Logistics & Supply Chain · Retail · Food & Beverages · Utilities ·
  Telecommunications · Hospital & Health Care · Higher Education · Government Administration.
- **Cargos (person titles):** Gerente de Logística, Gerente de Supply Chain, Gerente de Operaciones,
  Gerente de Transporte, Gerente / Jefe de Flota, Gerente de Sostenibilidad, Director de Operaciones,
  Gerente General, Gerente de Última Milla, Gerente de Abastecimiento.
- **Señales/keywords:** *electromovilidad, flota, última milla, descarbonización, last mile,
  sostenibilidad, reparto*.
""")

    st.subheader("2) Búsquedas listas por cuenta (Top 20 RM)")
    st.caption("Copia el nombre de empresa + los cargos en la búsqueda de Apollo (People → filtros).")
    rows = []
    for c in top_inmediatas(EMP, 20):
        q = apollo_query(c)
        rows.append({"Empresa (Apollo)": q["company"],
                     "Cargos objetivo": " · ".join(q["person_titles"][:5]),
                     "Ubicación": "Chile / Santiago"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=440)

    st.subheader("3) Flujo de extracción y enriquecimiento")
    st.markdown("""
1. **Crear una Saved Search** por segmento (Courier RM, Retail RM, Utilities RM, Salud/Universidades, Sector público).
2. **Aplicar filtros ICP** (ubicación + cargos + tamaño + industria).
3. **Verificar email** (Apollo email status = *Verified*) antes de exportar.
4. **Exportar a lista/CSV** y/o **sincronizar al CRM**.
5. **Secuencias (Apollo Sequences):** 1 email + 1 LinkedIn + 1 llamada, personalizados por la *señal de compra* de la ficha.
6. **Disparadores:** crear alertas por *job changes* y noticias (nuevos CD, reportes ESG, licitaciones).
""")

    st.subheader("4) Plantilla de primer correo (personalizable por señal)")
    st.code(
        "Asunto: {Empresa}: bajar el costo de su última milla con vans eléctricas\n\n"
        "Hola {Nombre},\n\n"
        "Vi que {señal de compra: p.ej. 'anunciaron su meta de carbono-neutralidad 2030' / "
        "'inauguraron el CD de Colina'}. En operaciones urbanas repetitivas como la de {Empresa}, "
        "la van eléctrica Gecko EV48 reduce el costo por kilómetro frente al diésel y baja la "
        "mantención, con un TCO favorable.\n\n"
        "¿Tendría 20 minutos para mostrarle el caso de ahorro aplicado a una de sus rutas? "
        "Podemos partir con un piloto de 1–3 unidades y medir el ahorro real.\n\n"
        "Saludos,\n{Tu nombre} — E-Auto Global", language="text")
    st.info("Las dos vías que pediste están cubiertas: (a) este **playbook para extraer** en Apollo, "
            "y (b) si exportas tu lista de Apollo y la pegas en el chat, la **enriquezco y la integro** "
            "a esta base con el mismo scoring.")


def page_informe():
    st.header("📄 Informe ejecutivo (estilo McKinsey)")
    md = generar_informe(EMP, datamod.TCO_DEFAULTS)
    st.download_button("⬇️ Descargar informe (Markdown)", md.encode("utf-8"),
                       "informe_ejecutivo_ev48.md", "text/markdown", type="primary")
    st.markdown(md)


def page_metodo():
    st.header("ℹ️ Metodología, supuestos y límites")
    st.markdown(f"""
**Universo.** {N} empresas/instituciones con flota y operación urbana relevante para la Gecko EV48,
RM-first. **{sum(c['origen']=='investigado' for c in EMP)}** fueron investigadas con fuentes públicas
(reportes de sostenibilidad, memorias, prensa, Mercado Público) en 2023–2026; el resto proviene de un
**mapeo asistido por IA** (workflow multi-agente con verificación parcial) y está marcado como
**«⚙ Mapeo (validar)»**.

**Scoring.** Cada dimensión se evalúa con categorías auditables que mapean a un puntaje 0–100; el Lead
Score pondera Flota 25%, Urbano 20%, ESG 15%, Financiero 15%, Adopción 15%, Acceso 10%. La probabilidad
de compra ajusta el score por presencia de competidor EV instalado, perfil greenfield de alto volumen y
canal de compra (las licitaciones alargan el ciclo).

**Estimaciones.** Las cantidades de vehículos/vans y el ahorro son **estimaciones etiquetadas**, no
cifras auditadas. El ahorro a nivel de empresa asume una flota convertible ilustrativa por banda de
tamaño. Validar siempre contra la operación real del cliente.

**Datos de personas.** No se incluyen nombres, correos ni teléfonos de personas. Solo se listan
**cargos/áreas** objetivo. La capa de contactos verificados se construye en **Apollo Professional**.

**Límites conocidos.** Algunos segmentos del mapeo (municipios adicionales, residuos/aseo, facilities,
minería urbana) y la verificación adversarial de los nuevos prospectos quedaron pendientes por límite de
sesión y se completarán en una próxima corrida. Las cuentas de electromovilidad/energía (Enel X Way,
Engie) aparecen como prospecto pero son más bien **aliados de infraestructura de carga** que clientes.

**Próximos pasos.** (1) Verificar el set de mapeo; (2) extraer contactos en Apollo; (3) integrar export
de Apollo a esta base; (4) generar secuencias y empezar por los Top 10 fáciles de cerrar.
""")
    st.caption("E-Auto Global · Gecko EV48 · Dashboard de prospección — uso interno.")


def page_apollo_live():
    st.header("🔌 Apollo en vivo — decisores reales por empresa")
    key = apollo.get_api_key()
    if not key:
        st.warning("No hay API key de Apollo configurada.")
        st.markdown("""
**Cómo conectar (no pegues la key en el chat):**
1. En **Apollo → Settings → Integrations → API** copia tu *API Key*.
2. **Local:** crea `.streamlit/secrets.toml` con `apollo_api_key = "TU_API_KEY"`, o exporta
   `APOLLO_API_KEY=...` antes de `streamlit run`.
3. **Streamlit Cloud:** pégala en *Settings → Secrets* como `apollo_api_key`.
4. Recarga esta página.

> Requiere que tu plan **Apollo Professional** tenga habilitado el **acceso a API**.
> La búsqueda y el enriquecimiento **consumen créditos** de tu cuenta.
""")
        return

    st.success("API key detectada. ⚠️ Cada búsqueda/enriquecimiento consume créditos de Apollo.")
    if st.button("🔌 Probar conexión"):
        try:
            h = apollo.ApolloClient(key).health()
            (st.success if h["ok"] else st.error)(
                ("✅ Conexión OK — " if h["ok"] else "❌ Falló — ") + str(h["detalle"]))
        except apollo.ApolloError as e:
            st.error(str(e))

    st.divider()
    st.subheader("Buscar decisores por empresa")
    pick = st.selectbox("Empresa", [c["nombre"] for c in EMP], key="ap_emp")
    c = next(x for x in EMP if x["nombre"] == pick)
    q = apollo_query(c)
    render_apollo_block(q["company"], q["person_titles"], apollo.guess_domain(c["nombre"]),
                        key_prefix=f"apl_{c['rank']}")
    st.caption("La capa de contactos verificados vive en Apollo; aquí solo orquestamos las búsquedas del ICP.")


def page_evaluar():
    st.header("🔎 Evaluar / rankear una empresa nueva")
    st.caption("Ingresa cualquier empresa (esté o no en la base): el sistema la puntúa con el MISMO "
               "modelo, te dice en qué puesto quedaría frente a las demás y Apollo trae sus decisores.")
    nombre = st.text_input("Nombre de la empresa", placeholder="Ej: Transportes XYZ S.A.")

    st.markdown("**Clasifica sus atributos** (ajusta lo que sepas; el resto deja el valor por defecto):")

    def sel(col, field, label, default):
        opts = list(LABELS[field].keys())
        labs = [LABELS[field][k] for k in opts]
        ch = col.selectbox(label, labs, index=opts.index(default), key=f"ev_{field}")
        return opts[labs.index(ch)]

    cols = st.columns(2)
    flota = sel(cols[0], "flota_band", "Flota (tamaño y propiedad)", "mediana")
    urbano = sel(cols[1], "urbano_level", "Recorridos urbanos", "distribucion_mixta")
    esg = sel(cols[0], "esg_level", "Madurez ESG", "medio")
    fin = sel(cols[1], "fin_level", "Capacidad financiera", "media")
    adop = sel(cols[0], "adopcion_level", "Facilidad de adopción", "media")
    acc = sel(cols[1], "acceso_level", "Acceso a decisores", "medio")
    canal = sel(cols[0], "canal_compra", "Canal de compra", "venta_directa")
    comp = sel(cols[1], "competidor_ev", "Competidor EV instalado", "ninguno")

    c = {"nombre": nombre or "Empresa nueva", "industria": "(ingresada manualmente)", "nivel": 1,
         "foco_rm": True, "flota_band": flota, "urbano_level": urbano, "esg_level": esg,
         "fin_level": fin, "adopcion_level": adop, "acceso_level": acc, "canal_compra": canal,
         "competidor_ev": comp, "decisores_titulos": []}
    e = scoring.enrich(c)
    pos = 1 + sum(1 for x in EMP if x["score"] > e["score"])
    total = len(EMP) + 1
    pct = round(100 * (total - pos) / total)

    st.subheader(f"Resultado: {c['nombre']}")
    m = st.columns(4)
    m[0].metric("Lead Score", e["score"])
    m[1].metric("Tier", e["tier"])
    m[2].metric("Prob. compra", e["prob_compra"])
    m[3].metric("Ranking", f"#{pos} de {total}")
    st.caption(f"Quedaría por sobre el **{pct}%** de las {len(EMP)} empresas de la base "
               f"(percentil {pct}).")

    a, b = st.columns([1, 1])
    with a:
        sub = e["sub"]
        dd = pd.DataFrame([{"Dimensión": k, "Puntaje": v} for k, v in {
            "Flota": sub["flota"], "Urbano": sub["urbano"], "ESG": sub["esg"],
            "Financiero": sub["financiero"], "Adopción": sub["adopcion"], "Acceso": sub["acceso"]}.items()])
        st.altair_chart(alt.Chart(dd).mark_bar(color="#00B86B").encode(
            x=alt.X("Puntaje:Q", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Dimensión:N", sort="-x"), tooltip=["Dimensión", "Puntaje"]).properties(height=220),
            use_container_width=True)
    with b:
        ordenada = sorted(EMP, key=lambda x: x["score"], reverse=True)
        arriba = [x for x in ordenada if x["score"] >= e["score"]][-2:]
        abajo = [x for x in ordenada if x["score"] < e["score"]][:2]
        st.markdown("**Vecinos en el ranking** (para contexto):")
        vec = [{"Empresa": x["nombre"][:34], "Score": x["score"], "Tier": x["tier"]} for x in arriba]
        vec += [{"Empresa": f"➡️ {c['nombre'][:31]}", "Score": e["score"], "Tier": e["tier"]}]
        vec += [{"Empresa": x["nombre"][:34], "Score": x["score"], "Tier": x["tier"]} for x in abajo]
        st.dataframe(pd.DataFrame(vec), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Decisores en Apollo")
    render_apollo_block(c["nombre"], apollo_query(c)["person_titles"],
                        apollo.guess_domain(c["nombre"]), key_prefix="ev")


ROUTES = {
    "🏠 Resumen ejecutivo": page_resumen, "🎯 Base de datos": page_base,
    "🔎 Evaluar empresa nueva": page_evaluar,
    "🏆 Rankings": page_rankings, "🧮 Modelo de scoring": page_scoring,
    "📈 Matriz de priorización": page_matriz, "⚔️ Plan de ataque (Top 20)": page_plan,
    "💰 Calculadora TCO & CO₂": page_tco, "🔍 Playbook Apollo": page_apollo,
    "🔌 Apollo en vivo": page_apollo_live,
    "📄 Informe ejecutivo": page_informe, "ℹ️ Metodología": page_metodo,
}
ROUTES[page]()
