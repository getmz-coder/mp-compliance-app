"""
QA v3 — fixes finales.

Aplica cambios para:
  A. Persistir checks de no motorizados en BD (limpiar en corte diario)
  B. Renombrar 'Mis Solicitudes' -> 'Mis Respuestas' (menu + titulo)
  C. Categorizar ejec sin planeacion (positivo CIO) — nuevo estado 'sin_planeacion'
  D. Fix filtros dashboard admin (guard filBus en JS)

Archivos que modifica:
  - models.py                              (nueva tabla no_motor_checks)
  - sync_data.py                           (corte diario limpia checks + estado sin_planeacion)
  - app.py                                 (cio_no_motor persistente + toggle + admin_indicadores)
  - templates/base.html                    (rename Mis Solicitudes)
  - templates/cio/mis_solicitudes.html     (titulo + descripcion)
  - templates/admin/dashboard.html         (guard filBus)

Idempotente. Corre desde ~/mp-compliance-app/.
"""
import ast
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime

MODELS = Path('models.py')
SYNC = Path('sync_data.py')
APP = Path('app.py')
BASE = Path('templates/base.html')
MIS_SOL = Path('templates/cio/mis_solicitudes.html')
ADMIN_DASH = Path('templates/admin/dashboard.html')


# ============================================================
# MODELS.PY — Nueva tabla no_motor_checks
# ============================================================

MODELS_TABLE_MARKER = "CREATE TABLE IF NOT EXISTS no_motor_checks"
MODELS_MIGRATE_MARKER = "def _migrate_no_motor_checks"

MODELS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS no_motor_checks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id  INTEGER REFERENCES equipos(id),
            usuario_id INTEGER REFERENCES usuarios(id),
            sync_id    INTEGER NOT NULL,
            timestamp  DATETIME NOT NULL,
            UNIQUE(equipo_id, usuario_id, sync_id)
        );
"""

MODELS_MIGRATE_FN = '''

def _migrate_no_motor_checks(conn):
    """v3 - crea tabla no_motor_checks si no existe (en DBs existentes)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS no_motor_checks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id  INTEGER REFERENCES equipos(id),
            usuario_id INTEGER REFERENCES usuarios(id),
            sync_id    INTEGER NOT NULL,
            timestamp  DATETIME NOT NULL,
            UNIQUE(equipo_id, usuario_id, sync_id)
        )
    """)
'''


# ============================================================
# SYNC_DATA.PY — Corte diario limpia checks + estado sin_planeacion
# ============================================================

# En _aplicar_corte_diario, añadir DELETE de no_motor_checks
SYNC_CORTE_OLD = """    # 3. Registrar el corte en ciclos_diarios
    cur.execute(
        \"\"\"INSERT INTO ciclos_diarios"""

SYNC_CORTE_NEW = """    # 3. Limpiar checks de no motorizados del ciclo anterior
    cur.execute("DELETE FROM no_motor_checks WHERE sync_id != ?", (sync_id,))

    # 4. Registrar el corte en ciclos_diarios
    cur.execute(
        \"\"\"INSERT INTO ciclos_diarios"""

# En detección de ejec no reportadas, categorizar 'sin_planeacion' cuando no hubo solicitud
SYNC_EJEC_OLD = """        ya = cur.execute(
            \"\"\"SELECT 1 FROM ejecuciones_no_reportadas
               WHERE UPPER(vehiculo) = ? AND sync_id_anterior = ? AND sync_id_nuevo = ?
               LIMIT 1\"\"\",
            (vehiculo.upper(), prev_sync_id, sync_id)
        ).fetchone()
        if ya:
            continue

        # v2 — clasificar por categoría de vehículo
        tipo_cat = _tipo_categoria_from(prev.get('categoria'))

        cur.execute(
            \"\"\"INSERT INTO ejecuciones_no_reportadas
                   (vehiculo, familia, rutina, ind_desviacion_anterior,
                    ind_desviacion_nuevo, sync_id_anterior, sync_id_nuevo,
                    estado, tipo_categoria, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)\"\"\",
            (vehiculo, prev['familia'], prev['rutina'],
             prev['ind'], min(new_inds),
             prev_sync_id, sync_id, tipo_cat, ahora_nr)
        )"""

SYNC_EJEC_NEW = """        ya = cur.execute(
            \"\"\"SELECT 1 FROM ejecuciones_no_reportadas
               WHERE UPPER(vehiculo) = ? AND sync_id_anterior = ? AND sync_id_nuevo = ?
               LIMIT 1\"\"\",
            (vehiculo.upper(), prev_sync_id, sync_id)
        ).fetchone()
        if ya:
            continue

        # v2 — clasificar por categoría de vehículo
        tipo_cat = _tipo_categoria_from(prev.get('categoria'))

        # v3 — si NO había solicitud previa del admin → 'sin_planeacion' (proactivo CIO)
        had_solicitud = cur.execute(
            \"\"\"SELECT 1 FROM solicitudes s
               JOIN equipos e ON e.id = s.equipo_id
               WHERE UPPER(e.vehiculo) = ? AND s.sync_id = ?
               LIMIT 1\"\"\",
            (vehiculo.upper(), prev_sync_id)
        ).fetchone()
        estado_nr = 'pendiente' if had_solicitud else 'sin_planeacion'

        cur.execute(
            \"\"\"INSERT INTO ejecuciones_no_reportadas
                   (vehiculo, familia, rutina, ind_desviacion_anterior,
                    ind_desviacion_nuevo, sync_id_anterior, sync_id_nuevo,
                    estado, tipo_categoria, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\"\"\",
            (vehiculo, prev['familia'], prev['rutina'],
             prev['ind'], min(new_inds),
             prev_sync_id, sync_id, estado_nr, tipo_cat, ahora_nr)
        )"""


# ============================================================
# APP.PY — cio_no_motorizados persistente + toggle route + indicadores
# ============================================================

# 1. Reemplazar cio_no_motorizados para incluir checked_ids
APP_CIO_NM_OLD_BODY = r'''    """Vista visual del CIO para no motorizados en riesgo. Checks son locales (no persisten)."""
    if current_user.rol not in ('cio', 'admin', 'superadmin'):
        flash('Sin permiso.', 'error')
        return redirect(url_for('dashboard_redirect'))

    conn = get_db()
    sync_id = _current_sync_id(conn)
    if not sync_id:
        conn.close()
        return render_template('cio/no_motorizados.html', equipos=[], current_sync_id=None)

    _ESTADOS_RIESGO = ('Vencido por tiempo', 'Vencido por medidor', 'Próximo', 'En tolerancia')

    equipos = conn.execute(
        """SELECT e.id, e.vehiculo, e.categoria, e.familia, e.rutina,
                  e.desviacion, e.ind_desviacion, e.estado_mp
           FROM equipos e
           WHERE e.sync_id = ?
             AND COALESCE(e.tipo_rutina, 'principal') = 'principal'
             AND e.estado_mp IN ({})
             AND LOWER(e.categoria) LIKE '%no motoriz%'
           ORDER BY e.ind_desviacion DESC""".format(
               ','.join('?' * len(_ESTADOS_RIESGO))
           ),
        (sync_id,) + _ESTADOS_RIESGO
    ).fetchall()

    conn.close()
    return render_template('cio/no_motorizados.html',
        equipos=[dict(e) for e in equipos],
        current_sync_id=sync_id,
    )'''

APP_CIO_NM_NEW_BODY = r'''    """v3 — Vista de no motorizados en riesgo con checks persistentes por usuario/ciclo."""
    if current_user.rol not in ('cio', 'admin', 'superadmin'):
        flash('Sin permiso.', 'error')
        return redirect(url_for('dashboard_redirect'))

    conn = get_db()
    sync_id = _current_sync_id(conn)
    if not sync_id:
        conn.close()
        return render_template('cio/no_motorizados.html',
            equipos=[], checked_ids=set(), current_sync_id=None)

    _ESTADOS_RIESGO = ('Vencido por tiempo', 'Vencido por medidor', 'Próximo', 'En tolerancia')

    equipos = conn.execute(
        """SELECT e.id, e.vehiculo, e.categoria, e.familia, e.rutina,
                  e.desviacion, e.ind_desviacion, e.estado_mp
           FROM equipos e
           WHERE e.sync_id = ?
             AND COALESCE(e.tipo_rutina, 'principal') = 'principal'
             AND e.estado_mp IN ({})
             AND LOWER(e.categoria) LIKE '%no motoriz%'
           ORDER BY e.ind_desviacion DESC""".format(
               ','.join('?' * len(_ESTADOS_RIESGO))
           ),
        (sync_id,) + _ESTADOS_RIESGO
    ).fetchall()

    # v3 — cargar checks persistidos del usuario en el ciclo actual
    checked_ids = set()
    for r in conn.execute(
        "SELECT equipo_id FROM no_motor_checks WHERE usuario_id = ? AND sync_id = ?",
        (current_user.id, sync_id)
    ).fetchall():
        checked_ids.add(r['equipo_id'])

    conn.close()
    return render_template('cio/no_motorizados.html',
        equipos=[dict(e) for e in equipos],
        checked_ids=checked_ids,
        current_sync_id=sync_id,
    )'''


# 2. Nueva ruta POST /cio/no-motorizados/toggle
APP_NEW_TOGGLE_ROUTE = '''

# ---------------------------------------------------------------------------
# v3 — Persistir/borrar checks de no motorizados (por usuario/ciclo)
# ---------------------------------------------------------------------------

@app.route('/cio/no-motorizados/toggle', methods=['POST'])
@login_required
def cio_no_motor_toggle():
    """Persiste el check de un equipo no motorizado. Body JSON: {equipo_id, checked}."""
    if current_user.rol not in ('cio', 'admin', 'superadmin'):
        return jsonify({'success': False, 'error': 'Sin permiso'}), 403

    data = request.get_json(force=True, silent=True) or {}
    equipo_id = data.get('equipo_id')
    checked = bool(data.get('checked', False))
    if not equipo_id:
        return jsonify({'success': False, 'error': 'equipo_id requerido'}), 400

    conn = get_db()
    try:
        sync_id = _current_sync_id(conn)
        if not sync_id:
            return jsonify({'success': False, 'error': 'Sin ciclo activo'}), 400

        if checked:
            conn.execute(
                """INSERT OR IGNORE INTO no_motor_checks
                   (equipo_id, usuario_id, sync_id, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (equipo_id, current_user.id, sync_id, datetime.now(TZ_COL).isoformat())
            )
        else:
            conn.execute(
                """DELETE FROM no_motor_checks
                   WHERE equipo_id = ? AND usuario_id = ? AND sync_id = ?""",
                (equipo_id, current_user.id, sync_id)
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'checked': checked})

'''


# 3. Extender admin_indicadores con conteos sin_planeacion (para KPI positivo CIO)
# Buscamos el bloque de enr_motor / enr_no_motor y añadimos las variantes sin_planeacion

INDIC_OLD = """    enr_motor = enr_motor_row['c'] or 0
    enr_no_motor = enr_no_motor_row['c'] or 0"""

INDIC_NEW = """    enr_motor = enr_motor_row['c'] or 0
    enr_no_motor = enr_no_motor_row['c'] or 0

    # v3 — ejec sin planeación (proactivo CIO)
    if d_desde and d_hasta:
        ejec_sp_motor_row = conn.execute(
            \"\"\"SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas
               WHERE estado = 'sin_planeacion' AND tipo_categoria = 'motorizado'
                 AND date(timestamp) >= date(?)
                 AND date(timestamp) <= date(?)\"\"\",
            (d_desde, d_hasta)
        ).fetchone()
        ejec_sp_no_motor_row = conn.execute(
            \"\"\"SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas
               WHERE estado = 'sin_planeacion'
                 AND (tipo_categoria = 'no_motorizado' OR tipo_categoria IS NULL)
                 AND date(timestamp) >= date(?)
                 AND date(timestamp) <= date(?)\"\"\",
            (d_desde, d_hasta)
        ).fetchone()
    else:
        ejec_sp_motor_row = conn.execute(
            \"SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE estado = 'sin_planeacion' AND tipo_categoria = 'motorizado'\"
        ).fetchone()
        ejec_sp_no_motor_row = conn.execute(
            \"SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE estado = 'sin_planeacion' AND (tipo_categoria = 'no_motorizado' OR tipo_categoria IS NULL)\"
        ).fetchone()
    ejec_sp_motor = ejec_sp_motor_row['c'] or 0
    ejec_sp_no_motor = ejec_sp_no_motor_row['c'] or 0"""

# Y agregar las variables al render_template
INDIC_RENDER_OLD = """        enr_motor=enr_motor,
        enr_no_motor=enr_no_motor,"""
INDIC_RENDER_NEW = """        enr_motor=enr_motor,
        enr_no_motor=enr_no_motor,
        ejec_sp_motor=ejec_sp_motor,
        ejec_sp_no_motor=ejec_sp_no_motor,"""


# ============================================================
# BASE.HTML — rename Mis Solicitudes -> Mis Respuestas
# ============================================================

BASE_RENAME_OLD = """<a href="{{ url_for('cio_mis_solicitudes') }}"
           {% if request.endpoint == 'cio_mis_solicitudes' %}class="active"{% endif %}>Mis Solicitudes</a>"""
BASE_RENAME_NEW = """<a href="{{ url_for('cio_mis_solicitudes') }}"
           {% if request.endpoint == 'cio_mis_solicitudes' %}class="active"{% endif %}>Mis Respuestas</a>"""


# ============================================================
# MIS_SOLICITUDES.HTML — titulo + descripcion
# ============================================================

MIS_SOL_TITLE_OLD = """  <div class="page-hdr">
    <h1>Mis Solicitudes</h1>
    <p>Historial de equipos solicitados a Operaciones con el resultado de cada entrega</p>
  </div>"""
MIS_SOL_TITLE_NEW = """  <div class="page-hdr">
    <h1>Mis Respuestas</h1>
    <p>Historial de sus respuestas a las solicitudes enviadas por Planeación</p>
  </div>"""


# ============================================================
# ADMIN/DASHBOARD.HTML — guard filBus en JS
# ============================================================

ADMIN_DASH_JS_OLD = """  var filCat  = document.getElementById('adm-fil-cat');
  var filFam  = document.getElementById('adm-fil-fam');
  var filBus  = document.getElementById('adm-fil-bus');
  var rows    = document.querySelectorAll('#adm-equipos-body tr');
  var noRes   = document.getElementById('adm-no-results');
  var counter = document.getElementById('adm-count');

  if (!filCat) return;

  function applyFilters() {
    var cat = filCat.value.toLowerCase();
    var fam = filFam.value.toLowerCase();
    var bus = filBus.value.trim().toLowerCase();
    var visible = 0;
    rows.forEach(function (tr) {
      var ok = true;
      if (cat && (tr.dataset.categoria || '').toLowerCase() !== cat) ok = false;
      if (fam && (tr.dataset.familia   || '').toLowerCase() !== fam) ok = false;
      if (bus && !(tr.dataset.vehiculo || '').toLowerCase().includes(bus)) ok = false;
      tr.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    if (noRes)   noRes.style.display   = visible === 0 ? '' : 'none';
    if (counter) counter.textContent   = visible + ' equipo(s)';
  }

  filCat.addEventListener('change', applyFilters);
  filFam.addEventListener('change', applyFilters);
  filBus.addEventListener('input',  applyFilters);"""

ADMIN_DASH_JS_NEW = """  var filCat  = document.getElementById('adm-fil-cat');
  var filFam  = document.getElementById('adm-fil-fam');
  var rows    = document.querySelectorAll('#adm-equipos-body tr');
  var noRes   = document.getElementById('adm-no-results');
  var counter = document.getElementById('adm-count');

  if (!filCat && !filFam) return;

  function applyFilters() {
    var cat = filCat ? filCat.value.toLowerCase() : '';
    var fam = filFam ? filFam.value.toLowerCase() : '';
    var visible = 0;
    rows.forEach(function (tr) {
      var ok = true;
      if (cat && (tr.dataset.categoria || '').toLowerCase() !== cat) ok = false;
      if (fam && (tr.dataset.familia   || '').toLowerCase() !== fam) ok = false;
      tr.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    if (noRes)   noRes.style.display   = visible === 0 ? '' : 'none';
    if (counter) counter.textContent   = visible + ' equipo(s)';
  }

  if (filCat) filCat.addEventListener('change', applyFilters);
  if (filFam) filFam.addEventListener('change', applyFilters);"""


# ============================================================
# HELPERS
# ============================================================

def find_function_range(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = node.lineno
            for dec in node.decorator_list:
                start = min(start, dec.lineno)
            return (start, node.end_lineno)
    return None


def apply_patch(path, patches, banner):
    """Aplica lista de (old, new) al archivo. Retorna True si algo cambió."""
    if not path.exists():
        print(f"  [!!] {path} no encontrado")
        return False
    src = path.read_text(encoding='utf-8')
    original = src
    for old, new in patches:
        if old in src:
            src = src.replace(old, new, 1)
    if src != original:
        bak = f'{path}.bak_v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(path, bak)
        path.write_text(src, encoding='utf-8')
        print(f"  [OK] {banner}")
        return True
    print(f"  [SK] {banner} — sin cambios (anchors no encontrados o ya aplicado)")
    return False


# ============================================================
# MAIN
# ============================================================

def patch_models():
    if not MODELS.exists():
        print("  [!!] models.py no encontrado")
        return
    src = MODELS.read_text(encoding='utf-8')
    if MODELS_TABLE_MARKER in src and MODELS_MIGRATE_MARKER in src:
        print("  [SK] models.py ya tiene tabla no_motor_checks + migración")
        return

    original = src

    # Agregar CREATE TABLE en el executescript
    if MODELS_TABLE_MARKER not in src:
        anchor = "CREATE TABLE IF NOT EXISTS ciclos_diarios"
        idx = src.find(anchor)
        if idx != -1:
            src = src.replace(anchor, MODELS_TABLE_SQL.rstrip() + "\n\n        " + anchor, 1)
            print("  [OK] CREATE TABLE no_motor_checks agregado a init_db")
        else:
            print("  [!!] Anchor ciclos_diarios no encontrado — agrego al final del executescript")

    # Agregar función de migración
    if MODELS_MIGRATE_MARKER not in src:
        # Insertar antes de def seed_motivos
        anchor = "def seed_motivos"
        idx = src.find(anchor)
        if idx != -1:
            src = src[:idx] + MODELS_MIGRATE_FN.lstrip() + "\n\n" + src[idx:]
            print("  [OK] Función _migrate_no_motor_checks agregada")

    # Llamar la migración en init_db (buscar el bloque de migraciones existentes)
    if "_migrate_no_motor_checks(conn)" not in src:
        anchor = "    _migrate_ejecuciones_no_reportadas(conn)"
        if anchor in src:
            src = src.replace(anchor, anchor + "\n    _migrate_no_motor_checks(conn)", 1)
            print("  [OK] init_db llama _migrate_no_motor_checks")

    if src != original:
        bak = f'models.py.bak_v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(MODELS, bak)
        MODELS.write_text(src, encoding='utf-8')


def patch_sync_data():
    if not SYNC.exists():
        print("  [!!] sync_data.py no encontrado")
        return
    src = SYNC.read_text(encoding='utf-8')
    original = src

    # Corte diario limpia no_motor_checks
    if "DELETE FROM no_motor_checks" not in src and SYNC_CORTE_OLD in src:
        src = src.replace(SYNC_CORTE_OLD, SYNC_CORTE_NEW, 1)
        print("  [OK] Corte diario ahora limpia no_motor_checks")
    elif "DELETE FROM no_motor_checks" in src:
        print("  [SK] Corte diario ya limpia no_motor_checks")
    else:
        print("  [!!] Anchor corte diario no encontrado")

    # Estado 'sin_planeacion' cuando no había solicitud previa
    if "sin_planeacion" not in src and SYNC_EJEC_OLD in src:
        src = src.replace(SYNC_EJEC_OLD, SYNC_EJEC_NEW, 1)
        print("  [OK] Ejec no reportada categoriza 'sin_planeacion' si no había solicitud")
    elif "sin_planeacion" in src:
        print("  [SK] Categorización 'sin_planeacion' ya aplicada")
    else:
        print("  [!!] Anchor ejec no reportadas no encontrado")

    if src != original:
        bak = f'sync_data.py.bak_v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(SYNC, bak)
        SYNC.write_text(src, encoding='utf-8')


def patch_app():
    if not APP.exists():
        print("  [!!] app.py no encontrado")
        return
    src = APP.read_text(encoding='utf-8')
    original = src

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  [!!] SYNTAX ERROR previo: {e}")
        return

    # 1. Reemplazar cuerpo de cio_no_motorizados
    if 'checked_ids' not in src or 'no_motor_checks' not in src:
        rng = find_function_range(tree, 'cio_no_motorizados')
        if rng:
            lines = src.split('\n')
            new_body_lines = APP_CIO_NM_NEW_BODY.split('\n')
            lines[rng[0] : rng[1]] = new_body_lines
            src = '\n'.join(lines)
            print("  [OK] cio_no_motorizados actualizado (persistente)")
        else:
            print("  [!!] cio_no_motorizados no encontrado")
    else:
        print("  [SK] cio_no_motorizados ya persistente")

    # 2. Agregar nueva ruta toggle
    if 'def cio_no_motor_toggle(' not in src:
        anchor = "if __name__ == '__main__':"
        idx = src.find(anchor)
        if idx != -1:
            src = src[:idx] + APP_NEW_TOGGLE_ROUTE + "\n\n" + src[idx:]
            print("  [OK] Ruta POST /cio/no-motorizados/toggle agregada")
        else:
            src = src.rstrip() + '\n' + APP_NEW_TOGGLE_ROUTE + '\n'
            print("  [OK] Ruta toggle agregada al final del archivo")
    else:
        print("  [SK] Ruta toggle ya existe")

    # 3. Extender admin_indicadores con sin_planeacion
    if 'ejec_sp_motor' not in src and INDIC_OLD in src:
        src = src.replace(INDIC_OLD, INDIC_NEW, 1)
        src = src.replace(INDIC_RENDER_OLD, INDIC_RENDER_NEW, 1)
        print("  [OK] admin_indicadores incluye ejec_sp_motor y ejec_sp_no_motor")
    elif 'ejec_sp_motor' in src:
        print("  [SK] admin_indicadores ya con sin_planeacion")
    else:
        print("  [!!] Anchor admin_indicadores no encontrado")

    # Validar
    if src != original:
        try:
            ast.parse(src)
        except SyntaxError as e:
            print(f"  [!!] SYNTAX ERROR resultado: {e}")
            print("       app.py NO modificado")
            return
        bak = f'app.py.bak_v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(APP, bak)
        APP.write_text(src, encoding='utf-8')


def main():
    print("=" * 66)
    print("QA v3 — 4 fixes consolidados")
    print("=" * 66)

    print("\n[1/6] models.py — tabla no_motor_checks")
    patch_models()

    print("\n[2/6] sync_data.py — corte diario limpia checks + sin_planeacion")
    patch_sync_data()

    print("\n[3/6] app.py — cio_no_motor persistente + toggle + indicadores sin_planeacion")
    patch_app()

    print("\n[4/6] templates/base.html — Mis Solicitudes -> Mis Respuestas")
    apply_patch(BASE, [(BASE_RENAME_OLD, BASE_RENAME_NEW)], "Menú renombrado")

    print("\n[5/6] templates/cio/mis_solicitudes.html — título/descripción")
    apply_patch(MIS_SOL, [(MIS_SOL_TITLE_OLD, MIS_SOL_TITLE_NEW)], "Título actualizado")

    print("\n[6/6] templates/admin/dashboard.html — guard filBus en JS")
    apply_patch(ADMIN_DASH, [(ADMIN_DASH_JS_OLD, ADMIN_DASH_JS_NEW)], "Filtros dashboard corregidos")

    print("\n" + "=" * 66)
    print("Aplicar migración BD:")
    print("  python3 models.py")
    print("Luego: Web -> Reload")
    print("=" * 66)
    return 0


if __name__ == '__main__':
    sys.exit(main())
