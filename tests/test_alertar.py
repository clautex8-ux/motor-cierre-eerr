"""Pruebas del módulo de alertas de fuga de ingresos."""
import pandas as pd

from motor import alertar


def _caso(prov_monto, facturas, maestros):
    mapeo = pd.DataFrame([{"CAMPANA": "Campana X", "CodigoProyecto": "PY_10101"}])
    prov = pd.DataFrame([{"CAMPANA": "Campana X", "PROVISION": prov_monto}])
    fact = pd.DataFrame(facturas, columns=["CodigoProyecto", "Tipo", "Monto"])
    return alertar.conciliar(prov, fact, mapeo, maestros["proyectos"])


def test_provision_sin_factura_genera_alerta_alta(maestros):
    _, al, _ = _caso(50_000_000, [], maestros)
    assert al.loc[0, "TipoAlerta"] == "Provision sin factura"
    assert al.loc[0, "Monto"] == -50_000_000
    assert al.loc[0, "Severidad"] == "Alta"


def test_diferencia_dentro_de_tolerancia_no_alerta(maestros):
    conc, al, _ = _caso(50_000_000, [("PY_10101", "Factura", 49_800_000)], maestros)
    assert al.empty
    assert bool(conc.loc[0, "Conciliado"])


def test_nota_de_credito_no_provisionada(maestros):
    _, al, _ = _caso(50_000_000, [("PY_10101", "Factura", 50_000_000),
                                  ("PY_10101", "Nota de Credito", -2_500_000)], maestros)
    assert "Nota de credito no provisionada" in set(al["TipoAlerta"])


def test_campana_sin_mapeo_se_reporta(maestros):
    mapeo = pd.DataFrame([{"CAMPANA": "Otra", "CodigoProyecto": "PY_10101"}])
    prov = pd.DataFrame([{"CAMPANA": "Campana nueva", "PROVISION": 1_000_000}])
    fact = pd.DataFrame(columns=["CodigoProyecto", "Tipo", "Monto"])
    _, _, sin_mapeo = alertar.conciliar(prov, fact, mapeo, maestros["proyectos"])
    assert list(sin_mapeo["CAMPANA"]) == ["Campana nueva"]
