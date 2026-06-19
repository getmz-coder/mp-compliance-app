import os
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import config
from models import get_db
import sync_data

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para acceder.'
login_manager.login_message_category = 'error'


class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.nombre_completo = row['nombre_completo']
        self.rol = row['rol']
        self.activo = row['activo']

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE id = ? AND activo = 1", (user_id,)
    ).fetchone()
    conn.close()
    return User(row) if row else None


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.rol != 'admin':
            flash('Acceso restringido a administradores.', 'error')
            return redirect(url_for('dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated


def cio_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.rol != 'cio':
            flash('Acceso restringido a CIO.', 'error')
            return redirect(url_for('dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated


def _log_actividad(conn, usuario_id, accion_tipo, detalle):
    conn.execute(
        """INSERT INTO log_actividad (usuario_id, accion_tipo, detalle, ip_address, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (usuario_id, accion_tipo, detalle, request.remote_addr, datetime.now().isoformat())
    )


def _current_sync_id(conn):
    row = conn.execute("SELECT MAX(sync_id) AS sync_id FROM equipos").fetchone()
    return row['sync_id'] if row and row['sync_id'] else None


_ALLOWED_EXCEL = {'xlsx', 'xls'}

def _allowed_excel(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in _ALLOWED_EXCEL


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_redirect'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM usuarios WHERE username = ? AND activo = 1", (username,)
        ).fetchone()

        if row and check_password_hash(row['password_hash'], password):
            user = User(row)
            login_user(user, remember=remember)
            _log_actividad(conn, user.id, 'login', f'Login exitoso desde {request.remote_addr}')
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard_redirect'))

        _log_actividad(conn, row['id'] if row else None, 'login',
                       f'Intento fallido: usuario={username}')
        conn.commit()
        conn.close()
        error = 'Usuario o contraseña incorrectos.'

    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
    conn = get_db()
    _log_actividad(conn, current_user.id, 'login', 'Cierre de sesión')
    conn.commit()
    conn.close()
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard_redirect():
    destinos = {
        'admin': 'admin_dashboard',
        'cio':   'cio_dashboard',
    }
    return redirect(url_for(destinos.get(current_user.rol, 'login')))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    sync_id = _current_sync_id(conn)

    total_equipos = 0
    solicitados   = 0
    respondidos   = 0

    if sync_id:
        total_equipos = conn.execute(
            "SELECT COUNT(*) AS c FROM equipos WHERE sync_id = ?", (sync_id,)
        ).fetchone()['c']

        solicitados = conn.execute(
            "SELECT COUNT(*) AS c FROM solicitudes WHERE sync_id = ?", (sync_id,)
        ).fetchone()['c']

        respondidos = conn.execute(
            """SELECT COUNT(*) AS c FROM respuestas r
               JOIN solicitudes s ON s.id = r.solicitud_id
               WHERE s.sync_id = ?""",
            (sync_id,)
        ).fetchone()['c']

    pendientes = max(0, solicitados - respondidos)

    ultimas_sync = conn.execute(
        """SELECT l.timestamp, l.detalle, u.nombre_completo
           FROM log_actividad l
           LEFT JOIN usuarios u ON u.id = l.usuario_id
           WHERE l.accion_tipo = 'sync'
           ORDER BY l.timestamp DESC
           LIMIT 10"""
    ).fetchall()

    conn.close()

    return render_template('admin/dashboard.html',
        total_equipos=total_equipos,
        solicitados=solicitados,
        respondidos=respondidos,
        pendientes=pendientes,
        ultimas_sync=ultimas_sync,
        current_sync_id=sync_id,
    )


@app.route('/admin/sync', methods=['GET', 'POST'])
@admin_required
def admin_sync():
    if request.method == 'GET':
        return render_template('admin/sync.html')

    file_prog = request.files.get('file_programacion')
    file_filt = request.files.get('file_filtros')

    has_prog = file_prog and file_prog.filename
    has_filt = file_filt and file_filt.filename

    if not has_prog and not has_filt:
        flash('Debes subir al menos un archivo.', 'error')
        return render_template('admin/sync.html')

    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()

    if has_prog:
        if not _allowed_excel(file_prog.filename):
            flash('Programación MP: formato no válido. Solo se aceptan .xlsx o .xls', 'error')
        else:
            save_path = os.path.join(config.UPLOAD_FOLDER, 'programacion_mp.xlsx')
            file_prog.save(save_path)
            try:
                res = sync_data.sync_programacion(save_path)
                msg = (f'Programación MP sincronizada: {res["nuevos"]} nuevos, '
                       f'{res["actualizados"]} actualizados — {res["total"]} equipos totales '
                       f'(ciclo {res["sync_id"]})')
                flash(msg, 'success')
                _log_actividad(conn, current_user.id, 'sync', msg)
            except Exception as exc:
                flash(f'Error en programación MP: {exc}', 'error')

    if has_filt:
        if not _allowed_excel(file_filt.filename):
            flash('Maestro Filtración: formato no válido. Solo se aceptan .xlsx o .xls', 'error')
        else:
            save_path = os.path.join(config.UPLOAD_FOLDER, 'maestro_filtracion.xlsx')
            file_filt.save(save_path)
            try:
                res = sync_data.sync_filtros(save_path)
                msg = (f'Maestro Filtración sincronizado: {res["total_registros"]} registros, '
                       f'{res["equipos_unicos"]} equipos únicos')
                flash(msg, 'success')
                _log_actividad(conn, current_user.id, 'sync', msg)
            except Exception as exc:
                flash(f'Error en maestro filtración: {exc}', 'error')

    conn.commit()
    conn.close()
    return redirect(url_for('admin_sync'))


# ---------------------------------------------------------------------------
# CIO
# ---------------------------------------------------------------------------

@app.route('/cio')
@cio_required
def cio_dashboard():
    conn = get_db()
    sync_id = _current_sync_id(conn)

    equipos = []
    familias = []
    estados  = []

    if sync_id:
        equipos = conn.execute(
            """SELECT * FROM equipos
               WHERE sync_id = ?
               ORDER BY ind_desviacion DESC""",
            (sync_id,)
        ).fetchall()

        familias = [r['familia'] for r in conn.execute(
            """SELECT DISTINCT familia FROM equipos
               WHERE sync_id = ? AND familia IS NOT NULL
               ORDER BY familia""",
            (sync_id,)
        ).fetchall()]

        estados = [r['estado_mp'] for r in conn.execute(
            """SELECT DISTINCT estado_mp FROM equipos
               WHERE sync_id = ? AND estado_mp IS NOT NULL
               ORDER BY estado_mp""",
            (sync_id,)
        ).fetchall()]

    vencidos  = sum(1 for e in equipos if e['estado_mp'] and 'vencido' in e['estado_mp'].lower())
    proximos  = sum(1 for e in equipos if e['estado_mp'] and ('próximo' in e['estado_mp'].lower() or 'proximo' in e['estado_mp'].lower()))

    solicitudes_map = {}
    if sync_id:
        rows_sol = conn.execute(
            """SELECT s.id, s.equipo_id, s.estado, s.solicitado_por,
                      r.accion, m.descripcion AS motivo_desc, r.comentario_libre
               FROM solicitudes s
               LEFT JOIN respuestas r ON r.solicitud_id = s.id
               LEFT JOIN catalogo_motivos m ON m.id = r.motivo_id
               WHERE s.sync_id = ?""",
            (sync_id,)
        ).fetchall()
        for row in rows_sol:
            solicitudes_map[row['equipo_id']] = {
                'id':             row['id'],
                'estado':         row['estado'],
                'solicitado_por': row['solicitado_por'],
                'accion':         row['accion'],
                'motivo_desc':    row['motivo_desc'],
                'comentario_libre': row['comentario_libre'],
            }

    respondidos = sum(1 for s in solicitudes_map.values() if s['estado'] == 'respondido')

    conn.close()

    return render_template('cio/dashboard.html',
        equipos=equipos,
        familias=familias,
        estados=estados,
        total=len(equipos),
        vencidos=vencidos,
        proximos=proximos,
        ya_solicitados=len(solicitudes_map),
        respondidos=respondidos,
        solicitudes_map=solicitudes_map,
        current_sync_id=sync_id,
    )


@app.route('/cio/solicitar', methods=['POST'])
@cio_required
def cio_solicitar():
    equipo_ids = request.form.getlist('equipo_ids')
    if not equipo_ids:
        flash('No seleccionaste ningún equipo.', 'error')
        return redirect(url_for('cio_dashboard'))

    conn = get_db()
    sync_id = _current_sync_id(conn)
    ahora   = datetime.now().isoformat()
    registrados = 0

    for raw_id in equipo_ids:
        try:
            eid = int(raw_id)
        except ValueError:
            continue

        existing = conn.execute(
            "SELECT id FROM solicitudes WHERE equipo_id = ? AND sync_id = ?",
            (eid, sync_id)
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO solicitudes
                       (equipo_id, solicitado_por, fecha_solicitud, sync_id, estado)
                   VALUES (?, ?, ?, ?, 'pendiente')""",
                (eid, current_user.id, ahora, sync_id)
            )
            registrados += 1

    _log_actividad(conn, current_user.id, 'solicitud',
                   f'Solicitud de {registrados} equipo(s) (ciclo {sync_id})')
    conn.commit()
    conn.close()

    if registrados:
        flash(f'{registrados} equipo(s) solicitados exitosamente. '
              'Notifica a Operaciones para coordinar la entrega.', 'success')
    else:
        flash('Los equipos seleccionados ya estaban solicitados en este ciclo.', 'warning')

    return redirect(url_for('cio_dashboard'))


@app.route('/cio/motivos')
@cio_required
def cio_motivos():
    conn = get_db()
    motivos = conn.execute(
        "SELECT id, descripcion FROM catalogo_motivos WHERE activo = 1 ORDER BY orden"
    ).fetchall()
    conn.close()
    return jsonify([{'id': m['id'], 'descripcion': m['descripcion']} for m in motivos])


@app.route('/cio/responder', methods=['POST'])
@cio_required
def cio_responder():
    data = request.get_json(force=True) or {}
    solicitud_id  = data.get('solicitud_id')
    accion        = data.get('accion')
    motivo_id     = data.get('motivo_id')
    comentario    = (data.get('comentario_libre') or '').strip() or None

    if not solicitud_id or accion not in ('entregado', 'no_entregado'):
        return jsonify({'success': False, 'error': 'Datos inválidos.'}), 400

    if accion == 'no_entregado' and not motivo_id:
        return jsonify({'success': False, 'error': 'Motivo obligatorio para "No entregado".'}), 400

    conn = get_db()
    solicitud = conn.execute(
        "SELECT * FROM solicitudes WHERE id = ?", (solicitud_id,)
    ).fetchone()

    if not solicitud:
        conn.close()
        return jsonify({'success': False, 'error': 'Solicitud no encontrada.'}), 404

    if solicitud['solicitado_por'] != current_user.id:
        conn.close()
        return jsonify({'success': False, 'error': 'Sin permiso para esta solicitud.'}), 403

    if solicitud['estado'] == 'respondido':
        conn.close()
        return jsonify({'success': False, 'error': 'Solicitud ya respondida.'}), 409

    ahora = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO respuestas
               (solicitud_id, respondido_por, accion, motivo_id, comentario_libre, timestamp, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (solicitud_id, current_user.id, accion, motivo_id or None, comentario, ahora, request.remote_addr)
    )
    conn.execute("UPDATE solicitudes SET estado = 'respondido' WHERE id = ?", (solicitud_id,))

    motivo_desc = None
    if motivo_id:
        m = conn.execute(
            "SELECT descripcion FROM catalogo_motivos WHERE id = ?", (motivo_id,)
        ).fetchone()
        if m:
            motivo_desc = m['descripcion']

    _log_actividad(conn, current_user.id, 'respuesta',
                   f'Respuesta solicitud #{solicitud_id}: {accion}'
                   + (f' — {motivo_desc}' if motivo_desc else ''))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/cio/mis-solicitudes')
@cio_required
def cio_mis_solicitudes():
    conn = get_db()
    sync_id = _current_sync_id(conn)

    solicitudes = conn.execute(
        """SELECT s.id, s.fecha_solicitud, s.estado, e.vehiculo, e.familia,
                  e.rutina, e.estado_mp,
                  r.accion, r.timestamp AS resp_timestamp,
                  m.descripcion AS motivo, r.comentario_libre
           FROM solicitudes s
           JOIN equipos e ON e.id = s.equipo_id
           LEFT JOIN respuestas r ON r.solicitud_id = s.id
           LEFT JOIN catalogo_motivos m ON m.id = r.motivo_id
           WHERE s.solicitado_por = ?
           ORDER BY s.fecha_solicitud DESC
           LIMIT 100""",
        (current_user.id,)
    ).fetchall()

    conn.close()

    return render_template('cio/mis_solicitudes.html',
        solicitudes=solicitudes,
        current_sync_id=sync_id,
    )


# ---------------------------------------------------------------------------
# Equipo detalle (accesible por ambos roles)
# ---------------------------------------------------------------------------

@app.route('/equipo/<vehiculo>')
@login_required
def equipo_detalle(vehiculo):
    vehiculo = vehiculo.upper().strip()
    conn = get_db()
    sync_id = _current_sync_id(conn)

    rutinas = conn.execute(
        """SELECT * FROM equipos
           WHERE UPPER(vehiculo) = ? AND sync_id = ?
           ORDER BY ind_desviacion DESC""",
        (vehiculo, sync_id)
    ).fetchall() if sync_id else []

    filtros = conn.execute(
        """SELECT * FROM filtros_equipo
           WHERE UPPER(equipo) = ?
           ORDER BY tipo_filtro, nombre_articulo""",
        (vehiculo,)
    ).fetchall()

    historial = conn.execute(
        """SELECT s.fecha_solicitud, s.estado,
                  u.nombre_completo AS solicitado_por,
                  r.accion, r.timestamp AS resp_timestamp,
                  m.descripcion AS motivo, r.comentario_libre
           FROM solicitudes s
           JOIN equipos e ON e.id = s.equipo_id
           JOIN usuarios u ON u.id = s.solicitado_por
           LEFT JOIN respuestas r ON r.solicitud_id = s.id
           LEFT JOIN catalogo_motivos m ON m.id = r.motivo_id
           WHERE UPPER(e.vehiculo) = ?
           ORDER BY s.fecha_solicitud DESC
           LIMIT 20""",
        (vehiculo,)
    ).fetchall()

    conn.close()

    if not rutinas:
        flash(f'No se encontraron datos para el vehículo {vehiculo} en el ciclo actual.', 'warning')
        return redirect(url_for('dashboard_redirect'))

    return render_template('equipo_detalle.html',
        vehiculo=vehiculo,
        equipo=rutinas[0],
        rutinas=rutinas,
        filtros=filtros,
        historial=historial,
    )


# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('exports', exist_ok=True)
    app.run(debug=True)
