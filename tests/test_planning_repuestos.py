import pytest
from planning import agregar_repuestos
from models import get_db


@pytest.fixture
def db_con_filtros(temp_db):
    conn = get_db()
    conn.execute(
        "INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
        ('AGPU 21', 'GPU', 'FILTRO ACEITE', '10001', 'Fleetguard')
    )
    conn.execute(
        "INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
        ('AGPU 22', 'GPU', 'FILTRO ACEITE', '10001', 'Fleetguard')
    )
    conn.execute(
        "INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
        ('AGPU 21', 'GPU', 'FILTRO AIRE', '20002', 'Fleetguard')
    )
    conn.commit()
    yield conn
    conn.close()


def test_agrega_por_sap(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['AGPU 21', 'AGPU 22'])
    saps = [x['codigo_sap'] for x in r]
    assert '10001' in saps
    aceite = next(x for x in r if x['codigo_sap'] == '10001')
    assert aceite['cantidad'] == 2


def test_lista_vacia(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, [])
    assert r == []


def test_vehiculo_inexistente(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['EQUIPO 99'])
    assert r == []


def test_orden_descendente(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['AGPU 21', 'AGPU 22'])
    cantidades = [x['cantidad'] for x in r]
    assert cantidades == sorted(cantidades, reverse=True)
