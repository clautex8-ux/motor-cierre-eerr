"""Prueba de punta a punta del cierre mensual."""
import pytest

from motor import pipeline


def test_cierre_completo_genera_salidas(datos_tmp, tmp_path, monkeypatch):
    from motor import extraer
    monkeypatch.setattr(extraer, "RAIZ", datos_tmp.parent)
    maestros = extraer.leer_maestros(datos_tmp / "maestros")
    monkeypatch.setattr(extraer, "leer_maestros", lambda carpeta=None: maestros)
    r = pipeline.procesar_mes("2026-09", datos_tmp / "raw", tmp_path, registrar=False)
    assert r["estado"] == "OK"
    assert (tmp_path / "EERR_Distribuido_2026-09.xlsx").exists()
    assert (tmp_path / "powerbi" / "fact_eerr_2026-09.csv").exists()
    assert r["log"]["DifCuadratura"] == 0


def test_mes_inexistente_falla_y_no_genera_salida(datos_tmp, tmp_path):
    with pytest.raises(Exception):
        pipeline.procesar_mes("2030-01", datos_tmp / "raw", tmp_path, registrar=False)
    assert not any(tmp_path.iterdir())


def test_proyeccion_quincenal_genera_comite(datos_tmp, tmp_path, monkeypatch):
    """Q1 de un mes usa el cierre anterior como referencia; aquí se simula con el mismo mes."""
    import numpy as np

    from motor import extraer, generar_datos
    base = extraer.leer_base_eerr("2026-09", datos_tmp / "raw")
    reglas = pipeline.cargar_reglas()
    fmt = reglas["formato_csv"]
    q1 = generar_datos.corte_quincenal(base, np.random.default_rng(5))
    q1["Mes"], q1["Fecha"] = "2026-10-01", "2026-10-15"
    q1[reglas["columnas_base"]].to_csv(datos_tmp / "raw" / "Base_EERR_2026-10_Q1.csv", sep=fmt["separador"],
                                        encoding=fmt["encoding"], index=False)
    maestros = extraer.leer_maestros(datos_tmp / "maestros")
    monkeypatch.setattr(extraer, "leer_maestros", lambda carpeta=None: maestros)
    r = pipeline.proyectar_mes("2026-10", datos_tmp / "raw", tmp_path, registrar=False)
    assert r["estado"] == "OK"
    assert (tmp_path / "Proyeccion_Cierre_2026-10_Q1.xlsx").exists()
    assert (tmp_path / "comite_rentabilidad_2026-10_Q1.csv").exists()
    assert r["log"]["DifCuadratura"] == 0
