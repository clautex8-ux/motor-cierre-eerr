"""Capa de salida: EERR distribuido en Excel (formato IBR) y tabla para Power BI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

NAVY, AZUL, ROSA, ROSA_CLARO = "2B3990", "0D20E6", "F06B9E", "F8AAC9"
FMT_CLP = '#,##0;[Red]-#,##0'
FMT_PCT = '0.0%'


def _formatear_hoja(ws, df: pd.DataFrame, cols_monto=(), cols_pct=()):
    borde = Border(bottom=Side(style="thin", color="D9DBE1"))
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF", name="Calibri")
        celda.fill = PatternFill("solid", fgColor=NAVY)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns, start=1):
        letra = get_column_letter(i)
        largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(300)])
        ws.column_dimensions[letra].width = min(max(10, largo + 2), 45)
        fmt = FMT_CLP if col in cols_monto else FMT_PCT if col in cols_pct else None
        if fmt:
            for celda in ws[letra][1:]:
                celda.number_format = fmt
    for fila in ws.iter_rows(min_row=2, max_row=min(ws.max_row, 2000)):
        for celda in fila:
            celda.border = borde


def exportar_excel(ruta: Path, hojas: dict[str, tuple[pd.DataFrame, list, list]]):
    """hojas = {nombre: (df, columnas_monto, columnas_pct)}"""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        for nombre, (df, montos, pcts) in hojas.items():
            df.to_excel(xw, sheet_name=nombre, index=False)
            _formatear_hoja(xw.sheets[nombre], df, montos, pcts)
        portada = xw.book[list(hojas)[0]]
        portada.sheet_properties.tabColor = ROSA


def exportar_powerbi(ruta: Path, eerr: pd.DataFrame, mes: str):
    """Tabla de hechos plana para el modelo de Power BI (una fila por movimiento)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cols = ["Mes", "CodigoProyecto", "Proyecto", "Cliente", "LineaDeNegocio", "Cross1",
            "EERR", "Clasificacion", "CuentaContable", "Saldo", "Cross"]
    eerr[cols].assign(MesCierre=mes).to_csv(ruta, index=False)
