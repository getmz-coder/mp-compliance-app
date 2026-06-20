import os

_BASE = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.urandom(24)

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
