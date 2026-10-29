"""Capa de calidad: contrato de datos de la base EERR (KPI IL3).

1. Normaliza valores corregibles (espacios, mayúsculas, línea desde el maestro).
2. Aplica las reglas del contrato y separa filas válidas de la cuarentena.
3. Devuelve un reporte con el % de filas válidas y el detalle por regla.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor.config import cargar_reglas


@dataclass
class ReporteCalidad:
    mes: str
    filas_total: int
    filas_validas: int
    filas_cuarentena: int
    filas_corregidas: int
    monto_cuarentena: float
    por_regla: dict = field(default_factory=dict)

    @property
    def pct_validas(self) -> float:
        return self.filas_validas / self.filas_total if self.filas_total else 0.0


def _lineas_validas(reglas) -> set[str]:
    return set(reglas["lineas_productivas"]) | {reglas["linea_staff"]}


def normalizar(df: pd.DataFrame, maestro: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Corrige lo que se puede corregir sin juicio humano. Devuelve (df, n_corregidas)."""
    reglas = cargar_reglas()
    df = df.copy()
    validas = _lineas_validas(reglas)
    por_mayus = {v.upper(): v for v in validas}

    for c in ("Proyecto", "CodigoProyecto", "LineaDeNegocio", "EERR", "Tabla"):
        df[c] = df[c].astype(str).str.strip()

    original = df["LineaDeNegocio"].copy()
    df["LineaDeNegocio"] = df["LineaDeNegocio"].map(lambda x: por_mayus.get(x.upper(), x))
    # La línea oficial es la del maestro: se corrige toda fila cuyo código existe
    # en el maestro y trae una línea distinta (mal digitada o desconocida)
    linea_maestro = maestro.set_index("CodigoProyecto")["LineaDeNegocio"]
    conocido = df["CodigoProyecto"].isin(linea_maestro.index)
    df.loc[conocido, "LineaDeNegocio"] = df.loc[conocido, "CodigoProyecto"].map(linea_maestro)
    corregidas = int((original != df["LineaDeNegocio"]).sum())
    return df, corregidas


def validar(df: pd.DataFrame, mes: str, maestro: pd.DataFrame):
    """Aplica el contrato de datos. Devuelve (validas, cuarentena, ReporteCalidad)."""
    reglas = cargar_reglas()
    df, corregidas = normalizar(df, maestro)

    reglas_check = {
        "R1 proyecto informado": (df["Proyecto"] != "") & (df["CodigoProyecto"] != ""),
        "R2 codigo existe en maestro": df["CodigoProyecto"].isin(maestro["CodigoProyecto"]),
        "R3 linea de negocio valida": df["LineaDeNegocio"].isin(_lineas_validas(reglas)),
        "R4 monto numerico": df["Saldo"].notna(),
        "R5 saldo = haber - debe": (df["Saldo"] - (df["Credit"].fillna(0) - df["Debit"].fillna(0))).abs() <= 1,
        "R6 mes coherente": df["Mes"].str[:7] == mes,
        "R7 criterio STAFF valido": (df["LineaDeNegocio"] != reglas["linea_staff"])
        | df["Tabla"].isin(reglas["criterios_staff"]),
    }
    ok = np.logical_and.reduce(list(reglas_check.values()))
    motivos = pd.Series("", index=df.index)
    for nombre, cumple in reglas_check.items():
        motivos[~cumple] = motivos[~cumple] + nombre + "; "

    validas = df[ok].copy()
    cuarentena = df[~ok].copy()
    cuarentena["MotivoCuarentena"] = motivos[~ok].str.rstrip("; ")

    reporte = ReporteCalidad(
        mes=mes,
        filas_total=len(df),
        filas_validas=len(validas),
        filas_cuarentena=len(cuarentena),
        filas_corregidas=corregidas,
        monto_cuarentena=float(cuarentena["Saldo"].sum()),
        por_regla={k: int((~v).sum()) for k, v in reglas_check.items()},
    )
    return validas, cuarentena, reporte
