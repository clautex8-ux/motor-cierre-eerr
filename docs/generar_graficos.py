"""Genera los gráficos del informe y la presentación a partir de las salidas del motor.

Uso (desde la raíz del repositorio):
    PYTHONPATH=src python docs/generar_graficos.py
"""
from __future__ import annotations

import glob
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
IMG = RAIZ / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

NAVY, CELESTE, ROSA, GRIS, TINTA, SUAVE = "#2B3990", "#1CADE4", "#F06B9E", "#C9CCD6", "#1F2430", "#6B7080"
plt.rcParams.update({
    "font.family": "Carlito", "font.size": 12, "axes.edgecolor": GRIS, "axes.labelcolor": SUAVE,
    "xtick.color": SUAVE, "ytick.color": SUAVE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#ECEDF1", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.facecolor": "white",
})
MESES = {"2026-04": "Abr", "2026-05": "May", "2026-06": "Jun", "2026-07": "Jul",
         "2026-08": "Ago", "2026-09": "Sep"}


def _titulo(ax, texto, sub=None):
    ax.set_title(texto, loc="left", fontsize=15, fontweight="bold", color=TINTA, pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=11, color=SUAVE)


def mm(x):
    return f"${x / 1e6:,.0f} MM".replace(",", ".")


def calidad(ej):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = list(range(len(ej)))
    pct = (ej["PctValidas"] * 100).tolist()
    ax.axhline(99.5, color=ROSA, lw=1.5, ls="--")
    ax.text(-0.3, 99.53, "meta 99,5%", color=ROSA, fontsize=11)
    ax.plot(x, pct, color=NAVY, lw=2, marker="o", ms=8)
    for i, (p, c, q) in enumerate(zip(pct, ej["FilasCorregidas"], ej["FilasCuarentena"])):
        ax.text(i, p + 0.035, f"{p:.2f}%".replace(".", ","), ha="center", fontsize=11, color=TINTA)
        ax.text(i, 99.12, f"{c} corregidas\n{q} cuarentena", ha="center", fontsize=9.5, color=SUAVE)
    ax.set_xticks(x, [MESES[m] for m in ej["Mes"]])
    ax.set_ylim(99.0, 100.1)
    ax.set_xlim(-0.5, len(x) - 0.5)
    ax.set_ylabel("% filas válidas")
    ax.grid(axis="x", visible=False)
    _titulo(ax, "IL3 · Todas las corridas superan 99,5% de filas válidas",
            "Filas corregidas automáticamente y filas enviadas a cuarentena por mes")
    fig.savefig(IMG / "il3_calidad.png")
    plt.close(fig)


def alertas(al):
    g = al.groupby("TipoAlerta").agg(n=("Monto", "size"), monto=("Monto", lambda s: s.abs().sum()))
    g = g.sort_values("monto")
    g.index = g.index.str.replace("Provision", "Provisión").str.replace("provision", "provisión") \
        .str.replace("credito", "crédito")
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    colores = [ROSA if t == "Provisión sin factura" else NAVY for t in g.index]
    ax.barh(g.index, g["monto"] / 1e6, color=colores, height=0.55)
    for i, (m, n) in enumerate(zip(g["monto"], g["n"])):
        ax.text(m / 1e6 + 15, i, f"{mm(m)} · {n} alertas", va="center", fontsize=11, color=TINTA)
    ax.set_xlim(0, g["monto"].max() / 1e6 * 1.45)
    ax.set_xlabel("Monto acumulado Abr–Sep 2026 (MM CLP, datos sintéticos)")
    ax.grid(axis="y", visible=False)
    _titulo(ax, "IL5 · La provisión sin factura concentra el monto en riesgo",
            f"{len(al)} alertas de diferencia provisión vs. facturación en 6 cierres")
    fig.savefig(IMG / "il5_alertas_tipo.png")
    plt.close(fig)


def tiempos(ej):
    etapas = ["extraer", "validar", "distribuir", "alertar", "exportar"]
    prom = ej[[f"Seg_{e}" for e in etapas]].mean()
    fig, ax = plt.subplots(figsize=(7.5, 2.9))
    ax.barh([e.capitalize() for e in etapas][::-1], prom.values[::-1], color=NAVY, height=0.55)
    for i, v in enumerate(prom.values[::-1]):
        ax.text(v + 0.08, i, f"{v:.2f} s".replace(".", ","), va="center", fontsize=11, color=TINTA)
    ax.set_xlim(0, prom.max() * 1.25)
    ax.set_xlabel("Segundos promedio por cierre")
    ax.grid(axis="y", visible=False)
    _titulo(ax, f"IL4 · Un cierre completo corre en {ej['DuracionSeg'].mean():.1f} s".replace(".", ","),
            "La escritura del Excel formateado es el 97% del tiempo")
    fig.savefig(IMG / "il4_tiempos.png")
    plt.close(fig)


def horas():
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.bar(["Cierre manual\n(línea base)", "Cierre con motor\n(meta)"], [40, 16],
           color=[GRIS, NAVY], width=0.5)
    ax.text(0, 41, "40 h · 5 días", ha="center", fontsize=12, color=TINTA)
    ax.text(1, 17, "16 h · 2 días", ha="center", fontsize=12, color=TINTA)
    ax.annotate("", xy=(1, 24), xytext=(0, 38), arrowprops=dict(arrowstyle="->", color=ROSA, lw=1.8))
    ax.text(0.55, 33, "–24 h/mes\n+60% productividad", color=ROSA, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 48)
    ax.set_ylabel("Horas de cierre por mes")
    ax.grid(axis="x", visible=False)
    _titulo(ax, "IL5 · Meta: liberar 24 horas por cierre", "Se valida con el registro mensual de horas")
    fig.savefig(IMG / "il5_horas.png")
    plt.close(fig)


def margen(ruta_xlsx):
    r = pd.read_excel(ruta_xlsx, sheet_name="Resumen_Linea").sort_values("Ingresos De Explotacion")
    fig, ax = plt.subplots(figsize=(7.5, 3.3))
    ax.barh(r["LineaDeNegocio"], r["Ingresos De Explotacion"] / 1e6, color=GRIS, height=0.6,
            label="Ingresos")
    ax.barh(r["LineaDeNegocio"], r["Resultado"] / 1e6, color=NAVY, height=0.6, label="Resultado neto")
    for i, (ing, res, mg) in enumerate(zip(r["Ingresos De Explotacion"], r["Resultado"], r["Margen %"])):
        ax.text(ing / 1e6 + 10, i, f"margen {mg * 100:.1f}%".replace(".", ","), va="center",
                fontsize=11, color=TINTA)
    ax.set_xlim(0, r["Ingresos De Explotacion"].max() / 1e6 * 1.3)
    ax.set_xlabel("MM CLP, septiembre 2026 (datos sintéticos)")
    ax.legend(frameon=False, loc="lower right", fontsize=10)
    ax.grid(axis="y", visible=False)
    _titulo(ax, "Salida · Resultado neto por línea después de distribuir",
            "Incluye gerencias, STAFF, OH Latam e impuesto asignados a cada proyecto")
    fig.savefig(IMG / "salida_margen_linea.png")
    plt.close(fig)


def main():
    ej = pd.read_csv(RAIZ / "logs" / "ejecuciones.csv")
    ej = ej[ej["Estado"] == "OK"].drop_duplicates("Mes", keep="last").sort_values("Mes")
    al = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(str(RAIZ / "output" / "alertas_*.csv")))])
    calidad(ej)
    alertas(al)
    tiempos(ej)
    horas()
    margen(RAIZ / "output" / f"EERR_Distribuido_{ej['Mes'].iloc[-1]}.xlsx")
    print("Gráficos en", IMG)


if __name__ == "__main__":
    main()
