"""Carga de configuración y rutas del proyecto."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_REGLAS = RAIZ / "config" / "reglas.yaml"


@lru_cache(maxsize=1)
def cargar_reglas(ruta: str | None = None) -> dict:
    """Lee config/reglas.yaml (parámetros de negocio versionados)."""
    with open(ruta or RUTA_REGLAS, encoding="utf-8") as f:
        return yaml.safe_load(f)
