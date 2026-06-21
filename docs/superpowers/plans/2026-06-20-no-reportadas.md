# No Reportadas — Justificado como Ejecutado + Eliminar Registro

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los registros `justificado` en `ejecuciones_no_reportadas` cuenten como ejecutados en todos los KPIs, con badges diferenciados por estado en historial; y agregar botón Eliminar para esos registros.

**Architecture:** Cambios backend en `app.py` (queries SQLite, nueva ruta POST), cambios frontend en dos templates Jinja2. Sin migraciones de esquema — la columna `estado` ya existe.

**Tech Stack:** Python 3.11 / Flask / SQLite / Jinja2 / JS vanilla

## Global Constraints

- Branding Talma: Azul `#002D6E`, Verde `#80AE3F`, Cielo `#1E88E5`, Ámbar `#E67E22`, Fondo `#F0F2F5`
- Zero CDN externos — CSS/JS embebido o en static/
- Español en UI, inglés en variables/funciones
- CSRF via `getCsrfToken()` (lee `<meta name="csrf-token">` en base.html) en todos los fetch()
- Commits en español, descriptivos

---

## Archivos modificados

| Archivo | Cambios |
|---|---|
| `app.py` | `admin_indicadores` (KPIs), `_build_familias_chart_data` (barras), `admin_dashboard` (alerta), nueva ruta `admin_no_reportada_eliminar` |
| `templates/admin/historial.html` | Badges CSS+HTML, botón Eliminar, modal `modalEliminarNR`, JS |
| `templates/admin/indicadores.html` | KPI card sub-line desglose, cálculo `pct_f` en tabla familias |

---

### Task 1: app.py — KPIs en admin_indicadores + alerta dashboard

**Files:**
- Modify: `app.py:2280-2286` (query sin_reporte_total → split)
- Modify: `app.py:2370-2392` (render_template — agregar nuevas variables)
- Modify: `app.py:382-384` (admin_dashboard alerta)

**Interfaces:**
- Produce: variables `sin_reporte_justificados` y `sin_reporte_pendientes` disponibles en template `indicadores.html`

- [ ] **Step 1: Reemplazar query sin_reporte_total en admin_indicadores**

En `app.py` localizar el bloque exacto (líneas ~2280–2286):
```python
    sin_reporte_total = conn.execute(
        f"SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE {nr_where}",
        nr_params
    ).fetchone()['c'] or 0

    total_con_nr = total_solicitados + sin_reporte_total
    pct_ejecucion = round((ejecutados + sin_reporte_total) / total_con_nr * 100) if total_con_nr else 0
```

Reemplazar con:
```python
    nr_kpi = conn.execute(
        f"""SELECT
              SUM(CASE WHEN estado = 'justificado' THEN 1 ELSE 0 END) AS justificados,
              COUNT(*) AS total
            FROM ejecuciones_no_reportadas WHERE {nr_where}""",
        nr_params
    ).fetchone()
    sin_reporte_justificados = nr_kpi['justificados'] or 0
    sin_reporte_total        = nr_kpi['total']        or 0
    sin_reporte_pendientes   = sin_reporte_total - sin_reporte_justificados

    total_con_nr  = total_solicitados + sin_reporte_total
    ejecutados_ef = ejecutados + sin_reporte_justificados
    pct_ejecucion = round(ejecutados_ef / total_con_nr * 100) if total_con_nr else 0
```

- [ ] **Step 2: Agregar nuevas variables al render_template de admin_indicadores**

Localizar en `app.py` (~línea 2374):
```python
        sin_reporte_total=sin_reporte_total,
        pct_ejecucion=pct_ejecucion,
```

Reemplazar con:
```python
        sin_reporte_total=sin_reporte_total,
        sin_reporte_justificados=sin_reporte_justificados,
        sin_reporte_pendientes=sin_reporte_pendientes,
        pct_ejecucion=pct_ejecucion,
```

- [ ] **Step 3: Ampliar WHERE en alerta_no_reportadas del dashboard**

Localizar en `app.py` (~línea 382):
```python
        alerta_no_reportadas = conn.execute(
            "SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE estado = 'pendiente'"
        ).fetchone()['c'] or 0
```

Reemplazar con:
```python
        alerta_no_reportadas = conn.execute(
            "SELECT COUNT(*) AS c FROM ejecuciones_no_reportadas WHERE estado IN ('pendiente', 'sin_justificar')"
        ).fetchone()['c'] or 0
```

- [ ] **Step 4: Verificar sintaxis Python**

```
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```
Esperado: `OK`

- [ ] **Step 5: Commit**

```
git add app.py
git commit -m "KPIs: justificado cuenta como ejecutado en indicadores y alerta dashboard"
```

---

### Task 2: app.py — _build_familias_chart_data y query nr_por_familia

**Files:**
- Modify: `app.py:2321-2334` (query nr_por_familia → split por estado)
- Modify: `app.py:2135-2144` (_build_familias_chart_data — lógica de barras)

**Interfaces:**
- Consumes: `familias_cumplimiento` con nuevas claves `sin_reporte_just` y `sin_reporte_pend`
- Produce: `familias_chart['rows'][i]['ejec_px']` incluye justificados; `sin_px` solo no-justificados

- [ ] **Step 1: Reemplazar query nr_por_familia**

Localizar en `app.py` (~línea 2321):
```python
    nr_por_familia = {
        r['familia']: r['cnt']
        for r in conn.execute(
            f"""SELECT familia, COUNT(*) AS cnt
               FROM ejecuciones_no_reportadas
               WHERE familia IS NOT NULL AND {nr_where}
               GROUP BY familia""",
            nr_params
        ).fetchall()
    }

    familias_cumplimiento = [
        dict(f, sin_reporte=nr_por_familia.get(f['familia'], 0))
        for f in familias_cumplimiento_raw
    ]
```

Reemplazar con:
```python
    nr_familia_rows = conn.execute(
        f"""SELECT familia,
              SUM(CASE WHEN estado = 'justificado' THEN 1 ELSE 0 END) AS just,
              COUNT(*) AS total
            FROM ejecuciones_no_reportadas
            WHERE familia IS NOT NULL AND {nr_where}
            GROUP BY familia""",
        nr_params
    ).fetchall()
    nr_just_familia = {r['familia']: r['just']  for r in nr_familia_rows}
    nr_tot_familia  = {r['familia']: r['total'] for r in nr_familia_rows}

    familias_cumplimiento = [
        dict(f,
             sin_reporte=nr_tot_familia.get(f['familia'], 0),
             sin_reporte_just=nr_just_familia.get(f['familia'], 0),
             sin_reporte_pend=nr_tot_familia.get(f['familia'], 0) - nr_just_familia.get(f['familia'], 0))
        for f in familias_cumplimiento_raw
    ]
```

- [ ] **Step 2: Actualizar lógica de barras en _build_familias_chart_data**

Localizar en `app.py` (~línea 2135), el bloque dentro del for:
```python
        sin_rep = f.get('sin_reporte', 0) or 0
        total_base = sol + sin_rep
        pct = round((ejec + sin_rep) / total_base * 100) if total_base else 0
        ejec_px  = round((ejec    / total_base) * BAR_W) if total_base else 0
        sin_px   = round((sin_rep / total_base) * BAR_W) if total_base else 0
        no_px    = round((no_ejec / total_base) * BAR_W) if total_base else 0
```

Reemplazar con:
```python
        sin_rep_just = f.get('sin_reporte_just', 0) or 0
        sin_rep_pend = f.get('sin_reporte_pend', 0) or 0
        sin_rep      = sin_rep_just + sin_rep_pend
        total_base   = sol + sin_rep
        ejec_ef      = ejec + sin_rep_just
        pct      = round(ejec_ef / total_base * 100) if total_base else 0
        ejec_px  = round(ejec_ef / total_base * BAR_W) if total_base else 0
        sin_px   = round(sin_rep_pend / total_base * BAR_W) if total_base else 0
        no_px    = round(no_ejec / total_base * BAR_W) if total_base else 0
```

- [ ] **Step 3: Verificar sintaxis Python**

```
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```
Esperado: `OK`

- [ ] **Step 4: Commit**

```
git add app.py
git commit -m "KPIs familias: justificado suma a ejecutados en barras y porcentajes"
```

---

### Task 3: app.py — nueva ruta POST eliminar no_reportada

**Files:**
- Modify: `app.py` — insertar nueva ruta después de `admin_no_reportadas_justificar` (~línea 2466)

**Interfaces:**
- Produce: `POST /admin/no-reportada/<int:nr_id>/eliminar` → `{"success": true}` o `{"success": false, "error": "..."}`

- [ ] **Step 1: Insertar la nueva ruta**

Localizar el final de `admin_no_reportadas_justificar` en `app.py`:
```python
    return jsonify({'success': True, 'estado': estado})


# ---------------------------------------------------------------------------
# Dev
```

Reemplazar con:
```python
    return jsonify({'success': True, 'estado': estado})


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
             f'Eliminado registro no_reportada id={nr_id} vehiculo={row["vehiculo"]}',
             request.remote_addr,
             datetime.now(TZ_COL).isoformat())
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Dev
```

- [ ] **Step 2: Verificar sintaxis Python**

```
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```
Esperado: `OK`

- [ ] **Step 3: Commit**

```
git add app.py
git commit -m "Backend: ruta POST /admin/no-reportada/<id>/eliminar con log"
```

---

### Task 4: historial.html — badges CSS + Estado + Acción

**Files:**
- Modify: `templates/admin/historial.html:196-198` (colores CSS badges NR)
- Modify: `templates/admin/historial.html:493-501` (textos badges Estado)
- Modify: `templates/admin/historial.html:529-531` (badge Acción para justificado)

**Interfaces:**
- Consumes: `f.nr_estado` ('pendiente' | 'justificado' | 'sin_justificar'), `f.accion` ('sin_reporte')

- [ ] **Step 1: Cambiar colores CSS de los badges NR**

Localizar en `templates/admin/historial.html`:
```css
  .badge-nr-pendiente    { background:#fff2f2; color:#991b1b; border:1px solid #fca5a5; }
  .badge-nr-justificado  { background:#f0fdf4; color:#166534; border:1px solid #86efac; }
  .badge-nr-sin-just     { background:#fffbeb; color:#92400e; border:1px solid #fde68a; }
```

Reemplazar con:
```css
  .badge-nr-pendiente    { background:#fff7ed; color:#9a3412; border:1px solid #fdba74; }
  .badge-nr-justificado  { background:#f0fdf4; color:#166534; border:1px solid #86efac; }
  .badge-nr-sin-just     { background:#fff2f2; color:#991b1b; border:1px solid #fca5a5; }
```

- [ ] **Step 2: Cambiar textos de los badges de Estado**

Localizar en `templates/admin/historial.html`:
```html
              {% if f.nr_estado == 'pendiente' %}
                  <span class="badge-sol-estado badge-nr-pendiente">Pendiente</span>
                {% elif f.nr_estado == 'justificado' %}
                  <span class="badge-sol-estado badge-nr-justificado">Justificado</span>
                {% elif f.nr_estado == 'sin_justificar' %}
                  <span class="badge-sol-estado badge-nr-sin-just">Sin justificar</span>
```

Reemplazar con:
```html
              {% if f.nr_estado == 'pendiente' %}
                  <span class="badge-sol-estado badge-nr-pendiente">Sin reporte - pendiente</span>
                {% elif f.nr_estado == 'justificado' %}
                  <span class="badge-sol-estado badge-nr-justificado">Justificado</span>
                {% elif f.nr_estado == 'sin_justificar' %}
                  <span class="badge-sol-estado badge-nr-sin-just">No reportado sin justificar</span>
```

- [ ] **Step 3: Diferenciar badge Acción para justificado**

Localizar en `templates/admin/historial.html`:
```html
              {% elif f.accion == 'sin_reporte' %}
                <span class="badge-accion badge-sin-rep">⚠ Sin reporte</span>
```

Reemplazar con:
```html
              {% elif f.accion == 'sin_reporte' %}
                {% if f.nr_estado == 'justificado' %}
                  <span class="badge-accion badge-ent">✓ Justificado</span>
                {% else %}
                  <span class="badge-accion badge-sin-rep">⚠ Sin reporte</span>
                {% endif %}
```

- [ ] **Step 4: Commit**

```
git add templates/admin/historial.html
git commit -m "Historial: badges NR diferenciados por estado (pendiente=naranja, sin_justificar=rojo, justificado=verde)"
```

---

### Task 5: indicadores.html — KPI desglose + tabla familias

**Files:**
- Modify: `templates/admin/indicadores.html:546-550` (KPI card Sin Reporte)
- Modify: `templates/admin/indicadores.html:746-748` (cálculo pct_f en tabla familias)

**Interfaces:**
- Consumes: `sin_reporte_justificados`, `sin_reporte_pendientes` (del render_template — Task 1)
- Consumes: `f.sin_reporte_just` en cada familia (de familias_cumplimiento — Task 2)

- [ ] **Step 1: Actualizar KPI card "Sin Reporte" para mostrar desglose**

Localizar en `templates/admin/indicadores.html`:
```html
    <div class="kpi-card kpi-amber">
      <div class="kpi-value">{{ sin_reporte_total }}</div>
      <div class="kpi-label">Sin Reporte</div>
      <div class="kpi-sub">ejecutados sin registrar</div>
    </div>
```

Reemplazar con:
```html
    <div class="kpi-card kpi-amber">
      <div class="kpi-value">{{ sin_reporte_total }}</div>
      <div class="kpi-label">Sin Reporte</div>
      <div class="kpi-sub">
        <span style="color:#166534;">{{ sin_reporte_justificados }} justificados</span>
        / <span style="color:#991b1b;">{{ sin_reporte_pendientes }} pendientes</span>
      </div>
    </div>
```

- [ ] **Step 2: Actualizar cálculo pct_f en tabla por familia**

Localizar en `templates/admin/indicadores.html`:
```html
              {% set sin_rep_f = f.sin_reporte if f.sin_reporte is defined else 0 %}
              {% set total_f  = sol_f + sin_rep_f %}
              {% set pct_f    = (((ejec_f + sin_rep_f) / total_f) * 100)|round|int if total_f else 0 %}
```

Reemplazar con:
```html
              {% set sin_rep_f      = f.sin_reporte if f.sin_reporte is defined else 0 %}
              {% set sin_rep_just_f = f.sin_reporte_just if f.sin_reporte_just is defined else 0 %}
              {% set total_f  = sol_f + sin_rep_f %}
              {% set pct_f    = (((ejec_f + sin_rep_just_f) / total_f) * 100)|round|int if total_f else 0 %}
```

- [ ] **Step 3: Commit**

```
git add templates/admin/indicadores.html
git commit -m "Indicadores: KPI desglose justificados/pendientes, pct_f usa solo justificados"
```

---

### Task 6: historial.html — botón Eliminar + modal + JS

**Files:**
- Modify: `templates/admin/historial.html:562-568` (celda acciones no_reportada — agregar botón)
- Modify: `templates/admin/historial.html` después de `modalJust` — agregar `modalEliminarNR`
- Modify: `templates/admin/historial.html:800-806` (Escape handler — agregar cierre NR modal)
- Modify: `templates/admin/historial.html` dentro del bloque `{% if es_admin %}` en JS — agregar bloque modal NR

**Interfaces:**
- Consumes: `f.row_id` (int), `f.vehiculo` (str) del contexto Jinja
- Consumes: `POST /admin/no-reportada/<id>/eliminar` → `{success: bool}` (Task 3)
- Consumes: `getCsrfToken()` — definida en base.html

- [ ] **Step 1: Agregar botón Eliminar junto al botón Gestionar**

Localizar en `templates/admin/historial.html` (celda acciones de no_reportada):
```html
              {% elif f.tipo == 'no_reportada' and es_admin %}
                <button class="btn-just"
                        onclick="abrirModalJust({{ f.row_id }}, '{{ (f.vehiculo or '')|e }}', '{{ (f.familia or '')|e }}', '{{ (f.rutina or '')|replace("'", "\\'")|replace('"', '&quot;') }}', {{ f.ind_desviacion_anterior or 0 }}, {{ f.ind_desviacion_nuevo or 0 }}, '{{ f.nr_estado or 'pendiente' }}', '{{ (f.justificacion or '')|e|replace("'", "\\'") }}')">
                  <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  Gestionar
                </button>
```

Reemplazar con:
```html
              {% elif f.tipo == 'no_reportada' and es_admin %}
                <div style="display:flex;flex-direction:column;gap:4px;">
                  <button class="btn-just"
                          onclick="abrirModalJust({{ f.row_id }}, '{{ (f.vehiculo or '')|e }}', '{{ (f.familia or '')|e }}', '{{ (f.rutina or '')|replace("'", "\\'")|replace('"', '&quot;') }}', {{ f.ind_desviacion_anterior or 0 }}, {{ f.ind_desviacion_nuevo or 0 }}, '{{ f.nr_estado or 'pendiente' }}', '{{ (f.justificacion or '')|e|replace("'", "\\'") }}')">
                    <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    Gestionar
                  </button>
                  <button class="btn-del"
                          data-nrid="{{ f.row_id }}"
                          data-vehiculo="{{ f.vehiculo }}"
                          onclick="confirmarEliminarNR(this)">
                    <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    Eliminar
                  </button>
                </div>
```

- [ ] **Step 2: Agregar modal modalEliminarNR después del cierre de modalJust**

Localizar en `templates/admin/historial.html`:
```html
<!-- ── Modal gestionar no-reportada ── -->
<div class="modal-overlay" id="modalJust">
```

Este bloque termina antes de `{% endif %}` (el que cierra `{% if es_admin %}`). Localizar el final del bloque `modalJust` (justo antes de ese `{% endif %}`):
```html
  </div>
</div>
{% endif %}
```

Reemplazar esa última parte (el cierre de modalJust + endif) con:
```html
  </div>
</div>

<!-- ── Modal confirmar eliminación no-reportada ── -->
<div class="modal-overlay" id="modalEliminarNR">
  <div class="modal-box">
    <div class="modal-icon">
      <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
    </div>
    <h3>¿Eliminar este registro?</h3>
    <p id="modalEliminarNRMsg">Se eliminará el registro de ejecución sin reporte. Esta acción no se puede deshacer.</p>
    <div class="modal-actions">
      <button class="btn-modal-cancel" onclick="cerrarModalEliminarNR()">Cancelar</button>
      <button class="btn-modal-confirm" id="btnConfirmarEliminarNR">Eliminar</button>
    </div>
  </div>
</div>

{% endif %}
```

- [ ] **Step 3: Agregar bloque JS para modal NR (antes del Escape handler)**

Localizar en el bloque `<script>` de `templates/admin/historial.html`:
```javascript
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var mel = document.getElementById('modalEliminar');
      var mjust = document.getElementById('modalJust');
      if (mel && mel.classList.contains('visible'))   cerrarModalEliminar();
      if (mjust && mjust.classList.contains('visible')) cerrarModalJust();
    }
  });
```

Reemplazar con:
```javascript
  /* ════════════════════════════════
     Modal eliminar no-reportada
  ════════════════════════════════ */
  var _pendingNrId  = null;
  var _pendingNrRow = null;

  window.confirmarEliminarNR = function (btn) {
    _pendingNrId  = btn.dataset.nrid;
    _pendingNrRow = document.getElementById('row-no_reportada-' + _pendingNrId);
    document.getElementById('modalEliminarNRMsg').textContent =
      'Se eliminará el registro sin reporte del vehículo ' + btn.dataset.vehiculo +
      '. Esta acción no se puede deshacer.';
    var confirmBtn = document.getElementById('btnConfirmarEliminarNR');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Eliminar';
    document.getElementById('modalEliminarNR').classList.add('visible');
  };

  function cerrarModalEliminarNR() {
    document.getElementById('modalEliminarNR').classList.remove('visible');
    _pendingNrId  = null;
    _pendingNrRow = null;
  }
  window.cerrarModalEliminarNR = cerrarModalEliminarNR;

  document.getElementById('btnConfirmarEliminarNR').addEventListener('click', function () {
    if (!_pendingNrId) return;
    var btn = this;
    btn.disabled = true;
    btn.textContent = 'Eliminando…';

    fetch('/admin/no-reportada/' + _pendingNrId + '/eliminar', {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': getCsrfToken() }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        if (_pendingNrRow) {
          _pendingNrRow.style.transition = 'opacity 0.25s';
          _pendingNrRow.style.opacity = '0';
          setTimeout(function () { _pendingNrRow.remove(); }, 260);
        }
        cerrarModalEliminarNR();
      } else {
        alert('Error: ' + (data.error || 'No se pudo eliminar.'));
        btn.disabled = false;
        btn.textContent = 'Eliminar';
      }
    })
    .catch(function () {
      alert('Error de red. Intenta de nuevo.');
      btn.disabled = false;
      btn.textContent = 'Eliminar';
    });
  });

  document.getElementById('modalEliminarNR').addEventListener('click', function (e) {
    if (e.target === this) cerrarModalEliminarNR();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var mel   = document.getElementById('modalEliminar');
      var mjust = document.getElementById('modalJust');
      var mnr   = document.getElementById('modalEliminarNR');
      if (mel   && mel.classList.contains('visible'))   cerrarModalEliminar();
      if (mjust && mjust.classList.contains('visible')) cerrarModalJust();
      if (mnr   && mnr.classList.contains('visible'))   cerrarModalEliminarNR();
    }
  });
```

- [ ] **Step 4: Verificar que el HTML cierra bien (sin etiquetas huérfanas)**

Revisar visualmente que:
- `{% if es_admin %}` tiene su `{% endif %}` correspondiente
- El nuevo modal está dentro de ese bloque
- El `<script>` está cerrado con `</script>`

- [ ] **Step 5: Commit**

```
git add templates/admin/historial.html
git commit -m "Historial: botón Eliminar para no-reportadas, modal confirmación y JS"
```
