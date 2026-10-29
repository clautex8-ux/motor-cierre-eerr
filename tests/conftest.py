import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from motor import generar_datos  # noqa: E402
from motor.config import cargar_reglas  # noqa: E402


@pytest.fixture(scope="session")
def datos_tmp(tmp_path_factory):
    """Genera un mes sintético en una carpeta temporal (no toca data/)."""
    raiz = tmp_path_factory.mktemp("datos")
    reglas = cargar_reglas()
    fmt = reglas["formato_csv"]
    generar_datos.guardar_maestros(raiz / "maestros")
    (raiz / "raw").mkdir()
    base, prov, fact = generar_datos.generar_mes("2026-09", np.random.default_rng(7))
    base[reglas["columnas_base"]].to_csv(raiz / "raw" / "Base_EERR_2026-09.csv",
                                         sep=fmt["separador"], encoding=fmt["encoding"], index=False)
    prov.to_csv(raiz / "raw" / "Provision_Ingresos_2026-09.csv", index=False)
    fact.to_csv(raiz / "raw" / "Facturacion_2026-09.csv", index=False)
    return raiz


@pytest.fixture(scope="session")
def maestros(datos_tmp):
    from motor import extraer
    return extraer.leer_maestros(datos_tmp / "maestros")


@pytest.fixture(scope="session")
def base(datos_tmp):
    from motor import extraer
    return extraer.leer_base_eerr("2026-09", datos_tmp / "raw")
