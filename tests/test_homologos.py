from models import get_db


def test_tabla_homologos_existe():
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(homologos)")}
    conn.close()
    assert cols == {'id', 'grupo', 'codigo_sap', 'descripcion', 'estado'}
