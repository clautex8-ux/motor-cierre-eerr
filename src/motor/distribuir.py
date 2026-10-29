"""Capa de procesamiento: reglas de distribución del cierre EERR.

Orden de aplicación:
  1. Gerencias de línea  -> proyectos de la misma línea, por % de ingresos.
  2. Áreas STAFF         -> proyectos, según el criterio de la columna Tabla.
  3. OH Latam            -> -3% de los ingresos de cada proyecto.
  4. Impuesto a la renta -> -27% del RAI de cada proyecto.

La distribución es fila a fila: cada fila origen se reemplaza por N filas
destino que conservan toda la información contable y solo cambian proyecto,
cliente, línea, monto y la marca de trazabilidad (columna Cross). El redondeo
se hace a pesos y el residuo va al proyecto de mayor base, de modo que la
suma distribuida cuadra exactamente con el origen.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor.config import cargar_reglas


@dataclass
class Cuadratura:
    regla: str
    filas_origen: int
    filas_destino: int
    monto_origen: float
    monto_destino: float

    @property
    def diferencia(self) -> float:
        return round(self.monto_destino - self.monto_origen, 2)


def _ingresos_por_proyecto(df: pd.DataFrame) -> pd.DataFrame:
    reglas = cargar_reglas()
    ing = df[df["EERR"] == reglas["rubro_ingresos"]]
    out = ing.groupby(["CodigoProyecto", "LineaDeNegocio", "Cross1"], as_index=False)["Saldo"].sum()
    return out[out["Saldo"] > 0].rename(columns={"Saldo": "Base"})


def _prorratear(origen: pd.DataFrame, pesos: pd.DataFrame, maestro: pd.DataFrame,
                marca: str) -> pd.DataFrame:
    """Expande cada fila origen según la tabla de pesos (columnas Clave, CodigoProyecto, Base)."""
    if origen.empty:
        return origen.assign(Cross=marca)
    origen = origen.reset_index(drop=True).copy()
    origen["_id"] = origen.index
    p = pesos.copy()
    p["Peso"] = p["Base"] / p.groupby("Clave")["Base"].transform("sum")
    exp = origen.drop(columns=["CodigoProyecto"]).merge(p[["Clave", "CodigoProyecto", "Peso", "Base"]],
                                                        on="Clave", how="left")
    sin_base = exp["Peso"].isna()
    if sin_base.any():
        claves = sorted(exp.loc[sin_base, "Clave"].unique())
        raise ValueError(f"Sin base de distribución para: {claves}")

    exp["SaldoDist"] = np.round(exp["Saldo"] * exp["Peso"], 0)
    # Residuo de redondeo al destino de mayor base dentro de cada fila origen
    residuo = exp.groupby("_id")["Saldo"].first() - exp.groupby("_id")["SaldoDist"].sum()
    idx_max = exp.groupby("_id")["Base"].idxmax()
    exp.loc[idx_max.values, "SaldoDist"] += residuo.loc[idx_max.index].values

    exp["Saldo"] = exp["SaldoDist"]
    exp["Debit"] = np.where(exp["Saldo"] < 0, -exp["Saldo"], 0.0)
    exp["Credit"] = np.where(exp["Saldo"] > 0, exp["Saldo"], 0.0)

    m = maestro.set_index("CodigoProyecto")
    exp["Proyecto"] = exp["CodigoProyecto"].map(m["Proyecto"])
    exp["Cliente"] = exp["CodigoProyecto"].map(m["Cliente"])
    exp["LineaDeNegocio"] = exp["CodigoProyecto"].map(m["LineaDeNegocio"])
    exp["Memo1"] = exp["LineaDeNegocio"]
    exp["Cross1"] = exp["CodigoProyecto"].map(m["Cross1"])
    exp["CustomerJob"] = exp["Cliente"] + " : " + exp["Proyecto"]
    exp["DocumentNumber"] = marca
    exp["Cross"] = marca
    return exp.drop(columns=["_id", "Peso", "Base", "SaldoDist", "Clave"])


def distribuir_gerencias(df, maestro):
    reglas = cargar_reglas()
    es_ger = df["Proyecto"].str.startswith("Gerencia") & df["LineaDeNegocio"].isin(reglas["lineas_productivas"])
    origen = df[es_ger].copy()
    origen["Clave"] = origen["LineaDeNegocio"]
    base = _ingresos_por_proyecto(df[~es_ger]).rename(columns={"LineaDeNegocio": "Clave"})
    dist = _prorratear(origen, base, maestro, "Cross_gerencia")
    cuad = Cuadratura("Gerencias por ingresos de línea", len(origen), len(dist),
                      origen["Saldo"].sum(), dist["Saldo"].sum())
    return pd.concat([df[~es_ger], dist], ignore_index=True), cuad


def _bases_staff(df, maestro) -> pd.DataFrame:
    ing = _ingresos_por_proyecto(df)
    bases = [
        ing[ing["Cross1"] == "Local"].assign(Clave="Ingresos Local"),
        ing[ing["Cross1"] == "Off-Shore"].assign(Clave="Ingresos Offshore"),
        ing.assign(Clave="Ingresos Local + Offshore"),
        maestro[["CodigoProyecto", "FTE"]].rename(columns={"FTE": "Base"}).assign(Clave="FTE"),
    ]
    return pd.concat([b[["Clave", "CodigoProyecto", "Base"]] for b in bases], ignore_index=True)


def distribuir_staff(df, maestro):
    reglas = cargar_reglas()
    es_staff = df["LineaDeNegocio"] == reglas["linea_staff"]
    origen = df[es_staff].copy()
    origen["Clave"] = origen["Tabla"]
    dist = _prorratear(origen, _bases_staff(df[~es_staff], maestro), maestro, "Cross_STAFF")
    cuad = Cuadratura("STAFF por criterio", len(origen), len(dist),
                      origen["Saldo"].sum(), dist["Saldo"].sum())
    return pd.concat([df[~es_staff], dist], ignore_index=True), cuad


def _fila_calculada(plantilla: pd.Series, codigo, maestro_idx, rubro, cuenta, saldo, marca, mes):
    f = plantilla.copy()
    f["CodigoProyecto"] = codigo
    f["Proyecto"] = maestro_idx.loc[codigo, "Proyecto"]
    f["Cliente"] = maestro_idx.loc[codigo, "Cliente"]
    f["LineaDeNegocio"] = maestro_idx.loc[codigo, "LineaDeNegocio"]
    f["Memo1"] = f["LineaDeNegocio"]
    f["Cross1"] = maestro_idx.loc[codigo, "Cross1"]
    f["CustomerJob"] = f"{f['Cliente']} : {f['Proyecto']}"
    f["EERR"] = f["Clasificacion"] = rubro
    f["CuentaContable"] = cuenta
    f["Type"] = "Diario"
    f["Saldo"] = saldo
    f["Debit"] = -saldo if saldo < 0 else 0.0
    f["Credit"] = saldo if saldo > 0 else 0.0
    f["DocumentNumber"] = f["Cross"] = marca
    f["TransactionID"] = f"{marca}-{codigo}"
    f["Memo"] = f"{cuenta} calculado {mes}"
    f["Tabla"] = ""
    return f


def calcular_oh_latam(df, maestro, mes):
    r = cargar_reglas()["oh_latam"]
    ing = _ingresos_por_proyecto(df)
    m = maestro.set_index("CodigoProyecto")
    plantilla = df.iloc[0]
    filas = [_fila_calculada(plantilla, row.CodigoProyecto, m, r["rubro"], r["cuenta"],
                             round(-r["tasa"] * row.Base, 0), "Calculo_OH", mes)
             for row in ing.itertuples()]
    return pd.concat([df, pd.DataFrame(filas)], ignore_index=True)


def calcular_impuesto(df, maestro, mes):
    reglas = cargar_reglas()
    r = reglas["impuesto_renta"]
    rai = (df[df["EERR"].isin(reglas["rubros_rai"])]
           .groupby("CodigoProyecto")["Saldo"].sum())
    m = maestro.set_index("CodigoProyecto")
    plantilla = df.iloc[0]
    filas = [_fila_calculada(plantilla, cod, m, r["rubro"], r["cuenta"],
                             round(-r["tasa"] * valor, 0), "Calculo_Impuesto", mes)
             for cod, valor in rai.items() if cod in m.index]
    return pd.concat([df, pd.DataFrame(filas)], ignore_index=True)


def ejecutar_distribucion(validas: pd.DataFrame, maestro: pd.DataFrame, mes: str):
    """Aplica las 4 reglas en orden. Devuelve (eerr_distribuido, [Cuadratura])."""
    df = validas.copy()
    df["Cross"] = ""
    df, c1 = distribuir_gerencias(df, maestro)
    df, c2 = distribuir_staff(df, maestro)
    total_antes = validas["Saldo"].sum()
    total_despues = df["Saldo"].sum()
    c0 = Cuadratura("Total EERR antes vs. después de distribuir", len(validas), len(df),
                    total_antes, total_despues)
    df = calcular_oh_latam(df, maestro, mes)
    df = calcular_impuesto(df, maestro, mes)
    return df, [c1, c2, c0]


def resumen_por_proyecto(df: pd.DataFrame) -> pd.DataFrame:
    """EERR por proyecto en columnas de rubro, con margen y resultado."""
    piv = df.pivot_table(index=["LineaDeNegocio", "CodigoProyecto", "Proyecto"],
                         columns="EERR", values="Saldo", aggfunc="sum", fill_value=0).reset_index()
    rubros = [c for c in piv.columns if c not in ("LineaDeNegocio", "CodigoProyecto", "Proyecto")]
    piv["Resultado"] = piv[rubros].sum(axis=1)
    ing = piv.get("Ingresos De Explotacion", 0)
    piv["Margen %"] = np.where(ing != 0, piv["Resultado"] / ing, 0.0)
    return piv.sort_values(["LineaDeNegocio", "Resultado"], ascending=[True, False])
