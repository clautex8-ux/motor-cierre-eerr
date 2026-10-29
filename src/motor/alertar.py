"""Capa de alertas: fuga de ingresos entre provisión y facturación.

Cruza el ingreso provisionado por campaña (base del EERR) con lo efectivamente
facturado y las notas de crédito del ERP. Cada diferencia sobre la tolerancia
genera una alerta con monto, severidad y área responsable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from motor.config import cargar_reglas


def _severidad(monto: float) -> str:
    m = abs(monto)
    if m >= 10_000_000:
        return "Alta"
    if m >= 2_000_000:
        return "Media"
    return "Baja"


def conciliar(provision: pd.DataFrame, facturacion: pd.DataFrame, mapeo: pd.DataFrame,
              maestro: pd.DataFrame):
    """Devuelve (conciliacion por proyecto, alertas, campañas sin mapeo)."""
    tol = cargar_reglas()["alertas"]
    prov = provision.merge(mapeo[["CAMPANA", "CodigoProyecto"]], on="CAMPANA", how="left")
    sin_mapeo = prov[prov["CodigoProyecto"].isna()].copy()
    prov = prov.dropna(subset=["CodigoProyecto"])
    prov = prov.groupby("CodigoProyecto", as_index=False)["PROVISION"].sum()

    fac = facturacion.copy()
    fac["Facturado"] = np.where(fac["Tipo"] == "Factura", fac["Monto"], 0.0)
    fac["NotasCredito"] = np.where(fac["Tipo"] == "Nota de Credito", fac["Monto"], 0.0)
    fac = fac.groupby("CodigoProyecto", as_index=False)[["Facturado", "NotasCredito"]].sum()

    c = prov.merge(fac, on="CodigoProyecto", how="outer").fillna(0.0)
    c = c.merge(maestro[["CodigoProyecto", "Proyecto", "LineaDeNegocio", "Cliente"]],
                on="CodigoProyecto", how="left")
    c["FacturadoNeto"] = c["Facturado"] + c["NotasCredito"]
    c["Diferencia"] = c["FacturadoNeto"] - c["PROVISION"]
    c["DiferenciaPct"] = np.where(c["PROVISION"] != 0, c["Diferencia"] / c["PROVISION"], 1.0)
    c["Conciliado"] = (c["DiferenciaPct"].abs() <= tol["tolerancia_pct"]) | \
                      (c["Diferencia"].abs() < tol["tolerancia_monto"])

    alertas = []
    for r in c.itertuples():
        base = {"CodigoProyecto": r.CodigoProyecto, "Proyecto": r.Proyecto,
                "LineaDeNegocio": r.LineaDeNegocio, "Cliente": r.Cliente,
                "Provision": r.PROVISION, "FacturadoNeto": r.FacturadoNeto}
        if r.PROVISION > 0 and r.Facturado == 0:
            alertas.append({**base, "TipoAlerta": "Provision sin factura", "Monto": -r.PROVISION,
                            "Responsable": "Facturacion"})
            continue
        if r.PROVISION == 0 and r.Facturado > 0:
            alertas.append({**base, "TipoAlerta": "Factura sin provision", "Monto": r.Facturado,
                            "Responsable": "Control de Gestion"})
            continue
        if r.NotasCredito < 0:
            alertas.append({**base, "TipoAlerta": "Nota de credito no provisionada",
                            "Monto": r.NotasCredito, "Responsable": "Comercial"})
        dif_fact = r.Facturado - r.PROVISION
        if abs(dif_fact) >= tol["tolerancia_monto"] and abs(dif_fact / r.PROVISION) > tol["tolerancia_pct"]:
            tipo = "Facturado menor a provision" if dif_fact < 0 else "Facturado mayor a provision"
            alertas.append({**base, "TipoAlerta": tipo, "Monto": dif_fact,
                            "Responsable": "Facturacion" if dif_fact < 0 else "Control de Gestion"})

    al = pd.DataFrame(alertas, columns=["CodigoProyecto", "Proyecto", "LineaDeNegocio", "Cliente",
                                        "Provision", "FacturadoNeto", "TipoAlerta", "Monto",
                                        "Responsable"])
    al["Severidad"] = al["Monto"].map(_severidad)
    al["Estado"] = "Pendiente"
    al = al.sort_values("Monto", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    return c, al, sin_mapeo
