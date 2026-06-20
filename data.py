# -*- coding: utf-8 -*-
"""Carga y consolida el universo de empresas (investigadas + mapeo workflow)."""
import json
import os
import unicodedata

from data_core import EMPRESAS as _CORE, PRODUCTO, TCO_DEFAULTS  # noqa: F401

_HERE = os.path.dirname(os.path.abspath(__file__))


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return "".join(c for c in s if c.isalnum())


def _load_mapped() -> list:
    path = os.path.join(_HERE, "data_mapped.json")
    if not os.path.exists(path):
        return []
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return []


def cargar_empresas() -> list:
    """Devuelve la lista consolidada y deduplicada de empresas (dicts crudos)."""
    out, vistos = [], set()
    # Núcleo investigado primero (prioridad de dato)
    for c in _CORE:
        c = dict(c)
        c.setdefault("origen", "investigado")
        c.setdefault("verificado", True)
        k = _norm(c["nombre"])
        if k in vistos:
            continue
        vistos.add(k)
        out.append(c)
    # Mapeo del workflow (excluye exactos ya presentes)
    for c in _load_mapped():
        k = _norm(c.get("nombre", ""))
        if not k or k in vistos:
            continue
        vistos.add(k)
        out.append(c)
    return out


# Conjunto cargado una vez
EMPRESAS_ALL = cargar_empresas()
