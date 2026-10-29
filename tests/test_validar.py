"""Pruebas del contrato de datos (KPI IL3)."""
import pandas as pd
import pytest

from motor import extraer, validar


def test_filas_sin_proyecto_van_a_cuarentena(base, maestros):
    validas, cuarentena, rep = validar.validar(base, "2026-09", maestros["codigos"])
    assert (validas["Proyecto"] != "").all()
    assert rep.filas_validas + rep.filas_cuarentena == rep.filas_total
    assert rep.por_regla["R1 proyecto informado"] == (base["Proyecto"].str.strip() == "").sum()


def test_linea_mal_digitada_se_corrige_desde_maestro(base, maestros):
    validas, _, rep = validar.validar(base, "2026-09", maestros["codigos"])
    assert rep.filas_corregidas > 0
    assert set(validas["LineaDeNegocio"]) <= {"BPO", "Cobranza", "Vtas_ATC", "Vtas_Servicios",
                                              "Off-Shore", "STAFF"}
    oficial = maestros["codigos"].set_index("CodigoProyecto")["LineaDeNegocio"]
    assert (validas["LineaDeNegocio"] == validas["CodigoProyecto"].map(oficial)).all()


def test_criterio_staff_invalido_va_a_cuarentena(base, maestros):
    df = base.copy()
    i = df.index[df["LineaDeNegocio"] == "STAFF"][0]
    df.loc[i, "Tabla"] = "Criterio inventado"
    _, cuarentena, rep = validar.validar(df, "2026-09", maestros["codigos"])
    assert i in cuarentena.index
    assert rep.por_regla["R7 criterio STAFF valido"] >= 1


def test_saldo_inconsistente_va_a_cuarentena(base, maestros):
    df = base.copy()
    df.loc[df.index[0], "Saldo"] = df.loc[df.index[0], "Saldo"] + 1000
    _, cuarentena, _ = validar.validar(df, "2026-09", maestros["codigos"])
    assert df.index[0] in cuarentena.index


def test_archivo_sin_columna_obligatoria_falla(tmp_path, datos_tmp):
    df = pd.read_csv(datos_tmp / "raw" / "Base_EERR_2026-09.csv", sep=";", encoding="latin1")
    df.drop(columns=["Saldo"]).to_csv(tmp_path / "Base_EERR_2026-09.csv", sep=";",
                                       encoding="latin1", index=False)
    with pytest.raises(extraer.ErrorEntrada):
        extraer.leer_base_eerr("2026-09", tmp_path)
