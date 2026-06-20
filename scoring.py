"""
Motor de scoring de leads — Gecko EV48 / E-Auto Global.

Implementa el modelo de scoring del brief (pesos exactos) sobre atributos
CATEGÓRICOS por empresa. Mantener las categorías como única fuente de verdad
permite que el scoring sea consistente, reproducible y auditable.

    Flota                 25%
    Recorridos urbanos    20%
    Compromisos ESG       15%
    Capacidad financiera  15%
    Facilidad de adopción 15%
    Acceso a decisores    10%

    Lead Score = 0..100
    Tier A > 80 | B 60-80 | C 40-59 | D < 40
"""

PESOS = {
    "flota": 0.25,
    "urbano": 0.20,
    "esg": 0.15,
    "financiero": 0.15,
    "adopcion": 0.15,
    "acceso": 0.10,
}

# --- Mapas categoría -> puntaje (0-100) -------------------------------------
MAP_FLOTA = {
    "muy_grande": 95,   # > 1.000 vehículos propios última milla / servicio
    "grande": 85,       # 300 - 1.000
    "mediana": 70,      # 100 - 300
    "pequena": 55,      # 30 - 100
    "muy_pequena": 40,  # < 30
    "tercerizada_gig": 30,  # subcontratada / modelo gig
}
MAP_URB = {
    "ultima_milla_rm": 95,
    "servicio_urbano_rm": 88,
    "distribucion_mixta": 75,
    "interurbano": 60,
    "fuera_rm": 45,
}
MAP_ESG = {"lider": 92, "alto": 78, "medio": 62, "bajo": 45, "nulo": 28}
MAP_FIN = {"muy_alta": 92, "alta": 82, "media": 68, "baja": 50, "restringida": 38}
MAP_ADO = {"alta": 80, "media": 62, "baja": 45}
MAP_ACC = {"alto": 82, "medio": 62, "bajo": 45}

# Etiquetas legibles para mostrar en el dashboard
LABELS = {
    "flota_band": {
        "muy_grande": "Muy grande (>1.000)", "grande": "Grande (300-1.000)",
        "mediana": "Mediana (100-300)", "pequena": "Pequeña (30-100)",
        "muy_pequena": "Muy pequeña (<30)", "tercerizada_gig": "Tercerizada / gig",
    },
    "urbano_level": {
        "ultima_milla_rm": "Última milla RM", "servicio_urbano_rm": "Servicio urbano RM",
        "distribucion_mixta": "Distribución mixta", "interurbano": "Interurbano",
        "fuera_rm": "Fuera de la RM",
    },
    "esg_level": {"lider": "Líder", "alto": "Alto", "medio": "Medio", "bajo": "Bajo", "nulo": "Nulo"},
    "fin_level": {"muy_alta": "Muy alta", "alta": "Alta", "media": "Media", "baja": "Baja", "restringida": "Restringida"},
    "adopcion_level": {"alta": "Alta", "media": "Media", "baja": "Baja"},
    "acceso_level": {"alto": "Alto", "medio": "Medio", "bajo": "Bajo"},
    "canal_compra": {"venta_directa": "Venta directa B2B", "mercado_publico": "Mercado Público", "mixto": "Mixto"},
    "competidor_ev": {"ninguno": "Sin competidor (greenfield)", "parcial": "Competidor parcial", "fuerte": "Competidor instalado"},
    "potencial_elect": {"alto": "Alto", "medio": "Medio", "bajo": "Bajo"},
    "dato_calidad": {"investigado": "Investigado (con fuente)", "estimacion": "Estimación — validar en Apollo"},
}

NIVEL_LABEL = {
    1: "Nivel 1 — Núcleo logístico/retail",
    2: "Nivel 2 — Instituciones/servicios",
    3: "Nivel 3 — Utilities/sector público",
}


def subscores(c: dict) -> dict:
    """Devuelve los 6 sub-puntajes 0-100 a partir de las categorías."""
    return {
        "flota": MAP_FLOTA.get(c.get("flota_band"), 50),
        "urbano": MAP_URB.get(c.get("urbano_level"), 60),
        "esg": MAP_ESG.get(c.get("esg_level"), 50),
        "financiero": MAP_FIN.get(c.get("fin_level"), 60),
        "adopcion": MAP_ADO.get(c.get("adopcion_level"), 55),
        "acceso": MAP_ACC.get(c.get("acceso_level"), 55),
    }


def lead_score(c: dict) -> float:
    s = subscores(c)
    total = sum(s[k] * PESOS[k] for k in PESOS)
    return round(total, 1)


def tier(score: float) -> str:
    if score > 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def prob_compra(c: dict, score: float) -> str:
    """Probabilidad de compra cualitativa (Muy Alta / Alta / Media / Baja).

    Parte del score y ajusta por presencia de competidor EV, perfil greenfield
    de alto volumen y canal de compra (licitación alarga el ciclo).
    """
    niveles = ["Baja", "Media", "Alta", "Muy Alta"]
    if score > 82:
        idx = 2
    elif score >= 68:
        idx = 2 if c.get("competidor_ev") == "ninguno" else 1
    elif score >= 45:
        idx = 1
    else:
        idx = 0

    # Greenfield de alto volumen con ESG fuerte = oportunidad de venta nueva ideal
    if (c.get("competidor_ev") == "ninguno"
            and c.get("flota_band") in ("grande", "muy_grande")
            and c.get("esg_level") in ("alto", "lider")
            and score >= 72):
        idx = 3
    # Competidor EV ya instalado: desplazar al incumbente es más difícil
    if c.get("competidor_ev") == "fuerte":
        idx = max(0, idx - 1)
    # Mercado Público: ciclo largo, techo en "Alta"
    if c.get("canal_compra") == "mercado_publico":
        idx = min(idx, 2)
    return niveles[idx]


def enrich(c: dict) -> dict:
    """Devuelve una copia de la empresa con score, tier, prob y sub-scores."""
    out = dict(c)
    s = subscores(c)
    score = lead_score(c)
    out["sub"] = s
    out["score"] = score
    out["tier"] = tier(score)
    out["prob_compra"] = prob_compra(c, score)
    return out


def prob_reunion(c: dict) -> str:
    """Probabilidad de conseguir reunión (Alta/Media/Baja)."""
    base = {"alto": 2, "medio": 1, "bajo": 0}[c.get("acceso_level", "medio")]
    if c.get("canal_compra") == "venta_directa" and c.get("competidor_ev") == "ninguno":
        base = min(2, base + 1)
    if c.get("canal_compra") == "mercado_publico":
        base = max(0, base - 1)
    return ["Baja", "Media", "Alta"][base]


def prob_piloto(c: dict, score: float) -> str:
    """Probabilidad de avanzar a piloto (Alta/Media/Baja)."""
    pts = 0
    if c.get("adopcion_level") == "alta":
        pts += 2
    elif c.get("adopcion_level") == "media":
        pts += 1
    if c.get("esg_level") in ("lider", "alto"):
        pts += 1
    if c.get("potencial_elect") == "alto":
        pts += 1
    if score >= 75:
        pts += 1
    return ["Baja", "Baja", "Media", "Media", "Alta", "Alta"][min(pts, 5)]


def facilidad_cierre(c: dict) -> float:
    """Métrica 0-100: qué tan fácil es cerrar (adopción + acceso + canal + competidor)."""
    s = subscores(c)
    base = 0.45 * s["adopcion"] + 0.30 * s["acceso"] + 0.25 * s["esg"]
    if c.get("canal_compra") == "venta_directa":
        base += 8
    elif c.get("canal_compra") == "mercado_publico":
        base -= 10
    if c.get("competidor_ev") == "ninguno":
        base += 6
    elif c.get("competidor_ev") == "fuerte":
        base -= 10
    return round(max(0, min(100, base)), 1)


def impacto_volumen(c: dict) -> float:
    """Métrica 0-100: potencial de volumen de vans (flota + intensidad urbana)."""
    s = subscores(c)
    return round(0.65 * s["flota"] + 0.35 * s["urbano"], 1)


def aptitud_piloto(c: dict) -> float:
    """Métrica 0-100: idoneidad para un piloto (ESG + adopción + urbano + acceso + RM)."""
    s = subscores(c)
    base = 0.30 * s["esg"] + 0.25 * s["adopcion"] + 0.25 * s["urbano"] + 0.20 * s["acceso"]
    if c.get("foco_rm"):
        base += 4
    return round(max(0, min(100, base)), 1)


def enrich(c: dict) -> dict:  # noqa: F811  (redefine con métricas extra)
    out = dict(c)
    s = subscores(c)
    score = lead_score(c)
    out["sub"] = s
    out["score"] = score
    out["tier"] = tier(score)
    out["prob_compra"] = prob_compra(c, score)
    out["prob_reunion"] = prob_reunion(c)
    out["prob_piloto"] = prob_piloto(c, score)
    out["facilidad_cierre"] = facilidad_cierre(c)
    out["impacto_volumen"] = impacto_volumen(c)
    out["aptitud_piloto"] = aptitud_piloto(c)
    return out


def enrich_all(companies: list) -> list:
    out = [enrich(c) for c in companies]
    out.sort(key=lambda x: x["score"], reverse=True)
    for i, c in enumerate(out, 1):
        c["rank"] = i
    return out
