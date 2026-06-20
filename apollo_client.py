# -*- coding: utf-8 -*-
"""
Cliente de la API de Apollo.io para traer decisores reales por empresa.

La API key NUNCA se hardcodea: se lee de st.secrets["apollo_api_key"] o de la
variable de entorno APOLLO_API_KEY. La búsqueda consume créditos de Apollo, por
lo que se ejecuta solo bajo demanda (botón), no automáticamente.

Notas de la API (pueden cambiar según el plan/versión de Apollo):
- Auth por header  X-Api-Key.
- People Search:   POST /api/v1/mixed_people/search   (emails suelen venir
  enmascarados; revelarlos consume créditos vía enriquecimiento).
- People Match:    POST /api/v1/people/match          (enriquece 1 persona).
- Org Search:      POST /api/v1/mixed_companies/search
"""
from __future__ import annotations

import os
import requests

BASE = "https://api.apollo.io"
TIMEOUT = 25


class ApolloError(Exception):
    pass


def get_api_key() -> str | None:
    """Obtiene la API key de secrets o entorno (sin exponerla)."""
    try:
        import streamlit as st
        if "apollo_api_key" in st.secrets:
            return str(st.secrets["apollo_api_key"]).strip()
    except Exception:
        pass
    k = os.environ.get("APOLLO_API_KEY")
    return k.strip() if k else None


class ApolloClient:
    def __init__(self, api_key: str, base: str = BASE):
        if not api_key:
            raise ApolloError("Falta la API key de Apollo.")
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
            "X-Api-Key": api_key,
        })

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base}{path}"
        try:
            r = self.s.post(url, json=payload, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ApolloError(f"Error de red: {e}")
        if r.status_code == 401:
            raise ApolloError("401: API key inválida o sin permisos de API en tu plan.")
        if r.status_code == 403:
            raise ApolloError("403: tu plan no habilita este endpoint (search/enrichment via API).")
        if r.status_code == 422:
            raise ApolloError(f"422: parámetros inválidos — {r.text[:200]}")
        if r.status_code == 429:
            raise ApolloError("429: límite de tasa o créditos agotados en Apollo.")
        if not r.ok:
            raise ApolloError(f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except Exception:
            raise ApolloError("Respuesta no-JSON de Apollo.")

    # ---- Operaciones --------------------------------------------------------
    def health(self) -> dict:
        """Verifica la conexión. Intenta /auth/health y cae a una micro-búsqueda."""
        url = f"{self.base}/api/v1/auth/health"
        try:
            r = self.s.get(url, timeout=TIMEOUT)
            if r.ok:
                j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                logged = j.get("is_logged_in", j.get("logged_in"))
                if logged is False:
                    return {"ok": False, "detalle": "API key inválida o no autenticada (is_logged_in=false)."}
                return {"ok": True, "detalle": j or "Conexión OK."}
            if r.status_code in (401, 403):
                return {"ok": False, "detalle": f"HTTP {r.status_code}: revisa la API key / permisos de API."}
        except requests.RequestException as e:
            return {"ok": False, "detalle": f"Error de red: {e}"}
        # Fallback: búsqueda mínima
        try:
            self.search_people(titles=["Gerente de Operaciones"], locations=["Chile"], per_page=1)
            return {"ok": True, "detalle": "Conexión OK (vía people search)."}
        except ApolloError as e:
            return {"ok": False, "detalle": str(e)}

    def search_people(self, titles: list[str], locations: list[str] | None = None,
                      org_domains: list[str] | None = None, org_name: str | None = None,
                      page: int = 1, per_page: int = 10) -> dict:
        payload = {
            "person_titles": titles,
            "person_locations": locations or ["Chile"],
            "page": page,
            "per_page": max(1, min(per_page, 25)),
        }
        if org_domains:
            payload["q_organization_domains_list"] = org_domains
        elif org_name:
            payload["q_keywords"] = org_name
        data = self._post("/api/v1/mixed_people/api_search", payload)
        people = [_norm_person(p) for p in (data.get("people") or [])]
        pg = data.get("pagination", {}) or {}
        return {"people": people, "total": pg.get("total_entries"), "page": pg.get("page"),
                "raw_count": len(people)}

    def enrich_person(self, first_name: str, last_name: str, org_name: str | None = None,
                     domain: str | None = None, reveal_personal_emails: bool = False) -> dict:
        payload = {"first_name": first_name, "last_name": last_name,
                   "reveal_personal_emails": reveal_personal_emails}
        if org_name:
            payload["organization_name"] = org_name
        if domain:
            payload["domain"] = domain
        data = self._post("/api/v1/people/match", payload)
        return _norm_person(data.get("person") or {})

    def search_organizations(self, name: str, locations: list[str] | None = None,
                            per_page: int = 5) -> dict:
        payload = {"q_organization_name": name, "page": 1, "per_page": per_page}
        if locations:
            payload["organization_locations"] = locations
        data = self._post("/api/v1/mixed_companies/api_search", payload)
        orgs = []
        for o in (data.get("organizations") or data.get("accounts") or []):
            orgs.append({"name": o.get("name"), "domain": o.get("primary_domain") or o.get("website_url"),
                         "id": o.get("id"), "ciudad": o.get("city")})
        return {"organizations": orgs}


def _norm_person(p: dict) -> dict:
    org = p.get("organization") or {}
    phones = p.get("phone_numbers") or []
    phone = phones[0].get("sanitized_number") if phones else (p.get("sanitized_phone") or "")
    return {
        "nombre": (f"{p.get('first_name','')} {p.get('last_name','')}".strip() or p.get("name", "")),
        "first_name": p.get("first_name", ""), "last_name": p.get("last_name", ""),
        "cargo": p.get("title", ""), "seniority": p.get("seniority", ""),
        "email": p.get("email", ""), "email_status": p.get("email_status", ""),
        "linkedin": p.get("linkedin_url", ""), "telefono": phone,
        "empresa": org.get("name", ""), "dominio": org.get("primary_domain", "") or org.get("website_url", ""),
        "ciudad": p.get("city", "") or p.get("present_raw_address", ""),
        "id": p.get("id", ""),
    }


def guess_domain(nombre: str) -> str:
    """Heurística simple de dominio .cl a partir del nombre (editable por el usuario)."""
    base = nombre.lower().split("(")[0].split("/")[0]
    for w in ["s.a.", "spa", "ltda", "chile", "global", "·", ".", ","]:
        base = base.replace(w, " ")
    token = "".join(base.split())
    token = "".join(c for c in token if c.isalnum())
    return f"{token}.cl" if token else ""
