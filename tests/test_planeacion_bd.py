import pytest
from models import get_db


def test_tabla_promedios_familia():
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(promedios_familia)")}
    conn.close()
    assert cols == {'id', 'familia', 'horas_promedio_dia', 'km_promedio_dia',
                    'actualizado_por', 'timestamp'}


def test_tabla_frecuencias_rutinas():
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(frecuencias_rutinas)")}
    conn.close()
    assert cols == {'id', 'rutina', 'frecuencia_medidor', 'frecuencia_dias'}


def test_promedios_familia_unique_familia():
    conn = get_db()
    conn.execute(
        "INSERT INTO promedios_familia (familia, horas_promedio_dia) VALUES ('PAYMOVER', 2.5)"
    )
    conn.commit()
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO promedios_familia (familia, horas_promedio_dia) VALUES ('PAYMOVER', 3.0)"
        )
    conn.close()
