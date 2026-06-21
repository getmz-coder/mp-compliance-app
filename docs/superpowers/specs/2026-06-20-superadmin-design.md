# Diseño: Panel Superadmin — 5 Funcionalidades

**Fecha:** 2026-06-20  
**Proyecto:** App Seguimiento MP GET Talma  
**Scope:** Funcionalidades exclusivas para el rol `superadmin`

---

## Contexto

El proyecto ya tiene el rol `superadmin` definido en la BD y en los decorators existentes (`admin_required` lo incluye). El usuario `mz13` tiene este rol. No existe aún un decorator dedicado ni rutas exclusivas para superadmin. Este spec define las 5 funcionalidades nuevas.

---

## Decisión arquitectural: Decorator `superadmin_required`

Se añade un nuevo decorator en `app.py` junto a los existentes (`admin_required`, `cio_required`, `tecnico_required`):

```python
def superadmin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.rol != 'superadmin':
            flash('Acceso restringido a superadministradores.', 'error')
            return redirect(url_for('dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated
```

Todas las rutas nuevas de superadmin usan `@superadmin_required`. No se usa `@admin_required` para estas rutas.

---

## Rutas nuevas

| Ruta | Métodos | Función Flask | Descripción |
|---|---|---|---|
| `/admin/usuario/<id>/reset-password` | POST | `admin_reset_password` | Resetear contraseña de un usuario |
| `/admin/backup` | GET | `admin_backup` | Descarga `app.db` completa |
| `/admin/limpiar` | GET, POST | `admin_limpiar` | Página limpiar data masiva |
| `/admin/limpiar/preview` | POST | `admin_limpiar_preview` | Preview JSON de registros a borrar |
| `/admin/motivos` | GET, POST | `admin_motivos` | Lista y creación de motivos |
| `/admin/motivos/<id>/editar` | POST | `admin_motivo_editar` | Editar motivo existente |
| `/admin/motivos/<id>/toggle` | POST | `admin_motivo_toggle` | Activar/desactivar motivo |
| `/admin/sistema` | GET | `admin_sistema` | Panel de estadísticas del sistema |

**Templates nuevos:** `templates/admin/limpiar.html`, `templates/admin/motivos.html`, `templates/admin/sistema.html`

**Templates modificados:** `templates/base.html`, `templates/admin/dashboard.html`, `templates/admin/usuarios.html`

---

## Funcionalidad 1: Resetear contraseña

### Backend
- Ruta `POST /admin/usuario/<id>/reset-password`, protegida con `@superadmin_required`.
- Recibe `nueva_password` y `confirmar_password` del form + `_csrf_token`.
- Validaciones:
  - Los dos campos deben coincidir.
  - Longitud mínima: 8 caracteres.
  - El usuario objetivo debe existir y estar activo.
- Operación: `UPDATE usuarios SET password_hash = ? WHERE id = ?` usando `generate_password_hash`.
- Registra en `log_actividad`: `accion_tipo='reset_password'`, `detalle=f'Contraseña reseteada para usuario {username}'`.
- Responde con redirect a `/admin/usuarios` + flash success/error.

### Frontend — `templates/admin/usuarios.html`
- En la tabla de usuarios, columna "Acciones", agregar botón "Cambiar contraseña" **solo si** `is_superadmin`.
- El botón abre un modal con:
  - Campo `nueva_password` (type="password", required, minlength=8).
  - Campo `confirmar_password` (type="password", required).
  - Validación JS: al submit, verificar que los dos campos coincidan antes de enviar.
  - Si no coinciden, mostrar error inline sin cerrar el modal.
  - El modal muestra el nombre del usuario objetivo en el título.
- El form del modal hace POST al endpoint correcto con CSRF token.

---

## Funcionalidad 2: Backup de BD

### Backend
- Ruta `GET /admin/backup`, protegida con `@superadmin_required`.
- Usa `send_file(config.DATABASE_PATH, as_attachment=True, download_name=nombre)`.
- Nombre del archivo: `backup_mp_YYYYMMDD_HHMM.db` (timestamp en hora Bogotá).
- Registra en `log_actividad`: `accion_tipo='backup'`, `detalle='Descarga backup BD'`.

### Frontend — `templates/admin/dashboard.html`
- Botón "Descargar Backup" visible **solo si** `current_user.rol == 'superadmin'`.
- Ubicación: fila de acciones rápidas en el dashboard, después de los KPIs.
- Estilo: `btn-outline` con ícono de descarga (SVG inline).
- Es un `<a href="/admin/backup">`, no un form (es GET).

---

## Funcionalidad 3: Limpiar data masiva

### Backend
**`POST /admin/limpiar/preview`** (JSON):
- Recibe `{ "modo": "fechas"|"ciclo"|"todo", "fecha_desde": "...", "fecha_hasta": "...", "sync_id": N }`.
- Devuelve `{ "solicitudes": N, "respuestas": N, "no_reportadas": N, "sugerencias": N, "total": N }`.
- No borra nada, solo cuenta.

**`POST /admin/limpiar`**:
- Recibe `modo`, parámetros según modo, y `confirmacion` (debe ser exactamente `"CONFIRMAR"`).
- Si `confirmacion != "CONFIRMAR"`: flash error, redirect.
- Modos:
  - `fechas`: borra `solicitudes` con `fecha_solicitud BETWEEN fecha_desde AND fecha_hasta` (y en cascada `respuestas` via subquery de `solicitud_id`).
  - `ciclo`: borra `solicitudes` con `sync_id = N` (y `respuestas` en cascada).
  - `todo`: borra `solicitudes`, `respuestas`, `ejecuciones_no_reportadas`, `sugerencias_filtros` (sin WHERE).
- Registra en `log_actividad`: `accion_tipo='limpiar_data'`, `detalle` con modo y cantidad de registros borrados.
- Flash success con resumen de filas borradas.

### Frontend — `templates/admin/limpiar.html`
- Tres secciones colapsables (acordeón CSS puro, sin JS externo).
- **Sección A — Por rango de fechas:**
  - Inputs `date` para `fecha_desde` y `fecha_hasta`.
  - Botón "Ver cuántos registros" → fetch AJAX al preview endpoint → muestra tabla de conteos.
- **Sección B — Por ciclo sync:**
  - Dropdown con sync_ids disponibles (cargados desde BD al renderizar GET).
  - Botón "Ver cuántos registros" → fetch AJAX preview.
- **Sección C — Todo (nuclear):**
  - Descripción clara de qué se borra.
  - Botón "Ver cuántos registros" → fetch AJAX preview (modo=todo).
- Modal de confirmación (compartido por las 3 secciones):
  - Muestra tabla de conteos del preview.
  - Campo de texto: "Escriba CONFIRMAR para proceder".
  - Botón "Ejecutar limpieza" (rojo) habilitado solo cuando el texto es exactamente `CONFIRMAR`.
  - Al confirmar, submit del form con `modo` y parámetros de la sección activa.

### Nota de integridad
Las `respuestas` tienen FK a `solicitudes`. Al borrar solicitudes, se borran las respuestas asociadas usando `DELETE FROM respuestas WHERE solicitud_id IN (SELECT id FROM solicitudes WHERE ...)` primero, luego `DELETE FROM solicitudes WHERE ...`.

---

## Funcionalidad 4: Configurar motivos

### Backend
- `GET /admin/motivos`: renderiza lista de todos los motivos ordenados por `orden ASC`.
- `POST /admin/motivos`: crea nuevo motivo. Campos: `codigo` (único, max 10 chars), `descripcion` (max 200), `orden` (int). Valida que el código no exista ya.
- `POST /admin/motivos/<id>/editar`: actualiza `codigo`, `descripcion`, `orden` de un motivo existente. Responde JSON `{ "success": true }`.
- `POST /admin/motivos/<id>/toggle`: alterna `activo` (0↔1). Responde JSON `{ "success": true, "activo": 0|1 }`.
- Todos con `@superadmin_required`.

### Frontend — `templates/admin/motivos.html`
- Tabla con columnas: Orden, Código, Descripción, Estado, Acciones.
- Motivos inactivos: fondo `#f9fafb`, badge "Inactivo" (gris).
- Botón "Editar" por fila: convierte esa fila en inputs editables inline. Botones "Guardar" / "Cancelar" aparecen. Guardar hace fetch POST JSON al endpoint editar, cancela restaura el DOM original.
- Botón "Activar/Desactivar" por fila: hace fetch POST al endpoint toggle, actualiza el badge y el botón sin recargar.
- Formulario al pie (siempre visible): campos Código, Descripción, Orden + botón "Agregar motivo" → POST al GET/POST de la misma ruta → redirect con flash.
- Link "Motivos" en navbar de `base.html`: `{% if current_user.rol == 'superadmin' %}`.

### Impacto en dropdown CIO
- La consulta que carga el `catalogo_motivos` en el formulario del CIO ya debe filtrar `WHERE activo = 1`.
- Los registros históricos en `respuestas` hacen JOIN por `motivo_id` sin filtrar `activo`, así el nombre siempre aparece.

---

## Funcionalidad 5: Panel estadísticas del sistema

### Backend
- `GET /admin/sistema`, protegida con `@superadmin_required`.
- Consultas a la BD:
  - `SELECT COUNT(*) FROM usuarios WHERE activo = 1` → total usuarios activos.
  - `SELECT COUNT(*) FROM equipos WHERE sync_id = (SELECT MAX(sync_id) FROM equipos)` → equipos sync actual.
  - `SELECT COUNT(*) FROM filtros_equipo` → total filtros maestro.
  - `os.path.getsize(config.DATABASE_PATH) / (1024*1024)` → peso BD en MB (2 decimales).
  - `SELECT MAX(timestamp) FROM log_actividad WHERE accion_tipo = 'sync'` → fecha último sync.
  - `SELECT COUNT(*) FROM solicitudes` → total histórico solicitudes.
  - `SELECT COUNT(*) FROM respuestas` → total histórico respuestas.
  - `SELECT * FROM usuarios ORDER BY created_at DESC` → tabla de usuarios.

### Frontend — `templates/admin/sistema.html`
- Grid superior 4 cols: Total usuarios activos (azul), Equipos cargados (verde), Filtros en maestro (cielo), Peso BD MB (ámbar).
- Grid secundario 3 cols: Fecha último sync, Total solicitudes históricas, Total respuestas históricas.
- Tabla de usuarios: Nombre completo, Username, Rol (badge por color), Activo (badge verde/gris), Fecha creación.
- Link "Sistema" en navbar de `base.html`: `{% if current_user.rol == 'superadmin' %}`.

---

## Navbar — cambios en `base.html`

Dentro del bloque `{% if current_user.rol in ('admin', 'superadmin') %}`, añadir al final:

```html
{% if current_user.rol == 'superadmin' %}
  <a href="{{ url_for('admin_motivos') }}"
     {% if request.endpoint == 'admin_motivos' %}class="active"{% endif %}>Motivos</a>
  <a href="{{ url_for('admin_sistema') }}"
     {% if request.endpoint == 'admin_sistema' %}class="active"{% endif %}>Sistema</a>
{% endif %}
```

---

## Log actividad — tipos usados

| `accion_tipo` | Cuándo |
|---|---|
| `reset_password` | Resetear contraseña de usuario |
| `backup` | Descargar backup BD |
| `limpiar_data` | Ejecutar limpieza masiva |
| `motivo_crear` | Crear nuevo motivo |
| `motivo_editar` | Editar motivo existente |
| `motivo_toggle` | Activar/desactivar motivo |

---

## Restricciones de seguridad

- Todas las rutas nuevas usan `@superadmin_required` (incluye `@login_required` implícito).
- Todos los POST incluyen validación CSRF (ya implementada globalmente en `@app.before_request`).
- El backup no requiere form/CSRF porque es GET (solo descarga de archivo propio).
- El texto "CONFIRMAR" en limpiar se valida en backend además de en JS — el JS es solo UX.

---

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `app.py` | Nuevo decorator + 8 rutas nuevas |
| `templates/base.html` | Links Motivos y Sistema en navbar |
| `templates/admin/dashboard.html` | Botón Descargar Backup |
| `templates/admin/usuarios.html` | Botón Cambiar contraseña + modal |
| `templates/admin/limpiar.html` | **Nuevo** |
| `templates/admin/motivos.html` | **Nuevo** |
| `templates/admin/sistema.html` | **Nuevo** |
