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
