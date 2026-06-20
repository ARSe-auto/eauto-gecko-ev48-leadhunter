# ⚡ E-Auto Global · Gecko EV48 — Lead Hunter (RM)

Dashboard de cacería de leads para la van eléctrica **Gecko EV48** de **E-Auto Global**, con foco en la
Región Metropolitana de Chile. Construido en **Python + Streamlit**, con **acceso restringido** por
contraseña.

## ¿Qué incluye?
- **131 empresas/instituciones** chilenas con flota y operación urbana (56 investigadas con fuentes +
  75 del mapeo multi-agente, marcadas para validar).
- **Modelo de scoring** ponderado (Flota 25%, Urbano 20%, ESG 15%, Financiero 15%, Adopción 15%,
  Acceso 10%) → Lead Score 0–100 y Tiers A/B/C/D.
- Rankings: **Top 100, Top 20 inmediatas, Top 10 fáciles de cerrar, Top 10 volumen, Top 10 piloto**.
- **Plan de ataque** del Top 20 (argumento, ahorro, riesgos, objeciones, estrategia, probabilidades).
- **Calculadora de TCO y CO₂** interactiva (diésel vs. EV48).
- **Playbook de Apollo** (ICP, filtros, búsquedas por cuenta, secuencias, plantilla de correo).
- **Apollo en vivo**: integración con la **API de Apollo** que trae decisores reales por empresa
  (búsqueda + enriquecimiento bajo demanda). Requiere `apollo_api_key` en secrets/entorno y plan con
  acceso a API; consume créditos.
- **Informe ejecutivo** estilo McKinsey, descargable.
- Matriz de priorización y fichas por empresa.

## Ejecutar en local
```bash
cd eauto-dashboard
pip install -r requirements.txt
# Define la contraseña (recomendado): copia el ejemplo y edítalo
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # edita la clave
streamlit run app.py
```
La contraseña de acceso se define en `.streamlit/secrets.toml` (clave `password`) o en la variable
de entorno `EAUTO_DASH_PASSWORD`. **No hay clave por defecto**: sin ese secret, la app queda
bloqueada (seguridad para repo público).

## Publicar en la web con acceso restringido

### Opción A — Streamlit Community Cloud (recomendada, gratis)
1. Sube este proyecto a un repo de GitHub (ver abajo).
2. Entra a https://share.streamlit.io → **New app** → elige el repo, rama y `app.py`.
3. En **Advanced settings → Secrets**, pega:
   ```toml
   password = "tu-clave-secreta"
   ```
4. Deploy. La app queda en `https://<algo>.streamlit.app` con la contraseña como control de acceso.
   (Para restringir aún más, mantén el repo **privado** y usa el login.)

### Opción B — túnel rápido desde tu máquina (demo)
```bash
streamlit run app.py --server.port 8520 &
cloudflared tunnel --url http://localhost:8520
```
Te entrega una URL pública temporal mientras tu equipo corre el proceso.

## Estructura
```
app.py          UI Streamlit (login + páginas)
data_core.py    56 empresas investigadas (con fuentes)
data_mapped.json 75 empresas del mapeo multi-agente (validar)
data.py         consolida y dedupe el universo
scoring.py      modelo de scoring (pesos, tiers, probabilidades)
lib.py          TCO, planes de ataque, Apollo, rankings
report.py       informe ejecutivo (Markdown)
```

## Notas
- No contiene nombres/correos/teléfonos de personas: solo cargos. La capa de contactos verificados se
  extrae en **Apollo Professional**.
- Las cantidades de flota y los ahorros son **estimaciones etiquetadas**; validar contra la operación
  real y depurar en Apollo.
