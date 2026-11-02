"""Proyección de cierre al corte quincenal y alertas de rentabilidad para el comité.

Con el extracto del ERP al día 15 (corte Q1) el motor construye una base EERR
proyectada a mes completo, la distribuye con las mismas reglas del cierre y
calcula el margen neto esperado de cada proyecto. Los proyectos bajo el margen
mínimo entran a la lista del comité de rentabilidad con la utilidad en juego.

Método de proyección por rubro (config/reglas.yaml -> proyeccion):
  - Provisión proyectada (ingresos y costo de personal): en la quincena Control de
    Gestión carga la provisión proyectada del mes completo; se toma tal cual.
  - Rubros run-rate (operacionales, offshore, no operacional): lo contabilizado
    a la quincena se escala a mes completo (saldo / fracción transcurrida).
  - Rubros de referencia (gastos generales fijos): se mantienen del último mes
    cerrado del mismo proyecto.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor.config import cargar_reglas


@dataclass
class ResumenProyeccion:
    mes: str
    referencia: str
    filas_corte: int
    filas_proyectadas: int
    filas_run_rate: int
    filas_referencia: int


def construir_base_proyectada(corte: pd.DataFrame, cierre_ref: pd.DataFrame, mes: str):
    """Devuelve (base proyectada a mes completo, ResumenProyeccion)."""
    r = cargar_reglas()
    p = r["proyeccion"]
    frac = p["fraccion_quincena"]
    prov_rubros = p["rubros_provision_proyectada"]

    provision = corte[corte["EERR"].isin(prov_rubros)].assign(Origen="Provision proyectada")

    run = corte[corte["EERR"].isin(p["rubros_run_rate"])].copy()
    run["Saldo"] = np.round(run["Saldo"] / frac, 0)
    run["Debit"] = np.where(run["Saldo"] < 0, -run["Saldo"], 0.0)
    run["Credit"] = np.where(run["Saldo"] > 0, run["Saldo"], 0.0)
    run["Origen"] = "Run-rate quincena"

    ref = cierre_ref[cierre_ref["EERR"].isin(p["rubros_referencia"])].copy()
    ref["Mes"] = f"{mes}-01"
    ref["Fecha"] = f"{mes}-15"
    ref["Memo"] = ref["Memo"].astype(str) + " (referencia cierre anterior)"
    ref["Origen"] = "Referencia cierre anterior"

    otros = corte[~corte["EERR"].isin([*prov_rubros, *p["rubros_run_rate"], *p["rubros_referencia"]])]
    otros = otros.assign(Origen="Contabilizado")

    base = pd.concat([provision, run, ref, otros], ignore_index=True)
    resumen = ResumenProyeccion(mes, str(cierre_ref["Mes"].iloc[0])[:7], len(corte), len(base),
                                len(run), len(ref))
    return base, resumen


def alertas_rentabilidad(resumen_proy: pd.DataFrame, mes: str) -> pd.DataFrame:
    """Proyectos bajo el margen mínimo, con la utilidad en juego para el comité."""
    r = cargar_reglas()["rentabilidad"]
    ing = "Ingresos De Explotacion"
    d = resumen_proy[resumen_proy[ing] > 0].copy()
    d["MargenProyectado"] = d["Resultado"] / d[ing]
    bajo = d[d["MargenProyectado"] < r["margen_minimo"]].copy()
    bajo["Mes"] = mes
    bajo["Severidad"] = np.where(bajo["MargenProyectado"] < 0, "Margen negativo", "Margen bajo")
    bajo["BrechaPP"] = (r["margen_objetivo"] - bajo["MargenProyectado"]) * 100
    bajo["UtilidadPorPunto"] = np.round(bajo[ing] * 0.01, 0)
    bajo["UtilidadEnJuego"] = np.round((r["margen_objetivo"] - bajo["MargenProyectado"]) * bajo[ing], 0)
    bajo["Accion"] = "Revisar en comité de rentabilidad"
    bajo["Estado"] = "Pendiente"
    cols = ["Mes", "LineaDeNegocio", "CodigoProyecto", "Proyecto", ing, "Resultado", "MargenProyectado",
            "Severidad", "BrechaPP", "UtilidadPorPunto", "UtilidadEnJuego", "Accion", "Estado"]
    return bajo[cols].sort_values("MargenProyectado").reset_index(drop=True)


def comparar_con_cierre(resumen_proy: pd.DataFrame, resumen_real: pd.DataFrame) -> pd.DataFrame:
    """Precisión de la proyección: margen proyectado vs. margen real por proyecto."""
    ing = "Ingresos De Explotacion"
    a = resumen_proy[["CodigoProyecto", "Proyecto", "LineaDeNegocio", ing, "Resultado"]].rename(
        columns={ing: "IngresosProy", "Resultado": "ResultadoProy"})
    b = resumen_real[["CodigoProyecto", ing, "Resultado"]].rename(
        columns={ing: "IngresosReal", "Resultado": "ResultadoReal"})
    c = a.merge(b, on="CodigoProyecto", how="inner")
    c = c[(c["IngresosProy"] > 0) & (c["IngresosReal"] > 0)]
    c["MargenProy"] = c["ResultadoProy"] / c["IngresosProy"]
    c["MargenReal"] = c["ResultadoReal"] / c["IngresosReal"]
    c["ErrorPP"] = (c["MargenProy"] - c["MargenReal"]) * 100
    r = cargar_reglas()["rentabilidad"]
    c["ClasifProy"] = np.where(c["MargenProy"] < r["margen_minimo"], "Bajo", "OK")
    c["ClasifReal"] = np.where(c["MargenReal"] < r["margen_minimo"], "Bajo", "OK")
    c["Acierto"] = c["ClasifProy"] == c["ClasifReal"]
    return c.sort_values("ErrorPP", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
