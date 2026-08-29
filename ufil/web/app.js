/* Interfaz del análisis documental — UFIL Paraná.
   JavaScript sin dependencias ni compilación: se lee entero y se entiende.
   La regla visual que sostiene todo: lo que está en monoespaciada se leyó de un
   papel y tiene anclaje; lo que está en bastardilla serif es una conjetura. */
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const vista = $('#vista');
const fmtNum = new Intl.NumberFormat('es-AR');
const fmtPesos = c => c == null ? null
  : '$' + new Intl.NumberFormat('es-AR', {minimumFractionDigits: 2}).format(c / 100);

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(ruta, opciones) {
  const r = await fetch(ruta, opciones);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

/* Quién revisa: queda registrado en cada decisión humana. */
function revisor() {
  let q = localStorage.getItem('ufil.revisor');
  if (!q) {
    q = (prompt('¿Quién está revisando? (queda registrado en cada decisión)') || '').trim();
    if (q) localStorage.setItem('ufil.revisor', q);
  }
  return q;
}

/* ── piezas visuales ───────────────────────────────────────────────────── */
function barraConf(c) {
  if (c == null) return '';
  const n = Math.max(0, Math.min(5, Math.round(c * 5)));
  const clase = c >= 0.85 ? '' : (c >= 0.5 ? ' media' : ' baja');
  return `<span class="barra-conf${clase}">${
    [0,1,2,3,4].map(i => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</span>`;
}

function celdaValor(c) {
  if (c.nulo_motivo)
    return `<span class="nulo ${c.nulo_motivo === 'conflicto' ? 'conf' : ''}">Ø ${esc(c.nulo_motivo)}</span>`;
  const dudoso = c.confianza != null && c.confianza < 0.85 ? ' dudoso' : '';
  return `<span class="mono${dudoso}">${esc(c.valor_literal)}</span>`;
}

function bloque(folio, rotulo, html) {
  return `<section class="bloque">
    <div class="marginalia"><span>${esc(folio)}</span><span class="rotulo">${esc(rotulo)}</span></div>
    <div class="cuerpo">${html}</div></section>`;
}

function tabla(cols, filas, opts = {}) {
  if (!filas.length) return `<div class="tabla-env"><div class="vacio">Sin resultados.</div></div>`;
  const th = cols.map(c => `<th>${esc(c.t)}</th>`).join('');
  const tr = filas.map((f, i) => `<tr class="${opts.alClic ? 'clic' : ''}" data-i="${i}">${
    cols.map(c => `<td class="${c.c || ''}">${c.r ? c.r(f) : esc(f[c.k] ?? '')}</td>`).join('')
  }</tr>`).join('');
  return `<div class="tabla-env"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

function interpHTML(i) {
  const fuentes = (i.fuentes || []).map(f =>
    `<a class="chip" href="#/documento/${f.documento_id}">${esc(f.archivo || f.nota || ('doc ' + f.documento_id))}</a>`).join('');
  return `<div class="interp">
    <span class="clase">${esc(i.clase)} · ${esc(i.origen)}</span>
    <p class="texto">${esc(i.texto)}</p>
    <div class="fuentes">${fuentes || '<span class="chip">sin fuentes</span>'}</div>
  </div>`;
}

/* ── vistas ────────────────────────────────────────────────────────────── */
async function vPanel() {
  const p = await api('/api/panel');
  const cob = p.cobertura.filter(c => c.campo !== 'cargo');

  vista.innerHTML =
    bloque('f. 0001', 'Estado', `
      <h2>Estado del lote</h2>
      <div class="cifras">
        <div class="cifra"><b>${fmtNum.format(p.documentos)}</b><span>documentos</span></div>
        <div class="cifra"><b>${fmtNum.format(p.paginas)}</b><span>páginas leídas</span></div>
        <div class="cifra ok"><b>${p.cobertura_pct}%</b><span>resuelto solo</span></div>
        <div class="cifra alerta"><b>${fmtNum.format(p.a_revisar)}</b><span>a revisar</span></div>
        <div class="cifra alerta"><b>${fmtNum.format(p.conflictos)}</b><span>conflictos</span></div>
        <div class="cifra"><b>${fmtNum.format(p.verificados)}</b><span>verificados a mano</span></div>
        <div class="cifra"><b>${fmtNum.format(p.personas)}</b><span>personas</span></div>
        <div class="cifra"><b>${fmtNum.format(p.duplicados)}</b><span>copias exactas</span></div>
      </div>`) +

    bloque('f. 0002', 'Hallazgos', `
      <h2>Hallazgos del análisis</h2>
      <p class="prosa">Todo lo de acá abajo sale de consultas SQL sobre la tabla de datos.
        Se puede reproducir a mano y no interviene ningún modelo.</p>
      <div class="cifras">
        <div class="cifra"><b>${fmtNum.format(p.superposiciones)}</b><span>superposiciones</span></div>
        <div class="cifra"><b>${fmtNum.format(p.ambas_camaras)}</b><span>en ambas cámaras</span></div>
        <div class="cifra alerta"><b>${fmtNum.format(p.fechas_imposibles)}</b><span>fechas imposibles</span></div>
        <div class="cifra"><b>${fmtNum.format(p.excluidos)}</b><span>fuera del cruce</span></div>
      </div>
      <p class="prosa" style="margin-top:12px"><strong>${fmtNum.format(p.excluidos)} contratos
        quedaron fuera del cruce</strong> por faltarles algún dato firme. El total de
        hallazgos no debe leerse como si el universo estuviera completo:
        <a href="#/consultas/06_excluidos_del_cruce">ver cuáles y por qué</a>.</p>`) +

    bloque('f. 0003', 'Cobertura', `
      <h2>Qué se pudo leer</h2>
      <p class="prosa">El denominador honesto, campo por campo. Una cola larga no es una
        falla: es el sistema prefiriendo dudar antes que equivocarse callado.</p>
      ${tabla([
        {t:'Campo', k:'campo'},
        {t:'Total', k:'total', c:'num'},
        {t:'Resueltos solos', k:'resueltos_solos', c:'num'},
        {t:'Con valor, a revisar', k:'con_valor_a_revisar', c:'num'},
        {t:'Verificados', k:'verificados_a_mano', c:'num'},
        {t:'Conflictos', c:'num', r:f => f.conflictos ? `<span class="marca">${f.conflictos}</span>` : '0'},
        {t:'Ilegibles', k:'ilegibles', c:'num'},
        {t:'Ausentes', k:'ausentes', c:'num'},
        {t:'Sin intervención', c:'num', r:f => f.pct_sin_intervencion + '%'},
      ], cob)}`);
}

async function vContratos() {
  const filas = await api('/api/contratos');
  vista.innerHTML = bloque('f. 0004', 'Datos', `
    <h2>Contratos</h2>
    <p class="prosa">La tabla consolidada. Un campo entra sólo si tiene valor y no tiene
      conflicto abierto: lo que no se pudo leer aparece vacío, nunca completado.</p>
    ${tabla([
      {t:'Doc', k:'documento_id', c:'fol'},
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', k:'camara'},
      {t:'Contratado/a', r:f => f.nombre_literal ? esc(f.nombre_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Documento', c:'mono', r:f => f.documento_literal ? esc(f.documento_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Inicio', k:'inicio', c:'mono'},
      {t:'Fin', r:f => f.fin ? `<span class="mono">${esc(f.fin)}</span>` : '<span class="nulo">Ø sin dato</span>'},
      {t:'Monto', c:'num', r:f => f.monto_centavos == null ? '<span class="nulo">Ø sin dato</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], filas, {alClic:true})}`);
  vista.querySelectorAll('tbody tr').forEach(tr =>
    tr.onclick = () => location.hash = '#/documento/' + filas[+tr.dataset.i].documento_id);
}

async function vSuperposiciones() {
  const r = await api('/api/consulta?id=01_superposicion');
  vista.innerHTML = bloque('f. 0005', 'Cruce', `
    <h2>Superposición temporal</h2>
    <p class="prosa">Pares de contratos de una misma persona cuyos períodos se pisan.
      Sólo entran contratos con las dos fechas firmes.</p>
    ${tabla([
      {t:'Folios', c:'fol', r:f => `${esc(f.archivo_a)}<br>${esc(f.archivo_b)}`},
      {t:'Contratado/a', k:'contratado'},
      {t:'Documento', k:'documento', c:'mono'},
      {t:'Cruce', r:f => f.cruce === 'intercámara' ? `<span class="marca">${esc(f.cruce)}</span>` : esc(f.cruce)},
      {t:'Períodos', c:'mono', r:f => `${esc(f.periodo_a)}<br>${esc(f.periodo_b)}`},
      {t:'Días', k:'dias_solapados', c:'num'},
      {t:'Suma', c:'num', r:f => esc(fmtPesos(f.suma_centavos))},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], r.filas, {alClic:true})}`);
  vista.querySelectorAll('tbody tr').forEach(tr =>
    tr.onclick = () => location.hash = '#/documento/' + r.filas[+tr.dataset.i].doc_a);
}

async function vDocumento(id) {
  const d = await api('/api/documento?id=' + id);
  const doc = d.documento;
  const anclables = d.campos.filter(c => c.x0 != null);

  const campos = d.campos.map(c => {
    const conf = d.conflictos[c.nombre];
    if (conf) {
      return `<div class="campo"><dt>${esc(c.nombre)}</dt><dd><div class="conflicto">${
        conf.map(v => `<div class="ruta"><span>${esc(v.ruta)}</span><span>${esc(v.valor)}</span></div>`).join('')
      }</div></dd></div>`;
    }
    const ancla = c.x0 != null
      ? `<button class="ancla" data-campo="${c.id}">f.${c.pagina_nro} · ▣</button>` : '';
    const marca = c.estado === 'verificado' || c.estado === 'corregido'
      ? ' <span class="sello ok" style="font-size:8.5px;padding:1px 5px;outline:none">✓ verificado</span>' : '';
    return `<div class="campo"><dt>${esc(c.nombre)}</dt>
      <dd>${celdaValor(c)}${ancla}${marca}</dd></div>`;
  }).join('');

  vista.innerHTML = bloque('f. ' + String(id).padStart(4, '0'), 'Visor', `
    <h2>${esc(doc.archivo)}</h2>
    <p class="prosa" style="font-size:13px">
      Cámara ${esc(doc.camara || '—')} · perfil <span class="mono">${esc(doc.perfil)}</span> ·
      lote ${esc(doc.lote || '—')}<br>
      <span class="mono" style="font-size:11px">sha256 ${esc(String(doc.sha256).slice(0, 32))}…</span></p>
    <div class="visor">
      <div class="datos">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px">
          <span class="rotulo">Carril de datos — leído del documento</span>
        </div>
        ${campos}
      </div>
      <div class="lamina">
        <div class="lienzo" id="lienzo">
          <img src="/pagina?doc=${id}&nro=1" alt="Folio 1 de ${esc(doc.archivo)}">
          <div class="recuadro" id="recuadro" style="display:none"></div>
        </div>
        <div class="pie-lamina"><span id="pie-campo">tocá una ficha de anclaje</span>
          <span id="pie-xy"></span></div>
      </div>
    </div>
    ${d.interpretaciones.length ? `
      <div style="margin-top:22px">
        <span class="rotulo">Carril de interpretación — conjeturas del sistema</span>
        <p class="prosa" style="font-size:13px;margin:6px 0 12px">Esto no se leyó de ningún
          papel: son hipótesis armadas cruzando datos. Pueden estar mal. Cada una linkea a
          los documentos que la sostienen.</p>
        ${d.interpretaciones.map(interpHTML).join('')}
      </div>` : ''}`);

  const pag = d.paginas[0] || {ancho_pt: 595, alto_pt: 842};
  const recuadro = $('#recuadro');
  vista.querySelectorAll('.ancla').forEach(b => b.onclick = () => {
    const c = anclables.find(x => x.id === +b.dataset.campo);
    if (!c) return;
    recuadro.style.display = 'block';
    recuadro.style.left   = (100 * c.x0 / pag.ancho_pt) + '%';
    recuadro.style.top    = (100 * c.y0 / pag.alto_pt) + '%';
    recuadro.style.width  = (100 * (c.x1 - c.x0) / pag.ancho_pt) + '%';
    recuadro.style.height = (100 * (c.y1 - c.y0) / pag.alto_pt) + '%';
    recuadro.className = 'recuadro' + (c.nulo_motivo ? ' conf' : '');
    $('#pie-campo').textContent = 'campo: ' + c.nombre + (c.ruta ? ' · ruta ' + c.ruta : '');
    $('#pie-xy').textContent = `f.${c.pagina_nro} · [${[c.x0,c.y0,c.x1,c.y1].map(v=>Math.round(v)).join(',')}]`;
    vista.querySelectorAll('.ancla').forEach(o => o.setAttribute('aria-pressed', o === b));
  });
}

/* ── cola de revisión, operable con el teclado ─────────────────────────── */
let colaEstado = {filas: [], foco: 0};

async function vCola() {
  const filas = await api('/api/cola');
  colaEstado = {filas, foco: 0};
  if (!filas.length) {
    vista.innerHTML = bloque('f. 0006', 'Cola', `<h2>Cola de revisión</h2>
      <div class="cola"><div class="vacio">No queda nada por revisar.</div></div>`);
    return;
  }
  vista.innerHTML = bloque('f. 0006', 'Cola', `
    <h2>Cola de revisión</h2>
    <p class="prosa">Todo lo que el sistema no resolvió, ordenado por lo que más daño hace
      si queda mal. Se opera con el teclado: <kbd>J</kbd>/<kbd>K</kbd> para moverse,
      las teclas de cada fila para decidir. <strong>Ninguna acción es «aceptar todo».</strong></p>
    <div class="cola" id="cola">${filas.map(filaCola).join('')}</div>`);
  pintarFoco();
  vista.querySelectorAll('[data-accion]').forEach(b => b.onclick = () =>
    decidir(+b.dataset.campo, b.dataset.accion, b.dataset.valor));
}

function filaCola(f, i) {
  const acciones = [];
  if (f.clase === 'conflicto' && f.variantes) {
    f.variantes.forEach((v, n) => acciones.push(
      [String(n + 1), `tomar ${v.ruta}`, 'corregir', v.valor]));
    acciones.push(['N', 'ninguna, Ø ambiguo', 'ambiguo', '']);
  } else if (f.motivo) {
    acciones.push(['C', 'cargar a mano', 'pedir', '']);
    acciones.push(['X', `Ø ${f.motivo}, firme`, 'verificar', '']);
  } else {
    acciones.push(['V', 'es correcto', 'verificar', '']);
    acciones.push(['C', 'corregir', 'pedir', '']);
    acciones.push(['X', 'Ø ilegible', 'ilegible', '']);
  }
  const cuerpo = (f.clase === 'conflicto' && f.variantes)
    ? `<div class="conflicto">${f.variantes.map(v =>
        `<div class="ruta"><span>${esc(v.ruta)}</span><span>${esc(v.valor)}</span></div>`).join('')}</div>`
    : `<div class="mono" style="font-size:13px">${f.valor
        ? esc(f.valor) : `<span class="nulo">Ø ${esc(f.motivo)}</span>`} ${barraConf(f.confianza)}</div>`;

  return `<div class="fila" data-i="${i}">
    <div class="marginalia"><span>${esc(f.archivo.replace('.pdf', ''))}</span>
      <span>f. ${f.pagina_nro ?? '—'}</span></div>
    <div class="med">
      <div style="display:flex;gap:9px;align-items:baseline;margin-bottom:7px;flex-wrap:wrap">
        <span class="rotulo">${esc(f.clase)}</span>
        <span class="sello ${f.clase === 'conflicto' ? 'alerta' : ''}">${esc(f.campo)}</span>
        <a class="chip" href="#/documento/${f.documento_id}">ver el folio</a>
      </div>
      ${cuerpo}
    </div>
    <div class="acc">${acciones.map(([k, t, a, v]) =>
      `<button class="tecla" data-campo="${f.campo_id}" data-accion="${a}" data-valor="${esc(v)}">
         <kbd>${k}</kbd> ${esc(t)}</button>`).join('')}</div>
  </div>`;
}

function pintarFoco() {
  const filas = vista.querySelectorAll('.fila');
  filas.forEach((f, i) => f.classList.toggle('foco', i === colaEstado.foco));
  filas[colaEstado.foco]?.scrollIntoView({block: 'nearest'});
}

async function decidir(campoId, accion, valor) {
  const quien = revisor();
  if (!quien) return;
  if (accion === 'pedir') {
    valor = (prompt('Valor tal como figura en el documento:') || '').trim();
    if (!valor) return;
    accion = 'corregir';
  }
  try {
    await api('/api/campo', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({campo_id: campoId, accion, valor, quien})});
    await vCola();
    refrescarCuentas();
  } catch (e) { alert('No se pudo guardar: ' + e.message); }
}

document.addEventListener('keydown', e => {
  if (!location.hash.startsWith('#/cola') || e.target.tagName === 'INPUT') return;
  const f = colaEstado.filas[colaEstado.foco];
  if (e.key === 'j' || e.key === 'ArrowDown') {
    colaEstado.foco = Math.min(colaEstado.foco + 1, colaEstado.filas.length - 1); pintarFoco();
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    colaEstado.foco = Math.max(colaEstado.foco - 1, 0); pintarFoco();
  } else if (f) {
    const fila = vista.querySelectorAll('.fila')[colaEstado.foco];
    const botones = [...fila.querySelectorAll('[data-accion]')];
    const kb = botones.find(b => b.querySelector('kbd').textContent.toLowerCase() === e.key.toLowerCase());
    if (kb) { e.preventDefault(); kb.click(); }
  }
});

async function vIdentidad() {
  const fus = await api('/api/fusiones');
  vista.innerHTML = bloque('f. 0007', 'Identidad', `
    <h2>Fusiones propuestas</h2>
    <p class="prosa">CUIT, CUIL y DNI son clave fuerte: dos contratos con el mismo documento
      ya están unidos, solos. <strong>El nombre nunca alcanza.</strong> Lo de acá abajo son
      propuestas; ninguna se aplica sin que alguien la confirme, porque una fusión errónea
      inventa un contratado con el doble de contratos.</p>
    <div class="cola">${fus.length ? fus.map((f, i) => `
      <div class="fila" data-i="${i}">
        <div class="marginalia"><span>#${f.id}</span><span>${(f.score * 100).toFixed(0)}%</span></div>
        <div class="med">
          <div class="rotulo" style="margin-bottom:7px">${esc(f.motivo)}</div>
          <div class="mono" style="font-size:12.5px;display:flex;flex-direction:column;gap:3px">
            <span>${esc(f.lit_a)} <span style="color:var(--tinta-3)">— ${esc(f.doc_a || 'sin documento')}</span></span>
            <span>${esc(f.lit_b)} <span style="color:var(--tinta-3)">— ${esc(f.doc_b || 'sin documento')}</span></span>
          </div>
        </div>
        <div class="acc">
          <button class="tecla" data-fus="${f.id}" data-ok="1"><kbd>F</kbd> son la misma persona</button>
          <button class="tecla" data-fus="${f.id}" data-ok="0"><kbd>S</kbd> son distintas</button>
        </div>
      </div>`).join('') : '<div class="vacio">No hay fusiones pendientes.</div>'}</div>`);
  vista.querySelectorAll('[data-fus]').forEach(b => b.onclick = async () => {
    const quien = revisor(); if (!quien) return;
    try {
      await api('/api/fusion', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id:+b.dataset.fus, aceptar: b.dataset.ok === '1', quien})});
      await vIdentidad(); refrescarCuentas();
    } catch (e) { alert('No se pudo guardar: ' + e.message); }
  });
}

async function vInterpretacion() {
  const items = await api('/api/interpretaciones');
  const porClase = {};
  items.forEach(i => (porClase[i.clase] ||= []).push(i));
  vista.innerHTML = bloque('f. 0008', 'Conjetura', `
    <h2>Interpretación</h2>
    <div class="aviso"><span class="sello alerta" style="flex:none">Otro carril</span>
      <span>Nada de esta pantalla se leyó de un documento. Son hipótesis y patrones que el
      sistema arma cruzando los datos. <strong>Pueden estar equivocados.</strong> Cada
      afirmación linkea a los documentos que la sostienen: chequealos antes de usarla.</span></div>
    ${Object.entries(porClase).map(([clase, its]) => `
      <h3 style="margin-top:18px">${esc(clase)} <span class="rotulo">(${its.length})</span></h3>
      ${its.map(interpHTML).join('')}`).join('') || '<div class="vacio">Sin interpretaciones.</div>'}
    <div style="margin-top:16px"><button class="boton" id="b-regen">Volver a generar</button></div>`);
  $('#b-regen').onclick = async () => {
    await api('/api/interpretar', {method: 'POST'}); vInterpretacion();
  };
}

async function vConsultas(id) {
  const cat = await api('/api/consultas');
  const activa = id || cat[0]?.id;
  const r = activa ? await api('/api/consulta?id=' + activa) : null;
  vista.innerHTML = bloque('f. 0009', 'SQL', `
    <h2>Consultas</h2>
    <p class="prosa">Cada consulta es un archivo <span class="mono">.sql</span> versionado en
      el repositorio, no una cadena escondida en el código. Cuando pidan una variante se
      copia el archivo, se edita, y quedan las dos.</p>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px">
      ${cat.map(c => `<a class="chip" href="#/consultas/${c.id}"
        style="${c.id === activa ? 'background:var(--sello);color:var(--papel);border-color:var(--sello)' : ''}"
        >${esc(c.id)}</a>`).join('')}
    </div>
    ${r ? `<pre class="sql">${esc(r.sql.trim())}</pre>
      <p class="prosa" style="font-size:12px;margin:10px 0">${esc(r.ruta)} · ${r.n} filas</p>
      ${tabla(r.columnas.map(c => ({t:c, k:c, c: /centavos|dias|total|_id|^n$/.test(c) ? 'num' : ''})), r.filas)}`
    : ''}`);
}



/* ── Búsqueda ──────────────────────────────────────────────────────────── */
function resaltar(fragmento) {
  return esc(fragmento).replace(/\[\[/g, '<mark>').replace(/\]\]/g, '</mark>');
}

async function vBuscar(q) {
  q = q ? decodeURIComponent(q) : '';
  const r = q ? await api('/api/buscar?q=' + encodeURIComponent(q)) : null;
  vista.innerHTML = bloque('f. 0010', 'Buscar', `
    <h2>Buscar en el corpus</h2>
    <form id="f-buscar" style="display:flex; gap:8px; margin:12px 0 6px; flex-wrap:wrap">
      <input type="text" id="q" value="${esc(q)}" style="flex:1; min-width:260px; font-size:14px"
        placeholder="un apellido, un CUIL, una palabra del contrato…" autocomplete="off">
      <button class="boton" type="submit">Buscar</button>
    </form>
    <p class="prosa" style="font-size:13px">Sin tildes está bien: <span class="mono">locacion</span>
      encuentra <span class="mono">locación</span>. Entre comillas busca la frase exacta.</p>
    ${r ? resultadosHTML(r) : '<div class="vacio">Escribí algo y dale a Buscar.</div>'}`);

  const form = $('#f-buscar');
  form.onsubmit = e => { e.preventDefault();
    location.hash = '#/buscar/' + encodeURIComponent($('#q').value.trim()); };
  if (!q) $('#q').focus();
}

function resultadosHTML(r) {
  if (r.aviso) return `<div class="aviso"><span class="sello alerta">Atención</span>
    <span>${esc(r.aviso)}</span></div>`;
  const nada = !r.campos.length && !r.paginas.length;
  if (nada) return `<div class="vacio">Sin coincidencias para «${esc(r.consulta)}».</div>`;
  return `
    ${r.campos.length ? `
      <h3 style="margin-top:22px">En los datos extraídos <span class="rotulo">(${r.campos.length})</span></h3>
      <p class="prosa" style="font-size:13px">Esto son <strong>contratos</strong>: el dato ya
        está leído y anclado.</p>
      ${tabla([
        {t:'Archivo', k:'archivo', c:'fol'},
        {t:'Campo', k:'campo'},
        {t:'Valor leído', c:'mono', r:f => esc(f.valor_literal)},
        {t:'Contratado/a', r:f => esc(f.nombre_literal || '—')},
        {t:'Período', c:'mono', r:f => f.inicio ? `${esc(f.inicio)} → ${esc(f.fin || '?')}` : '—'},
        {t:'Monto', c:'num', r:f => f.monto_centavos == null ? '—' : esc(fmtPesos(f.monto_centavos))},
      ], r.campos, {alClic:true})}` : ''}
    ${r.paginas.length ? `
      <h3 style="margin-top:24px">En el texto de los folios <span class="rotulo">(${r.paginas.length})</span></h3>
      <p class="prosa" style="font-size:13px">Esto son <strong>lugares donde mirar</strong>:
        apareció en la página, sin que sea un campo extraído.</p>
      <div class="hallazgos">${r.paginas.map(p => `
        <a class="hallazgo" href="#/documento/${p.documento_id}">
          <span class="fol">${esc(p.archivo)} · f. ${p.nro}</span>
          <span class="frag">${resaltar(p.fragmento)}</span>
        </a>`).join('')}</div>` : ''}`;
}

/* ── Personas ──────────────────────────────────────────────────────────── */
async function vPersonas() {
  const filas = await api('/api/documentos');
  vista.innerHTML = bloque('f. 0011', 'Personas', `
    <h2>Contratados</h2>
    <p class="prosa">Agrupados por documento cuando lo hay. <strong>Los que no tienen
      documento legible aparecen sueltos</strong>, uno por contrato: sin clave fuerte el
      sistema no los junta solo, y eso es a propósito.</p>
    ${tabla([
      {t:'Contratado/a', k:'contratado'},
      {t:'Documento', c:'mono', r:f => f.documento ? esc(f.documento) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Contratos', k:'contratos', c:'num'},
      {t:'Sin monto', c:'num', r:f => f.contratos_sin_monto ? `<span class="marca">${f.contratos_sin_monto}</span>` : '0'},
      {t:'Acumulado', c:'num', r:f => esc(fmtPesos(f.acumulado_centavos))},
      {t:'Cámaras', r:f => esc(f.camaras || '—')},
      {t:'Desde', k:'primer_inicio', c:'mono'},
      {t:'Hasta', k:'ultimo_fin', c:'mono'},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], filas, {alClic:true})}`);
  vista.querySelectorAll('tbody tr').forEach(tr =>
    tr.onclick = () => location.hash = '#/persona/' + filas[+tr.dataset.i].persona_id);
}

/* Cronología de tramos: un renglón por contrato sobre un eje temporal común.
   Un solo tono para los contratos; el rojo de estado marca SÓLO la superposición,
   que es lo que el gráfico existe para mostrar. La cámara va como texto, no como
   color: la identidad nunca depende del color solo. */
function cronologia(contratos, solapes) {
  const conFechas = contratos.filter(c => c.inicio && c.fin);
  if (conFechas.length < 1) return '';
  const dia = 86400000;
  const t0 = Math.min(...conFechas.map(c => +new Date(c.inicio)));
  const t1 = Math.max(...conFechas.map(c => +new Date(c.fin)));
  const margen = Math.max((t1 - t0) * 0.03, 10 * dia);
  const a = t0 - margen, b = t1 + margen;
  const x = t => (100 * (t - a) / (b - a));

  const anios = [];
  for (let y = new Date(a).getFullYear(); y <= new Date(b).getFullYear(); y++) {
    const t = +new Date(y, 0, 1);
    if (t >= a && t <= b) anios.push({y, izq: x(t)});
  }

  const tramos = conFechas.map(c => {
    const i = +new Date(c.inicio), f = +new Date(c.fin);
    const solapa = solapes.some(s => s.doc_a === c.documento_id || s.doc_b === c.documento_id);
    const dias = Math.round((f - i) / dia) + 1;
    return `<div class="tramo-fila">
      <div class="tramo-rot">
        <span class="mono">Cám. ${esc(c.camara || '?')}</span>
        <span class="fol">${esc(c.archivo.replace('.pdf',''))}</span>
      </div>
      <div class="tramo-pista">
        ${anios.map(n => `<i class="guia" style="left:${n.izq}%"></i>`).join('')}
        <a class="tramo${solapa ? ' solapa' : ''}" href="#/documento/${c.documento_id}"
           style="left:${x(i)}%; width:${Math.max(x(f) - x(i), 0.7)}%"
           title="${esc(c.inicio)} → ${esc(c.fin)} · ${dias} días · ${esc(c.cargo || 'sin cargo')}${
             c.monto_centavos != null ? ' · ' + fmtPesos(c.monto_centavos) : ''}"></a>
      </div>
      <div class="tramo-dato mono">${esc(c.inicio)} → ${esc(c.fin)}</div>
    </div>`;
  }).join('');

  const sinFechas = contratos.length - conFechas.length;
  return `
    <div class="cronologia">
      <div class="tramo-fila eje">
        <div class="tramo-rot"></div>
        <div class="tramo-pista">${anios.map(n =>
          `<span class="anio" style="left:${n.izq}%">${n.y}</span>`).join('')}</div>
        <div class="tramo-dato"></div>
      </div>
      ${tramos}
    </div>
    <div class="leyenda">
      <span><i class="mues"></i> contrato</span>
      <span><i class="mues solapa"></i> se pisa con otro de la misma persona</span>
      ${sinFechas ? `<span class="marca">${sinFechas} contrato${sinFechas===1?'':'s'} sin
        fechas firmes, fuera del gráfico</span>` : ''}
    </div>`;
}

async function vPersona(id) {
  const d = await api('/api/persona?id=' + id);
  const t = d.totales;
  const nombre = d.alias[0] ? d.alias[0].nombre_literal : '(sin nombre legible)';
  const otros = d.alias.slice(1);

  vista.innerHTML = bloque('f. ' + String(id).padStart(4,'0'), 'Ficha', `
    <h2>${esc(nombre)}</h2>
    <p class="prosa" style="font-size:13.5px">
      ${d.persona.clave_fuerte
        ? `Documento <span class="mono">${esc(d.persona.doc_tipo)} ${esc(d.persona.doc_numero)}</span> ·
           los contratos se agruparon por clave fuerte.`
        : `<strong>Sin documento legible.</strong> Este contratado no se agrupó con ningún otro:
           el nombre solo nunca alcanza para decir que dos contratos son de la misma persona.`}
      ${otros.length ? `<br>También aparece escrito como ${otros.map(o =>
        `<span class="mono">${esc(o.nombre_literal)}</span>`).join(', ')}.` : ''}</p>

    <div class="cifras" style="margin:14px 0 4px">
      <div class="cifra"><b>${t.contratos}</b><span>contratos</span></div>
      <div class="cifra"><b>${esc(fmtPesos(t.acumulado_centavos) || '—')}</b><span>acumulado</span></div>
      <div class="cifra ${d.solapes.length ? 'alerta' : ''}"><b>${d.solapes.length}</b><span>superposiciones</span></div>
      <div class="cifra"><b>${esc((t.camaras || []).join(' + ') || '—')}</b><span>cámaras</span></div>
      <div class="cifra ${t.sin_monto ? 'alerta' : ''}"><b>${t.sin_monto}</b><span>sin monto legible</span></div>
    </div>
    ${t.sin_monto || t.sin_fechas ? `<p class="prosa" style="font-size:12.5px">
      El acumulado suma sólo los contratos con monto firme: hay ${t.sin_monto} sin monto y
      ${t.sin_fechas} sin fechas completas. <strong>Es un piso, no un total.</strong></p>` : ''}

    <h3 style="margin-top:24px">Cronología</h3>
    ${cronologia(d.contratos, d.solapes)}

    ${d.solapes.length ? `
      <h3 style="margin-top:26px">Períodos que se pisan</h3>
      ${tabla([
        {t:'Folios', c:'fol', r:f => `${esc(f.archivo_a)}<br>${esc(f.archivo_b)}`},
        {t:'Cruce', r:f => f.cruce === 'intercámara' ? `<span class="marca">${esc(f.cruce)}</span>` : esc(f.cruce)},
        {t:'Desde', k:'desde', c:'mono'},
        {t:'Hasta', k:'hasta', c:'mono'},
        {t:'Días', k:'dias', c:'num'},
      ], d.solapes)}` : ''}

    <h3 style="margin-top:26px">Contratos</h3>
    ${tabla([
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', k:'camara'},
      {t:'Cargo', r:f => esc(f.cargo || '—')},
      {t:'Inicio', k:'inicio', c:'mono'},
      {t:'Fin', r:f => f.fin ? `<span class="mono">${esc(f.fin)}</span>` : '<span class="nulo">Ø sin dato</span>'},
      {t:'Monto', c:'num', r:f => f.monto_centavos == null ? '<span class="nulo">Ø sin dato</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], d.contratos, {alClic:true})}

    ${d.interpretaciones.length ? `
      <div style="margin-top:26px">
        <span class="rotulo">Carril de interpretación</span>
        <p class="prosa" style="font-size:13px;margin:6px 0 12px">Nada de esto se leyó de un
          papel. Son hipótesis armadas cruzando los datos de arriba, y pueden estar mal.</p>
        ${d.interpretaciones.map(interpHTML).join('')}
      </div>` : ''}`);

  const tablas = vista.querySelectorAll('.tabla-env table');
  const ultima = tablas[tablas.length - 1];
  if (ultima) ultima.querySelectorAll('tbody tr').forEach(tr =>
    tr.onclick = () => location.hash = '#/documento/' + d.contratos[+tr.dataset.i].documento_id);
}

/* ── Carga de escaneos ─────────────────────────────────────────────────── */
let subiendo = false;

async function vIngesta() {
  const t = await api('/api/trabajo');
  const lote = localStorage.getItem('ufil.lote') || '';
  vista.innerHTML = bloque('f. 0000', 'Ingesta', `
    <h2>Cargar escaneos</h2>
    <p class="prosa">Arrastrá acá los PDF escaneados, o elegilos. Se guardan tal cual
      llegaron, bajo su propio hash y en solo lectura: <strong>el archivo que subís no se
      vuelve a tocar nunca más</strong>. Si un PDF ya estaba, no se duplica — se anota que
      apareció de nuevo y se sigue.</p>

    <div class="campos-lote">
      <label>Lote <input type="text" id="i-lote" value="${esc(lote)}"
        placeholder="contratos-camara-A-2024"></label>
      <label>Legajo <input type="text" id="i-legajo" placeholder="opcional"></label>
      <label>Quién carga <input type="text" id="i-operador"
        value="${esc(localStorage.getItem('ufil.revisor') || '')}" placeholder="apellido.nombre"></label>
    </div>

    <div class="soltar" id="soltar" tabindex="0" role="button"
         aria-label="Soltar archivos PDF acá o presionar para elegirlos">
      <b>Soltá los PDF acá</b>
      <span>o hacé clic para elegirlos · sólo PDF · hasta 200 MB cada uno</span>
      <input type="file" id="i-archivos" accept="application/pdf,.pdf" multiple hidden>
    </div>
    <div id="subidas"></div>

    <div style="display:flex; gap:10px; align-items:center; margin-top:18px; flex-wrap:wrap">
      <button class="boton" id="b-procesar" ${t.sin_leer ? '' : 'disabled'}>
        Procesar ${t.sin_leer || 0} documento${t.sin_leer === 1 ? '' : 's'} sin leer</button>
      <span class="rotulo" id="estado-trabajo"></span>
    </div>
    <div id="progreso"></div>

    ${t.lotes && t.lotes.length ? `
      <h3 style="margin-top:26px">Lotes cargados</h3>
      ${tabla([
        {t:'Lote', k:'lote'},
        {t:'Archivos', k:'archivos', c:'num'},
        {t:'Páginas', k:'paginas', c:'num'},
        {t:'Última carga', c:'fol', r:f => esc(String(f.ultimo || '').slice(0,16).replace('T',' '))},
      ], t.lotes)}` : ''}`);

  const zona = $('#soltar'), input = $('#i-archivos');
  zona.onclick = () => input.click();
  zona.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } };
  input.onchange = () => subir([...input.files]);
  ['dragenter','dragover'].forEach(ev => zona.addEventListener(ev, e => {
    e.preventDefault(); zona.classList.add('encima'); }));
  ['dragleave','drop'].forEach(ev => zona.addEventListener(ev, e => {
    e.preventDefault(); zona.classList.remove('encima'); }));
  zona.addEventListener('drop', e => subir([...e.dataTransfer.files]));

  $('#b-procesar').onclick = async () => {
    const r = await api('/api/procesar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({})});
    if (!r.ok) return alert(r.motivo || 'No se pudo arrancar');
    seguirTrabajo();
  };
  if (t.estado === 'corriendo') seguirTrabajo(); else pintarTrabajo(t);
}

async function subir(archivos) {
  if (subiendo || !archivos.length) return;
  const pdfs = archivos.filter(f => /\.pdf$/i.test(f.name) || f.type === 'application/pdf');
  const salteados = archivos.length - pdfs.length;
  if (!pdfs.length) return alert('Ninguno de esos archivos es un PDF.');

  const lote = ($('#i-lote').value || '').trim();
  if (!lote) { $('#i-lote').focus(); return alert('Poné un nombre de lote antes de subir.'); }
  localStorage.setItem('ufil.lote', lote);
  const operador = ($('#i-operador').value || '').trim();
  if (operador) localStorage.setItem('ufil.revisor', operador);

  subiendo = true;
  const caja = $('#subidas');
  caja.innerHTML = `<div class="lista-subida"></div>`;
  const lista = caja.firstElementChild;
  let nuevos = 0, dups = 0, fallos = 0;

  for (const [i, f] of pdfs.entries()) {
    const fila = document.createElement('div');
    fila.className = 'subida';
    fila.innerHTML = `<span class="fol">${i+1}/${pdfs.length}</span>
      <span class="nom">${esc(f.name)}</span><span class="res">subiendo…</span>`;
    lista.appendChild(fila);
    fila.scrollIntoView({block:'nearest'});
    try {
      const q = new URLSearchParams({nombre: f.name, lote,
        legajo: ($('#i-legajo').value || '').trim(), operador});
      const r = await fetch('/api/subir?' + q, {method:'POST',
        headers:{'Content-Type':'application/pdf'}, body: f});
      const j = await r.json();
      if (!r.ok || !j.ok) { fallos++; fila.querySelector('.res').innerHTML =
        `<span class="marca">${esc(j.error || 'error')}</span>`; }
      else if (j.duplicado) { dups++; fila.querySelector('.res').innerHTML =
        `<span class="nulo">ya estaba</span>`; }
      else { nuevos++; fila.querySelector('.res').innerHTML =
        `<span class="ok-txt">${j.paginas} pág.</span>`; }
    } catch (e) {
      fallos++; fila.querySelector('.res').innerHTML = `<span class="marca">${esc(e.message)}</span>`;
    }
  }
  subiendo = false;
  const resumen = document.createElement('p');
  resumen.className = 'prosa';
  resumen.style.marginTop = '12px';
  resumen.innerHTML = `<strong>${nuevos} nuevo${nuevos===1?'':'s'}</strong>, ${dups} ya estaban` +
    (fallos ? `, <span class="marca">${fallos} con error</span>` : '') +
    (salteados ? `, ${salteados} salteados por no ser PDF` : '') +
    `. Ahora tocá <em>Procesar</em>.`;
  caja.appendChild(resumen);

  const b = $('#b-procesar');
  const t = await api('/api/trabajo');
  b.disabled = !t.sin_leer;
  b.textContent = `Procesar ${t.sin_leer} documento${t.sin_leer===1?'':'s'} sin leer`;
  refrescarCuentas();
}

function pintarTrabajo(t) {
  const p = $('#progreso'); if (!p) return;
  if (t.estado === 'inactivo') { p.innerHTML = ''; return; }
  const pct = t.total ? Math.round(100 * t.hecho / t.total) : 0;
  const falta = t.faltan_segundos != null
    ? ` · faltan ~${t.faltan_segundos > 90 ? Math.round(t.faltan_segundos/60)+' min' : t.faltan_segundos+' s'}`
    : '';
  p.innerHTML = `
    <div class="progreso">
      <div class="cab"><span class="rotulo">${esc(t.etapa || t.estado)}</span>
        <span class="mono">${t.hecho}/${t.total}${esc(falta)}</span></div>
      <div class="riel"><i style="width:${pct}%"></i></div>
      ${t.estado === 'terminado' ? `<p class="prosa" style="font-size:13px;margin:10px 0 0">
         <strong>Listo.</strong> ${esc(t.mensaje)} · ${t.segundos} s.
         <a href="#/panel">Ver el panel</a> · <a href="#/cola">Ir a la cola</a></p>` : ''}
      ${t.estado === 'error' ? `<div class="aviso" style="margin-top:10px">
         <span class="sello alerta">Error</span><span>${esc(t.mensaje)}</span></div>` : ''}
      ${(t.errores || []).length ? `<details style="margin-top:10px"><summary class="rotulo">
         ${t.errores.length} documento(s) con problemas</summary>
         <ul style="margin-top:8px">${t.errores.slice(0,20).map(e =>
           `<li>${esc(e.etapa)}: ${esc(e.detalle)}</li>`).join('')}</ul></details>` : ''}
    </div>`;
}

let temporizador = null;
async function seguirTrabajo() {
  clearTimeout(temporizador);
  const t = await api('/api/trabajo');
  pintarTrabajo(t);
  const b = $('#b-procesar');
  if (b) b.disabled = t.estado === 'corriendo' || !t.sin_leer;
  if (t.estado === 'corriendo') {
    temporizador = setTimeout(seguirTrabajo, 1500);
  } else {
    refrescarCuentas();
  }
}

/* ── ruteo ─────────────────────────────────────────────────────────────── */
async function refrescarCuentas() {
  try {
    const p = await api('/api/panel');
    const c = $('#n-cola'), f = $('#n-fus');
    c.textContent = p.a_revisar; c.hidden = !p.a_revisar;
    f.textContent = p.fusiones;  f.hidden = !p.fusiones;
    $('#f-lote').textContent = 'lote ' + (p.lote || '—');
    const s = $('#sello-estado');
    s.textContent = p.a_revisar ? `${p.a_revisar} a revisar` : 'al día';
    s.className = 'sello ' + (p.a_revisar ? 'alerta' : 'ok');
  } catch (e) { /* base todavía vacía */ }
}

const rutas = [
  [/^#\/panel$/,                 vPanel],
  [/^#\/ingesta$/,               vIngesta],
  [/^#\/contratos$/,             vContratos],
  [/^#\/personas$/,              vPersonas],
  [/^#\/persona\/(\d+)$/,        vPersona],
  [/^#\/buscar\/?(.*)$/,         vBuscar],
  [/^#\/superposiciones$/,       vSuperposiciones],
  [/^#\/documento\/(\d+)$/,      vDocumento],
  [/^#\/cola$/,                  vCola],
  [/^#\/identidad$/,             vIdentidad],
  [/^#\/interpretacion$/,        vInterpretacion],
  [/^#\/consultas\/?(.*)$/,      vConsultas],
];

async function rutear() {
  const h = location.hash || '#/panel';
  document.querySelectorAll('nav a').forEach(a =>
    a.classList.toggle('activo', h.startsWith(a.getAttribute('href'))));
  vista.innerHTML = '<div class="cargando">Cargando…</div>';
  for (const [re, fn] of rutas) {
    const m = h.match(re);
    if (m) {
      try { return await fn(m[1]); }
      catch (e) { return vista.innerHTML =
        `<div class="bloque"><div class="marginalia"></div><div class="cuerpo">
         <div class="aviso"><span class="sello alerta">Error</span><span>${esc(e.message)}</span></div>
         </div></div>`; }
    }
  }
  location.hash = '#/panel';
}

$('#b-tema').onclick = () => {
  const actual = document.documentElement.dataset.tema;
  const nuevo = actual === 'oscuro' ? 'claro' : 'oscuro';
  document.documentElement.dataset.tema = nuevo;
  localStorage.setItem('ufil.tema', nuevo);
};
try { const t = localStorage.getItem('ufil.tema'); if (t) document.documentElement.dataset.tema = t; } catch (e) {}

$('#f-fecha').textContent = new Date().toLocaleDateString('es-AR');
addEventListener('hashchange', rutear);
rutear();
refrescarCuentas();
