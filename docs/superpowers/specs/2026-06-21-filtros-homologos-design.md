# Filtros Homólogos — Spec de Diseño

**Fecha:** 2026-06-21  
**Estado:** Aprobado  

---

## Contexto

La app de Seguimiento MP GET Talma gestiona filtros de equipos GSE. Actualmente cada filtro tiene un tipo (Fleetguard / Homólogo) pero no hay relación explícita entre el filtro original y sus alternativas homólogas. El área de almacén maneja un Excel con grupos de homólogos que vincula códigos SAP equivalentes. Esta funcionalidad hace ese catálogo visible en la app.

---

## Alcance

1. Nueva tabla `homologos` en SQLite.
2. Función ETL `sync_homologos()` que lee hoja Excel `Grupos_Homologos`.
3. Tercer campo de upload en `/admin/sync`.
4. Visualización expandible en ficha de equipo (`/equipo/<vehiculo>`) y consulta flota (`/taller/flota`).
5. Hoja adicional `Homólogos` en la descarga Excel de ficha de equipo.

---

## 1. Base de Datos

### Tabla nueva: `homologos`

```sql
CREATE TABLE IF NOT EXISTS homologos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo       INTEGER,
    codigo_sap  VARCHAR(30),
    descripcion VARCHAR(200),
    estado      VARCHAR(50)
);
```

- `grupo`: número entero que agrupa códigos SAP equivalentes. Todos los homólogos del mismo grupo comparten el mismo valor.
- `estado`: viene del Excel; valores esperados `'Ya correcto'` o `'Revisar'`.
- No hay FK a `filtros_equipo`. El vínculo es por valor de `codigo_sap` en tiempo de consulta. Esto permite que el catálogo de homólogos exista independientemente del maestro de filtración.

### Cambio en `init_db()` (`models.py`)

Agregar el `CREATE TABLE IF NOT EXISTS homologos` dentro del `executescript` existente, después de `filtros_equipo`.

No requiere `_migrate_*` adicional (la tabla es nueva; si ya existe nada cambia).

---

## 2. Sincronización ETL (`sync_data.py`)

### Columnas esperadas en hoja `Grupos_Homologos`

| Columna Excel | Mapeado a | Notas |
|---|---|---|
| `Grupo` | `grupo` | Entero |
| `Tamaño Grupo` | — | Se lee pero no se persiste |
| `Estado` | `estado` | `'Ya correcto'` / `'Revisar'` |
| `Codigo SAP` | `codigo_sap` | Limpiado con `_clean_sap()` |
| `Descripcion` | `descripcion` | Strip |

### Función `sync_homologos(filepath)`

```python
def sync_homologos(filepath):
    """
    Lee Excel hoja 'Grupos_Homologos' y reemplaza tabla homologos
    con DELETE + INSERT completo.
    Retorna: {'total_registros': X, 'grupos': Y}
    """
```

- Valida columnas requeridas: `Grupo`, `Estado`, `Codigo SAP`, `Descripcion`.
- Descarta filas donde `Grupo` o `Codigo SAP` sean nulos.
- `codigo_sap` pasa por `_clean_sap()` igual que en `sync_filtros`.
- DELETE FROM homologos → INSERT todos los registros.
- Retorna `{'total_registros': X, 'grupos': Y}` donde `grupos` es `df['Grupo'].nunique()`.

### Cambios en route `/admin/sync` (`app.py`)

- Agrega `file_homologos = request.files.get('file_homologos')`.
- Bloque idéntico al de `file_filtros`: validar extensión, guardar como `maestro_homologos.xlsx`, llamar `sync_homologos()`, flash éxito/error, borrar archivo.
- Condición de validación cambia a: al menos uno de los tres archivos debe estar presente.

---

## 3. UI — Ficha de Equipo y Flota

### Query adicional en `equipo_detalle` (y su equivalente en flota)

Después de cargar `filtros`, una sola query trae todos los homólogos del equipo:

```sql
SELECT h.grupo, h.codigo_sap, h.descripcion, h.estado,
       f.id AS filtro_id
FROM filtros_equipo f
JOIN homologos h ON h.grupo = (
    SELECT grupo FROM homologos
    WHERE codigo_sap = f.codigo_sap LIMIT 1
)
WHERE UPPER(f.equipo) = ?
ORDER BY h.grupo, h.estado DESC, h.codigo_sap
```

En Python, construir:

```python
homologos_map = {}  # filtro_id -> [rows]
for row in homologos_raw:
    homologos_map.setdefault(row['filtro_id'], []).append(row)
```

Pasar `homologos_map` al template.

### Renderizado en template

En la tabla de filtros, para cada fila donde `filtro.id in homologos_map`:

1. En la celda de acciones (o al final de la fila): botón `▼ Ver homólogos (N)`.
2. Debajo de la fila (como fila extra con `colspan` completo): `<div>` oculto con sub-tabla.

**Sub-tabla de homólogos:**

| Código SAP | Descripción | Estado |
|---|---|---|
| 10045678 (resaltado) | FILTRO ACEITE MOTOR | badge verde "Ya correcto" |
| 10045679 | FILTRO ACEITE HOMÓLOGO A | badge ámbar "Revisar" |

- La fila cuyo `codigo_sap` coincide con el del filtro padre se marca con fondo verde suave (`#f0fdf4`) y chip "Principal".
- `Ya correcto` → badge verde (`#f0fdf4 / #14532d`).
- `Revisar` → badge ámbar (`#fffbeb / #92400e`).
- Toggle con JS puro: `element.style.display`. El botón alterna texto `▼ Ver homólogos (N)` / `▲ Ocultar`.
- Si el filtro no tiene `codigo_sap`, o no hay entrada en `homologos_map`, no se muestra nada extra.

**La misma lógica aplica en `taller/flota`** — la ficha del equipo accesible desde flota usa `equipo_detalle` directamente, por lo que no requiere cambios adicionales.

---

## 4. Exportación Excel (`exportar_ficha_equipo`)

### Query adicional

```sql
SELECT f.nombre_articulo AS filtro_original, f.codigo_sap AS sap_original,
       h.grupo, h.codigo_sap AS sap_homologo, h.descripcion, h.estado
FROM filtros_equipo f
JOIN homologos h ON h.grupo = (
    SELECT grupo FROM homologos WHERE codigo_sap = f.codigo_sap LIMIT 1
)
WHERE UPPER(f.equipo) = ?
ORDER BY h.grupo, h.estado DESC, h.codigo_sap
```

### Hoja `Homólogos` (tercera)

Columnas: `Filtro Original`, `SAP Original`, `Grupo`, `SAP Homólogo`, `Descripción`, `Estado`

- Encabezados con fondo `#002D6E` y texto blanco, igual que hojas existentes.
- Si ningún filtro del equipo tiene homólogos, la hoja **no se crea**.
- Las hojas `Filtros` e `Historial Cambios` no se modifican.

---

## 5. Template — Página Sync (`admin/sync.html`)

Agregar tercera sección upload después de "Maestro Filtración":

- Ícono: color naranja/ámbar (`#FFF7ED` / `var(--ambar)`).
- Título: "Homólogos de Filtros" con badge `OPCIONAL`.
- Descripción: "Catálogo de equivalencias entre códigos SAP. Reemplaza completamente la tabla existente."
- `name="file_homologos"`.
- Columnas hint: `Grupo` · `Tamaño Grupo` · `Estado` · `Codigo SAP` · `Descripcion`.

---

## Decisiones de diseño

| Decisión | Elegida | Descartada | Razón |
|---|---|---|---|
| Cargar homólogos | Pre-cargado en HTML, toggle JS | AJAX por expand | Lista pequeña (≤8 filtros), patrón server-rendered existente |
| Vínculo homólogos-filtros | Por valor `codigo_sap` en query | FK en tabla | Independencia entre sync de filtros y sync de homólogos |
| Homólogos en Excel | Hoja separada `Homólogos` | Columnas en hoja `Filtros` | Más limpio, hoja existente sin cambios |
| Estado | Badge de color en sub-tabla | Solo admin / ignorar | Útil para técnico al seleccionar alternativas |

---

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `models.py` | Tabla `homologos` en `init_db()` |
| `sync_data.py` | Función `sync_homologos()` |
| `app.py` | Route `/admin/sync` (tercer upload), `equipo_detalle` (query + map), `exportar_ficha_equipo` (hoja Homólogos) |
| `templates/admin/sync.html` | Tercera sección upload |
| `templates/equipo_detalle.html` | Botón expand + sub-tabla en tabla de filtros |

No se crean archivos nuevos. El template de flota (`templates/tecnico/flota.html`) no requiere cambios porque accede a la ficha vía `equipo_detalle`.
