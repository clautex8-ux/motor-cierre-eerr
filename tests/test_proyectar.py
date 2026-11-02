"""Pruebas de la proyección quincenal y las alertas de rentabilidad."""
import numpy as np
import pandas as pd
import pytest

from motor import distribuir, generar_datos, proyectar, validar
from motor.config import cargar_reglas


@pytest.fixture(scope="module")
def proyeccion(base, maestros):
    corte = generar_datos.corte_quincenal(base, np.random.default_rng(3))
    validas_c, _, _ = validar.validar(corte, "2026-09", maestros["codigos"])
    validas_r, _, _ = validar.validar(base, "2026-09", maestros["codigos"])
    base_proy, res = proyectar.construir_base_proyectada(validas_c, validas_r, "2026-09")
    eerr, cuad = distribuir.ejecutar_distribucion(base_proy, maestros["proyectos"], "2026-09")
    return base_proy, res, eerr, cuad, validas_r


def test_provision_proyectada_se_toma_tal_cual_del_corte(proyeccion):
    base_proy, _, _, _, real = proyeccion
    for rubro in cargar_reglas()["proyeccion"]["rubros_provision_proyectada"]:
        proy = base_proy.loc[base_proy["EERR"] == rubro, "Saldo"].sum()
        obs = real.loc[real["EERR"] == rubro, "Saldo"].sum()
        assert abs(proy / obs - 1) < 0.05, rubro          # provisión cargada ≈ cierre real
        assert (base_proy.loc[base_proy["EERR"] == rubro, "Origen"] == "Provision proyectada").all()


def test_rubros_run_rate_se_escalan_a_mes_completo(proyeccion):
    base_proy, res, _, _, real = proyeccion
    r = cargar_reglas()
    for rubro in r["proyeccion"]["rubros_run_rate"]:
        proy = base_proy.loc[base_proy["EERR"] == rubro, "Saldo"].sum()
        obs = real.loc[real["EERR"] == rubro, "Saldo"].sum()
        assert abs(proy / obs - 1) < 0.15, rubro      # dentro de la dispersión simulada
    assert res.filas_run_rate > 0 and res.filas_referencia > 0


def test_rubros_de_referencia_vienen_del_cierre_anterior(proyeccion):
    base_proy, _, _, _, real = proyeccion
    for rubro in cargar_reglas()["proyeccion"]["rubros_referencia"]:
        assert base_proy.loc[base_proy["EERR"] == rubro, "Saldo"].sum() == real.loc[real["EERR"] == rubro, "Saldo"].sum()
        assert (base_proy.loc[base_proy["EERR"] == rubro, "Origen"] == "Referencia cierre anterior").all()


def test_proyeccion_distribuida_cuadra(proyeccion):
    _, _, _, cuad, _ = proyeccion
    assert all(c.diferencia == 0 for c in cuad)


def test_alertas_rentabilidad_solo_bajo_margen_minimo(proyeccion):
    _, _, eerr, _, _ = proyeccion
    r = cargar_reglas()["rentabilidad"]
    resumen = distribuir.resumen_por_proyecto(eerr)
    al = proyectar.alertas_rentabilidad(resumen, "2026-09")
    assert (al["MargenProyectado"] < r["margen_minimo"]).all()
    assert (al["UtilidadPorPunto"] == np.round(al["Ingresos De Explotacion"] * 0.01, 0)).all()
    esperado = (r["margen_objetivo"] - al["MargenProyectado"]) * al["Ingresos De Explotacion"]
    assert (al["UtilidadEnJuego"] - esperado).abs().max() <= 1
    assert set(al["Severidad"]) <= {"Margen negativo", "Margen bajo"}


def test_comparacion_con_cierre_calcula_error_y_acierto():
    proy = pd.DataFrame({"CodigoProyecto": ["A", "B"], "Proyecto": ["a", "b"], "LineaDeNegocio": ["BPO", "BPO"],
                         "Ingresos De Explotacion": [100.0, 100.0], "Resultado": [12.0, 2.0]})
    real = pd.DataFrame({"CodigoProyecto": ["A", "B"], "Ingresos De Explotacion": [100.0, 100.0],
                         "Resultado": [10.0, 6.0]})
    c = proyectar.comparar_con_cierre(proy, real).set_index("CodigoProyecto")
    assert round(c.loc["A", "ErrorPP"], 6) == 2.0
    assert c.loc["A", "Acierto"] and not c.loc["B", "Acierto"]
