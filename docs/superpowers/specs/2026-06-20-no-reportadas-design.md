# Spec: Ejecuciones No Reportadas — Justificado como Ejecutado + Eliminar

**Fecha:** 2026-06-20  
**Alcance:** `app.py`, `templates/admin/historial.html`, `templates/admin/indicadores.html`

---

## Contexto

La tabla `ejecuciones_no_reportadas` registra equipos que pasaron por mantenimiento sin haber sido solicitados a través de la app. El admin puede gestionar cada registro asignándole un estado:

| Estado | Significado |
|---|---|
| `pendiente` | Detectado, sin gestionar |
| `justificado` | Admin confirmó que el MP sí ocurrió (válido) |
| `sin_justificar` | Admin revisó y no lo justificó (inválido) |

Actualmente todos los registros `sin_reporte` se cuentan igual en KPIs (como ejecutados implícitos). El sistema tampoco permite eliminar estos registros.

---

## Cambio 1: justificado = ejecutado en KPIs

### Regla de negocio

- `estado = 'justificado'` → cuenta como **EJECUTADO** en todos los KPIs e indicadores
- `estado IN ('pendiente', 'sin_justificar')` → cuenta como **NO REPORTADO** (no suma a ejecutados)

### Modificaciones en `app.py`

**1. `admin_indicadores` (~línea 2280)**

Reemplazar la query única de `sin_reporte_total` por dos conteos:

```python
nr_row = conn.execute(
    f"""SELECT
          SUM(CASE WHEN estado = 'justificado' THEN 1 ELSE 0 END) AS justificados,
          COUNT(*) AS total
        FROM ejecuciones_no_reportadas WHERE {nr_where}""",
    nr_params
).fetchone()
sin_reporte_justificados = nr_row['justificados'] or 0
sin_reporte_total        = nr_row['total'] or 0
sin_reporte_pendientes   = sin_reporte_total - sin_reporte_justificados
```

Recalcular `pct_ejecucion`:
```python
total_con_nr  = total_solicitados + sin_reporte_total
ejecutados_ef = ejecutados + sin_reporte_justificados
pct_ejecucion = round(ejecutados_ef / total_con_nr * 100) if total_con_nr else 0
```

Pasar al template: `sin_reporte_justificados`, `sin_reporte_pendientes`, `sin_reporte_total`.

**2. `_build_familias_chart_data` (~línea 2321)**

Reemplazar `nr_por_familia` (dict simple) por dos dicts separados:

```python
nr_just_familia = {}   # justificados por familia
nr_pend_familia = {}   # pendiente+sin_justificar por familia
for r in conn.execute(
    f"""SELECT familia,
          SUM(CASE WHEN estado = 'justificado' THEN 1 ELSE 0 END) AS just,
          SUM(CASE WHEN estado != 'justificado' THEN 1 ELSE 0 END) AS pend
        FROM ejecuciones_no_reportadas
        WHERE familia IS NOT NULL AND {nr_where}
        GROUP BY familia""",
    nr_params
).fetchall():
    nr_just_familia[r['familia']] = r['just']
    nr_pend_familia[r['familia']] = r['pend']

familias_cumplimiento = [
    dict(f,
         sin_reporte_just=nr_just_familia.get(f['familia'], 0),
         sin_reporte_pend=nr_pend_familia.get(f['familia'], 0),
         sin_reporte=nr_just_familia.get(f['familia'], 0) + nr_pend_familia.get(f['familia'], 0))
    for f in familias_cumplimiento_raw
]
```

En `_build_familias_chart_data`, actualizar el cálculo del % y barras:
```python
sin_rep_just = f.get('sin_reporte_just', 0) or 0
sin_rep_pend = f.get('sin_reporte_pend', 0) or 0
sin_rep_total = sin_rep_just + sin_rep_pend
total_base = sol + sin_rep_total
pct = round((ejec + sin_rep_just) / total_base * 100) if total_base else 0
ejec_px = round(((ejec + sin_rep_just) / total_base) * BAR_W) if total_base else 0
sin_px  = round((sin_rep_pend / total_base) * BAR_W) if total_base else 0
```

**3. `admin_dashboard` (~línea 382)**

Ampliar el WHERE:
```python
alerta_no_reportadas = conn.execute(
    "SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE estado IN ('pendiente', 'sin_justificar')"
).fetchone()['c'] or 0
```

### Modificaciones en templates

**`templates/admin/historial.html` — columna Estado**

Cambiar textos y colores de los tres badges `nr_estado`:

| Estado | Texto actual | Texto nuevo | Color |
|---|---|---|---|
| `pendiente` | "Pendiente" | "Sin reporte - pendiente" | Naranja |
| `sin_justificar` | "Sin justificar" | "No reportado sin justificar" | Rojo |
| `justificado` | "Justificado" | "Justificado" | Verde (sin cambio) |

CSS: cambiar `badge-nr-pendiente` a naranja (`#fff7ed / #9a3412 / #fdba74`) y `badge-nr-sin-just` a rojo (`#fff2f2 / #991b1b / #fca5a5`).

**`templates/admin/historial.html` — columna Acción**

Para `tipo == 'no_reportada'`: mostrar badge según `nr_estado`:
- `nr_estado == 'justificado'` → `<span class="badge-accion badge-ent">✓ Justificado</span>`
- cualquier otro → `<span class="badge-accion badge-sin-rep">⚠ Sin reporte</span>` (igual que ahora)

**`templates/admin/indicadores.html`**

Donde se muestre `sin_reporte_total`, pasar a mostrar desglosado: `sin_reporte_justificados` (ejecutados implícitos) y `sin_reporte_pendientes` (requieren atención). El total sigue siendo la suma de ambos.

---

## Cambio 2: eliminar no_reportada

### Backend — nueva ruta en `app.py`

```python
@app.route('/admin/no-reportada/<int:nr_id>/eliminar', methods=['POST'])
@admin_required
def admin_no_reportada_eliminar(nr_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, vehiculo FROM ejecuciones_no_reportadas WHERE id = ?", (nr_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Registro no encontrado.'}), 404
        conn.execute("DELETE FROM ejecuciones_no_reportadas WHERE id = ?", (nr_id,))
        conn.execute(
            """INSERT INTO log_actividad (usuario_id, accion_tipo, detalle, ip_address, timestamp)
               VALUES (?, 'eliminar_no_reportada', ?, ?, ?)""",
            (current_user.id,
             f'Eliminado registro no_reportada id={nr_id} vehículo={row["vehiculo"]}',
             request.remote_addr,
             datetime.now(TZ_COL).isoformat())
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True})
```

Se usa POST (no DELETE) para consistencia con el resto del proyecto (fetch con `method: 'POST'`).

### Frontend — `templates/admin/historial.html`

**Botón Eliminar** (junto al botón Gestionar para `tipo == 'no_reportada'`):

```html
{% elif f.tipo == 'no_reportada' and es_admin %}
  <div style="display:flex;flex-direction:column;gap:4px;">
    <button class="btn-just" onclick="abrirModalJust(...)">
      <!-- svg editar --> Gestionar
    </button>
    <button class="btn-del"
            data-nrid="{{ f.row_id }}"
            data-vehiculo="{{ f.vehiculo }}"
            onclick="confirmarEliminarNR(this)">
      <!-- svg basura --> Eliminar
    </button>
  </div>
{% endif %}
```

**Modal de confirmación** (reutilizar el modal existente o agregar un segundo modal con id `modal-del-nr`):

```html
<div id="modal-del-nr" class="modal-overlay">
  <div class="modal-box">
    <div class="modal-icon"><!-- svg basura --></div>
    <h3>Eliminar registro</h3>
    <p>¿Eliminar el registro sin reporte de <strong id="modal-del-nr-vehiculo"></strong>?
       Esta acción no se puede deshacer.</p>
    <div class="modal-actions">
      <button class="btn-modal-cancel" onclick="cerrarModalDelNR()">Cancelar</button>
      <button id="btn-modal-del-nr-confirm" class="btn-modal-confirm">Eliminar</button>
    </div>
  </div>
</div>
```

**JS** — función `confirmarEliminarNR(btn)`:

```javascript
function confirmarEliminarNR(btn) {
  const nrid     = btn.dataset.nrid;
  const vehiculo = btn.dataset.vehiculo;
  document.getElementById('modal-del-nr-vehiculo').textContent = vehiculo;
  document.getElementById('btn-modal-del-nr-confirm').onclick = () => ejecutarEliminarNR(nrid, btn);
  document.getElementById('modal-del-nr').classList.add('visible');
}

function cerrarModalDelNR() {
  document.getElementById('modal-del-nr').classList.remove('visible');
}

async function ejecutarEliminarNR(nrid, btn) {
  const confirmBtn = document.getElementById('btn-modal-del-nr-confirm');
  confirmBtn.disabled = true;
  const resp = await fetch(`/admin/no-reportada/${nrid}/eliminar`, { method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN} });
  const data = await resp.json();
  cerrarModalDelNR();
  if (data.success) {
    document.getElementById(`row-no_reportada-${nrid}`)?.remove();
  } else {
    alert(data.error || 'Error al eliminar.');
  }
  confirmBtn.disabled = false;
}
```

---

## Archivos modificados

| Archivo | Cambios |
|---|---|
| `app.py` | `admin_indicadores`, `_build_familias_chart_data`, `admin_dashboard`, nueva ruta `admin_no_reportada_eliminar` |
| `templates/admin/historial.html` | Badges Estado+Acción, botón Eliminar, modal confirmación, JS |
| `templates/admin/indicadores.html` | Desglose KPIs sin_reporte_justificados vs sin_reporte_pendientes |

## Fuera de alcance

- No se modifican templates CIO ni el flujo de justificación existente
- No se agrega paginación ni filtros nuevos
- No se exporta el campo `estado` al Excel (ya existente en admin_export)
