# -*- coding: utf-8 -*-
"""Lógica de negocio del dashboard: TCO, planes de ataque, Apollo, rankings."""
from scoring import LABELS, subscores

# Vans convertibles asumidas por banda de flota (ILUSTRATIVO para estimar ahorro)
VANS_ASUMIDAS = {
    "muy_grande": 150, "grande": 60, "mediana": 30,
    "pequena": 12, "muy_pequena": 4, "tercerizada_gig": 25,
}

PROB_EMOJI = {"Muy Alta": "🟢🟢", "Alta": "🟢", "Media": "🟡", "Baja": "🔴"}
TIER_COLOR = {"A": "#00B86B", "B": "#3DA5FF", "C": "#F5A623", "D": "#9AA0A6"}


def fmt_clp(v) -> str:
    try:
        return "$" + f"{round(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def tco_por_vehiculo(p: dict) -> dict:
    """Costos y ahorro anual por vehículo (diésel vs EV) con los supuestos `p`."""
    km = p["km_anio"]
    e_diesel = km * p["diesel_l_100"] / 100 * p["precio_diesel"]
    e_ev = km * p["ev_kwh_100"] / 100 * p["precio_kwh"]
    m_diesel = km * p["mant_diesel_km"]
    m_ev = km * p["mant_ev_km"]
    total_diesel = e_diesel + m_diesel
    total_ev = e_ev + m_ev
    ahorro = total_diesel - total_ev
    co2_diesel = km * p["diesel_l_100"] / 100 * p["co2_diesel_kg_l"]
    co2_ev = km * p["ev_kwh_100"] / 100 * p["co2_grid_kg_kwh"]
    return {
        "energia_diesel": e_diesel, "energia_ev": e_ev,
        "mant_diesel": m_diesel, "mant_ev": m_ev,
        "total_diesel": total_diesel, "total_ev": total_ev,
        "ahorro_anual": ahorro,
        "co2_diesel_t": co2_diesel / 1000, "co2_ev_t": co2_ev / 1000,
        "co2_ahorro_t": (co2_diesel - co2_ev) / 1000,
    }


def ahorro_estimado_empresa(c: dict, p: dict) -> dict:
    """Ahorro anual estimado a nivel de empresa según vans convertibles asumidas."""
    n = VANS_ASUMIDAS.get(c.get("flota_band"), 20)
    base = tco_por_vehiculo(p)
    return {
        "vans": n,
        "ahorro_anual_flota": base["ahorro_anual"] * n,
        "co2_anual_flota_t": base["co2_ahorro_t"] * n,
        "ahorro_unitario": base["ahorro_anual"],
    }


# Cargos por defecto para la búsqueda en Apollo (siempre incluye Logística y Flota)
DEFAULT_TITLES = [
    "Gerente de Logística", "Jefe de Flota", "Gerente de Operaciones",
    "Gerente de Supply Chain", "Gerente de Transporte", "Gerente de Sostenibilidad",
    "Director de Operaciones", "Gerente General",
]


def apollo_query(c: dict) -> dict:
    """Construye los parámetros de búsqueda Apollo para la empresa.

    Siempre antepone 'Gerente de Logística' y 'Jefe de Flota', luego suma los
    cargos específicos de la empresa y completa con los defaults.
    """
    titulos = ["Gerente de Logística", "Jefe de Flota"]
    for t in list(c.get("decisores_titulos") or []) + DEFAULT_TITLES:
        if t not in titulos:
            titulos.append(t)
    return {
        "company": c["nombre"].split("(")[0].split("/")[0].strip(),
        "person_titles": titulos[:8],
        "person_locations": ["Chile", "Santiago, Chile", "Región Metropolitana"],
        "keywords": "flota OR logística OR sostenibilidad OR last mile OR electromovilidad",
    }


def riesgos_objeciones(c: dict) -> dict:
    """Riesgos de adopción y objeciones probables, derivados de los atributos."""
    riesgos, objeciones = [], []
    if c.get("competidor_ev") == "fuerte":
        riesgos.append("Competidor EV ya instalado: hay que desplazar a un incumbente con relación y postventa probadas.")
        objeciones.append("«Ya tenemos proveedor de vans eléctricas».")
    elif c.get("competidor_ev") == "parcial":
        objeciones.append("«Estamos evaluando con otra marca».")
    if c.get("canal_compra") == "mercado_publico":
        riesgos.append("Compra por licitación (Mercado Público): ciclo largo y especificaciones rígidas.")
        objeciones.append("«Debe ir a licitación / convenio marco».")
    if c.get("flota_band") in ("tercerizada_gig",):
        riesgos.append("Flota tercerizada/gig: la decisión depende de operadores externos, no solo del cliente.")
        objeciones.append("«La flota la ponen nuestros transportistas».")
    if c.get("esg_level") in ("bajo", "nulo"):
        objeciones.append("«El ESG no es prioridad / no hay presupuesto verde».")
    if c.get("fin_level") == "restringida":
        riesgos.append("Restricción financiera: sensibilidad alta a CAPEX inicial.")
        objeciones.append("«No hay CAPEX disponible este año».")
    # Objeciones universales de EV comercial
    objeciones.append("«¿La autonomía aguanta nuestra ruta diaria?»")
    objeciones.append("«¿Dónde y cuánto cuesta cargar la flota?»")
    if not riesgos:
        riesgos.append("Riesgo bajo: validar autonomía real vs. ruta y disponibilidad de carga.")
    return {"riesgos": riesgos, "objeciones": objeciones}


def estrategia_acercamiento(c: dict) -> str:
    if c.get("canal_compra") == "mercado_publico":
        return ("Doble vía: (1) reunión técnica temprana con el área usuaria y Sostenibilidad para "
                "influir en las bases; (2) seguimiento de licitaciones en Mercado Público y propuesta "
                "de prueba de concepto. Adjuntar caso de ahorro/TCO y referencias municipales.")
    if c.get("competidor_ev") == "fuerte":
        return ("Entrar como segundo proveedor competitivo: foco en TCO, postventa local y disponibilidad. "
                "Proponer un piloto comparativo lado a lado en una ruta acotada.")
    if c.get("flota_band") == "tercerizada_gig":
        return ("Abordar al área corporativa de sostenibilidad/operaciones con un esquema de financiamiento/"
                "leasing para sus transportistas, más un piloto con la flota propia disponible.")
    return ("Venta directa consultiva: llegar al área de Operaciones/Logística con un análisis de TCO de su "
            "ruta urbana, ofrecer test drive y un piloto de 1-3 unidades con medición de ahorro y CO₂.")


def plan_ataque(c: dict, p: dict) -> dict:
    """Genera el plan de ataque comercial completo para una empresa enriquecida."""
    ah = ahorro_estimado_empresa(c, p)
    ro = riesgos_objeciones(c)
    titulos = c.get("decisores_titulos") or ["Gerente de Operaciones"]
    primer = next((t for t in titulos if any(k in t for k in
                  ["Sostenib", "Sustent"])), None) if c.get("esg_level") in ("lider", "alto") else None
    if not primer:
        primer = next((t for t in titulos if any(k in t for k in
                      ["Logística", "Operac", "Flota", "Supply", "Distribuc"])), titulos[0])
    return {
        "argumento": f"{c.get('beneficio_ev48','')} TCO favorable: ahorro estimado de "
                     f"{fmt_clp(ah['ahorro_unitario'])}/año por van vs. diésel.",
        "ahorro_esperado": f"~{fmt_clp(ah['ahorro_anual_flota'])}/año si convierte ~{ah['vans']} vans "
                           f"(ilustrativo) · evita ~{ah['co2_anual_flota_t']:.0f} t CO₂/año.",
        "riesgos": ro["riesgos"],
        "objeciones": ro["objeciones"],
        "estrategia": estrategia_acercamiento(c),
        "primer_contacto": primer,
        "prob_reunion": c.get("prob_reunion"),
        "prob_piloto": c.get("prob_piloto"),
        "prob_compra": c.get("prob_compra"),
    }


# ---- Rankings derivados -----------------------------------------------------
def top_inmediatas(emp: list, n=20) -> list:
    rm = [c for c in emp if c.get("foco_rm")]
    return sorted(rm, key=lambda c: (c["score"], c["facilidad_cierre"]), reverse=True)[:n]


def top_faciles(emp: list, n=10) -> list:
    cand = [c for c in emp if c["score"] >= 55 and c.get("foco_rm")]
    return sorted(cand, key=lambda c: c["facilidad_cierre"], reverse=True)[:n]


def top_volumen(emp: list, n=10) -> list:
    return sorted(emp, key=lambda c: (c["impacto_volumen"], c["score"]), reverse=True)[:n]


def top_piloto(emp: list, n=10) -> list:
    cand = [c for c in emp if c.get("foco_rm")]
    return sorted(cand, key=lambda c: c["aptitud_piloto"], reverse=True)[:n]
