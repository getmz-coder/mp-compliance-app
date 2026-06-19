# App Seguimiento Cumplimiento MP — GET Talma

## Qué es
App web Flask para seguimiento de cumplimiento de Mantenimiento Preventivo GSE en la base BOG (piloto).
Planeación administra y mantiene la data actualizada → CIO valida la información, programa equipos, solicita a Operaciones que los traiga al taller, y luego registra en la app qué se entregó y qué no + motivo → Todo queda registrado con trazabilidad completa (quién pidió, cuándo, qué se trajo, qué no y por qué).

## Problema que resuelve
Planeación no tiene trazabilidad de lo planeado vs lo ejecutado. No se registra quién solicitó qué equipo, si Operaciones lo trajo o no, ni por qué no se realizó el MP.

## Stack obligatorio
- Python 3.11+, Flask, SQLite
- flask-login para autenticación
- werkzeug.security para hash de passwords
- openpyxl + pandas para lectura de Excel
- Jinja2 para templates HTML
- Deploy target: PythonAnywhere (tier gratuito)

## Reglas inquebrantables
- Branding Talma: Azul #002D6E, Verde #80AE3F, Cielo #1E88E5, Ámbar #E67E22, Fondo #F0F2F5
- Zero CDN externos — todo CSS/JS embebido o en static/
- Cada acción queda en tabla `respuestas` con timestamp, usuario, IP
- Respuestas son INMUTABLES — una vez registradas no se pueden editar ni eliminar
- Datos fuente del Excel: SOLO LECTURA — la app no modifica los datos fuente
- Diseño profesional ejecutivo, estilo corporativo, no genérico
- Responsive para laptop/tablet de estación

## Roles y actores
- **admin** (Planeación): administra la app, sube Excel, mantiene datos actualizados, gestiona usuarios y catálogos, monitorea indicadores, exporta historial
- **cio**: revisa y valida la información de equipos, programa cuáles se requieren para MP, solicita equipos a Operaciones (fuera de la app), y luego registra en la app qué se trajo y qué no + motivo
- **operaciones** NO usa la app — solo recibe la solicitud (correo, verbal) y entrega lo que puede. Es el CIO quien verifica y registra el resultado

## Flujo operacional
1. Planeación (admin) genera y sube Excel de programación MP a la app
2. App muestra equipos con desviación en rango [-10%, +10%] (vencidos y próximos)
3. CIO revisa y valida la información, decide qué equipos programar para MP
4. CIO selecciona equipos y los marca como "solicitados" → queda registrado: qué equipos, quién solicitó, cuándo
5. CIO comunica a Operaciones qué equipos necesita (correo, verbal, etc. — fuera de la app)
6. Operaciones trae lo que puede al taller (proceso externo a la app)
7. CIO verifica qué llegó y qué no → registra en la app para cada equipo:
   - ✓ "Entregado" (Operaciones trajo el equipo)
   - ✗ "No entregado" + motivo obligatorio del catálogo
8. Todo queda en tabla de trazabilidad con timestamp

## Motivos predefinidos (catálogo configurable)
1. Operaciones no lo trajo
2. Baja disponibilidad de la familia
3. Sin repuestos
4. Sin personal altamente capacitado (Equipos especiales)
5. [Comentario libre] — opción adicional con campo de texto

## Datos de entrada — Excel programación MP
Columnas del Excel que la app consume (tabla ya procesada):
| Columna | Tipo | Ejemplo |
|---------|------|---------|
| fecha_programacion | datetime | 19/06/2026 8:31 |
| consecutivo | int | 23409 |
| categoria | string | Motorizado |
| estado_vehiculo | string | Activo |
| vehiculo | string | TTT 04 |
| familia | string | PAYMOVER |
| rutina | string | MANTENIMIENTO TIPO A CADA 400 HORAS TT GOLDHOFER |
| desviacion | string | Hace 46 Horas / Falta 1 Hora / Hoy / Falta 43.9 Horas / Falta 17d |
| Ind_desviacion | string/percent | 12%, 0%, -9% |
| estado_mp | string | Vencido por medidor / Próximo / Vencido por tiempo |

**Nota:** La columna `vehiculo` es la llave principal de cruce entre archivos. Un mismo vehículo puede aparecer con múltiples consecutivos (diferentes rutinas MP).

## Datos de entrada — Maestro Filtración
| Columna | Tipo | Ejemplo |
|---------|------|---------|
| EQUIPO | string | TTT 04 |
| TIPO | string | Tractor |
| NOMBRE ARTÍCULO | string | FILTRO ACEITE MOTOR |
| CODIGO SAP | string | 10045678 |
| TIPO FILTRO | string | Fleetguard / Homólogo |

**Nota:** Un equipo puede tener hasta 8 filas (múltiples filtros). El filtro principal es Fleetguard + homólogos.

## Base de datos SQLite — Esquema
### Tabla `equipos` (se sincroniza desde Excel)
- id INTEGER PK
- consecutivo INTEGER
- vehiculo VARCHAR(30) — llave de cruce
- categoria VARCHAR(50)
- estado_vehiculo VARCHAR(20)
- familia VARCHAR(100)
- rutina TEXT
- desviacion VARCHAR(50)
- ind_desviacion VARCHAR(10)
- estado_mp VARCHAR(50)
- fecha_programacion DATETIME
- sync_id INTEGER — ID del ciclo de sync
- sync_timestamp DATETIME

### Tabla `filtros_equipo` (se sincroniza desde Excel maestro filtración)
- id INTEGER PK
- equipo VARCHAR(30) — FK lógica a equipos.vehiculo
- tipo VARCHAR(50)
- nombre_articulo VARCHAR(200)
- codigo_sap VARCHAR(30)
- tipo_filtro VARCHAR(50)

### Tabla `usuarios`
- id INTEGER PK
- username VARCHAR(50) UNIQUE
- password_hash VARCHAR(256)
- nombre_completo VARCHAR(100)
- rol VARCHAR(20) — 'admin' | 'cio'
- activo BOOLEAN DEFAULT TRUE
- created_at DATETIME

### Tabla `solicitudes` (CIO solicita equipos a Operaciones)
- id INTEGER PK
- equipo_id INTEGER FK → equipos.id
- solicitado_por INTEGER FK → usuarios.id
- fecha_solicitud DATETIME
- sync_id INTEGER — ciclo de programación al que pertenece
- estado VARCHAR(20) — 'pendiente' | 'respondido'

### Tabla `respuestas` (CIO registra resultado de entrega)
- id INTEGER PK
- solicitud_id INTEGER FK → solicitudes.id
- respondido_por INTEGER FK → usuarios.id
- accion VARCHAR(20) — 'entregado' | 'no_entregado'
- motivo_id INTEGER FK → catalogo_motivos.id (nullable)
- comentario_libre TEXT (nullable)
- timestamp DATETIME
- ip_address VARCHAR(45)

### Tabla `catalogo_motivos`
- id INTEGER PK
- codigo VARCHAR(10)
- descripcion VARCHAR(200)
- activo BOOLEAN DEFAULT TRUE
- orden INTEGER

### Tabla `log_actividad`
- id INTEGER PK
- usuario_id INTEGER FK
- accion_tipo VARCHAR(30) — login/sync/solicitud/respuesta/export
- detalle TEXT
- ip_address VARCHAR(45)
- timestamp DATETIME

## Convenciones de código
- Español en UI y docstrings
- Inglés en variables y funciones
- Commits en español, descriptivos
- Un archivo por responsabilidad: app.py (rutas), models.py (BD), sync_data.py (ETL), config.py (constantes)

## Piloto
- Solo base BOG
- Usuarios iniciales: admin/admin123 (Planeación), cio_bog/cio123 (CIO BOG)
- Una vez validado en BOG, se escala a estaciones
