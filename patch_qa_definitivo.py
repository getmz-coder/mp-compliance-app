"""
Master QA v2 — patch definitivo consolidado.

Aplica TODOS los fixes pendientes de la auditoría:

  BASE.HTML:
    - Agrega 'Solicitar' al menú admin
    - Agrega 'No Motorizados' al menú CIO
    - Retira bloque tecnico
    - Simplifica menú almacén (Consulta Filtros | Sync Ubicaciones)

  ADMIN/DASHBOARD.HTML (F1):
    - "por CIO a Operaciones" -> "por Planeación"

  CIO/MIS_SOLICITUDES.HTML:
    - Empty state text corregido

  ALMACEN/EQUIPO_FILTROS.HTML (F5):
    - Badge de estado homólogo con color default (evita texto invisible)

  APP.PY:
    - Retira stub cio_solicitar
    - Retira 'tecnico' de valid_roles_create en admin_usuarios (F2)

  ARCHIVOS ELIMINADOS:
    - templates/almacen/dashboard.html (orphan tras redirect)

Idempotente. Uso:
    cd ~/mp-compliance-app
    python3 patch_qa_definitivo.py
"""
import ast
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime

APP = Path('app.py')
BASE = Path('templates/base.html')
ADMIN_DASH = Path('templates/admin/dashboard.html')
MIS_SOL = Path('templates/cio/mis_solicitudes.html')
ALM_EQF = Path('templates/almacen/equipo_filtros.html')
ALM_DASH_TPL = Path('templates/almacen/dashboard.html')


# ============================================================
# BASE.HTML
# ============================================================

BASE_ADMIN_SOL_OLD = """<a href="{{ url_for('admin_sync') }}"
           {% if request.endpoint == 'admin_sync' %}class="active"{% endif %}>Sincronizar</a>
        <a href="{{ url_for('admin_historial') }}\""""
BASE_ADMIN_SOL_NEW = """<a href="{{ url_for('admin_sync') }}"
           {% if request.endpoint == 'admin_sync' %}class="active"{% endif %}>Sincronizar</a>
        <a href="{{ url_for('admin_solicitar') }}"
           {% if request.endpoint in ('admin_solicitar', 'admin_solicitar_crear') %}class="active"{% endif %}>Solicitar</a>
        <a href="{{ url_for('admin_historial') }}\""""

BASE_CIO_NOMOTOR_OLD = """<a href="{{ url_for('cio_dashboard') }}"
           {% if request.endpoint == 'cio_dashboard' %}class="active"{% endif %}>Equipos MP</a>
        <a href="{{ url_for('cio_mis_solicitudes') }}\""""
BASE_CIO_NOMOTOR_NEW = """<a href="{{ url_for('cio_dashboard') }}"
           {% if request.endpoint == 'cio_dashboard' %}class="active"{% endif %}>Equipos MP</a>
        <a href="{{ url_for('cio_no_motorizados') }}"
           {% if request.endpoint == 'cio_no_motorizados' %}class="active"{% endif %}>No Motorizados</a>
        <a href="{{ url_for('cio_mis_solicitudes') }}\""""

BASE_TECNICO_BLOCK = """      {% elif current_user.rol == 'tecnico' %}
        <a href="{{ url_for('taller') }}"
           {% if request.endpoint == 'taller' %}class="active"{% endif %}>Equipos en Taller</a>
        <a href="{{ url_for('taller_flota') }}"
           {% if request.endpoint == 'taller_flota' %}class="active"{% endif %}>Consulta Filtros</a>
"""

BASE_ALMACEN_OLD = """      {% elif current_user.rol == 'almacen' %}
        <a href="{{ url_for('almacen_dashboard') }}"
           {% if request.endpoint == 'almacen_dashboard' %}class="active"{% endif %}>Equipos en Taller</a>
        <a href="{{ url_for('almacen_flota') }}"
           {% if request.endpoint == 'almacen_flota' %}class="active"{% endif %}>Filtros Flota</a>
        <a href="{{ url_for('almacen_sync') }}"
           {% if request.endpoint == 'almacen_sync' %}class="active"{% endif %}>Sync Ubicaciones</a>"""
BASE_ALMACEN_NEW = """      {% elif current_user.rol == 'almacen' %}
        <a href="{{ url_for('almacen_flota') }}"
           {% if request.endpoint in ('almacen_flota', 'almacen_equipo_detalle') %}class="active"{% endif %}>Consulta Filtros</a>
        <a href="{{ url_for('almacen_sync') }}"
           {% if request.endpoint == 'almacen_sync' %}class="active"{% endif %}>Sync Ubicaciones</a>"""


# ============================================================
# ADMIN/DASHBOARD.HTML (F1)
# ============================================================

ADMIN_DASH_OLD = """<div class="kpi-value">{{ solicitados }}</div>
      <div class="kpi-label">Solicitados</div>
      <div class="kpi-sub">por CIO a Operaciones</div>"""
ADMIN_DASH_NEW = """<div class="kpi-value">{{ solicitados }}</div>
      <div class="kpi-label">Solicitados</div>
      <div class="kpi-sub">por Planeación</div>"""

ADMIN_DASH_PENDIENTES_OLD = """<div class="kpi-value">{{ pendientes }}</div>
      <div class="kpi-label">Pendientes</div>
      <div class="kpi-sub">sin respuesta del CIO</div>"""
ADMIN_DASH_PENDIENTES_NEW = """<div class="kpi-value">{{ pendientes }}</div>
      <div class="kpi-label">Pendientes</div>
      <div class="kpi-sub">esperando respuesta del CIO</div>"""


# ============================================================
# CIO/MIS_SOLICITUDES.HTML
# ============================================================

MIS_SOL_OLD = """<p>Ve a <a href="{{ url_for('cio_dashboard') }}"
                  style="color:var(--cielo);font-weight:600;">Equipos MP</a>
         para seleccionar equipos y solicitar a Operaciones.</p>"""
MIS_SOL_NEW = """<p>Cuando el planeador envíe equipos a su panel y usted responda, aparecerán aquí.<br>
         Revise los equipos pendientes en <a href="{{ url_for('cio_dashboard') }}"
         style="color:var(--cielo);font-weight:600;">Equipos MP</a>.</p>"""


# ============================================================
# ALMACEN/EQUIPO_FILTROS.HTML (F5)
# ============================================================

# Añadir colores por defecto al badge de estado para que texto sea legible
# aun cuando la clase específica no existe (ej. "Solo en su lista actual")
ALM_EQF_CSS_OLD = """.badge-estado {
    display: inline-block;
    padding: 1px 7px;
    font-size: 10.5px;
    font-weight: 700;
    border-radius: 8px;
    letter-spacing: 0.2px;
  }"""
ALM_EQF_CSS_NEW = """.badge-estado {
    display: inline-block;
    padding: 1px 7px;
    font-size: 10.5px;
    font-weight: 700;
    border-radius: 8px;
    letter-spacing: 0.2px;
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
  }"""


# ============================================================
# APP.PY — retirar 'tecnico' de valid_roles_create
# ============================================================
# La ruta admin_usuarios define una lista/tupla de roles válidos.
# Buscamos patrones comunes que incluyan 'tecnico'.

APP_ROLES_PATTERNS = [
    # Tupla común: ('cio', 'tecnico', 'almacen', ...)
    ("('cio', 'tecnico', 'almacen'", "('cio', 'almacen'"),
    ("(\"cio\", \"tecnico\", \"almacen\"", "(\"cio\", \"almacen\""),
    # Lista con espacios
    ("['cio', 'tecnico', 'almacen'", "['cio', 'almacen'"),
    # Con orden alternativo
    ("'tecnico', 'almacen', 'admin', 'superadmin'", "'almacen', 'admin', 'superadmin'"),
    ("'cio', 'tecnico',", "'cio',"),
]


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


def apply_text_patches(path, patches, banner=""):
    """Aplica lista de (old, new) al archivo. Reporta cada una."""
    if not path.exists():
        print(f"  [!!] {path} no encontrado")
        return False
    src = path.read_text(encoding='utf-8')
    original = src
    for old, new in patches:
        if old in src:
            src = src.replace(old, new, 1)
    if src != original:
        bak = f'{path}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(path, bak)
        path.write_text(src, encoding='utf-8')
        print(f"  [OK] {banner} — backup: {bak}")
    else:
        print(f"  [SK] {banner} — ya aplicado o anchors no encontrados")
    return True


def main():
    print("=" * 66)
    print("MASTER QA DEFINITIVO — v2 consolidado")
    print("=" * 66)

    # 1. base.html
    print("\n[1/6] Patching templates/base.html")
    if not BASE.exists():
        print("  [!!] templates/base.html no encontrado")
    else:
        src = BASE.read_text(encoding='utf-8')
        original = src

        if 'admin_solicitar' not in src and BASE_ADMIN_SOL_OLD in src:
            src = src.replace(BASE_ADMIN_SOL_OLD, BASE_ADMIN_SOL_NEW, 1)
            print("  [OK] Admin: link 'Solicitar' agregado")
        elif 'admin_solicitar' in src:
            print("  [SK] Admin 'Solicitar' ya presente")
        else:
            print("  [!!] Admin anchor no encontrado")

        if 'cio_no_motorizados' not in src and BASE_CIO_NOMOTOR_OLD in src:
            src = src.replace(BASE_CIO_NOMOTOR_OLD, BASE_CIO_NOMOTOR_NEW, 1)
            print("  [OK] CIO: link 'No Motorizados' agregado")
        elif 'cio_no_motorizados' in src:
            print("  [SK] CIO 'No Motorizados' ya presente")
        else:
            print("  [!!] CIO anchor no encontrado")

        if BASE_TECNICO_BLOCK in src:
            src = src.replace(BASE_TECNICO_BLOCK, '', 1)
            print("  [OK] Bloque tecnico retirado")
        else:
            print("  [SK] Bloque tecnico ya retirado")

        if BASE_ALMACEN_OLD in src:
            src = src.replace(BASE_ALMACEN_OLD, BASE_ALMACEN_NEW, 1)
            print("  [OK] Menú almacén simplificado")
        else:
            print("  [SK] Menú almacén ya simplificado o formato distinto")

        if src != original:
            bak = f'templates/base.html.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            shutil.copy(BASE, bak)
            BASE.write_text(src, encoding='utf-8')
            print(f"  Backup: {bak}")

    # 2. admin/dashboard.html
    print("\n[2/6] Patching templates/admin/dashboard.html (F1)")
    apply_text_patches(
        ADMIN_DASH,
        [(ADMIN_DASH_OLD, ADMIN_DASH_NEW), (ADMIN_DASH_PENDIENTES_OLD, ADMIN_DASH_PENDIENTES_NEW)],
        "KPI textos actualizados",
    )

    # 3. cio/mis_solicitudes.html
    print("\n[3/6] Patching templates/cio/mis_solicitudes.html")
    apply_text_patches(MIS_SOL, [(MIS_SOL_OLD, MIS_SOL_NEW)], "Empty state corregido")

    # 4. almacen/equipo_filtros.html (F5)
    print("\n[4/6] Patching templates/almacen/equipo_filtros.html (F5)")
    apply_text_patches(ALM_EQF, [(ALM_EQF_CSS_OLD, ALM_EQF_CSS_NEW)], "Badge estado con color default")

    # 5. app.py — retirar cio_solicitar + tecnico del dropdown
    print("\n[5/6] Patching app.py")
    if not APP.exists():
        print("  [!!] app.py no encontrado")
    else:
        src = APP.read_text(encoding='utf-8')
        original = src

        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            print(f"  [!!] SYNTAX ERROR previo: {e}")
            tree = None

        # Retirar cio_solicitar
        if tree:
            rng = find_function_range(tree, 'cio_solicitar')
            if rng:
                lines = src.split('\n')
                start, end = rng
                while end < len(lines) and lines[end].strip() == '':
                    end += 1
                while start > 1 and lines[start - 2].strip().startswith('#'):
                    start -= 1
                del lines[start - 1:end]
                src = '\n'.join(lines)
                print("  [OK] cio_solicitar (stub) retirado")
            else:
                print("  [SK] cio_solicitar ya retirado")

        # Retirar 'tecnico' de listas de roles válidos
        tecnico_removed = 0
        for old, new in APP_ROLES_PATTERNS:
            if old in src:
                src = src.replace(old, new)
                tecnico_removed += 1
        if tecnico_removed:
            print(f"  [OK] 'tecnico' retirado de {tecnico_removed} lista(s) de roles")
        else:
            print("  [SK] 'tecnico' ya no aparece en listas de roles (o formato distinto)")

        # Validar
        if src != original:
            try:
                ast.parse(src)
            except SyntaxError as e:
                print(f"  [!!] SYNTAX ERROR resultado: {e}")
                print("       app.py NO modificado")
            else:
                bak = f'app.py.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                shutil.copy(APP, bak)
                APP.write_text(src, encoding='utf-8')
                print(f"  Backup: {bak}")

    # 6. Eliminar dashboard.html orphan
    print("\n[6/6] Eliminando templates/almacen/dashboard.html (orphan)")
    if ALM_DASH_TPL.exists():
        bak = f'{ALM_DASH_TPL}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(ALM_DASH_TPL, bak)
        ALM_DASH_TPL.unlink()
        print(f"  [OK] eliminado (backup: {bak})")
    else:
        print("  [SK] ya no existe")

    print("\n" + "=" * 66)
    print("Done. Web -> Reload")
    print("=" * 66)
    return 0


if __name__ == '__main__':
    sys.exit(main())
