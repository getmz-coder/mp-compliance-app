import pytest
import openpyxl
from sync_data import sync_frecuencias
from models import get_db


@pytest.fixture
def frec_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'DB_FRECUENCIAS'
    ws.append(['rutina', 'frecuencia_medidor', 'frecuencia_dias'])
    ws.append(['MANTENIMIENTO TIPO A 400H', 400, 90])
    ws.append(['MANTENIMIENTO TIPO B 1000H', 1000, 180])
    path = str(tmp_path / 'frecuencias.xlsx')
    wb.save(path)
    return path


def test_sync_frecuencias_inserta(frec_xlsx):
    r = sync_frecuencias(frec_xlsx)
    assert r['total_registros'] == 2


def test_sync_frecuencias_reemplaza(frec_xlsx):
    sync_frecuencias(frec_xlsx)
    sync_frecuencias(frec_xlsx)
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM frecuencias_rutinas").fetchone()[0]
    conn.close()
    assert count == 2


def test_sync_frecuencias_columna_faltante(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'DB_FRECUENCIAS'
    ws.append(['rutina'])
    ws.append(['MANTENIMIENTO A'])
    path = str(tmp_path / 'bad.xlsx')
    wb.save(path)
    with pytest.raises(ValueError, match='frecuencia_medidor'):
        sync_frecuencias(path)
