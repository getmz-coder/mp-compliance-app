import pytest
from planning import parse_desviacion


def test_hoy():
    r = parse_desviacion('Hoy')
    assert r == {'tipo': 'dias', 'valor': 0, 'vencido': False}


def test_falta_dias():
    r = parse_desviacion('Falta 17d')
    assert r['tipo'] == 'dias'
    assert r['valor'] == 17
    assert r['vencido'] is False


def test_falta_horas_largo():
    r = parse_desviacion('Falta 43.9 Horas')
    assert r['tipo'] == 'horas'
    assert abs(r['valor'] - 43.9) < 0.01
    assert r['vencido'] is False


def test_falta_horas_corto():
    r = parse_desviacion('Falta 28 H')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 28


def test_falta_hora_singular():
    r = parse_desviacion('Falta 1 Hora')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 1


def test_hace_horas():
    r = parse_desviacion('Hace 46 Horas')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 46
    assert r['vencido'] is True


def test_hace_compuesto():
    r = parse_desviacion('Hace 2y 7M 1d')
    assert r['tipo'] == 'dias'
    assert r['vencido'] is True
    # 2*365 + 7*30 + 1 = 730 + 210 + 1 = 941
    assert abs(r['valor'] - 941) < 1


def test_falta_km():
    r = parse_desviacion('Falta 120 km')
    assert r['tipo'] == 'km'
    assert r['valor'] == 120


def test_none_input():
    assert parse_desviacion(None) is None


def test_empty_string():
    assert parse_desviacion('') is None


def test_unparseable():
    assert parse_desviacion('Sin información') is None


def test_hoy_case_insensitive():
    r = parse_desviacion('hoy')
    assert r is not None
    assert r['valor'] == 0
