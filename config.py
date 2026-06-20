import os
import secrets

_BASE = os.path.dirname(os.path.abspath(__file__))

# Lee de env var SECRET_KEY; si no, persiste una clave en data/.secret_key.
# Así la clave sobrevive reinicios sin estar en el código fuente.
_env_key = os.environ.get('SECRET_KEY')
if _env_key:
    SECRET_KEY = _env_key
else:
    _key_file = os.path.join(_BASE, 'data', '.secret_key')
    if os.path.exists(_key_file):
        with open(_key_file) as _f:
            SECRET_KEY = _f.read().strip()
    else:
        SECRET_KEY = secrets.token_hex(32)
        os.makedirs(os.path.join(_BASE, 'data'), exist_ok=True)
        with open(_key_file, 'w') as _f:
            _f.write(SECRET_KEY)

DATABASE_PATH = os.path.join(_BASE, 'data', 'app.db')
UPLOAD_FOLDER = os.path.join(_BASE, 'data')
EXPORT_FOLDER = os.path.join(_BASE, 'exports')

ESTACIONES_BOG = ['BOG']

CATALOGO_MOTIVOS_INICIAL = [
    {'codigo': 'M01', 'descripcion': 'Operaciones no lo trajo', 'orden': 1},
    {'codigo': 'M02', 'descripcion': 'Baja disponibilidad de la familia', 'orden': 2},
    {'codigo': 'M03', 'descripcion': 'Sin repuestos', 'orden': 3},
    {'codigo': 'M04', 'descripcion': 'Sin personal altamente capacitado (Equipos especiales)', 'orden': 4},
]
