"""
Migración v2 (una sola vez) — Rol técnico + KPIs por motivo.

Cambios que aplica:
  1. Elimina todos los usuarios con rol = 'tecnico'.
     Registros históricos que los referencian (log_actividad, respuestas, etc.)
     quedan con el ID pero sin usuario visible en /admin/usuarios.
  2. Verifica que el catálogo de motivos tenga impacta_a y fecha_inicio_registro
     con valores coherentes. Rellena huecos con defaults conservadores.
  3. Actualiza el motivo M05 (Falta de filtros) para asegurar impacta_a='admin'
     si ya existía sin ese valor.

Idempotente: se puede ejecutar múltiples veces sin efectos secundarios.

Uso:
    cd ~/mp-compliance-app
    python3 migracion_v2.py
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_COL = ZoneInfo('America/Bogota')


def main():
    from models import get_db

    conn = get_db()
    cur = conn.cursor()

    # ---- 1. Eliminar usuarios con rol 'tecnico' ----
    tecnicos = cur.execute(
        "SELECT id, username, nombre_completo FROM usuarios WHERE rol = 'tecnico'"
    ).fetchall()

    print("=" * 60)
    print("MIGRACIÓN v2 — Eliminación de rol técnico + KPIs por motivo")
    print("=" * 60)

    if tecnicos:
        print(f"\n[1/3] Usuarios con rol 'tecnico' encontrados: {len(tecnicos)}")
        for u in tecnicos:
            print(f"        - id={u['id']}  {u['username']}  ({u['nombre_completo']})")

        cur.execute("DELETE FROM usuarios WHERE rol = 'tecnico'")
        print(f"        → {cur.rowcount} usuarios eliminados de la tabla usuarios.")
    else:
        print("\n[1/3] No hay usuarios con rol 'tecnico'. Nada que eliminar.")

    # ---- 2. Rellenar impacta_a y fecha_inicio_registro faltantes ----
    huecos_impacta = cur.execute(
        "SELECT COUNT(*) AS c FROM catalogo_motivos WHERE impacta_a IS NULL OR impacta_a = ''"
    ).fetchone()['c']
    huecos_fecha = cur.execute(
        "SELECT COUNT(*) AS c FROM catalogo_motivos WHERE fecha_inicio_registro IS NULL"
    ).fetchone()['c']

    ahora = datetime.now(TZ_COL).isoformat()

    if huecos_impacta > 0:
        cur.execute(
            "UPDATE catalogo_motivos SET impacta_a = 'externo' WHERE impacta_a IS NULL OR impacta_a = ''"
        )
        print(f"\n[2/3] {cur.rowcount} motivos sin impacta_a → asignado 'externo'.")
    else:
        print(f"\n[2/3] Todos los motivos ya tienen impacta_a asignado.")

    if huecos_fecha > 0:
        cur.execute(
            "UPDATE catalogo_motivos SET fecha_inicio_registro = ? WHERE fecha_inicio_registro IS NULL",
            (ahora,)
        )
        print(f"       {cur.rowcount} motivos sin fecha_inicio_registro → asignado ahora.")

    # ---- 3. Asegurar que M05 (Falta de filtros) exista y sea impacta_a='admin' ----
    m05 = cur.execute(
        "SELECT id, impacta_a FROM catalogo_motivos WHERE codigo = 'M05'"
    ).fetchone()
    if m05:
        if m05['impacta_a'] != 'admin':
            cur.execute(
                "UPDATE catalogo_motivos SET impacta_a = 'admin' WHERE codigo = 'M05'"
            )
            print(f"\n[3/3] Motivo M05 existía con impacta_a='{m05['impacta_a']}' → corregido a 'admin'.")
        else:
            print(f"\n[3/3] Motivo M05 ya tiene impacta_a='admin'. Sin cambios.")
    else:
        cur.execute(
            """INSERT INTO catalogo_motivos
                   (codigo, descripcion, impacta_a, fecha_inicio_registro, activo, orden)
               VALUES ('M05', 'Falta de filtros', 'admin', ?, 1, 5)""",
            (ahora,)
        )
        print(f"\n[3/3] Motivo M05 (Falta de filtros) creado — impacta_a='admin'.")

    conn.commit()

    # ---- Reporte final ----
    total_usuarios = cur.execute("SELECT COUNT(*) AS c FROM usuarios").fetchone()['c']
    total_motivos = cur.execute("SELECT COUNT(*) AS c FROM catalogo_motivos").fetchone()['c']

    dist_impacta = cur.execute(
        "SELECT impacta_a, COUNT(*) AS c FROM catalogo_motivos GROUP BY impacta_a"
    ).fetchall()
    dist_rol = cur.execute(
        "SELECT rol, COUNT(*) AS c FROM usuarios GROUP BY rol"
    ).fetchall()

    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Usuarios totales      : {total_usuarios}")
    for r in dist_rol:
        print(f"    - {r['rol']:<15} {r['c']}")
    print(f"Motivos totales       : {total_motivos}")
    for r in dist_impacta:
        print(f"    - impacta_a={r['impacta_a']:<10} {r['c']}")
    print("=" * 60)
    print("Migración v2 aplicada correctamente.")
    print()
    print("Recuerde recargar la aplicación web (Web → Reload).")

    conn.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f"\nERROR en migración v2: {exc}", file=sys.stderr)
        sys.exit(1)
