import os

SECRET_KEY = os.urandom(24)

DATABASE_PATH = 'data/app.db'
UPLOAD_FOLDER = 'data/'
EXPORT_FOLDER = 'exports/'

ESTACIONES_BOG = ['BOG']

CATALOGO_MOTIVOS_INICIAL = [
    {'codigo': 'M01', 'descripcion': 'Operaciones no lo trajo', 'orden': 1},
    {'codigo': 'M02', 'descripcion': 'Baja disponibilidad de la familia', 'orden': 2},
    {'codigo': 'M03', 'descripcion': 'Sin repuestos', 'orden': 3},
    {'codigo': 'M04', 'descripcion': 'Sin personal altamente capacitado (Equipos especiales)', 'orden': 4},
]
