"""Pruebas de cuadratura de las reglas de distribución."""
import pytest

from motor import distribuir, validar
from motor.config import cargar_reglas


@pytest.fixture(scope="module")
def resultado(base, maestros):
    validas, _, _ = validar.validar(base, "2026-09", maestros["codigos"])
    eerr, cuad = distribuir.ejecutar_distribucion(validas, maestros["proyectos"], "2026-09")
    return validas, eerr, cuad


def test_cuadratura_exacta_en_cada_regla(resultado):
    _, _, cuad = resultado
    for c in cuad:
        assert c.diferencia == 0, c.regla


def test_no_quedan_gerencias_ni_staff_sin_distribuir(resultado):
    _, eerr, _ = resultado
    assert not (eerr["LineaDeNegocio"] == "STAFF").any()
    assert not eerr["Proyecto"].str.startswith("Gerencia").any()


def test_gerencia_solo_se_distribuye_en_su_linea(resultado):
    _, eerr, _ = resultado
    ger = eerr[eerr["Cross"] == "Cross_gerencia"]
    assert ger["DepartamentoGciaNombre"].str.replace("Gerencia ", "").notna().all()
    for nombre, grupo in ger.groupby("DepartamentoGciaNombre"):
        assert grupo["LineaDeNegocio"].nunique() == 1, nombre


def test_oh_latam_es_3_por_ciento_de_ingresos(resultado):
    _, eerr, _ = resultado
    tasa = cargar_reglas()["oh_latam"]["tasa"]
    ing = eerr[eerr["EERR"] == "Ingresos De Explotacion"].groupby("CodigoProyecto")["Saldo"].sum()
    oh = eerr[eerr["Cross"] == "Calculo_OH"].set_index("CodigoProyecto")["Saldo"]
    assert ((oh + tasa * ing.loc[oh.index]).abs() <= 1).all()


def test_impuesto_total_es_27_por_ciento_del_rai_consolidado(resultado):
    _, eerr, _ = resultado
    reglas = cargar_reglas()
    rai = eerr[eerr["EERR"].isin(reglas["rubros_rai"])]["Saldo"].sum()
    imp = eerr[eerr["Cross"] == "Calculo_Impuesto"]["Saldo"].sum()
    n = (eerr["Cross"] == "Calculo_Impuesto").sum()
    assert abs(imp + reglas["impuesto_renta"]["tasa"] * rai) <= n  # redondeo a pesos por proyecto
