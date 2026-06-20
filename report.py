# -*- coding: utf-8 -*-
"""Genera el informe ejecutivo (estilo McKinsey) en Markdown desde los datos."""
from collections import Counter

from scoring import LABELS, NIVEL_LABEL
from lib import (fmt_clp, tco_por_vehiculo, ahorro_estimado_empresa,
                 top_inmediatas, top_faciles, top_volumen, top_piloto, VANS_ASUMIDAS)


def _tbl(headers, rows):
    out = "| " + " | ".join(headers) + " |\n"
    out += "| " + " | ".join("---" for _ in headers) + " |\n"
    for r in rows:
        out += "| " + " | ".join(str(x) for x in r) + " |\n"
    return out + "\n"


def generar_informe(emp: list, p: dict) -> str:
    n = len(emp)
    rm = [c for c in emp if c.get("foco_rm")]
    tiers = Counter(c["tier"] for c in emp)
    niveles = Counter(c["nivel"] for c in emp)
    inv = [c for c in emp if c["origen"] == "investigado"]
    base = tco_por_vehiculo(p)

    # Mercado: suma de vans convertibles asumidas (ilustrativo)
    vans_tam = sum(VANS_ASUMIDAS.get(c.get("flota_band"), 20) for c in emp)
    vans_rm = sum(VANS_ASUMIDAS.get(c.get("flota_band"), 20) for c in rm)
    vans_AB = sum(VANS_ASUMIDAS.get(c.get("flota_band"), 20)
                  for c in emp if c["tier"] in ("A", "B") and c.get("foco_rm"))
    ahorro_flota_unit = base["ahorro_anual"]

    L = []
    A = L.append
    A("# Informe Ejecutivo — Oportunidad Gecko EV48 en Chile\n")
    A("### E-Auto Global · Cacería de leads de vans eléctricas comerciales · Foco Región Metropolitana\n")
    A("*Documento generado automáticamente desde la base de datos de prospección. "
      "Las cifras de flota y ahorro son estimaciones etiquetadas; los contactos nominales se "
      "extraen y verifican en Apollo Professional.*\n")
    A("\n---\n")

    # 1. RESUMEN EJECUTIVO
    A("## 1. Resumen ejecutivo\n")
    A(f"Se construyó un universo de **{n} empresas e instituciones** chilenas con flota y operación "
      f"urbana relevante para la van eléctrica **Gecko EV48**, de las cuales **{len(rm)} tienen foco "
      f"en la Región Metropolitana** (prioridad de la fase 1). De ese universo, **{len(inv)}** fueron "
      "investigadas con fuentes públicas (reportes de sostenibilidad, memorias, prensa, Mercado "
      f"Público) y el resto proviene de un mapeo asistido por IA pendiente de verificación.\n")
    A("La priorización se realizó con un modelo de scoring ponderado (Flota 25%, Recorridos urbanos "
      "20%, ESG 15%, Capacidad financiera 15%, Facilidad de adopción 15%, Acceso a decisores 10%) que "
      "clasifica cada cuenta en Tier A/B/C/D.\n\n")
    A("**Hallazgos clave:**\n")
    A(f"- **{tiers['A']} cuentas Tier A** (score > 80) y **{tiers['B']} Tier B** (60–80) concentran el "
      "pipeline accionable.\n")
    A("- Los segmentos de mayor encaje son **courier/última milla**, **distribución de consumo masivo**, "
      "**servicios técnicos urbanos** (sanitarias, eléctricas, gas, telco) y **flotas institucionales** "
      "(universidades multi-campus, aeropuerto, municipios).\n")
    A("- El mejor ángulo de venta nueva está en cuentas **greenfield de alto volumen** (flota propia "
      "grande, sin proveedor EV instalado) y en quienes **ya electrificaron parcialmente** y tienen un "
      "remanente cuantificado por convertir.\n")
    A(f"- **Mercado direccionable ilustrativo:** ~**{vans_tam:,}** vans convertibles en el universo "
      f"total y ~**{vans_rm:,}** en la RM. A un ahorro estimado de **{fmt_clp(ahorro_flota_unit)}/año "
      "por van** frente a diésel, el ahorro agregado para los clientes (y la propuesta de valor de "
      f"E-Auto) supera los **{fmt_clp(ahorro_flota_unit * vans_AB)}/año** solo en cuentas A/B de la RM.\n"
      .replace(",", "."))
    A("\n---\n")

    # 2. TAMAÑO DE MERCADO
    A("## 2. Tamaño de mercado (TAM / SAM / SOM)\n")
    A("Enfoque *bottom-up* sobre el universo identificado (no es el mercado total de vehículos "
      "comerciales de Chile, sino el direccionable por E-Auto con este producto y foco):\n\n")
    A(_tbl(["Nivel", "Definición", "Vans convertibles (ilustrativo)", "Ahorro potencial cliente/año"],
           [["**TAM**", f"Universo identificado ({n} cuentas, todo Chile)", f"~{vans_tam:,}".replace(",", "."),
             fmt_clp(ahorro_flota_unit * vans_tam)],
            ["**SAM**", f"Cuentas con foco RM ({len(rm)})", f"~{vans_rm:,}".replace(",", "."),
             fmt_clp(ahorro_flota_unit * vans_rm)],
            ["**SOM (12-18m)**", "Cuentas Tier A/B en RM, objetivo realista de captura inicial",
             f"~{vans_AB:,}".replace(",", "."), fmt_clp(ahorro_flota_unit * vans_AB)]]))
    A("*Supuestos del modelo de ahorro por van/año:* "
      f"{p['km_anio']:,} km/año".replace(",", ".") +
      f", diésel {p['diesel_l_100']} L/100km a {fmt_clp(p['precio_diesel'])}/L, "
      f"EV {p['ev_kwh_100']} kWh/100km a {fmt_clp(p['precio_kwh'])}/kWh, "
      f"mantención diésel {fmt_clp(p['mant_diesel_km'])}/km vs EV {fmt_clp(p['mant_ev_km'])}/km. "
      f"Ahorro unitario ≈ **{fmt_clp(ahorro_flota_unit)}/año** y ~**{base['co2_ahorro_t']:.1f} t CO₂/año** "
      "evitadas por van.\n")
    A("\n---\n")

    # 3. SEGMENTACIÓN
    A("## 3. Segmentación del pipeline\n")
    A("**Por nivel de industria objetivo:**\n\n")
    A(_tbl(["Nivel", "Descripción", "Cuentas"],
           [[f"Nivel {k}", NIVEL_LABEL.get(k, ""), niveles.get(k, 0)] for k in (1, 2, 3)]))
    A("**Por Tier de prioridad:**\n\n")
    A(_tbl(["Tier", "Rango score", "Cuentas", "Acción recomendada"],
           [["A", "> 80", tiers["A"], "Ataque inmediato — asignar a ventas senior"],
            ["B", "60–80", tiers["B"], "Nutrir y calificar — pipeline de mediano plazo"],
            ["C", "40–59", tiers["C"], "Reservar — reactivar con disparadores (licitación, expansión)"],
            ["D", "< 40", tiers.get("D", 0), "Descartar de la fase RM-first"]]))
    A("\n---\n")

    # 4. PRINCIPALES INDUSTRIAS
    A("## 4. Principales industrias\n")
    ind = Counter(c["industria"].split("/")[0].strip() for c in emp)
    A(_tbl(["Industria (agrupada)", "Cuentas"],
           [[k, v] for k, v in ind.most_common(12)]))
    A("Los rubros de **última milla** y **distribución de consumo masivo** lideran por número y por "
      "intensidad de uso urbano; los **servicios técnicos** (utilities, telco, gas, sanitarias) "
      "destacan por flotas de recorrido repetitivo ideales para el EV48.\n")
    A("\n---\n")

    # 5. OPORTUNIDADES POR REGIÓN
    A("## 5. Oportunidades por región\n")
    A(f"La estrategia es **RM-first**: **{len(rm)} de {n}** cuentas operan en la Región Metropolitana, "
      "donde la última milla y las cuadrillas urbanas maximizan el encaje (autonomía suficiente, "
      "recorridos repetitivos, densidad de carga). Fuera de la RM, las **sanitarias y eléctricas "
      "regionales** (Essbio, Saesa, Chilquinta, Aguas Araucanía, Esval) replican un perfil operativo "
      "idéntico y forman la **ola 2** de expansión geográfica.\n")
    A("\n---\n")

    # 6. RANKING
    A("## 6. Ranking de empresas — Top 30\n")
    A(_tbl(["#", "Empresa", "Industria", "Score", "Tier", "Prob. compra"],
           [[c["rank"], c["nombre"], c["industria"][:28], c["score"], c["tier"], c["prob_compra"]]
            for c in emp[:30]]))
    A("\n---\n")

    # 7. ESTRATEGIA COMERCIAL
    A("## 7. Estrategia comercial recomendada\n")
    A("1. **Segmentar por jugada de venta**, no solo por tamaño:\n"
      "   - *Greenfield de alto volumen* (p. ej. Starken, Claro/VTR, Entel): venta evangelizadora, ser el "
      "primer proveedor EV; foco en TCO y en un argumento ESG que aún no tienen.\n"
      "   - *Remanente por convertir* (Movistar, CCU, Aguas Andinas, Chilexpress): entrar en la siguiente "
      "ronda de electrificación con mejor TCO/postventa.\n"
      "   - *Mandato ESG corporativo* (Sodexo, Aramark, Falabella, Walmart, Nestlé): vincular la compra a "
      "metas SBTi/net-zero ya públicas.\n"
      "   - *Sector público* (municipios, universidades estatales, Metro): influir en bases de licitación "
      "y usar referencias municipales (Vitacura, Las Condes).\n")
    A("2. **Liderar siempre con el caso de TCO** de la ruta urbana específica del cliente + test drive + "
      "piloto de 1–3 unidades con medición de ahorro y CO₂.\n")
    A("3. **Resolver la objeción de carga** con un partner de infraestructura (Enel X / Copec Voltex) "
      "como parte de la oferta.\n")
    A("4. **Operar el pipeline en Apollo Professional**: secuencias por segmento, contactos verificados y "
      "disparadores (licitaciones, nuevos CD, reportes ESG).\n")
    A("\n---\n")

    # 8. ROADMAP 12 MESES
    A("## 8. Roadmap de ventas — 12 meses\n")
    A(_tbl(["Trimestre", "Foco", "Objetivo"],
           [["Q1", "Quick wins RM + montaje Apollo", "Cerrar 2–3 pilotos (greenfield + remanente); 40 contactos verificados/semana"],
            ["Q2", "Conversión de pilotos + grandes cuentas", "1–2 órdenes de flota inicial; entrar a bases de licitación municipales"],
            ["Q3", "Escalamiento RM + ola 2 regiones", "Repetir casos de éxito; abrir sanitarias/eléctricas regionales"],
            ["Q4", "Grandes cuentas estratégicas", "Marcos de suministro con 1–2 cuentas Tier A de alto volumen"]]))
    A("\n---\n")

    # 9. QUICK WINS
    A("## 9. Quick wins (cierre rápido)\n")
    A(_tbl(["#", "Empresa", "Facilidad de cierre", "Por qué"],
           [[i + 1, c["nombre"], c["facilidad_cierre"], c.get("justificacion", "")[:90]]
            for i, c in enumerate(top_faciles(emp, 10))]))
    A("\n---\n")

    # 10. GRANDES CUENTAS
    A("## 10. Grandes cuentas estratégicas (mayor volumen)\n")
    A(_tbl(["#", "Empresa", "Impacto volumen", "Flota", "Prob. compra"],
           [[i + 1, c["nombre"], c["impacto_volumen"],
             LABELS["flota_band"].get(c.get("flota_band"), "—"), c["prob_compra"]]
            for i, c in enumerate(top_volumen(emp, 10))]))
    A("\n---\n")

    # 11. RIESGOS
    A("## 11. Riesgos y mitigaciones\n")
    A(_tbl(["Riesgo", "Mitigación"],
           [["Autonomía vs. ruta real", "Piloto con telemetría; dimensionar por ruta antes de vender"],
            ["Infraestructura de carga", "Oferta conjunta con Enel X / Copec Voltex; estudio de carga"],
            ["Competidores instalados (Maxus, FUSO, JAC)", "Diferenciar por TCO, postventa local y disponibilidad"],
            ["Ciclos de licitación (sector público)", "Influir en bases tempranamente; referencias municipales"],
            ["Flotas tercerizadas (gig)", "Esquemas de leasing/financiamiento para transportistas"],
            ["Calidad del dato de flota", "Validar y enriquecer en Apollo antes de comprometer recursos"]]))
    A("\n---\n")

    # 12. CONCLUSIONES
    A("## 12. Conclusiones accionables\n")
    A("1. Priorizar de inmediato las **cuentas Tier A/B de la RM** con flota propia y sin competidor EV "
      "instalado: es el camino más corto a ventas nuevas.\n")
    A("2. Convertir el **remanente por electrificar** de quienes ya empezaron (telco, utilities, courier) "
      "compitiendo por TCO y postventa.\n")
    A("3. Construir 2–3 **casos de piloto medibles** en el primer trimestre y usarlos como prueba social "
      "para escalar.\n")
    A("4. **Operacionalizar todo en Apollo**: la base de este informe define el ICP y las búsquedas; la "
      "ejecución de contactos verificados ocurre en la plataforma.\n")
    A("\n---\n")
    A("*Metodología y supuestos detallados en la pestaña «Metodología». Las cuentas marcadas como "
      "«mapeo automático» requieren verificación antes de comprometer recursos comerciales.*\n")
    return "".join(L)
