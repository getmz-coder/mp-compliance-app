"""
Master QA patch — aplica todos los fixes pendientes de la auditoría v2.

Cambios:
  1. templates/base.html:
     - Agrega 'Solicitar' al menú admin (si falta)
     - Agrega 'No Motorizados' al menú CIO (si falta)
     - Elimina bloque tecnico (rol retirado en FASE 1)
     - Simplifica menú almacén: 'Consulta Filtros | Sync Ubicaciones'
  2. templates/cio/mis_solicitudes.html:
     - Empty state text corregido (CIO ya no solicita)
  3. app.py:
     - Retira el stub cio_solicitar (obsoleto tras QA-1)
  4. templates/almacen/dashboard.html:
     - Elimina archivo orphan (dashboard viejo, ya no renderizado)

Idempotente: se puede correr múltiples veces.

Uso:
    cd ~/mp-compliance-app
    python3 patch_master_qa.py
"""
import ast
import shutil
import sys
from pathlib import Path
from datetime import datetime

APP = Path('app.py')
BASE = Path('templates/base.html')
MIS_SOL = Path('templates/cio/mis_solicitudes.html')
ALMACEN_DASH_TPL = Path('templates/almacen/dashboard.html')


# ============================================================
# 1. BASE.HTML PATCHES
# ============================================================

BASE_ANCHOR_ADMIN_SOLICITAR_OLD = """<a href="{{ url_for('admin_sync') }}"
           {% if request.endpoint == 'admin_sync' %}class="active"{% endif %}>Sincronizar</a>
        <a href="{{ url_for('admin_historial') }}\""""

BASE_ANCHOR_ADMIN_SOLICITAR_NEW = """<a href="{{ url_for('admin_sync') }}"
           {% if request.endpoint == 'admin_sync' %}class="active"{% endif %}>Sincronizar</a>
        <a href="{{ url_for('admin_solicitar') }}"
           {% if request.endpoint in ('admin_solicitar', 'admin_solicitar_crear') %}class="active"{% endif %}>Solicitar</a>
        <a href="{{ url_for('admin_historial') }}\""""

BASE_ANCHOR_CIO_NOMOTOR_OLD = """<a href="{{ url_for('cio_dashboard') }}"
           {% if request.endpoint == 'cio_dashboard' %}class="active"{% endif %}>Equipos MP</a>
        <a href="{{ url_for('cio_mis_solicitudes') }}\""""

BASE_ANCHOR_CIO_NOMOTOR_NEW = """<a href="{{ url_for('cio_dashboard') }}"
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
# 2. MIS_SOLICITUDES.HTML EMPTY STATE
# ============================================================

MIS_SOL_OLD_TEXT = """<p>Ve a <a href="{{ url_for('cio_dashboard') }}"
                  style="color:var(--cielo);font-weight:600;">Equipos MP</a>
         para seleccionar equipos y solicitar a Operaciones.</p>"""

MIS_SOL_NEW_TEXT = """<p>Cuando el planeador envíe equipos a su panel y usted responda, aparecerán aquí.<br>
         Revise los equipos pendientes en <a href="{{ url_for('cio_dashboard') }}"
         style="color:var(--cielo);font-weight:600;">Equipos MP</a>.</p>"""


# ============================================================
# HELPERS
# ============================================================

def patch_text_file(path, replacements, marker=None, marker_present_msg=None):
    """
    Aplica lista de (old, new) al archivo. Retorna cantidad de reemplazos.
    Si marker se pasa y ya está en el archivo, no hace nada.
    """
    if not path.exists():
        print(f"  [!!] {path} no encontrado")
        return 0

    src = path.read_text(encoding='utf-8')

    if marker and marker in src and (old for old, new in replacements if old in src) == False:
        # Idempotencia via marker (útil cuando ya está aplicado)
        pass

    n = 0
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
            n += 1
    if n:
        bak = f'{path}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        # Restaurar contenido original al backup (antes del cambio)
        # Como ya modificamos src en memoria, hacemos backup del disco
        # Nota: como leemos + escribimos, backup se hace del original
        # ... simplificamos con copy del original antes de write
        shutil.copy(path, bak)
        path.write_text(src, encoding='utf-8')
    return n


def find_function_range(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = node.lineno
            for dec in node.decorator_list:
                start = min(start, dec.lineno)
            return (start, node.end_lineno)
    return None


# ============================================================
# MAIN
# ============================================================

def patch_base():
    if not BASE.exists():
        print("  [!!] templates/base.html no encontrado")
        return False
    src = BASE.read_text(encoding='utf-8')
    original = src

    bak = f'{BASE}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

    # 1.1 Admin solicitar
    if 'admin_solicitar' in src:
        print("  [SK] admin_solicitar ya presente")
    elif BASE_ANCHOR_ADMIN_SOLICITAR_OLD in src:
        src = src.replace(BASE_ANCHOR_ADMIN_SOLICITAR_OLD, BASE_ANCHOR_ADMIN_SOLICITAR_NEW, 1)
        print("  [OK] Admin: agregado link 'Solicitar'")
    else:
        print("  [!!] Anchor admin_sync -> admin_historial no encontrado")

    # 1.2 CIO no_motorizados
    if 'cio_no_motorizados' in src:
        print("  [SK] cio_no_motorizados ya presente")
    elif BASE_ANCHOR_CIO_NOMOTOR_OLD in src:
        src = src.replace(BASE_ANCHOR_CIO_NOMOTOR_OLD, BASE_ANCHOR_CIO_NOMOTOR_NEW, 1)
        print("  [OK] CIO: agregado link 'No Motorizados'")
    else:
        print("  [!!] Anchor cio_dashboard -> cio_mis_solicitudes no encontrado")

    # 1.3 Retirar tecnico
    if BASE_TECNICO_BLOCK in src:
        src = src.replace(BASE_TECNICO_BLOCK, '', 1)
        print("  [OK] Retirado bloque tecnico")
    else:
        print("  [SK] Bloque tecnico ya retirado (o formato distinto)")

    # 1.4 Simplificar almacen
    if BASE_ALMACEN_OLD in src:
        src = src.replace(BASE_ALMACEN_OLD, BASE_ALMACEN_NEW, 1)
        print("  [OK] Menú almacén simplificado (Consulta Filtros | Sync Ubicaciones)")
    elif "'almacen_flota', 'almacen_equipo_detalle'" in src:
        print("  [SK] Menú almacén ya simplificado")
    else:
        print("  [!!] Anchor menú almacén no encontrado")

    if src != original:
        shutil.copy(BASE, bak)
        BASE.write_text(src, encoding='utf-8')
        print(f"  Backup: {bak}")

    return True


def patch_mis_solicitudes():
    if not MIS_SOL.exists():
        print("  [!!] templates/cio/mis_solicitudes.html no encontrado")
        return False
    src = MIS_SOL.read_text(encoding='utf-8')

    if MIS_SOL_OLD_TEXT in src:
        bak = f'{MIS_SOL}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(MIS_SOL, bak)
        src = src.replace(MIS_SOL_OLD_TEXT, MIS_SOL_NEW_TEXT, 1)
        MIS_SOL.write_text(src, encoding='utf-8')
        print("  [OK] Empty state corregido")
    else:
        print("  [SK] Empty state ya corregido (o formato distinto)")
    return True


def patch_app():
    if not APP.exists():
        print("  [!!] app.py no encontrado")
        return False
    src = APP.read_text(encoding='utf-8')

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  [!!] SYNTAX ERROR previo: {e}")
        return False

    # Buscar cio_solicitar
    rng = find_function_range(tree, 'cio_solicitar')
    if rng is None:
        print("  [SK] cio_solicitar ya retirado")
        return True

    bak = f'app.py.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    shutil.copy(APP, bak)
    print(f"  Backup: {bak}")

    start, end = rng
    # Consumir líneas en blanco al final
    lines = src.split('\n')
    while end < len(lines) and lines[end].strip() == '':
        end += 1
    # Retroceder líneas de comentario justo arriba (bloque separador)
    while start > 1 and lines[start - 2].strip().startswith('#'):
        start -= 1

    del lines[start - 1:end]
    new_src = '\n'.join(lines)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"  [!!] SYNTAX ERROR resultado: {e}")
        return False

    APP.write_text(new_src, encoding='utf-8')
    print(f"  [OK] cio_solicitar (stub) retirado")
    return True


def delete_orphan_dashboard():
    if ALMACEN_DASH_TPL.exists():
        bak = f'{ALMACEN_DASH_TPL}.bak_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy(ALMACEN_DASH_TPL, bak)
        ALMACEN_DASH_TPL.unlink()
        print(f"  [OK] templates/almacen/dashboard.html eliminado (backup: {bak})")
    else:
        print("  [SK] templates/almacen/dashboard.html ya no existe")
    return True


def main():
    print("=" * 60)
    print("MASTER QA PATCH — v2")
    print("=" * 60)

    print("\n[1/4] Patching templates/base.html")
    patch_base()

    print("\n[2/4] Patching templates/cio/mis_solicitudes.html")
    patch_mis_solicitudes()

    print("\n[3/4] Patching app.py (retiro cio_solicitar)")
    patch_app()

    print("\n[4/4] Eliminando templates/almacen/dashboard.html (orphan)")
    delete_orphan_dashboard()

    print("\n" + "=" * 60)
    print("Done. Web -> Reload")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
