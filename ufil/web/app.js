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
  [/^#\/contratos$/,             vContratos],
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
