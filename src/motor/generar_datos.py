"""
Generador de datos sintéticos para el Motor de Cierre EERR.

DECLARACIÓN DE DATOS: todos los archivos generados por este script son
SINTÉTICOS. Replican la estructura real del extracto EERR del ERP (27 columnas,
CSV separado por punto y coma, codificación latin1) y la lógica de negocio del
cierre, pero los nombres de proyectos, clientes y los montos son ficticios y
están escalados. Se usan así por seguridad de la información.

Uso:
    python -m motor.generar_datos --meses 2026-04 2026-05 ... --semilla 42
"""
from __future__ import annotations

import argparse
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from motor.config import RAIZ, cargar_reglas

# ------------------------------------------------------------------
# Maestro de proyectos (ficticio)
# ------------------------------------------------------------------
PROYECTOS = [
    # codigo, proyecto, linea, cliente, cross1 (Local/Off-Shore), fte, ingreso_base_mm
    ("PY_10101", "BPO Back Office Banco A", "BPO", "Banco A", "Local", 62, 210),
    ("PY_10102", "BPO Digitalizacion Seguros B", "BPO", "Seguros B", "Local", 38, 120),
    ("PY_10103", "BPO Prendas Financiera C", "BPO", "Financiera C", "Local", 45, 175),
    ("PY_10104", "BPO Validacion Retail D", "BPO", "Retail D", "Local", 21, 64),
    ("PY_20101", "Cobranza Temprana Banco A", "Cobranza", "Banco A", "Local", 80, 240),
    ("PY_20102", "Cobranza Judicial Financiera C", "Cobranza", "Financiera C", "Local", 34, 98),
    ("PY_20103", "Cobranza Leasing Banco E", "Cobranza", "Banco E", "Local", 52, 150),
    ("PY_20104", "Cobranza Castigo Retail D", "Cobranza", "Retail D", "Local", 29, 80),
    ("PY_20105", "Cobranza Telco F", "Cobranza", "Telco F", "Local", 47, 130),
    ("PY_30101", "ATC Tarjeta Retail D", "Vtas_ATC", "Retail D", "Local", 95, 260),
    ("PY_30102", "ATC Retenciones Telco F", "Vtas_ATC", "Telco F", "Local", 70, 190),
    ("PY_30103", "ATC Compra Cartera Retail D", "Vtas_ATC", "Retail D", "Local", 26, 72),
    ("PY_30104", "ATC Seguros B", "Vtas_ATC", "Seguros B", "Local", 33, 88),
    ("PY_40101", "Ventas Inbound Telco F", "Vtas_Servicios", "Telco F", "Local", 88, 230),
    ("PY_40102", "Ventas Outbound Telco F", "Vtas_Servicios", "Telco F", "Local", 64, 165),
    ("PY_40103", "Ventas Web Fijo Telco G", "Vtas_Servicios", "Telco G", "Local", 41, 105),
    ("PY_40104", "Ventas Seguros Banco E", "Vtas_Servicios", "Banco E", "Local", 30, 82),
    ("PY_50101", "Off-Shore Retenciones Telco H", "Off-Shore", "Telco H", "Off-Shore", 110, 300),
    ("PY_50102", "Off-Shore Cobranza Telco H", "Off-Shore", "Telco H", "Off-Shore", 85, 220),
    ("PY_50103", "Off-Shore Upselling Telco H", "Off-Shore", "Telco H", "Off-Shore", 60, 160),
    ("PY_50104", "Off-Shore Back Office Telco F", "Off-Shore", "Telco F", "Off-Shore", 44, 115),
    ("PY_50105", "Off-Shore Mensajeria Telco H", "Off-Shore", "Telco H", "Off-Shore", 36, 92),
    ("PY_50106", "Off-Shore Outbound Peru Telco H", "Off-Shore", "Telco H", "Off-Shore", 28, 70),
]

GERENCIAS = [
    ("PY_19000", "Gerencia BPO", "BPO"),
    ("PY_29000", "Gerencia Cobranza", "Cobranza"),
    ("PY_39000", "Gerencia ATC", "Vtas_ATC"),
    ("PY_49000", "Gerencia Ventas Servicios", "Vtas_Servicios"),
    ("PY_59000", "Gerencia Off-Shore", "Off-Shore"),
]

STAFF = [
    # codigo, proyecto, criterio de distribución, gasto mensual base MM
    ("PY_90001", "Administracion y Finanzas", "Ingresos Local + Offshore", 55),
    ("PY_90002", "Tecnologia Corporativa", "FTE", 70),
    ("PY_90003", "Personas y Remuneraciones", "FTE", 38),
    ("PY_90004", "Gerencia General", "Ingresos Local + Offshore", 32),
    ("PY_90005", "Calidad y Procesos Locales", "Ingresos Local", 20),
    ("PY_90006", "Soporte Off-Shore", "Ingresos Offshore", 22),
]

# Cuentas por rubro: (cuenta contable, clasificación, peso, nro de líneas base)
CUENTAS_COSTO = {
    "Costos Del Personal": [
        ("Remuneraciones", "Costos Del Personal", 0.70, 120),
        ("Honorarios Personal De Operaciones", "Costos Del Personal", 0.12, 25),
        ("Desahucio Mes De Aviso_ Bonificacion Por Retiro", "Costos Del Personal", 0.08, 10),
        ("Gratificacion Anual", "Costos Del Personal", 0.10, 60),
    ],
    "Costos Operacionales": [
        ("Telefonia y Enlaces", "Costos Operacionales", 0.45, 12),
        ("Licencias de Software Operacion", "Costos Operacionales", 0.35, 10),
        ("Movilizacion y Colaciones", "Costos Operacionales", 0.20, 40),
    ],
    "Gastos Generales Fijos": [
        ("Arriendo Oficinas", "Gastos Generales Fijos", 0.55, 4),
        ("Servicios Basicos", "Gastos Generales Fijos", 0.20, 6),
        ("Aseo y Mantencion", "Gastos Generales Fijos", 0.25, 8),
    ],
    "No Operacional": [
        ("Gastos Financieros", "No Operacional", 0.7, 3),
        ("Diferencia de Cambio", "No Operacional", 0.3, 2),
    ],
}

# Nombre de campaña en la provisión ≠ nombre en el ERP (caso real del cierre)
ALIAS_PROVISION = {
    "PY_10103": "BPO Digital Prendas FinC",
    "PY_20103": "Cobranza Unidad Leasing E",
    "PY_30101": "ATC Tarjeta D ventas",
    "PY_40101": "Venta Inbound Fijo F",
    "PY_50101": "Offshore Telco Retenciones H COL",
    "PY_50102": "Offshore Telco Cobranza H COL",
    "PY_50105": "Offshore Blip Mensajeria H",
}


def _fila(mes, codigo, proyecto, linea, cliente, cross1, rubro, cuenta, clasif,
          saldo, tipo, n, tabla="", gerencia=""):
    """Construye una fila con las 27 columnas del extracto EERR."""
    debit = round(-saldo, 0) if saldo < 0 else 0.0
    credit = round(saldo, 0) if saldo > 0 else 0.0
    fecha = pd.Timestamp(mes) + pd.offsets.MonthEnd(0)
    return {
        "Account": str(zlib.crc32(cuenta.encode()) % 9000000 + 1000000),
        "Codigo": str(zlib.crc32(cuenta.encode()) % 9000000 + 1000000),
        "Mes": pd.Timestamp(mes).strftime("%Y-%m-01"),
        "CuentaContable": cuenta,
        "EERR": rubro,
        "Clasificacion": clasif,
        "Type": tipo,
        "TransactionID": f"TRX{pd.Timestamp(mes):%y%m}{n:07d}",
        "Fecha": fecha.strftime("%Y-%m-%d"),
        "DocumentNumber": f"DOC-{pd.Timestamp(mes):%y%m}-{n:06d}",
        "Nombre": cliente if rubro == "Ingresos De Explotacion" else "Proveedor / Nomina",
        "Memo": f"{cuenta} {pd.Timestamp(mes):%m-%Y}",
        "Debit": debit,
        "Credit": credit,
        "Saldo": round(saldo, 0),
        "NombreDelProyecto": "",
        "CustomerJob": f"{cliente} : {proyecto}",
        "DepartamentoGciaNombre": gerencia,
        "LineaDeNegocio": linea,
        "Memo1": linea,
        "SubsidiariaNombre": "Filial Chile SpA (anonimizada)",
        "CodigoProyecto": codigo,
        "Proyecto": proyecto,
        "Cliente": cliente,
        "Cross1": cross1,
        "Cross 2": "Off-Shore" if cross1 == "Off-Shore" and rubro == "Ingresos De Explotacion" else "Local",
        "Tabla": tabla,
    }


def _repartir(total, n, rng):
    """Reparte un total en n líneas con pesos aleatorios (suma exacta)."""
    pesos = rng.gamma(2.0, 1.0, n)
    partes = np.round(total * pesos / pesos.sum(), 0)
    partes[-1] += round(total - partes.sum(), 0)
    return partes


def generar_mes(mes: str, rng: np.random.Generator, escala: float = 1_000_000):
    """Genera la base EERR, la provisión y la facturación de un mes."""
    filas, n = [], 0
    estacional = 1 + 0.04 * np.sin(pd.Timestamp(mes).month)

    provision, facturas = [], []
    for cod, proy, linea, cli, cross1, fte, ing_mm in PROYECTOS:
        ingreso = ing_mm * escala * estacional * rng.normal(1, 0.05)
        # Ingreso en EERR = provisión del mes (como en el cierre real)
        for parte in _repartir(ingreso, int(rng.integers(1, 4)), rng):
            n += 1
            filas.append(_fila(mes, cod, proy, linea, cli, cross1,
                               "Ingresos De Explotacion", "Ingresos por Servicios",
                               "Ingresos De Explotacion", parte, "Provision", n))
        provision.append({"MES": mes, "CAMPANA": ALIAS_PROVISION.get(cod, proy),
                          "PAIS": "COL" if cross1 == "Off-Shore" else "CHL",
                          "UN": linea, "PROVISION": round(ingreso, 0)})

        # Facturación real con desviaciones (fugas) inyectadas
        r = rng.random()
        facturado = ingreso * rng.normal(1, 0.004)
        if r < 0.04:
            facturado = 0.0                                   # provisión sin factura
        elif r < 0.12:
            facturado = ingreso * rng.uniform(0.85, 0.96)     # facturó menos
        elif r < 0.16:
            facturado = ingreso * rng.uniform(1.03, 1.08)     # facturó más
        if facturado > 0:
            facturas.append({"MES": mes, "CodigoProyecto": cod, "Cliente": cli,
                             "Tipo": "Factura", "Documento": f"F-{n:06d}",
                             "Monto": round(facturado, 0)})
        if rng.random() < 0.07:                               # NC no provisionada
            facturas.append({"MES": mes, "CodigoProyecto": cod, "Cliente": cli,
                             "Tipo": "Nota de Credito", "Documento": f"NC-{n:06d}",
                             "Monto": -round(ingreso * rng.uniform(0.02, 0.06), 0)})

        # Costos del proyecto
        margen_obj = rng.uniform(0.20, 0.32)
        costo_total = ingreso * (1 - margen_obj)
        mix = {"Costos Del Personal": 0.74, "Costos Operacionales": 0.14,
               "Gastos Generales Fijos": 0.10, "No Operacional": 0.02}
        if cross1 == "Off-Shore":
            mix = {"Costos Del Personal": 0.15, "Costos Operacionales": 0.05,
                   "Gastos Generales Fijos": 0.03, "No Operacional": 0.02,
                   "Costos Offshore Operacional": 0.75}
        for rubro, peso in mix.items():
            monto_rubro = costo_total * peso
            if rubro == "Costos Offshore Operacional":
                for parte in _repartir(monto_rubro, 3, rng):
                    n += 1
                    filas.append(_fila(mes, cod, proy, linea, cli, cross1, rubro,
                                       "Costo Off-Shore Colombia", rubro, -parte, "Factura Proveedor", n))
                continue
            for cuenta, clasif, w, lineas in CUENTAS_COSTO[rubro]:
                k = max(1, int(lineas * fte / 60))
                for parte in _repartir(monto_rubro * w, k, rng):
                    n += 1
                    tipo = "Diario" if rubro == "Costos Del Personal" else "Factura Proveedor"
                    filas.append(_fila(mes, cod, proy, linea, cli, cross1, rubro,
                                       cuenta, clasif, -parte, tipo, n))

    # Gerencias de línea (se distribuyen dentro de su línea por ingresos)
    for cod, proy, linea in GERENCIAS:
        gasto = rng.uniform(12, 20) * escala
        for cuenta, w in [("Remuneraciones", 0.8), ("Arriendo Oficinas", 0.2)]:
            rubro = "Costos Del Personal" if cuenta == "Remuneraciones" else "Gastos Generales Fijos"
            for parte in _repartir(gasto * w, 6, rng):
                n += 1
                filas.append(_fila(mes, cod, proy, linea, "Interno", "Local", rubro,
                                   cuenta, rubro, -parte, "Diario", n, gerencia=proy))

    # Áreas STAFF (se distribuyen con su criterio en la columna Tabla)
    for cod, proy, criterio, gasto_mm in STAFF:
        gasto = gasto_mm * escala * rng.normal(1, 0.04)
        for cuenta, rubro, w in [("Remuneraciones", "Costos Del Personal", 0.65),
                                 ("Licencias de Software Corporativo", "Gastos Generales Fijos", 0.20),
                                 ("Asesorias Externas", "Gastos Generales Fijos", 0.15)]:
            for parte in _repartir(gasto * w, 15, rng):
                n += 1
                filas.append(_fila(mes, cod, proy, "STAFF", "Interno", "Local", rubro,
                                   cuenta, rubro, -parte, "Diario", n, tabla=criterio))

    base = pd.DataFrame(filas)

    # Problemas de calidad típicos inyectados (para que el validador trabaje)
    n_vacios, n_typo, n_sin = (int(x) for x in rng.integers([1, 2, 2], [12, 9, 9]))
    idx = rng.choice(base.index, size=n_vacios + n_typo + n_sin, replace=False)
    base.loc[idx[:n_vacios], ["Proyecto", "CodigoProyecto"]] = ""
    base.loc[idx[n_vacios:n_vacios + n_typo], "LineaDeNegocio"] = " bpo "
    base.loc[idx[n_vacios + n_typo:], "LineaDeNegocio"] = "SIN_LINEA"

    return base, pd.DataFrame(provision), pd.DataFrame(facturas)


def guardar_maestros(destino: Path):
    destino.mkdir(parents=True, exist_ok=True)
    proyectos = pd.DataFrame(PROYECTOS, columns=["CodigoProyecto", "Proyecto", "LineaDeNegocio",
                                                 "Cliente", "Cross1", "FTE", "IngresoBaseMM"])
    proyectos["Tipo"] = "Proyecto"
    gerencias = pd.DataFrame([{"CodigoProyecto": c, "Proyecto": p, "LineaDeNegocio": linea,
                               "Cliente": "Interno", "Cross1": "Local", "FTE": 0,
                               "IngresoBaseMM": 0, "Tipo": "Gerencia"} for c, p, linea in GERENCIAS])
    staff = pd.DataFrame([{"CodigoProyecto": c, "Proyecto": p, "LineaDeNegocio": "STAFF",
                           "Cliente": "Interno", "Cross1": "Local", "FTE": 0,
                           "IngresoBaseMM": 0, "Tipo": "STAFF"} for c, p, _, _ in STAFF])
    pd.concat([proyectos, gerencias, staff], ignore_index=True).to_csv(
        destino / "maestro_proyectos.csv", index=False)
    mapeo = [{"CAMPANA": ALIAS_PROVISION.get(p[0], p[1]), "CodigoProyecto": p[0], "Proyecto": p[1]}
             for p in PROYECTOS]
    pd.DataFrame(mapeo).to_csv(destino / "mapeo_campanas.csv", index=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--meses", nargs="+",
                    default=["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"])
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--destino", default=str(RAIZ / "data"))
    a = ap.parse_args(argv)

    reglas = cargar_reglas()
    sep, enc = reglas["formato_csv"]["separador"], reglas["formato_csv"]["encoding"]
    rng = np.random.default_rng(a.semilla)
    destino = Path(a.destino)
    (destino / "raw").mkdir(parents=True, exist_ok=True)
    guardar_maestros(destino / "maestros")
    for mes in a.meses:
        base, prov, fact = generar_mes(mes, rng)
        base[reglas["columnas_base"]].to_csv(destino / "raw" / f"Base_EERR_{mes}.csv",
                                             sep=sep, encoding=enc, index=False)
        prov.to_csv(destino / "raw" / f"Provision_Ingresos_{mes}.csv", index=False)
        fact.to_csv(destino / "raw" / f"Facturacion_{mes}.csv", index=False)
        print(f"{mes}: {len(base):,} filas EERR | {len(prov)} campañas | {len(fact)} documentos")


if __name__ == "__main__":
    main()
