import pytest
from datetime import date
from planning import calcular_fecha_estimada, calcular_planeacion
from models import get_db


TODAY = date(2026, 6, 21)

PROMEDIOS = {
    'PAYMOVER': {'horas_promedio_dia': 8.0, 'km_promedio_dia': None},
    'TRACTOR': {'horas_promedio_dia': None, 'km_promedio_dia': 120.0},
}


def test_fecha_dias_falta():
    parsed = {'tipo': 'dias', 'valor': 10, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] == date(2026, 7, 1)
    assert not r['sin_dato']
    assert not r['vencido']


def test_fecha_dias_hace():
    parsed = {'tipo': 'dias', 'valor': 5, 'vencido': True}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] == date(2026, 6, 16)
    assert r['vencido'] is True


def test_fecha_horas_con_promedio():
    parsed = {'tipo': 'horas', 'valor': 80, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    # 80h / 8h/dia = 10 dias → 2026-07-01
    assert r['fecha'] == date(2026, 7, 1)
    assert not r['sin_dato']


def test_fecha_horas_sin_promedio():
    parsed = {'tipo': 'horas', 'valor': 80, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'FAMILIA_SIN_DATO', PROMEDIOS, today=TODAY)
    assert r['fecha'] is None
    assert r['sin_dato'] is True


def test_fecha_none_parsed():
    r = calcular_fecha_estimada(None, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] is None
    assert r['sin_dato'] is True


def test_calcular_planeacion_vacio(temp_db):
    conn = get_db()
    r = calcular_planeacion(conn, date(2026, 7, 1), date(2026, 8, 31), False, today=TODAY)
    conn.close()
    assert r['en_rango'] == []
    assert r['kpis']['total_en_rango'] == 0
