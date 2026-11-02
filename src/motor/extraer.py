"""Capa de entrada: lectura de las fuentes del cierre mensual.

En producción la base EERR se obtiene por SuiteQL desde el ERP o como CSV
exportado; el MVP lee los CSV desde data/raw para ser reproducible.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from motor.config import RAIZ, cargar_reglas


class ErrorEntrada(Exception):
    """Falta un archivo o su estructura no cumple el contrato de datos."""


def _ruta(carpeta: Path, nombre: str) -> Path:
    ruta = carpeta / nombre
    if not ruta.exists():
        raise ErrorEntrada(f"No se encontró el archivo de entrada: {ruta.name}")
    return ruta


def leer_base_eerr(mes: str, carpeta: Path | None = None, corte: str | None = None) -> pd.DataFrame:
    """Lee Base_EERR_<mes>.csv o, con corte="Q1", el extracto parcial Base_EERR_<mes>_Q1.csv."""
    reglas = cargar_reglas()
    carpeta = carpeta or RAIZ / "data" / "raw"
    fmt = reglas["formato_csv"]
    nombre = f"Base_EERR_{mes}_{corte}.csv" if corte else f"Base_EERR_{mes}.csv"
    df = pd.read_csv(_ruta(carpeta, nombre), sep=fmt["separador"],
                     encoding=fmt["encoding"], dtype=str, keep_default_na=False)
    faltantes = [c for c in reglas["columnas_base"] if c not in df.columns]
    if faltantes:
        raise ErrorEntrada(f"{nombre}: faltan columnas {faltantes}")
    for c in ("Debit", "Credit", "Saldo"):
        df[c] = pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce")
    return df


def leer_provision(mes: str, carpeta: Path | None = None) -> pd.DataFrame:
    carpeta = carpeta or RAIZ / "data" / "raw"
    return pd.read_csv(_ruta(carpeta, f"Provision_Ingresos_{mes}.csv"))


def leer_facturacion(mes: str, carpeta: Path | None = None) -> pd.DataFrame:
    carpeta = carpeta or RAIZ / "data" / "raw"
    return pd.read_csv(_ruta(carpeta, f"Facturacion_{mes}.csv"))


def leer_maestros(carpeta: Path | None = None) -> dict[str, pd.DataFrame]:
    carpeta = carpeta or RAIZ / "data" / "maestros"
    todos = pd.read_csv(_ruta(carpeta, "maestro_proyectos.csv"))
    return {
        "codigos": todos,                                   # proyectos + gerencias + STAFF
        "proyectos": todos[todos["Tipo"] == "Proyecto"].reset_index(drop=True),
        "mapeo": pd.read_csv(_ruta(carpeta, "mapeo_campanas.csv")),
    }
