"""KPIs del producto de datos por nivel de madurez (IL3, IL4, IL5).

Fuentes:
  logs/ejecuciones.csv               -> registro automático de cada corrida (Q1 y cierre)
  logs/seguimiento_productividad.csv -> horas de cierre registradas por Control de Gestión
  logs/seguimiento_comite.csv        -> proyectos intervenidos por el comité y su margen posterior
  output/comite_rentabilidad_*.csv   -> proyectos bajo margen mínimo en cada proyección
  output/precision_proyeccion_*.csv  -> margen proyectado vs. real al cierre
  output/alertas_*.csv               -> alertas de fuga y su estado

El IL5 principal es el impacto en rentabilidad: cada punto de margen que el comité
recupera en un proyecto equivale al 1% de los ingresos de ese proyecto en utilidad.

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
    if "Corte" not in ej.columns:
        ej["Corte"] = "Cierre"
    ok = ej[ej["Estado"] == "OK"]
    cierres = ok[ok["Corte"] == "Cierre"]
    cortes = ok[ok["Corte"] == "Q1"]

    def _leer(patron):
        rutas = sorted(SALIDA.glob(patron))
        return pd.concat([pd.read_csv(p) for p in rutas], ignore_index=True) if rutas else pd.DataFrame()
    comite = _leer("comite_rentabilidad_*_Q1.csv")
    precision = _leer("precision_proyeccion_*.csv")
    resumenes = _leer("resumen/resumen_cierre_*.csv")
    ing_mes = resumenes["Ingresos De Explotacion"].sum() / cierres["Mes"].nunique() if len(resumenes) else 0
    utilidad_por_punto = ing_mes * 0.01
    ultimo = comite[comite["Mes"] == comite["Mes"].max()] if len(comite) else comite

    seg_c = LOGS / "seguimiento_comite.csv"
    interv = pd.read_csv(seg_c) if seg_c.exists() else pd.DataFrame()
    medidos = interv[interv.get("MargenRealPosterior").notna()] if len(interv) else interv
    puntos_rec = (medidos["MargenRealPosterior"] - medidos["MargenProyectado"]).mean() * 100 if len(medidos) else None
    utilidad_rec = ((medidos["MargenRealPosterior"] - medidos["MargenProyectado"]) * medidos["Ingresos"]).sum() if len(medidos) else None
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
        ("IL4", "% de ejecuciones sin error (cortes Q1 + cierres)", len(ok) / len(ej), "≥ 99%",
         len(ok) / len(ej) >= 0.99, f"{len(ok)} de {len(ej)} corridas"),
        ("IL4", "Tiempo de ejecución por corrida (segundos)", ok["DuracionSeg"].mean(), "< 60 s",
         ok["DuracionSeg"].max() < 60, "promedio"),
        ("IL4", "Proyecciones quincenales entregadas", len(cortes), "1 por mes", True, "acumulado"),
        ("IL4", "Error medio de la proyección de margen (pp)", precision["ErrorPP"].abs().mean() if len(precision) else 0,
         "≤ 5 pp", (precision["ErrorPP"].abs().mean() <= 5) if len(precision) else None, "proyección vs. cierre"),
        ("IL4", "Acierto al clasificar proyectos bajo margen mínimo", precision["Acierto"].mean() if len(precision) else 0,
         "≥ 85%", (precision["Acierto"].mean() >= 0.85) if len(precision) else None, "proyección vs. cierre"),
        ("IL5", "Utilidad por cada punto de margen de la cartera ($/mes)", utilidad_por_punto, "informativo", True,
         "1% de los ingresos mensuales"),
        ("IL5", "Proyectos bajo margen mínimo en la última proyección", len(ultimo), "informativo", True,
         f"corte {ultimo['Mes'].max() if len(ultimo) else '-'} Q1"),
        ("IL5", "Utilidad en juego en la última proyección ($)", ultimo["UtilidadEnJuego"].sum() if len(ultimo) else 0,
         "informativo", True, "brecha a margen objetivo × ingresos"),
        ("IL5", "Puntos de margen recuperados en proyectos intervenidos (pp)", puntos_rec if puntos_rec is not None else 0,
         "≥ 3 pp", (puntos_rec >= 3) if puntos_rec is not None else None,
         f"medido ({len(medidos)} proyectos)" if puntos_rec is not None else "pendiente de medición"),
        ("IL5", "Utilidad adicional por intervenciones del comité ($)", utilidad_rec if utilidad_rec is not None else 0,
         "> 0", (utilidad_rec > 0) if utilidad_rec is not None else None,
         f"medido ({len(medidos)} proyectos)" if utilidad_rec is not None else "pendiente de medición"),
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
