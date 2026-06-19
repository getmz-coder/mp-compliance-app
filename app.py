import os
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
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
        'cio': 'cio_dashboard',
    }
    return redirect(url_for(destinos.get(current_user.rol, 'login')))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html')


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
    return render_template('cio/dashboard.html')


# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('exports', exist_ok=True)
    app.run(debug=True)
