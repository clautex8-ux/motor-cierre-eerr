"""Orquestador del cierre mensual: extraer -> validar -> distribuir -> alertar -> exportar.

Uso:
    python -m motor.pipeline --mes 2026-09
    python -m motor.pipeline --todos          # procesa todos los meses de data/raw

Cada ejecución queda registrada en logs/ejecuciones.csv (KPI IL4) y en logs/motor.log.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from motor import alertar, distribuir, exportar, extraer, validar
from motor.config import RAIZ, cargar_reglas

LOGS = RAIZ / "logs"
SALIDA = RAIZ / "output"
LOGS.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOGS / "motor.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("motor")


def _registrar(fila: dict):
    ruta = LOGS / "ejecuciones.csv"
    pd.DataFrame([fila]).to_csv(ruta, mode="a", header=not ruta.exists(), index=False)


def procesar_mes(mes: str, carpeta_raw: Path | None = None, salida: Path | None = None,
                 registrar: bool = True) -> dict:
    salida = salida or SALIDA
    t0 = time.perf_counter()
    tiempos = {}
    fila_log = {"FechaEjecucion": datetime.now().isoformat(timespec="seconds"), "Mes": mes}
    try:
        t = time.perf_counter()
        base = extraer.leer_base_eerr(mes, carpeta_raw)
        prov = extraer.leer_provision(mes, carpeta_raw)
        fact = extraer.leer_facturacion(mes, carpeta_raw)
        maestros = extraer.leer_maestros()
        tiempos["extraer"] = time.perf_counter() - t
        log.info("%s | extracción: %s filas EERR", mes, f"{len(base):,}")

        t = time.perf_counter()
        validas, cuarentena, calidad = validar.validar(base, mes, maestros["codigos"])
        tiempos["validar"] = time.perf_counter() - t
        log.info("%s | calidad: %.2f%% válidas, %d corregidas, %d en cuarentena",
                 mes, 100 * calidad.pct_validas, calidad.filas_corregidas, calidad.filas_cuarentena)

        t = time.perf_counter()
        eerr, cuadraturas = distribuir.ejecutar_distribucion(validas, maestros["proyectos"], mes)
        tiempos["distribuir"] = time.perf_counter() - t
        dif_max = max(abs(c.diferencia) for c in cuadraturas)
        if dif_max > 0:
            raise ValueError(f"Cuadratura fallida: diferencia de {dif_max:,.0f}")
        log.info("%s | distribución OK, cuadratura = 0", mes)

        t = time.perf_counter()
        conc, alertas, sin_mapeo = alertar.conciliar(prov, fact, maestros["mapeo"], maestros["proyectos"])
        tiempos["alertar"] = time.perf_counter() - t
        log.info("%s | %d alertas de fuga por %s", mes, len(alertas), f"{alertas['Monto'].abs().sum():,.0f}")

        t = time.perf_counter()
        resumen = distribuir.resumen_por_proyecto(eerr)
        por_linea = resumen.groupby("LineaDeNegocio", as_index=False).sum(numeric_only=True)
        por_linea["Margen %"] = por_linea["Resultado"] / por_linea["Ingresos De Explotacion"]
        rubros = [c for c in resumen.columns if c not in ("LineaDeNegocio", "CodigoProyecto",
                                                           "Proyecto", "Margen %")]
        cuad_df = pd.DataFrame([{"Regla": c.regla, "FilasOrigen": c.filas_origen,
                                 "FilasDestino": c.filas_destino, "MontoOrigen": c.monto_origen,
                                 "MontoDestino": c.monto_destino, "Diferencia": c.diferencia}
                                for c in cuadraturas])
        cal_df = pd.DataFrame([{"Indicador": k, "Valor": v} for k, v in {
            "Filas leídas": calidad.filas_total, "Filas válidas": calidad.filas_validas,
            "% filas válidas": round(calidad.pct_validas, 4),
            "Filas corregidas automáticamente": calidad.filas_corregidas,
            "Filas en cuarentena": calidad.filas_cuarentena,
            "Monto en cuarentena": calidad.monto_cuarentena,
            **{f"Incumple {k}": v for k, v in calidad.por_regla.items()}}.items()])

        exportar.exportar_excel(salida / f"EERR_Distribuido_{mes}.xlsx", {
            "Resumen_Linea": (por_linea, rubros, ["Margen %"]),
            "EERR_Proyecto": (resumen, rubros, ["Margen %"]),
            "Alertas_Fuga": (alertas, ["Provision", "FacturadoNeto", "Monto"], []),
            "Conciliacion": (conc, ["PROVISION", "Facturado", "NotasCredito", "FacturadoNeto",
                                    "Diferencia"], ["DiferenciaPct"]),
            "Cuadratura": (cuad_df, ["MontoOrigen", "MontoDestino", "Diferencia"], []),
            "Calidad_IL3": (cal_df, [], []),
            "Cuarentena": (cuarentena, ["Debit", "Credit", "Saldo"], []),
            "Detalle_Distribuido": (eerr, ["Debit", "Credit", "Saldo"], []),
        })
        exportar.exportar_powerbi(salida / "powerbi" / f"fact_eerr_{mes}.csv", eerr, mes)
        alertas.assign(Mes=mes).to_csv(salida / f"alertas_{mes}.csv", index=False)
        tiempos["exportar"] = time.perf_counter() - t

        fila_log.update({
            "Estado": "OK", "DuracionSeg": round(time.perf_counter() - t0, 2),
            "FilasLeidas": calidad.filas_total, "PctValidas": round(calidad.pct_validas, 4),
            "FilasCorregidas": calidad.filas_corregidas, "FilasCuarentena": calidad.filas_cuarentena,
            "DifCuadratura": dif_max, "FilasDistribuidas": len(eerr),
            "Alertas": len(alertas), "MontoAlertas": round(alertas["Monto"].abs().sum(), 0),
            "CampanasSinMapeo": len(sin_mapeo), "Error": "",
            **{f"Seg_{k}": round(v, 2) for k, v in tiempos.items()},
        })
        log.info("%s | ejecución OK en %.1f s", mes, fila_log["DuracionSeg"])
        return {"estado": "OK", "eerr": eerr, "resumen": resumen, "alertas": alertas,
                "calidad": calidad, "cuadraturas": cuadraturas, "log": fila_log}
    except Exception as e:  # registrar cualquier falla para el KPI IL4
        fila_log.update({"Estado": "FALLIDA", "DuracionSeg": round(time.perf_counter() - t0, 2),
                         "Error": str(e)})
        log.error("%s | ejecución FALLIDA: %s", mes, e)
        raise
    finally:
        if registrar:
            _registrar(fila_log)


def meses_disponibles(carpeta: Path | None = None) -> list[str]:
    carpeta = carpeta or RAIZ / "data" / "raw"
    return sorted(p.stem.replace("Base_EERR_", "") for p in carpeta.glob("Base_EERR_*.csv"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Motor de cierre EERR")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mes", help="Mes a procesar, formato AAAA-MM")
    g.add_argument("--todos", action="store_true", help="Procesa todos los meses en data/raw")
    a = ap.parse_args(argv)
    cargar_reglas()
    meses = meses_disponibles() if a.todos else [a.mes]
    fallas = 0
    for mes in meses:
        try:
            procesar_mes(mes)
        except Exception:
            fallas += 1
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
