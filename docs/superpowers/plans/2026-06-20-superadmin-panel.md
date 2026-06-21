# Panel Superadmin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir 5 funcionalidades exclusivas para el rol `superadmin`: resetear contraseñas, backup de BD, limpiar data masiva, configurar motivos y panel de estadísticas del sistema.

**Architecture:** Un nuevo decorator `superadmin_required` centraliza la protección de todas las rutas nuevas. Las rutas se añaden a `app.py` siguiendo el patrón existente. Los templates nuevos extienden `base.html` con el mismo estilo Talma del resto de la app.

**Tech Stack:** Python/Flask, SQLite (`get_db()`/`_log_actividad()`), Jinja2, CSS+JS inline (zero CDN), `send_file` para backup, `werkzeug.security.generate_password_hash`.

## Global Constraints

- Branding Talma: `--azul: #002D6E`, `--verde: #80AE3F`, `--cielo: #1E88E5`, `--ambar: #E67E22`, fondo `#F0F2F5`
- Zero CDN externos — todo CSS/JS embebido en el template
- Cada acción administrativa se registra en `log_actividad` via `_log_actividad(conn, usuario_id, accion_tipo, detalle)`
- CSRF: todos los POST incluyen `<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">` y se valida automáticamente por `@app.before_request`
- Backup es GET — no requiere CSRF
- El decorator `superadmin_required` redirige con flash, no con `abort(403)`, igual que los otros decorators del proyecto
- El texto de confirmación en limpiar se valida en backend además de en JS
- Español en UI, inglés en variables/funciones Python
- Responsive para laptop/tablet

---

## Mapa de archivos

| Archivo | Acción | Qué cambia |
|---|---|---|
| `app.py` | Modificar | Decorator `superadmin_required` + 8 rutas nuevas |
| `templates/base.html` | Modificar | Links Motivos y Sistema en navbar |
| `templates/admin/dashboard.html` | Modificar | Botón "Descargar Backup" en acciones rápidas |
| `templates/admin/usuarios.html` | Modificar | Botón "Cambiar contraseña" + modal |
| `templates/admin/limpiar.html` | Crear | Página limpiar data masiva |
| `templates/admin/motivos.html` | Crear | Gestión de catálogo de motivos |
| `templates/admin/sistema.html` | Crear | Panel estadísticas del sistema |

---

## Task 1: Decorator `superadmin_required` + links navbar

**Files:**
- Modify: `app.py` (después de `tecnico_required`, línea ~167)
- Modify: `templates/base.html` (dentro del bloque admin en navbar)

**Interfaces:**
- Produces: decorator `superadmin_required(f)` — úsalo en las tareas 2-6 igual que `@admin_required`

- [ ] **Step 1: Añadir decorator en `app.py`**

Insertar después de `tecnico_required` (línea ~167), antes de la línea vacía que precede a `_log_actividad`:

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

- [ ] **Step 2: Añadir links en navbar de `base.html`**

En `templates/base.html`, localizar el bloque del navbar admin. Después del link de "Sugerencias" y antes del `{% elif current_user.rol == 'cio' %}`, insertar:

```html
        {% if current_user.rol == 'superadmin' %}
          <a href="{{ url_for('admin_motivos') }}"
             {% if request.endpoint == 'admin_motivos' %}class="active"{% endif %}>Motivos</a>
          <a href="{{ url_for('admin_sistema') }}"
             {% if request.endpoint == 'admin_sistema' %}class="active"{% endif %}>Sistema</a>
        {% endif %}
```

- [ ] **Step 3: Verificar**

Iniciar la app (`python app.py`), iniciar sesión como `admin` (no superadmin) → los links Motivos y Sistema NO deben aparecer en la navbar.
Iniciar sesión como `mz13` (superadmin) → deben aparecer Motivos y Sistema.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/base.html
git commit -m "Superadmin: decorator superadmin_required y links navbar Motivos/Sistema"
```

---

## Task 2: Resetear contraseña

**Files:**
- Modify: `app.py` (nueva ruta `POST /admin/usuario/<id>/reset-password`)
- Modify: `templates/admin/usuarios.html` (botón + modal)

**Interfaces:**
- Consumes: `superadmin_required` (Task 1), `get_db()`, `generate_password_hash`, `_log_actividad`
- Produces: ruta Flask `admin_reset_password(user_id)`

- [ ] **Step 1: Añadir ruta en `app.py`**

Insertar después del bloque `admin_usuarios` (después de la función `admin_usuarios`, antes del comentario `# CIO` alrededor de línea 1010):

```python
@app.route('/admin/usuario/<int:user_id>/reset-password', methods=['POST'])
@superadmin_required
def admin_reset_password(user_id):
    nueva = request.form.get('nueva_password', '').strip()
    confirmar = request.form.get('confirmar_password', '').strip()

    if len(nueva) < 8:
        flash('La contraseña debe tener mínimo 8 caracteres.', 'error')
        return redirect(url_for('admin_usuarios'))
    if nueva != confirmar:
        flash('Las contraseñas no coinciden.', 'error')
        return redirect(url_for('admin_usuarios'))

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT username FROM usuarios WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            flash('Usuario no encontrado.', 'error')
            return redirect(url_for('admin_usuarios'))
        conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id = ?",
            (generate_password_hash(nueva), user_id)
        )
        _log_actividad(conn, current_user.id, 'reset_password',
                       f'Contraseña reseteada para usuario {row["username"]} (id={user_id})')
        conn.commit()
        flash(f'Contraseña de "{row["username"]}" actualizada correctamente.', 'success')
    finally:
        conn.close()
    return redirect(url_for('admin_usuarios'))
```

- [ ] **Step 2: Añadir CSS del modal en `templates/admin/usuarios.html`**

Al final del bloque `<style>` (antes del `</style>`), añadir:

```css
  /* ── Modal cambiar contraseña ── */
  .modal-hdr-blue { background: #eff6ff; }
  .modal-hdr-blue h3 { color: var(--azul); }
  .btn-modal-confirm-blue {
    padding: 8px 20px;
    background: var(--azul);
    color: #fff;
    border: none;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-modal-confirm-blue:hover { background: #001f4e; }
  .pwd-error {
    font-size: 12px;
    color: var(--rojo);
    margin-top: 6px;
    display: none;
  }
  .pwd-error.visible { display: block; }
```

- [ ] **Step 3: Añadir botón en la tabla de usuarios**

En `templates/admin/usuarios.html`, en la columna de acciones de cada fila (`<td style="white-space:nowrap;">`), después del bloque del botón "Eliminar" y antes del cierre `</td>`, añadir:

```html
                {% if is_superadmin and u.id != current_user.id %}
                <button type="button" class="btn-toggle activar"
                        style="margin-left:6px;"
                        onclick="abrirModalPwd({{ u.id }}, '{{ u.username }}')">
                  Cambiar pwd
                </button>
                {% endif %}
```

- [ ] **Step 4: Añadir modal HTML en `templates/admin/usuarios.html`**

Antes del cierre `</div>` del bloque `{% block content %}`, añadir:

```html
<!-- Modal cambiar contraseña -->
<div class="modal-overlay" id="modal-pwd" style="display:none;"
     onclick="if(event.target===this) cerrarModalPwd()">
  <div class="modal-box">
    <div class="modal-hdr modal-hdr-blue">
      <h3>Cambiar contraseña — <span id="modal-pwd-username"></span></h3>
      <button class="modal-close" onclick="cerrarModalPwd()">×</button>
    </div>
    <form id="form-pwd" method="POST" action="" onsubmit="return validarPwd()">
      <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
      <div class="modal-body">
        <div class="form-group" style="margin-bottom:14px;">
          <label>Nueva contraseña</label>
          <input type="password" name="nueva_password" id="pwd-nueva"
                 minlength="8" required autocomplete="new-password"
                 placeholder="Mínimo 8 caracteres">
        </div>
        <div class="form-group" style="margin-bottom:4px;">
          <label>Confirmar contraseña</label>
          <input type="password" name="confirmar_password" id="pwd-confirmar"
                 minlength="8" required autocomplete="new-password"
                 placeholder="Repite la contraseña">
        </div>
        <div class="pwd-error" id="pwd-error">Las contraseñas no coinciden.</div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn-modal-cancel" onclick="cerrarModalPwd()">Cancelar</button>
        <button type="submit" class="btn-modal-confirm-blue">Actualizar contraseña</button>
      </div>
    </form>
  </div>
</div>
```

- [ ] **Step 5: Añadir JS del modal**

Antes del cierre `{% endblock %}` de content, añadir:

```html
<script>
function abrirModalPwd(userId, username) {
  document.getElementById('modal-pwd-username').textContent = username;
  document.getElementById('form-pwd').action = '/admin/usuario/' + userId + '/reset-password';
  document.getElementById('pwd-nueva').value = '';
  document.getElementById('pwd-confirmar').value = '';
  document.getElementById('pwd-error').classList.remove('visible');
  document.getElementById('modal-pwd').style.display = 'flex';
  document.getElementById('pwd-nueva').focus();
}
function cerrarModalPwd() {
  document.getElementById('modal-pwd').style.display = 'none';
}
function validarPwd() {
  const nueva = document.getElementById('pwd-nueva').value;
  const conf  = document.getElementById('pwd-confirmar').value;
  const err   = document.getElementById('pwd-error');
  if (nueva !== conf) {
    err.classList.add('visible');
    return false;
  }
  err.classList.remove('visible');
  return true;
}
</script>
```

- [ ] **Step 6: Verificar**

Como `mz13` (superadmin): ir a Usuarios → debe verse botón "Cambiar pwd" en filas de otros usuarios.
Click en botón → abre modal con nombre de usuario.
Ingresar contraseñas que no coinciden → error inline, no se envía.
Ingresar contraseñas < 8 chars → el `minlength` del input previene submit.
Ingresar contraseña válida → redirige con flash success, el usuario puede loguearse con la nueva contraseña.
Como `admin` normal: el botón no debe aparecer.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/admin/usuarios.html
git commit -m "Superadmin: resetear contraseña de usuarios con modal de confirmación"
```

---

## Task 3: Backup de BD

**Files:**
- Modify: `app.py` (nueva ruta `GET /admin/backup`)
- Modify: `templates/admin/dashboard.html` (botón en acciones rápidas)

**Interfaces:**
- Consumes: `superadmin_required` (Task 1), `config.DATABASE_PATH`, `send_file`, `_log_actividad`
- Produces: ruta Flask `admin_backup()`

- [ ] **Step 1: Añadir ruta en `app.py`**

Insertar después de `admin_reset_password` (Task 2):

```python
@app.route('/admin/backup')
@superadmin_required
def admin_backup():
    nombre = f"backup_mp_{datetime.now(TZ_COL).strftime('%Y%m%d_%H%M')}.db"
    conn = get_db()
    try:
        _log_actividad(conn, current_user.id, 'backup', f'Descarga backup BD: {nombre}')
        conn.commit()
    finally:
        conn.close()
    return send_file(
        config.DATABASE_PATH,
        as_attachment=True,
        download_name=nombre,
        mimetype='application/octet-stream',
    )
```

- [ ] **Step 2: Añadir botón en `templates/admin/dashboard.html`**

En el bloque `<div class="actions-grid">`, añadir al final (después del último `</a>` de action-item), dentro de un guard `{% if current_user.rol == 'superadmin' %}`:

```html
        {% if current_user.rol == 'superadmin' %}
        <a href="{{ url_for('admin_backup') }}" class="action-item">
          <div class="action-icon blue">
            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </div>
          <div>
            <div class="action-label">Descargar Backup</div>
            <div class="action-sub">Copia completa de la BD</div>
          </div>
        </a>
        {% endif %}
```

- [ ] **Step 3: Verificar**

Como `mz13`: el botón "Descargar Backup" aparece en el dashboard → click → descarga un archivo `.db` con nombre `backup_mp_YYYYMMDD_HHMM.db`.
Como `admin` normal: el botón NO aparece.
Verificar que el archivo descargado se puede abrir con un cliente SQLite (DB Browser, DBeaver, etc.) y contiene las tablas correctas.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/admin/dashboard.html
git commit -m "Superadmin: backup BD descargable desde dashboard"
```

---

## Task 4: Limpiar data masiva

**Files:**
- Modify: `app.py` (rutas `GET+POST /admin/limpiar` y `POST /admin/limpiar/preview`)
- Create: `templates/admin/limpiar.html`

**Interfaces:**
- Consumes: `superadmin_required` (Task 1), `get_db()`, `_log_actividad`
- Produces: rutas `admin_limpiar()` y `admin_limpiar_preview()`

- [ ] **Step 1: Añadir rutas en `app.py`**

Insertar después de `admin_backup` (Task 3):

```python
@app.route('/admin/limpiar', methods=['GET', 'POST'])
@superadmin_required
def admin_limpiar():
    conn = get_db()
    sync_ids = [r['sync_id'] for r in conn.execute(
        "SELECT DISTINCT sync_id FROM solicitudes WHERE sync_id IS NOT NULL ORDER BY sync_id DESC"
    ).fetchall()]
    conn.close()

    if request.method == 'GET':
        return render_template('admin/limpiar.html', sync_ids=sync_ids)

    modo = request.form.get('modo', '')
    confirmacion = request.form.get('confirmacion', '').strip()

    if confirmacion != 'CONFIRMAR':
        flash('Debes escribir CONFIRMAR exactamente para proceder.', 'error')
        return render_template('admin/limpiar.html', sync_ids=sync_ids)

    conn = get_db()
    try:
        borrados = {'solicitudes': 0, 'respuestas': 0, 'no_reportadas': 0, 'sugerencias': 0}

        if modo == 'fechas':
            fecha_desde = request.form.get('fecha_desde', '')
            fecha_hasta = request.form.get('fecha_hasta', '')
            if not fecha_desde or not fecha_hasta:
                flash('Debes indicar fecha desde y hasta.', 'error')
                conn.close()
                return render_template('admin/limpiar.html', sync_ids=sync_ids)
            sol_ids = [r['id'] for r in conn.execute(
                "SELECT id FROM solicitudes WHERE DATE(fecha_solicitud) BETWEEN ? AND ?",
                (fecha_desde, fecha_hasta)
            ).fetchall()]
            if sol_ids:
                placeholders = ','.join('?' * len(sol_ids))
                cur = conn.execute(
                    f"DELETE FROM respuestas WHERE solicitud_id IN ({placeholders})", sol_ids
                )
                borrados['respuestas'] = cur.rowcount
                cur = conn.execute(
                    f"DELETE FROM solicitudes WHERE id IN ({placeholders})", sol_ids
                )
                borrados['solicitudes'] = cur.rowcount
            detalle = f'Limpieza por fechas {fecha_desde} a {fecha_hasta}'

        elif modo == 'ciclo':
            sync_id_limpiar = request.form.get('sync_id_limpiar', type=int)
            if not sync_id_limpiar:
                flash('Debes seleccionar un ciclo.', 'error')
                conn.close()
                return render_template('admin/limpiar.html', sync_ids=sync_ids)
            sol_ids = [r['id'] for r in conn.execute(
                "SELECT id FROM solicitudes WHERE sync_id = ?", (sync_id_limpiar,)
            ).fetchall()]
            if sol_ids:
                placeholders = ','.join('?' * len(sol_ids))
                cur = conn.execute(
                    f"DELETE FROM respuestas WHERE solicitud_id IN ({placeholders})", sol_ids
                )
                borrados['respuestas'] = cur.rowcount
                cur = conn.execute(
                    f"DELETE FROM solicitudes WHERE id IN ({placeholders})", sol_ids
                )
                borrados['solicitudes'] = cur.rowcount
            detalle = f'Limpieza ciclo sync_id={sync_id_limpiar}'

        elif modo == 'todo':
            cur = conn.execute("DELETE FROM respuestas")
            borrados['respuestas'] = cur.rowcount
            cur = conn.execute("DELETE FROM solicitudes")
            borrados['solicitudes'] = cur.rowcount
            cur = conn.execute("DELETE FROM ejecuciones_no_reportadas")
            borrados['no_reportadas'] = cur.rowcount
            cur = conn.execute("DELETE FROM sugerencias_filtros")
            borrados['sugerencias'] = cur.rowcount
            detalle = 'Limpieza total de data operacional'

        else:
            flash('Modo de limpieza inválido.', 'error')
            conn.close()
            return render_template('admin/limpiar.html', sync_ids=sync_ids)

        total = sum(borrados.values())
        _log_actividad(conn, current_user.id, 'limpiar_data',
                       f'{detalle} — {total} registros borrados: {borrados}')
        conn.commit()
        flash(
            f'Limpieza completada: {borrados["solicitudes"]} solicitudes, '
            f'{borrados["respuestas"]} respuestas, '
            f'{borrados["no_reportadas"]} no-reportadas, '
            f'{borrados["sugerencias"]} sugerencias eliminadas.',
            'success'
        )
    finally:
        conn.close()
    return redirect(url_for('admin_limpiar'))


@app.route('/admin/limpiar/preview', methods=['POST'])
@superadmin_required
def admin_limpiar_preview():
    data = request.get_json(force=True) or {}
    modo = data.get('modo', '')
    conn = get_db()
    try:
        counts = {'solicitudes': 0, 'respuestas': 0, 'no_reportadas': 0, 'sugerencias': 0}

        if modo == 'fechas':
            fecha_desde = data.get('fecha_desde', '')
            fecha_hasta = data.get('fecha_hasta', '')
            sol_ids = [r['id'] for r in conn.execute(
                "SELECT id FROM solicitudes WHERE DATE(fecha_solicitud) BETWEEN ? AND ?",
                (fecha_desde, fecha_hasta)
            ).fetchall()]
            counts['solicitudes'] = len(sol_ids)
            if sol_ids:
                placeholders = ','.join('?' * len(sol_ids))
                counts['respuestas'] = conn.execute(
                    f"SELECT COUNT(*) AS c FROM respuestas WHERE solicitud_id IN ({placeholders})",
                    sol_ids
                ).fetchone()['c']

        elif modo == 'ciclo':
            sync_id_p = data.get('sync_id')
            sol_ids = [r['id'] for r in conn.execute(
                "SELECT id FROM solicitudes WHERE sync_id = ?", (sync_id_p,)
            ).fetchall()]
            counts['solicitudes'] = len(sol_ids)
            if sol_ids:
                placeholders = ','.join('?' * len(sol_ids))
                counts['respuestas'] = conn.execute(
                    f"SELECT COUNT(*) AS c FROM respuestas WHERE solicitud_id IN ({placeholders})",
                    sol_ids
                ).fetchone()['c']

        elif modo == 'todo':
            counts['solicitudes']  = conn.execute("SELECT COUNT(*) AS c FROM solicitudes").fetchone()['c']
            counts['respuestas']   = conn.execute("SELECT COUNT(*) AS c FROM respuestas").fetchone()['c']
            counts['no_reportadas'] = conn.execute("SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas").fetchone()['c']
            counts['sugerencias']  = conn.execute("SELECT COUNT(*) AS c FROM sugerencias_filtros").fetchone()['c']

    finally:
        conn.close()

    counts['total'] = sum(counts.values())
    return jsonify(counts)
```

- [ ] **Step 2: Crear `templates/admin/limpiar.html`**

```html
{% extends "base.html" %}
{% block title %}Limpiar Data — Superadmin{% endblock %}

{% block styles %}
<style>
  .limpiar-page { max-width: 860px; margin: 0 auto; padding: 28px 28px 60px; }
  .page-hdr { margin-bottom: 28px; }
  .page-hdr h1 { font-size: 22px; font-weight: 700; color: var(--azul); letter-spacing: -0.3px; }
  .page-hdr p  { font-size: 13px; color: var(--gris); margin-top: 3px; }

  .warn-banner {
    background: #fff7ed; border: 1.5px solid #fdba74; border-radius: 10px;
    padding: 14px 18px; margin-bottom: 24px;
    display: flex; align-items: center; gap: 12px;
    font-size: 13px; color: #9a3412;
  }
  .warn-banner svg { flex-shrink: 0; width: 20px; height: 20px; stroke: #f97316; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

  /* Acordeón */
  .accordion { border: 1.5px solid var(--borde); border-radius: 12px; overflow: hidden; margin-bottom: 16px; background: #fff; box-shadow: 0 1px 8px rgba(0,45,110,0.06); }
  .accordion-hdr {
    display: flex; align-items: center; gap: 10px;
    padding: 16px 20px; cursor: pointer;
    font-size: 14px; font-weight: 700; color: var(--azul);
    user-select: none; list-style: none;
    transition: background 0.12s;
  }
  .accordion-hdr:hover { background: #f8fafc; }
  .accordion-hdr svg { width: 16px; height: 16px; stroke: var(--cielo); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
  .accordion-chevron { margin-left: auto; width: 16px; height: 16px; stroke: var(--gris); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; transition: transform 0.2s; }
  details[open] .accordion-chevron { transform: rotate(90deg); }
  .accordion-body { padding: 20px; border-top: 1px solid var(--borde); }

  .form-row { display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; }
  .form-group { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 140px; }
  .form-group label { font-size: 11.5px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.3px; }
  .form-group input[type="date"],
  .form-group select {
    padding: 9px 12px; border: 1.5px solid #d1d5db; border-radius: 8px;
    font-size: 13.5px; color: var(--texto); background: #fafafa;
    outline: none; font-family: inherit; transition: border-color 0.15s;
  }
  .form-group input:focus, .form-group select:focus { border-color: var(--cielo); background: #fff; }

  .btn-preview {
    padding: 9px 18px; background: #eff6ff; color: var(--azul);
    border: 1.5px solid #bfdbfe; border-radius: 8px;
    font-size: 13px; font-weight: 700; cursor: pointer;
    white-space: nowrap; transition: background 0.15s;
  }
  .btn-preview:hover { background: #dbeafe; }

  .preview-result {
    margin-top: 16px; padding: 14px 16px;
    border: 1.5px solid var(--borde); border-radius: 8px;
    background: #f8f9fb; display: none;
  }
  .preview-result.visible { display: block; }
  .preview-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 14px; }
  .preview-table th { text-align: left; padding: 6px 10px; font-size: 11px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 1px solid var(--borde); }
  .preview-table td { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; }
  .preview-table tr:last-child td { border-bottom: none; font-weight: 700; color: var(--rojo); }

  .btn-abrir-confirm {
    padding: 9px 20px; background: var(--rojo); color: #fff;
    border: none; border-radius: 8px; font-size: 13px; font-weight: 700;
    cursor: pointer; transition: background 0.15s;
  }
  .btn-abrir-confirm:hover { background: #b91c1c; }
  .btn-abrir-confirm:disabled { background: #d1d5db; cursor: not-allowed; }

  /* Modal confirmación */
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.45);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000; padding: 20px;
  }
  .modal-box {
    background: #fff; border-radius: 14px;
    box-shadow: 0 20px 60px rgba(0,45,110,0.2);
    width: 100%; max-width: 480px; overflow: hidden;
    animation: modal-in 0.18s ease;
  }
  @keyframes modal-in { from { transform: translateY(12px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
  .modal-hdr-rojo { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid var(--borde); background: #fff2f2; }
  .modal-hdr-rojo h3 { font-size: 15px; font-weight: 700; color: var(--rojo); }
  .modal-close { background: none; border: none; font-size: 18px; color: var(--gris); cursor: pointer; padding: 2px 6px; border-radius: 4px; line-height: 1; }
  .modal-close:hover { background: #f3f4f6; }
  .modal-body { padding: 18px 20px; font-size: 13.5px; color: var(--gris); line-height: 1.6; }
  .modal-body strong { color: var(--texto); }
  .confirm-input {
    width: 100%; padding: 9px 12px; margin-top: 12px;
    border: 1.5px solid #fca5a5; border-radius: 8px;
    font-size: 14px; font-family: 'Courier New', monospace;
    outline: none; transition: border-color 0.15s;
  }
  .confirm-input:focus { border-color: var(--rojo); }
  .modal-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 12px 20px 16px; border-top: 1px solid var(--borde); }
  .btn-modal-cancel { padding: 8px 18px; background: #f3f4f6; color: var(--gris); border: 1px solid #d1d5db; border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn-modal-cancel:hover { background: #e5e7eb; }
  .btn-ejecutar {
    padding: 8px 20px; background: var(--rojo); color: #fff;
    border: none; border-radius: 7px; font-size: 13px; font-weight: 700;
    cursor: pointer; transition: background 0.15s;
  }
  .btn-ejecutar:disabled { background: #d1d5db; cursor: not-allowed; }
  .btn-ejecutar:not(:disabled):hover { background: #b91c1c; }

  @media (max-width: 768px) {
    .limpiar-page { padding: 14px 12px 40px; }
    .form-row { flex-direction: column; }
    .modal-box { max-width: 100%; }
  }
</style>
{% endblock %}

{% block content %}
<div class="limpiar-page">

  <div class="page-hdr">
    <h1>Limpiar Data Masiva</h1>
    <p>Elimina registros operacionales. Esta acción es irreversible.</p>
  </div>

  <div class="warn-banner">
    <svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
    <span>Las eliminaciones son <strong>permanentes e irreversibles</strong>. Descarga un backup de la BD antes de proceder.</span>
  </div>

  <!-- Sección A: Por rango de fechas -->
  <details class="accordion" id="sec-fechas">
    <summary class="accordion-hdr">
      <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      Por rango de fechas
      <svg class="accordion-chevron" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </summary>
    <div class="accordion-body">
      <p style="font-size:13px;color:var(--gris);margin-bottom:14px;">
        Elimina solicitudes (y sus respuestas) creadas en el rango indicado.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>Desde</label>
          <input type="date" id="f-desde" name="fecha_desde">
        </div>
        <div class="form-group">
          <label>Hasta</label>
          <input type="date" id="f-hasta" name="fecha_hasta">
        </div>
        <button type="button" class="btn-preview" onclick="previewFechas()">Ver cuántos registros</button>
      </div>
      <div class="preview-result" id="prev-fechas">
        <table class="preview-table" id="prev-fechas-tabla"></table>
        <button type="button" class="btn-abrir-confirm" id="btn-confirm-fechas" onclick="abrirModal('fechas')">
          Proceder a eliminar
        </button>
      </div>
    </div>
  </details>

  <!-- Sección B: Por ciclo sync -->
  <details class="accordion" id="sec-ciclo">
    <summary class="accordion-hdr">
      <svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
      Por ciclo de sincronización
      <svg class="accordion-chevron" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </summary>
    <div class="accordion-body">
      <p style="font-size:13px;color:var(--gris);margin-bottom:14px;">
        Elimina todas las solicitudes y respuestas de un ciclo de programación MP.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>Ciclo Sync</label>
          <select id="sel-sync">
            {% for sid in sync_ids %}
            <option value="{{ sid }}">Ciclo #{{ sid }}</option>
            {% else %}
            <option value="" disabled>Sin ciclos disponibles</option>
            {% endfor %}
          </select>
        </div>
        <button type="button" class="btn-preview" onclick="previewCiclo()">Ver cuántos registros</button>
      </div>
      <div class="preview-result" id="prev-ciclo">
        <table class="preview-table" id="prev-ciclo-tabla"></table>
        <button type="button" class="btn-abrir-confirm" onclick="abrirModal('ciclo')">
          Proceder a eliminar
        </button>
      </div>
    </div>
  </details>

  <!-- Sección C: Todo -->
  <details class="accordion" id="sec-todo">
    <summary class="accordion-hdr" style="color:var(--rojo);">
      <svg viewBox="0 0 24 24" style="stroke:var(--rojo)"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
      Limpiar TODA la data operacional
      <svg class="accordion-chevron" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </summary>
    <div class="accordion-body">
      <p style="font-size:13px;color:var(--rojo);margin-bottom:14px;font-weight:600;">
        ⚠ Elimina <strong>todas</strong> las solicitudes, respuestas, ejecuciones no reportadas y sugerencias de filtros. No afecta equipos, usuarios ni catálogo de motivos.
      </p>
      <button type="button" class="btn-preview" onclick="previewTodo()">Ver cuántos registros</button>
      <div class="preview-result" id="prev-todo">
        <table class="preview-table" id="prev-todo-tabla"></table>
        <button type="button" class="btn-abrir-confirm" onclick="abrirModal('todo')">
          Proceder a eliminar todo
        </button>
      </div>
    </div>
  </details>

</div>

<!-- Modal confirmación -->
<div class="modal-overlay" id="modal-confirm" style="display:none;">
  <div class="modal-box">
    <div class="modal-hdr-rojo">
      <h3 id="modal-confirm-titulo">Confirmar eliminación</h3>
      <button class="modal-close" onclick="cerrarModal()">×</button>
    </div>
    <form method="POST" action="{{ url_for('admin_limpiar') }}" id="form-limpiar">
      <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="modo" id="hidden-modo">
      <input type="hidden" name="fecha_desde" id="hidden-desde">
      <input type="hidden" name="fecha_hasta" id="hidden-hasta">
      <input type="hidden" name="sync_id_limpiar" id="hidden-sync">
      <div class="modal-body">
        <div id="modal-preview-contenido"></div>
        <p style="margin-top:12px;">Para confirmar, escribe <strong>CONFIRMAR</strong> en el campo:</p>
        <input type="text" name="confirmacion" id="input-confirmar" class="confirm-input"
               placeholder="Escribe CONFIRMAR" autocomplete="off" oninput="checkConfirmar()">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn-modal-cancel" onclick="cerrarModal()">Cancelar</button>
        <button type="submit" class="btn-ejecutar" id="btn-ejecutar" disabled>Ejecutar limpieza</button>
      </div>
    </form>
  </div>
</div>

<script>
let _previewData = {};

function renderTabla(data, tableId) {
  const filas = [
    ['Solicitudes', data.solicitudes],
    ['Respuestas', data.respuestas],
    ['No reportadas', data.no_reportadas],
    ['Sugerencias de filtros', data.sugerencias],
    ['TOTAL', data.total],
  ];
  const t = document.getElementById(tableId);
  t.innerHTML = '<tr><th>Tabla</th><th>Registros a borrar</th></tr>' +
    filas.map((r, i) => `<tr${i === filas.length-1 ? ' style="font-weight:700;color:var(--rojo);"':''}>
      <td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');
}

async function doPreview(payload, resultId, tablaId) {
  const res = await fetch('{{ url_for("admin_limpiar_preview") }}', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': '{{ csrf_token() }}' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  _previewData[payload.modo] = { data, payload };
  renderTabla(data, tablaId);
  document.getElementById(resultId).classList.add('visible');
}

function previewFechas() {
  const desde = document.getElementById('f-desde').value;
  const hasta = document.getElementById('f-hasta').value;
  if (!desde || !hasta) { alert('Selecciona ambas fechas.'); return; }
  doPreview({ modo: 'fechas', fecha_desde: desde, fecha_hasta: hasta }, 'prev-fechas', 'prev-fechas-tabla');
}
function previewCiclo() {
  const sid = document.getElementById('sel-sync').value;
  if (!sid) { alert('Selecciona un ciclo.'); return; }
  doPreview({ modo: 'ciclo', sync_id: sid }, 'prev-ciclo', 'prev-ciclo-tabla');
}
function previewTodo() {
  doPreview({ modo: 'todo' }, 'prev-todo', 'prev-todo-tabla');
}

function abrirModal(modo) {
  const p = _previewData[modo];
  if (!p) return;
  document.getElementById('hidden-modo').value = modo;
  document.getElementById('hidden-desde').value = p.payload.fecha_desde || '';
  document.getElementById('hidden-hasta').value = p.payload.fecha_hasta || '';
  document.getElementById('hidden-sync').value = p.payload.sync_id || '';

  const titulos = { fechas: 'Eliminar por rango de fechas', ciclo: 'Eliminar ciclo de sync', todo: '⚠ Eliminar TODA la data operacional' };
  document.getElementById('modal-confirm-titulo').textContent = titulos[modo] || 'Confirmar';

  const tmp = document.createElement('table');
  tmp.className = 'preview-table';
  renderTabla(p.data, null);
  const filas = [
    ['Solicitudes', p.data.solicitudes],
    ['Respuestas', p.data.respuestas],
    ['No reportadas', p.data.no_reportadas],
    ['Sugerencias', p.data.sugerencias],
    ['TOTAL', p.data.total],
  ];
  document.getElementById('modal-preview-contenido').innerHTML =
    '<table class="preview-table"><tr><th>Tabla</th><th>Registros</th></tr>' +
    filas.map((r, i) => `<tr${i===filas.length-1?' style="font-weight:700;color:var(--rojo);"':''}>
      <td>${r[0]}</td><td>${r[1]}</td></tr>`).join('') + '</table>';

  document.getElementById('input-confirmar').value = '';
  document.getElementById('btn-ejecutar').disabled = true;
  document.getElementById('modal-confirm').style.display = 'flex';
  document.getElementById('input-confirmar').focus();
}

function cerrarModal() {
  document.getElementById('modal-confirm').style.display = 'none';
}

function checkConfirmar() {
  const val = document.getElementById('input-confirmar').value;
  document.getElementById('btn-ejecutar').disabled = (val !== 'CONFIRMAR');
}
</script>
{% endblock %}
```

- [ ] **Step 3: Verificar**

Iniciar app como `mz13` → ir a `/admin/limpiar`.
- Las 3 secciones se despliegan con click en el header.
- Sección fechas: ingresar rango → "Ver cuántos registros" → muestra tabla con conteos reales.
- Modal: aparece al click en "Proceder a eliminar", botón "Ejecutar" deshabilitado hasta escribir `CONFIRMAR`.
- Escribir cualquier otro texto → botón sigue deshabilitado.
- Escribir `CONFIRMAR` → botón se habilita → submit → flash con resumen, registros en log_actividad.
- Como `admin` normal: ir a `/admin/limpiar` → redirige con flash de error.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/admin/limpiar.html
git commit -m "Superadmin: limpiar data masiva — por fechas, por ciclo o todo"
```

---

## Task 5: Configurar motivos

**Files:**
- Modify: `app.py` (3 rutas nuevas)
- Create: `templates/admin/motivos.html`

**Interfaces:**
- Consumes: `superadmin_required` (Task 1), `get_db()`, `_log_actividad`
- Produces: rutas `admin_motivos()`, `admin_motivo_editar(motivo_id)`, `admin_motivo_toggle(motivo_id)`

- [ ] **Step 1: Añadir rutas en `app.py`**

Insertar después de `admin_limpiar_preview`:

```python
@app.route('/admin/motivos', methods=['GET', 'POST'])
@superadmin_required
def admin_motivos():
    conn = get_db()
    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip().upper()[:10]
        descripcion = request.form.get('descripcion', '').strip()[:200]
        orden = request.form.get('orden', type=int) or 99

        errores = []
        if not codigo:
            errores.append('El código es obligatorio.')
        if not descripcion:
            errores.append('La descripción es obligatoria.')
        if not errores:
            dup = conn.execute(
                "SELECT id FROM catalogo_motivos WHERE codigo = ?", (codigo,)
            ).fetchone()
            if dup:
                errores.append(f'Ya existe un motivo con código "{codigo}".')
        if errores:
            for e in errores:
                flash(e, 'error')
        else:
            conn.execute(
                "INSERT INTO catalogo_motivos (codigo, descripcion, activo, orden) VALUES (?, ?, 1, ?)",
                (codigo, descripcion, orden)
            )
            _log_actividad(conn, current_user.id, 'motivo_crear',
                           f'Motivo creado: {codigo} — {descripcion}')
            conn.commit()
            flash(f'Motivo "{codigo}" creado.', 'success')
        conn.close()
        return redirect(url_for('admin_motivos'))

    motivos = conn.execute(
        "SELECT * FROM catalogo_motivos ORDER BY orden ASC, id ASC"
    ).fetchall()
    conn.close()
    return render_template('admin/motivos.html', motivos=motivos)


@app.route('/admin/motivos/<int:motivo_id>/editar', methods=['POST'])
@superadmin_required
def admin_motivo_editar(motivo_id):
    data = request.get_json(force=True) or {}
    codigo = (data.get('codigo') or '').strip().upper()[:10]
    descripcion = (data.get('descripcion') or '').strip()[:200]
    orden = data.get('orden')
    try:
        orden = int(orden)
    except (TypeError, ValueError):
        orden = 99

    if not codigo or not descripcion:
        return jsonify({'success': False, 'error': 'Código y descripción son obligatorios.'}), 400

    conn = get_db()
    try:
        dup = conn.execute(
            "SELECT id FROM catalogo_motivos WHERE codigo = ? AND id != ?", (codigo, motivo_id)
        ).fetchone()
        if dup:
            return jsonify({'success': False, 'error': f'El código "{codigo}" ya existe en otro motivo.'}), 400
        conn.execute(
            "UPDATE catalogo_motivos SET codigo = ?, descripcion = ?, orden = ? WHERE id = ?",
            (codigo, descripcion, orden, motivo_id)
        )
        _log_actividad(conn, current_user.id, 'motivo_editar',
                       f'Motivo id={motivo_id} actualizado: {codigo} — {descripcion}')
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True})


@app.route('/admin/motivos/<int:motivo_id>/toggle', methods=['POST'])
@superadmin_required
def admin_motivo_toggle(motivo_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT activo, codigo FROM catalogo_motivos WHERE id = ?", (motivo_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Motivo no encontrado.'}), 404
        nuevo = 0 if row['activo'] else 1
        conn.execute(
            "UPDATE catalogo_motivos SET activo = ? WHERE id = ?", (nuevo, motivo_id)
        )
        verb = 'activado' if nuevo else 'desactivado'
        _log_actividad(conn, current_user.id, 'motivo_toggle',
                       f'Motivo {row["codigo"]} (id={motivo_id}) {verb}')
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'activo': nuevo})
```

- [ ] **Step 2: Crear `templates/admin/motivos.html`**

```html
{% extends "base.html" %}
{% block title %}Catálogo de Motivos — Superadmin{% endblock %}

{% block styles %}
<style>
  .motivos-page { max-width: 860px; margin: 0 auto; padding: 28px 28px 60px; }
  .page-hdr { margin-bottom: 28px; }
  .page-hdr h1 { font-size: 22px; font-weight: 700; color: var(--azul); letter-spacing: -0.3px; }
  .page-hdr p  { font-size: 13px; color: var(--gris); margin-top: 3px; }

  .content-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 8px rgba(0,45,110,0.08); overflow: hidden; margin-bottom: 24px; }
  .card-hdr { padding: 16px 22px; border-bottom: 1px solid var(--borde); display: flex; align-items: center; gap: 8px; }
  .card-hdr h2 { font-size: 14px; font-weight: 700; color: var(--azul); display: flex; align-items: center; gap: 7px; }
  .card-hdr h2 svg { width: 15px; height: 15px; stroke: var(--cielo); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .count-badge { margin-left: auto; font-size: 12px; color: var(--gris); background: #f3f4f6; border: 1px solid var(--borde); padding: 2px 9px; border-radius: 12px; }

  table.mot-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  table.mot-table thead tr { background: #f8f9fb; border-bottom: 2px solid var(--borde); }
  table.mot-table th { padding: 10px 14px; text-align: left; font-size: 11px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; }
  table.mot-table td { padding: 10px 14px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
  table.mot-table tbody tr:last-child td { border-bottom: none; }
  table.mot-table tbody tr:hover { background: #f8fafc; }
  table.mot-table tbody tr.inactivo { background: #f9fafb; color: #9ca3af; }

  .badge-activo-mot { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11.5px; font-weight: 700; }
  .badge-si  { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
  .badge-no  { background: #f3f4f6; color: #6b7280; border: 1px solid #d1d5db; }

  .td-codigo { font-family: 'Courier New', monospace; font-weight: 700; font-size: 12.5px; color: var(--azul); }

  .btn-sm { padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1.5px solid; white-space: nowrap; transition: background 0.15s, color 0.15s; background: transparent; }
  .btn-edit  { color: var(--cielo); border-color: var(--cielo); }
  .btn-edit:hover  { background: var(--cielo); color: #fff; }
  .btn-deact { color: var(--rojo); border-color: var(--rojo); }
  .btn-deact:hover { background: var(--rojo); color: #fff; }
  .btn-act   { color: var(--verde); border-color: var(--verde); }
  .btn-act:hover   { background: var(--verde); color: #fff; }

  /* Fila en modo edición */
  .edit-input { padding: 5px 8px; border: 1.5px solid var(--cielo); border-radius: 6px; font-size: 13px; font-family: inherit; width: 100%; outline: none; }
  .edit-input-sm { width: 60px; }
  .btn-save   { padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer; border: none; background: var(--verde); color: #fff; }
  .btn-save:hover { background: #5e8a28; }
  .btn-cancel-edit { padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1.5px solid #d1d5db; background: #f3f4f6; color: var(--gris); }

  /* Formulario agregar */
  .add-form { padding: 18px 22px; }
  .add-row { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
  .add-group { display: flex; flex-direction: column; gap: 5px; }
  .add-group label { font-size: 11px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.3px; }
  .add-group input { padding: 8px 10px; border: 1.5px solid #d1d5db; border-radius: 7px; font-size: 13px; font-family: inherit; outline: none; transition: border-color 0.15s; background: #fafafa; }
  .add-group input:focus { border-color: var(--verde); background: #fff; }
  .add-group.wide { flex: 1; min-width: 200px; }
  .add-group.sm input { width: 80px; }
  .btn-agregar { padding: 8px 18px; background: var(--azul); color: #fff; border: none; border-radius: 7px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; transition: background 0.15s; }
  .btn-agregar:hover { background: #001f4e; }

  @media (max-width: 768px) { .motivos-page { padding: 14px 12px 40px; } .add-row { flex-direction: column; } }
</style>
{% endblock %}

{% block content %}
<div class="motivos-page">

  <div class="page-hdr">
    <h1>Catálogo de Motivos</h1>
    <p>Gestiona los motivos disponibles para el CIO al registrar no-ejecuciones</p>
  </div>

  <div class="content-card">
    <div class="card-hdr">
      <h2>
        <svg viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
        Motivos registrados
      </h2>
      <span class="count-badge">{{ motivos|length }}</span>
    </div>

    <div style="overflow-x:auto;">
      <table class="mot-table">
        <thead>
          <tr>
            <th>Orden</th><th>Código</th><th>Descripción</th><th>Estado</th><th></th>
          </tr>
        </thead>
        <tbody id="mot-tbody">
          {% for m in motivos %}
          <tr id="row-{{ m.id }}" class="{{ '' if m.activo else 'inactivo' }}">
            <td id="cell-orden-{{ m.id }}">{{ m.orden }}</td>
            <td id="cell-codigo-{{ m.id }}" class="td-codigo">{{ m.codigo }}</td>
            <td id="cell-desc-{{ m.id }}">{{ m.descripcion }}</td>
            <td>
              <span class="badge-activo-mot {{ 'badge-si' if m.activo else 'badge-no' }}"
                    id="badge-{{ m.id }}">{{ 'Activo' if m.activo else 'Inactivo' }}</span>
            </td>
            <td style="white-space:nowrap;display:flex;gap:6px;align-items:center;">
              <button class="btn-sm btn-edit" id="btn-edit-{{ m.id }}"
                      onclick="iniciarEdicion({{ m.id }}, '{{ m.codigo }}', {{ m.orden }}, `{{ m.descripcion | replace('`', '\\`') | replace("'", "\\'") }}`)">
                Editar
              </button>
              <button class="btn-sm {{ 'btn-deact' if m.activo else 'btn-act' }}"
                      id="btn-toggle-{{ m.id }}"
                      onclick="toggleMotivo({{ m.id }})">
                {{ 'Desactivar' if m.activo else 'Activar' }}
              </button>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="padding:30px;text-align:center;color:var(--gris);">Sin motivos registrados.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Formulario agregar -->
    <div class="add-form" style="border-top:1px solid var(--borde);">
      <form method="POST" action="{{ url_for('admin_motivos') }}">
        <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
        <div class="add-row">
          <div class="add-group sm">
            <label>Código</label>
            <input type="text" name="codigo" placeholder="M05" maxlength="10" required style="width:80px;">
          </div>
          <div class="add-group wide">
            <label>Descripción</label>
            <input type="text" name="descripcion" placeholder="Descripción del motivo" maxlength="200" required>
          </div>
          <div class="add-group sm">
            <label>Orden</label>
            <input type="number" name="orden" value="{{ (motivos|length) + 1 }}" min="1" style="width:70px;">
          </div>
          <button type="submit" class="btn-agregar">Agregar motivo</button>
        </div>
      </form>
    </div>
  </div>

</div>

<script>
const _csrfToken = '{{ csrf_token() }}';

function iniciarEdicion(id, codigo, orden, descripcion) {
  const row = document.getElementById('row-' + id);

  const cOrd  = document.getElementById('cell-orden-' + id);
  const cCod  = document.getElementById('cell-codigo-' + id);
  const cDesc = document.getElementById('cell-desc-' + id);

  const origOrd  = cOrd.textContent.trim();
  const origCod  = cCod.textContent.trim();
  const origDesc = cDesc.textContent.trim();

  cOrd.innerHTML  = `<input class="edit-input edit-input-sm" id="ei-orden-${id}" type="number" value="${orden}" min="1" style="width:60px;">`;
  cCod.innerHTML  = `<input class="edit-input" id="ei-codigo-${id}" type="text" value="${codigo}" maxlength="10" style="width:80px;">`;
  cDesc.innerHTML = `<input class="edit-input" id="ei-desc-${id}" type="text" value="${descripcion}" maxlength="200">`;

  const tdAcc = row.querySelector('td:last-child');
  tdAcc.innerHTML = `
    <button class="btn-save" onclick="guardarEdicion(${id})">Guardar</button>
    <button class="btn-cancel-edit" onclick="cancelarEdicion(${id}, '${origCod}', ${origOrd}, \`${origDesc.replace(/`/g, '\\`')}\`)">Cancelar</button>
  `;
}

function cancelarEdicion(id, codigo, orden, descripcion) {
  document.getElementById('cell-orden-' + id).textContent = orden;
  document.getElementById('cell-codigo-' + id).textContent = codigo;
  document.getElementById('cell-desc-' + id).textContent = descripcion;
  const activo = document.getElementById('badge-' + id).textContent.trim() === 'Activo';
  document.getElementById('row-' + id).querySelector('td:last-child').innerHTML = `
    <button class="btn-sm btn-edit" id="btn-edit-${id}"
            onclick="iniciarEdicion(${id}, '${codigo}', ${orden}, \`${descripcion.replace(/`/g, '\\`')}\`)">Editar</button>
    <button class="btn-sm ${activo ? 'btn-deact' : 'btn-act'}" id="btn-toggle-${id}"
            onclick="toggleMotivo(${id})">${activo ? 'Desactivar' : 'Activar'}</button>
  `;
}

async function guardarEdicion(id) {
  const codigo     = document.getElementById('ei-codigo-' + id).value.trim();
  const descripcion = document.getElementById('ei-desc-' + id).value.trim();
  const orden      = parseInt(document.getElementById('ei-orden-' + id).value) || 99;

  if (!codigo || !descripcion) { alert('Código y descripción son obligatorios.'); return; }

  const res = await fetch(`/admin/motivos/${id}/editar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrfToken },
    body: JSON.stringify({ codigo, descripcion, orden }),
  });
  const data = await res.json();
  if (!data.success) { alert(data.error || 'Error al guardar.'); return; }

  document.getElementById('cell-orden-' + id).textContent = orden;
  document.getElementById('cell-codigo-' + id).textContent = codigo;
  document.getElementById('cell-desc-' + id).textContent = descripcion;
  const activo = document.getElementById('badge-' + id).textContent.trim() === 'Activo';
  document.getElementById('row-' + id).querySelector('td:last-child').innerHTML = `
    <button class="btn-sm btn-edit" id="btn-edit-${id}"
            onclick="iniciarEdicion(${id}, '${codigo}', ${orden}, \`${descripcion.replace(/`/g, '\\`')}\`)">Editar</button>
    <button class="btn-sm ${activo ? 'btn-deact' : 'btn-act'}" id="btn-toggle-${id}"
            onclick="toggleMotivo(${id})">${activo ? 'Desactivar' : 'Activar'}</button>
  `;
}

async function toggleMotivo(id) {
  const res = await fetch(`/admin/motivos/${id}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrfToken },
  });
  const data = await res.json();
  if (!data.success) { alert(data.error || 'Error.'); return; }
  const activo = data.activo === 1;
  const badge = document.getElementById('badge-' + id);
  badge.textContent = activo ? 'Activo' : 'Inactivo';
  badge.className = 'badge-activo-mot ' + (activo ? 'badge-si' : 'badge-no');
  const row = document.getElementById('row-' + id);
  row.className = activo ? '' : 'inactivo';
  const btn = document.getElementById('btn-toggle-' + id);
  btn.textContent = activo ? 'Desactivar' : 'Activar';
  btn.className = 'btn-sm ' + (activo ? 'btn-deact' : 'btn-act');
}
</script>
{% endblock %}
```

- [ ] **Step 3: Verificar**

Como `mz13` → ir a `/admin/motivos`:
- Tabla muestra los motivos del catálogo inicial (M01–M04).
- Click "Desactivar" en M01 → badge cambia a "Inactivo", fila se pone gris, botón cambia a "Activar" sin recargar.
- Click "Activar" → vuelve al estado anterior.
- Click "Editar" → fila muestra inputs con valores actuales.
- Modificar descripción → Guardar → fila vuelve al modo normal con nuevo valor.
- Agregar motivo nuevo → formulario al pie → aparece en la tabla.
- Como `admin` normal: acceder a `/admin/motivos` → redirige con flash.
- Como CIO: el dropdown de motivos en el formulario de respuesta NO debe mostrar motivos desactivados.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/admin/motivos.html
git commit -m "Superadmin: gestión CRUD de catálogo de motivos con edición inline"
```

---

## Task 6: Panel estadísticas del sistema

**Files:**
- Modify: `app.py` (ruta `GET /admin/sistema`)
- Create: `templates/admin/sistema.html`

**Interfaces:**
- Consumes: `superadmin_required` (Task 1), `get_db()`, `config.DATABASE_PATH`, `os.path.getsize`
- Produces: ruta `admin_sistema()`

- [ ] **Step 1: Añadir ruta en `app.py`**

Insertar después de `admin_motivo_toggle`:

```python
@app.route('/admin/sistema')
@superadmin_required
def admin_sistema():
    conn = get_db()
    sync_id = _current_sync_id(conn)

    total_usuarios_activos = conn.execute(
        "SELECT COUNT(*) AS c FROM usuarios WHERE activo = 1"
    ).fetchone()['c']

    total_equipos = 0
    if sync_id:
        total_equipos = conn.execute(
            "SELECT COUNT(*) AS c FROM equipos WHERE sync_id = ?", (sync_id,)
        ).fetchone()['c']

    total_filtros = conn.execute(
        "SELECT COUNT(*) AS c FROM filtros_equipo"
    ).fetchone()['c']

    ultimo_sync_row = conn.execute(
        """SELECT l.timestamp, u.nombre_completo
           FROM log_actividad l
           LEFT JOIN usuarios u ON u.id = l.usuario_id
           WHERE l.accion_tipo = 'sync'
           ORDER BY l.timestamp DESC LIMIT 1"""
    ).fetchone()

    total_solicitudes = conn.execute(
        "SELECT COUNT(*) AS c FROM solicitudes"
    ).fetchone()['c']

    total_respuestas = conn.execute(
        "SELECT COUNT(*) AS c FROM respuestas"
    ).fetchone()['c']

    usuarios = conn.execute(
        "SELECT * FROM usuarios ORDER BY created_at DESC"
    ).fetchall()

    conn.close()

    try:
        peso_mb = round(os.path.getsize(config.DATABASE_PATH) / (1024 * 1024), 2)
    except OSError:
        peso_mb = 0.0

    ultimo_sync_ts = _format_fecha_actualizacion(ultimo_sync_row['timestamp']) if ultimo_sync_row else None
    ultimo_sync_usuario = ultimo_sync_row['nombre_completo'] if ultimo_sync_row else None

    return render_template('admin/sistema.html',
        total_usuarios_activos=total_usuarios_activos,
        total_equipos=total_equipos,
        total_filtros=total_filtros,
        peso_mb=peso_mb,
        ultimo_sync_ts=ultimo_sync_ts,
        ultimo_sync_usuario=ultimo_sync_usuario,
        total_solicitudes=total_solicitudes,
        total_respuestas=total_respuestas,
        usuarios=usuarios,
        current_sync_id=sync_id,
    )
```

- [ ] **Step 2: Crear `templates/admin/sistema.html`**

```html
{% extends "base.html" %}
{% block title %}Panel del Sistema — Superadmin{% endblock %}

{% block styles %}
<style>
  .sistema-page { max-width: 1100px; margin: 0 auto; padding: 28px 28px 60px; }
  .page-hdr { margin-bottom: 28px; }
  .page-hdr h1 { font-size: 22px; font-weight: 700; color: var(--azul); letter-spacing: -0.3px; }
  .page-hdr p  { font-size: 13px; color: var(--gris); margin-top: 3px; }

  /* KPI grids */
  .kpi-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
  .kpi-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 28px; }
  @media (max-width: 900px) { .kpi-grid-4 { grid-template-columns: repeat(2, 1fr); } .kpi-grid-3 { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 480px)  { .kpi-grid-4, .kpi-grid-3 { grid-template-columns: 1fr; } }

  .kpi-card {
    background: #fff; border-radius: 12px; padding: 20px 22px;
    box-shadow: 0 1px 8px rgba(0,45,110,0.08); border-left: 4px solid transparent;
  }
  .kpi-card.blue  { border-color: var(--azul); }
  .kpi-card.green { border-color: var(--verde); }
  .kpi-card.sky   { border-color: var(--cielo); }
  .kpi-card.amber { border-color: var(--ambar); }
  .kpi-card.gray  { border-color: #9ca3af; }

  .kpi-value { font-size: 32px; font-weight: 700; letter-spacing: -1.5px; line-height: 1; margin-bottom: 5px; }
  .kpi-card.blue  .kpi-value { color: var(--azul); }
  .kpi-card.green .kpi-value { color: var(--verde); }
  .kpi-card.sky   .kpi-value { color: var(--cielo); }
  .kpi-card.amber .kpi-value { color: var(--ambar); }
  .kpi-card.gray  .kpi-value { color: #6b7280; }

  .kpi-label { font-size: 11.5px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-sub   { font-size: 12px; color: #9ca3af; margin-top: 3px; }

  /* Tabla usuarios */
  .content-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 8px rgba(0,45,110,0.08); overflow: hidden; }
  .card-hdr { padding: 16px 22px; border-bottom: 1px solid var(--borde); display: flex; align-items: center; gap: 8px; }
  .card-hdr h2 { font-size: 14px; font-weight: 700; color: var(--azul); display: flex; align-items: center; gap: 7px; }
  .card-hdr h2 svg { width: 15px; height: 15px; stroke: var(--cielo); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .count-badge { margin-left: auto; font-size: 12px; color: var(--gris); background: #f3f4f6; border: 1px solid var(--borde); padding: 2px 9px; border-radius: 12px; }

  table.sis-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  table.sis-table thead tr { background: #f8f9fb; border-bottom: 2px solid var(--borde); }
  table.sis-table th { padding: 10px 16px; text-align: left; font-size: 11px; font-weight: 700; color: var(--gris); text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; }
  table.sis-table td { padding: 11px 16px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
  table.sis-table tbody tr:last-child td { border-bottom: none; }
  table.sis-table tbody tr:hover { background: #f8fafc; }

  .badge-rol { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }
  .badge-superadmin { background: #fdf4ff; color: #6b21a8; border: 1px solid #e9d5ff; }
  .badge-admin      { background: #eff6ff; color: var(--azul); border: 1px solid #bfdbfe; }
  .badge-cio        { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
  .badge-tecnico    { background: #fff7ed; color: #9a3412; border: 1px solid #fed7aa; }
  .badge-activo-s { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11.5px; font-weight: 600; }
  .badge-si { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
  .badge-no { background: #fff7f7; color: #991b1b; border: 1px solid #fca5a5; }

  .td-ts { color: var(--gris); font-size: 12px; white-space: nowrap; }
  .td-username { font-family: 'Courier New', monospace; font-weight: 600; font-size: 13px; }

  @media (max-width: 768px) { .sistema-page { padding: 14px 12px 40px; } }
</style>
{% endblock %}

{% block content %}
<div class="sistema-page">

  <div class="page-hdr">
    <h1>Panel del Sistema</h1>
    <p>Estadísticas globales y estado de la base de datos</p>
  </div>

  <!-- KPIs principales -->
  <div class="kpi-grid-4">
    <div class="kpi-card blue">
      <div class="kpi-value">{{ total_usuarios_activos }}</div>
      <div class="kpi-label">Usuarios activos</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-value">{{ total_equipos }}</div>
      <div class="kpi-label">Equipos cargados</div>
      {% if current_sync_id %}<div class="kpi-sub">Ciclo #{{ current_sync_id }}</div>{% endif %}
    </div>
    <div class="kpi-card sky">
      <div class="kpi-value">{{ total_filtros }}</div>
      <div class="kpi-label">Filtros en maestro</div>
    </div>
    <div class="kpi-card amber">
      <div class="kpi-value">{{ peso_mb }}</div>
      <div class="kpi-label">Peso BD (MB)</div>
      <div class="kpi-sub">app.db</div>
    </div>
  </div>

  <!-- KPIs secundarios -->
  <div class="kpi-grid-3">
    <div class="kpi-card gray">
      <div class="kpi-label" style="margin-bottom:6px;">Último sync</div>
      {% if ultimo_sync_ts %}
        <div style="font-size:14px;font-weight:700;color:var(--texto);">{{ ultimo_sync_ts }}</div>
        {% if ultimo_sync_usuario %}<div class="kpi-sub">por {{ ultimo_sync_usuario }}</div>{% endif %}
      {% else %}
        <div style="font-size:14px;color:var(--gris);">Sin sincronizaciones</div>
      {% endif %}
    </div>
    <div class="kpi-card gray">
      <div class="kpi-value">{{ total_solicitudes }}</div>
      <div class="kpi-label">Solicitudes históricas</div>
      <div class="kpi-sub">Todos los ciclos</div>
    </div>
    <div class="kpi-card gray">
      <div class="kpi-value">{{ total_respuestas }}</div>
      <div class="kpi-label">Respuestas históricas</div>
      <div class="kpi-sub">Todos los ciclos</div>
    </div>
  </div>

  <!-- Tabla de usuarios -->
  <div class="content-card">
    <div class="card-hdr">
      <h2>
        <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        Todos los usuarios
      </h2>
      <span class="count-badge">{{ usuarios|length }}</span>
    </div>
    <div style="overflow-x:auto;">
      <table class="sis-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Nombre Completo</th>
            <th>Rol</th>
            <th>Activo</th>
            <th>Creado</th>
          </tr>
        </thead>
        <tbody>
          {% for u in usuarios %}
          <tr>
            <td class="td-username">{{ u.username }}</td>
            <td>{{ u.nombre_completo }}</td>
            <td>
              {% if u.rol == 'superadmin' %}
                <span class="badge-rol badge-superadmin">SuperAdmin</span>
              {% elif u.rol == 'admin' %}
                <span class="badge-rol badge-admin">Admin</span>
              {% elif u.rol == 'tecnico' %}
                <span class="badge-rol badge-tecnico">Técnico</span>
              {% else %}
                <span class="badge-rol badge-cio">CIO</span>
              {% endif %}
            </td>
            <td>
              <span class="badge-activo-s {{ 'badge-si' if u.activo else 'badge-no' }}">
                {{ 'Sí' if u.activo else 'No' }}
              </span>
            </td>
            <td class="td-ts">{{ u.created_at[:10] if u.created_at else '—' }}</td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="padding:30px;text-align:center;color:var(--gris);">Sin usuarios.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 3: Verificar**

Como `mz13` → ir a `/admin/sistema`:
- Los 4 KPI superiores muestran valores reales de la BD.
- El peso de la BD muestra un número > 0 (ej: 0.08 MB).
- Los 3 KPI secundarios muestran fecha del último sync y totales históricos.
- La tabla de usuarios lista todos los usuarios (incluyendo superadmin) con badges de colores.
- Como `admin` normal: `/admin/sistema` redirige con flash de error.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/admin/sistema.html
git commit -m "Superadmin: panel estadísticas del sistema — KPIs y tabla de usuarios"
```

---

## Self-Review

**Spec coverage:**
- ✅ Resetear contraseña — Task 2 (ruta + modal)
- ✅ Backup BD — Task 3 (ruta + botón dashboard)
- ✅ Limpiar data masiva — Task 4 (3 modos + preview AJAX + modal CONFIRMAR)
- ✅ Configurar motivos — Task 5 (CRUD + toggle + edición inline)
- ✅ Panel estadísticas — Task 6 (KPIs + tabla usuarios)
- ✅ Decorator `superadmin_required` — Task 1
- ✅ Links navbar — Task 1
- ✅ `historial_cambios_filtros` excluido del limpiar — correcto
- ✅ `cio_motivos` ya filtra `WHERE activo = 1` — sin cambios necesarios
- ✅ CSRF en todos los POST — confirmado en cada ruta y template
- ✅ `log_actividad` en todas las operaciones — confirmado

**Placeholders:** Ninguno encontrado.

**Consistencia de nombres:**
- `superadmin_required` definido en Task 1, usado en Tasks 2-6. ✅
- `admin_limpiar_preview` referenciado en el template de Task 4 via `url_for("admin_limpiar_preview")`. ✅
- `admin_motivos`, `admin_motivo_editar`, `admin_motivo_toggle` — nombres consistentes. ✅
- `admin_sistema` — nombre consistente en ruta y navbar. ✅
