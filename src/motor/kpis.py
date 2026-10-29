"""KPIs del producto de datos por nivel de madurez (IL3, IL4, IL5).

Fuentes:
  logs/ejecuciones.csv               -> registro automático de cada corrida
  logs/seguimiento_productividad.csv -> horas de cierre registradas por Control de Gestión
  output/alertas_*.csv               -> alertas de fuga y su estado

Uso:
    python -m motor.kpis
"""
from __future__ import annotations

import pandas as pd

from motor.config import RAIZ, cargar_reglas

LOGS, SALIDA = RAIZ / "logs", RAIZ / "output"


def calcular_kpis() -> pd.DataFrame:
    reglas = cargar_reglas()
    ej = pd.read_csv(LOGS / "ejecuciones.csv")
    ok = ej[ej["Estado"] == "OK"]
    alertas = pd.concat([pd.read_csv(p) for p in sorted(SALIDA.glob("alertas_*.csv"))],
                        ignore_index=True) if list(SALIDA.glob("alertas_*.csv")) else pd.DataFrame()

    base_h = reglas["linea_base_manual"]["dias_habiles_cierre"] * reglas["linea_base_manual"]["horas_por_dia"]
    meta_h = reglas["meta_motor"]["dias_habiles_cierre"] * reglas["linea_base_manual"]["horas_por_dia"]
    seg_path = LOGS / "seguimiento_productividad.csv"
    seg = pd.read_csv(seg_path) if seg_path.exists() else pd.DataFrame()
    reales = seg[(seg.get("Modalidad") == "Motor") & seg.get("HorasCierre").notna()] if not seg.empty else seg
    if len(reales):
        horas_motor, fuente = reales["HorasCierre"].mean(), f"medido ({len(reales)} cierres)"
    else:
        horas_motor, fuente = meta_h, "meta (pendiente de medición)"
    ahorro = base_h - horas_motor

    filas = [
        ("IL3", "% de filas con proyecto, línea y cuenta válidos", ok["PctValidas"].mean(), "≥ 99,5%",
         ok["PctValidas"].min() >= 0.995, "promedio de corridas"),
        ("IL3", "Diferencia de cuadratura origen vs. distribuido ($)", ok["DifCuadratura"].abs().max(), "$0",
         ok["DifCuadratura"].abs().max() == 0, "máximo de corridas"),
        ("IL3", "Filas corregidas automáticamente por mes", ok["FilasCorregidas"].mean(), "informativo",
         True, "promedio"),
        ("IL4", "% de ejecuciones mensuales sin error", len(ok) / len(ej), "≥ 99%",
         len(ok) / len(ej) >= 0.99, f"{len(ok)} de {len(ej)} corridas"),
        ("IL4", "Tiempo de ejecución por cierre (segundos)", ok["DuracionSeg"].mean(), "< 60 s",
         ok["DuracionSeg"].max() < 60, "promedio"),
        ("IL4", "Meses cerrados con el motor", ok["Mes"].nunique(), "1 por mes", True, "acumulado"),
        ("IL5", "Horas de cierre por mes (línea base manual)", base_h, "—", True, "declarado"),
        ("IL5", "Horas de cierre por mes con el motor", horas_motor, f"≤ {meta_h} h",
         None if not len(reales) else horas_motor <= meta_h, fuente),
        ("IL5", "Horas ahorradas por mes", ahorro, f"≥ {base_h - meta_h} h",
         None if not len(reales) else ahorro >= base_h - meta_h, fuente),
        ("IL5", "Aumento de productividad del cierre", ahorro / base_h, "≥ 60%",
         None if not len(reales) else ahorro / base_h >= 0.6, "horas ahorradas / horas base"),
        ("IL5", "Diferencias provisión vs. facturación detectadas ($, acumulado)",
         alertas["Monto"].abs().sum() if len(alertas) else 0, "informativo", True,
         f"{len(alertas)} alertas"),
    ]
    k = pd.DataFrame(filas, columns=["Nivel", "KPI", "Valor", "Meta", "Cumple", "Fuente"])
    k["Cumple"] = k["Cumple"].map({True: "Sí", False: "No", None: "Pendiente"}).fillna("Pendiente")
    k.loc[k["Meta"].isin(["informativo", "—"]), "Cumple"] = "—"
    k["Valor"] = k["Valor"].astype(float).round(4)
    return k


def main():
    k = calcular_kpis()
    SALIDA.mkdir(exist_ok=True)
    k.to_csv(SALIDA / "kpis_producto.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(k.to_string(index=False))


if __name__ == "__main__":
    main()
