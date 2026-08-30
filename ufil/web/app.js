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
  let r, j;
  try {
    r = await fetch(ruta, opciones);
    // Si el servidor se reinició, la sesión murió y esto es la pantalla de la clave.
    // Sin este chequeo, la app mostraría un error de sintaxis en vez de mandarte a
    // escribir la clave, que es lo único que hay que hacer.
    if (r.headers.get('X-UFIL-Acceso') === 'requerido') {
      location.reload();
      return new Promise(() => {});          // no sigue: la página se está recargando
    }
    j = await r.json();
  } catch (e) {
    const err = new Error('No se pudo hablar con el servidor. ¿Sigue corriendo?');
    err.caido = true;
    throw err;
  }
  if (!r.ok) {
    const err = new Error(j.error || r.statusText);
    err.noEncontrado = !!j.no_encontrado;
    err.estado = r.status;
    throw err;
  }
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

/* Estado vacío: en vez de una grilla de ceros, qué es esto y qué hacer ahora. */
/* Una vista entera en estado vacío, con la misma retícula que las demás. */
function vistaVacia(folio, rotulo, titulo, cabeza, texto) {
  vista.innerHTML = bloque(folio, rotulo,
    `<h2>${esc(titulo)}</h2>` + vacio(cabeza, esc(texto),
      {href:'#/ingesta', texto:'Cargar escaneos'}));
}

function vacio(titulo, texto, accion) {
  return `<div class="sin-datos">
    <b>${esc(titulo)}</b>
    <p>${texto}</p>
    ${accion ? `<a class="boton" href="${accion.href}">${esc(accion.texto)}</a>` : ''}
  </div>`;
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

  if (!p.documentos) {
    vista.innerHTML = bloque('f. 0001', 'Inicio', `
      <h2>Todavía no hay nada cargado</h2>
      <p class="prosa">Este sistema lee contratos escaneados, saca los datos con su
        ubicación exacta en el folio, y cruza los períodos para encontrar
        superposiciones. <strong>No modifica los originales y funciona sin conexión.</strong></p>
      ${vacio('Empezá cargando un lote de escaneos',
        'Arrastrá los PDF a la pantalla de carga y tocá Procesar. El sistema lee, extrae ' +
        'y cruza solo; lo que no puede leer con seguridad lo deja marcado para que lo ' +
        'revise una persona.',
        {href:'#/ingesta', texto:'Cargar escaneos'})}
      <p class="prosa" style="margin-top:18px;font-size:13px">
        ¿Primera vez? <a href="#/como-funciona">Cómo funciona</a> lo explica en una pantalla.</p>`);
    return;
  }

  const n = x => fmtNum.format(x);
  const destacados = p.destacados.map(d => `
    <a class="destacado-fila" href="#/persona/${d.persona_id}">
      <span class="dias mono">${d.dias}</span>
      <span class="quien">${esc(d.contratado)}</span>
      <span class="cruce ${d.cruce === 'intercámara' ? 'marca' : ''}">${esc(d.cruce)}</span>
      <span class="fol">${esc(d.archivo_a)} · ${esc(d.archivo_b)}</span>
    </a>`).join('');

  vista.innerHTML =
    bloque('f. 0001', 'Resumen', `
      <h2>Qué encontró el sistema</h2>
      <p class="prosa resumen">
        Sobre <strong>${n(p.documentos)} contratos</strong> leídos del lote
        «${esc(p.lote)}»: <strong>${n(p.personas_ambas_camaras)} personas</strong> figuran en
        las dos cámaras y <strong>${n(p.superposiciones)} pares</strong> de contratos se pisan
        en el tiempo${p.fechas_imposibles ? `, y <strong>${n(p.fechas_imposibles)}</strong>
        tiene${p.fechas_imposibles === 1 ? '' : 'n'} fechas imposibles` : ''}.
        El sistema resolvió solo el <strong>${p.cobertura_pct}%</strong> de los campos
        críticos; quedan <strong>${n(p.a_revisar)}</strong> esperando revisión
        ${p.excluidos ? `y <strong>${n(p.excluidos)} contratos afuera del cruce</strong>
          por faltarles algún dato firme` : ''}.
      </p>
      ${(p.contratos_repetidos || p.archivos_con_varios) ? `
        <div class="aviso" style="margin-top:14px">
          <span class="sello alerta" style="flex:none">Revisar</span>
          <span>${p.archivos_con_varios ? `<strong>${n(p.archivos_con_varios)} archivo(s)
            traen varios contratos adentro</strong> y se separaron solos. ` : ''}
            ${p.contratos_repetidos ? `<strong>${n(p.contratos_repetidos)} contrato(s)
            aparecen más de una vez</strong> y estarían contándose doble en los acumulados:
            <a href="#/consultas/08_contratos_repetidos">ver cuáles</a>.` : ''}</span>
        </div>` : ''}
      ${p.afuera ? `
        <div class="aviso" style="margin-top:14px">
          <span class="sello alerta" style="flex:none">Afuera</span>
          <span><strong>${n(p.afuera)} archivo(s) no produjeron ningún contrato</strong> y
            por lo tanto no entran en ninguno de estos números:
            <a href="#/afuera">ver cuáles y por qué</a>.</span>
        </div>` : ''}
      ${p.destacados.length ? `
        <h3 style="margin-top:20px">Las superposiciones más largas</h3>
        <div class="destacados">
          <div class="destacado-fila cab">
            <span class="dias">días</span><span class="quien">contratado/a</span>
            <span class="cruce">cruce</span><span class="fol">folios</span>
          </div>
          ${destacados}
        </div>
        <p class="prosa" style="font-size:13px;margin-top:10px">
          <a href="#/superposiciones">Ver las ${n(p.superposiciones)} superposiciones</a> ·
          <a href="#/personas">ver a todos los contratados</a></p>` : ''}`) +

    bloque('f. 0002', 'Lote', `
      <h2>Estado del lote</h2>
      <div class="cifras">
        <div class="cifra"><b>${n(p.documentos)}</b><span>documentos</span></div>
        <div class="cifra"><b>${n(p.paginas)}</b><span>páginas leídas</span></div>
        <div class="cifra ok"><b>${p.cobertura_pct}%</b><span>resuelto solo</span></div>
        <div class="cifra ${p.a_revisar ? 'alerta' : 'ok'}"><b>${n(p.a_revisar)}</b><span>a revisar</span></div>
        <div class="cifra ${p.conflictos ? 'alerta' : 'ok'}"><b>${n(p.conflictos)}</b><span>conflictos</span></div>
        <div class="cifra"><b>${n(p.verificados)}</b><span>verificados a mano</span></div>
        <div class="cifra"><b>${n(p.personas)}</b><span>personas</span></div>
        ${p.paginas_enderezadas ? `<div class="cifra"><b>${n(p.paginas_enderezadas)}</b>
          <span>fojas enderezadas</span></div>` : ''}
        <div class="cifra ancha"><b>${esc(fmtPesos(p.acumulado_centavos))}</b><span>monto leído en total</span></div>
      </div>
      <p class="prosa" style="font-size:12.5px;margin-top:10px">
        El total en pesos suma <strong>sólo los montos que se leyeron con seguridad</strong>.
        Es un piso, no el total del lote.${p.paginas_enderezadas ? `
        ${p.paginas_enderezadas === 1 ? 'Una foja llegó' : n(p.paginas_enderezadas) + ' fojas llegaron'}
        girada en el escaneo y se enderezó la copia de trabajo para poder leerla.` : ''}</p>
      ${(p.perfiles || []).length > 1 ? `
        <p class="prosa" style="font-size:12.5px">
          Se reconocieron <strong>${p.perfiles.length} formatos de formulario</strong> distintos:
          ${p.perfiles.map(f => `<span class="mono">${esc(f.perfil)}</span> (${f.n})`).join(', ')}.</p>` : ''}`) +

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
      ], cob)}
      ${p.excluidos ? `<p class="prosa" style="font-size:13px;margin-top:12px">
        <strong>${n(p.excluidos)} contratos quedaron fuera del cruce</strong> por faltarles
        algún dato firme: <a href="#/consultas/06_excluidos_del_cruce">ver cuáles y por qué</a>.</p>` : ''}`) +

    bloque('f. 0004', 'Salida', `
      <h2>Llevárselo</h2>
      <p class="prosa">Las tablas a planilla y el cuerpo a un documento de texto con
        interlineado 1,5, justificado y cuerpo 11. <strong>Cada afirmación del informe cita
        el archivo y la foja</strong> de donde salió el dato, para poder verificarla contra
        el original.</p>
      <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:12px">
        <a class="boton" href="/descargar?que=xlsx">Descargar la planilla (.xlsx)</a>
        <a class="boton gris" href="/descargar?que=rtf">Descargar el informe (.rtf)</a>
        <button class="boton gris" onclick="window.print()">Imprimir esta pantalla</button>
      </div>
      <p class="prosa" style="font-size:12.5px;margin-top:12px">La planilla abre con una
        portada que aclara qué campos no están verificados por una persona. Nada de lo que
        sale de acá debería incorporarse a un legajo sin cotejarlo contra el original.</p>`);
}

async function vContratos() {
  const filas = await api('/api/contratos');
  if (!filas.length) return vistaVacia('f. 0004', 'Datos', 'Contratos',
    'Todavía no hay contratos leídos',
    'Cargá un lote de escaneos y procesalo. Los contratos aparecen acá apenas termina.');
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
  if (!r.filas.length) return vistaVacia('f. 0005', 'Cruce', 'Superposición temporal',
    'No hay superposiciones para mostrar',
    'O no se detectó ninguna, o todavía no se procesó ningún lote. Sólo entran contratos ' +
    'con las dos fechas leídas con seguridad.');
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
  const paginas = d.paginas.length ? d.paginas : [{nro:1, ancho_pt:595, alto_pt:842}];
  const varios = d.hermanos.length > 1;

  const campos = d.campos.map(c => {
    const conf = d.conflictos[c.nombre];
    if (conf) {
      return `<div class="campo"><dt>${esc(c.nombre)}</dt><dd><div class="conflicto">${
        conf.map(v => `<div class="ruta"><span>${esc(v.ruta)}</span><span>${esc(v.valor)}</span></div>`).join('')
      }</div></dd></div>`;
    }
    const ancla = c.x0 != null
      ? `<button class="ancla" data-campo="${c.id}">f.${c.pagina_nro} · ▣</button>` : '';
    const tocado = c.estado === 'verificado' || c.estado === 'corregido';
    const marca = tocado
      ? ` <span class="sello ok" style="font-size:8.5px;padding:1px 5px;outline:none">✓ ${
           c.estado === 'corregido' ? 'cargado a mano' : 'verificado'}</span>` +
        ` <button class="deshacer" data-campo="${c.id}"
            title="volver a lo que había leído el sistema">deshacer</button>` : '';
    return `<div class="campo"><dt>${esc(c.nombre)}</dt>
      <dd>${celdaValor(c)}${ancla}${marca}</dd></div>`;
  }).join('');

  const tiras = paginas.map(p =>
    `<button class="foja" data-nro="${p.nro}"${p.rotacion ? ' data-girada="1"' : ''}
       title="${p.rotacion ? `esta foja llegó girada ${p.rotacion}° y se enderezó para leerla`
                           : `foja ${p.nro}`}">f. ${p.nro}${p.rotacion ? ' ↻' : ''}</button>`).join('');
  const enderezadas = paginas.filter(p => p.rotacion);

  vista.innerHTML = bloque('f. ' + String(id).padStart(4, '0'), 'Visor', `
    <h2>${esc(doc.archivo)}${varios ? ` <span class="rotulo">contrato ${doc.orden} de ${d.hermanos.length}</span>` : ''}</h2>
    <p class="prosa" style="font-size:13px">
      Cámara ${esc(doc.camara || '—')} · perfil <span class="mono">${esc(doc.perfil)}</span> ·
      lote ${esc(doc.lote || '—')} ·
      fojas <span class="mono">${doc.pagina_desde}–${doc.pagina_hasta}</span><br>
      <span class="mono" style="font-size:11px">sha256 ${esc(String(doc.sha256).slice(0, 32))}…</span></p>
    ${enderezadas.length ? `<div class="aviso" style="border-left-color:var(--sello);
      background:var(--sello-suave)"><span class="sello" style="flex:none">Enderezado</span>
      <span>${enderezadas.length === 1 ? 'La foja' : 'Las fojas'}
      ${enderezadas.map(p => `${p.nro} (${p.rotacion}°)`).join(', ')} llegó girada en el
      escaneo. <strong>El original no se tocó</strong>: se giró la copia de trabajo para
      poder leerla, y es esa la que ves acá.</span></div>` : ''}
    ${varios ? `<div class="aviso"><span class="sello alerta" style="flex:none">Ojo</span>
      <span>Este PDF trae <strong>${d.hermanos.length} contratos</strong> adentro. Estás
      viendo el número ${doc.orden}, que ocupa las fojas ${doc.pagina_desde} a
      ${doc.pagina_hasta}. Los otros:
      ${d.hermanos.filter(h => h.id !== doc.id).map(h =>
        `<a href="#/documento/${h.id}">#${h.orden} (f. ${h.pagina_desde}–${h.pagina_hasta})</a>`
      ).join(' · ')}</span></div>` : ''}
    <div class="visor">
      <div class="datos">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px">
          <span class="rotulo">Carril de datos — leído del documento</span>
        </div>
        ${campos}
      </div>
      <div class="lamina">
        ${paginas.length > 1 ? `<div class="fojas">${tiras}</div>` : ''}
        <div class="lienzo" id="lienzo">
          <img id="folio" alt="Foja de ${esc(doc.archivo)}">
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

  vista.querySelectorAll('.deshacer').forEach(b => b.onclick = async () => {
    const quien = revisor(); if (!quien) return;
    if (!confirm('¿Deshacer esta revisión? El campo vuelve a lo que había leído el sistema.')) return;
    try {
      await api('/api/campo', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({campo_id:+b.dataset.campo, accion:'revertir', quien})});
      await vDocumento(id); refrescarCuentas();
    } catch (e) { alert('No se pudo deshacer: ' + e.message); }
  });

  const recuadro = $('#recuadro');
  const folio = $('#folio');

  /* Abrir en la foja donde están los datos, no en la primera. En un expediente la
     primera suele ser la carátula, y arrancar ahí obliga a un clic de más siempre. */
  const cuenta = {};
  anclables.forEach(c => { if (c.pagina_nro) cuenta[c.pagina_nro] = (cuenta[c.pagina_nro] || 0) + 1; });
  const conDatos = Object.keys(cuenta).sort((a, b) => cuenta[b] - cuenta[a])[0];
  let actual = conDatos ? +conDatos : paginas[0].nro;

  /* Cambiar de foja: la imagen Y las dimensiones de referencia. Usar las de la primera
     página para todas hacía que el recuadro cayera corrido cuando el escaneo tenía
     hojas de tamaño distinto. */
  function verFoja(nro) {
    actual = nro;
    folio.src = `/pagina?doc=${id}&nro=${nro}`;
    folio.alt = `Foja ${nro} de ${doc.archivo}`;
    vista.querySelectorAll('.foja').forEach(b =>
      b.setAttribute('aria-current', String(+b.dataset.nro === nro)));
  }
  vista.querySelectorAll('.foja').forEach(b => b.onclick = () => {
    verFoja(+b.dataset.nro);
    recuadro.style.display = 'none';
    $('#pie-campo').textContent = 'tocá una ficha de anclaje';
    $('#pie-xy').textContent = '';
  });
  verFoja(actual);

  vista.querySelectorAll('.ancla').forEach(b => b.onclick = () => {
    const c = anclables.find(x => x.id === +b.dataset.campo);
    if (!c) return;
    const nro = c.pagina_nro || paginas[0].nro;
    if (nro !== actual) verFoja(nro);
    const pag = paginas.find(p => p.nro === nro) || paginas[0];
    recuadro.style.display = 'block';
    recuadro.style.left   = (100 * c.x0 / pag.ancho_pt) + '%';
    recuadro.style.top    = (100 * c.y0 / pag.alto_pt) + '%';
    recuadro.style.width  = (100 * (c.x1 - c.x0) / pag.ancho_pt) + '%';
    recuadro.style.height = (100 * (c.y1 - c.y0) / pag.alto_pt) + '%';
    recuadro.className = 'recuadro' + (c.nulo_motivo ? ' conf' : '');
    $('#pie-campo').textContent = 'campo: ' + c.nombre + (c.ruta ? ' · ruta ' + c.ruta : '');
    $('#pie-xy').textContent = `f.${nro} · [${[c.x0,c.y0,c.x1,c.y1].map(v=>Math.round(v)).join(',')}]`;
    vista.querySelectorAll('.ancla').forEach(o => o.setAttribute('aria-pressed', o === b));
  });
}

/* ── cola de revisión: el folio al lado, sin salir de la pantalla ──────── */
/* Antes cada campo costaba dos navegaciones (ir al folio y volver) y se perdía el
   lugar en la lista. Con 42 campos eso son 84 saltos de pantalla. Acá la foja
   acompaña a la fila que tiene el foco, con una lupa sobre el campo. */
let colaEstado = {filas: [], foco: 0};

async function vCola(campoId) {
  const filas = await api('/api/cola');
  // Se puede enlazar un campo puntual: #/cola/123 abre la cola parada en ese campo.
  // Sirve para decirle a un compañero "mirá este" sin explicarle dónde está.
  const pedido = campoId ? filas.findIndex(f => String(f.campo_id) === String(campoId)) : -1;
  colaEstado = {filas, foco: pedido >= 0 ? pedido : 0};
  if (!filas.length) {
    vista.innerHTML = bloque('f. 0006', 'Cola', `<h2>Cola de revisión</h2>
      ${vacio('No queda nada por revisar',
        'Todos los campos están resueltos o verificados. Cuando entre un lote nuevo, ' +
        'lo que el sistema no pueda sostener va a aparecer acá.',
        {href:'#/panel', texto:'Volver al panel'})}`);
    return;
  }
  const porDoc = new Set(filas.map(f => f.documento_id)).size;

  vista.innerHTML = bloque('f. 0006', 'Cola', `
    <h2>Cola de revisión</h2>
    <p class="prosa">${filas.length} campos en ${porDoc} documentos, ordenados por lo que
      más daño hace si queda mal. <strong>El folio está a la vista</strong>: no hace falta
      salir de acá.<span class="solo-teclado"> <kbd>J</kbd>/<kbd>K</kbd> para moverse,
      las teclas de cada fila para decidir.</span>
      <strong>Ninguna acción es «aceptar todo».</strong></p>
    <div class="cola-partida">
      <div class="cola" id="cola">${filas.map(filaCola).join('')}</div>
      <aside class="folio-lado" id="folio-lado">
        <div class="lupa" id="lupa"><img id="lupa-img" alt=""></div>
        <div class="pie-lamina"><span id="lupa-campo"></span><span id="lupa-xy"></span></div>
        <div class="lienzo" id="lienzo-cola">
          <img id="folio-cola" alt="">
          <div class="recuadro" id="recuadro-cola" style="display:none"></div>
        </div>
        <a class="chip" id="ir-doc" href="#/panel">ver el documento completo</a>
      </aside>
    </div>`);

  vista.querySelectorAll('[data-accion]').forEach(b => b.onclick = () => {
    colaEstado.foco = +b.closest('.fila').dataset.i;
    decidir(+b.dataset.campo, b.dataset.accion, b.dataset.valor);
  });
  vista.querySelectorAll('.fila').forEach(f => f.onclick = e => {
    if (e.target.closest('[data-accion]')) return;
    colaEstado.foco = +f.dataset.i; pintarFoco();
  });
  pintarFoco();
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
        <span class="etiqueta-campo ${f.clase === 'conflicto' ? 'alerta' : ''}">${esc(f.campo)}</span>
      </div>
      ${cuerpo}
    </div>
    <div class="acc">${acciones.map(([k, t, a, v]) =>
      `<button class="tecla" data-campo="${f.campo_id}" data-accion="${a}" data-valor="${esc(v)}">
         <kbd>${k}</kbd> ${esc(t)}</button>`).join('')}</div>
  </div>`;
}

/* Encuadra el campo en la lupa: la foja entera a la derecha se ve chica, y lo que hace
   falta para decidir es leer ESE renglón. */
function encuadrar(f) {
  const lupa = $('#lupa'), img = $('#lupa-img');
  if (!lupa || !img) return;
  const pag = f.pagina;
  if (!pag || f.x0 == null) {
    // Sin recuadro no hay lupa, pero el folio igual sirve: es lo que hay que mirar
    // para cargar el valor a mano.
    lupa.classList.add('sin-anclaje');
    img.removeAttribute('src');
    $('#lupa-campo').textContent = 'el sistema no encontró este campo en la foja';
    $('#lupa-xy').textContent = 'mirá el folio y cargalo a mano';
    const resp = f.pagina_respaldo;
    const folio0 = $('#folio-cola'), rec0 = $('#recuadro-cola');
    rec0.style.display = 'none';
    if (resp && resp.nro) {
      const src0 = `/pagina?doc=${f.documento_id}&nro=${resp.nro}`;
      if (folio0.getAttribute('src') !== src0) folio0.src = src0;
    } else {
      folio0.removeAttribute('src');
    }
    return;
  }
  lupa.classList.remove('sin-anclaje');
  const src = `/pagina?doc=${f.documento_id}&nro=${f.pagina_nro}`;
  if (img.getAttribute('src') !== src) img.src = src;

  const caja = {w: Math.max(f.x1 - f.x0, 8), h: Math.max(f.y1 - f.y0, 8)};
  const r = lupa.getBoundingClientRect();
  const aire = 1.5;
  // px mostrados por punto, acotado para no ampliar más allá de lo que el escaneo tiene
  const escala = Math.min(r.width / (caja.w * aire), r.height / (caja.h * aire * 2.2), 7);
  img.style.width = (pag.ancho_pt * escala) + 'px';
  img.style.left = -(f.x0 * escala - (r.width - caja.w * escala) / 2) + 'px';
  img.style.top = -(f.y0 * escala - (r.height - caja.h * escala) / 2) + 'px';
  $('#lupa-campo').textContent = `${f.campo}${f.ruta ? ' · ruta ' + f.ruta : ''}`;
  $('#lupa-xy').textContent = `f.${f.pagina_nro} · ${(escala / (200 / 72)).toFixed(1)}×`;

  const folio = $('#folio-cola'), rec = $('#recuadro-cola');
  if (folio.getAttribute('src') !== src) folio.src = src;
  rec.style.display = 'block';
  rec.style.left = (100 * f.x0 / pag.ancho_pt) + '%';
  rec.style.top = (100 * f.y0 / pag.alto_pt) + '%';
  rec.style.width = (100 * caja.w / pag.ancho_pt) + '%';
  rec.style.height = (100 * caja.h / pag.alto_pt) + '%';
  rec.className = 'recuadro' + (f.clase === 'conflicto' ? ' conf' : '');
}

function pintarFoco() {
  const filas = vista.querySelectorAll('.fila');
  if (!filas.length) return;
  colaEstado.foco = Math.max(0, Math.min(colaEstado.foco, filas.length - 1));
  filas.forEach((f, i) => f.classList.toggle('foco', i === colaEstado.foco));
  filas[colaEstado.foco].scrollIntoView({block: 'nearest'});
  const actual = colaEstado.filas[colaEstado.foco];
  if (actual && location.hash !== '#/cola/' + actual.campo_id) {
    history.replaceState(null, '', '#/cola/' + actual.campo_id);
  }
  const f = colaEstado.filas[colaEstado.foco];
  if (f) {
    encuadrar(f);
    const ir = $('#ir-doc');
    if (ir) ir.href = '#/documento/' + f.documento_id;
  }
}

async function decidir(campoId, accion, valor) {
  const quien = revisor();
  if (!quien) return;
  if (accion === 'pedir') {
    valor = (prompt('Valor tal como figura en el documento:') || '').trim();
    if (!valor) return;
    accion = 'corregir';
  }
  const posicion = colaEstado.foco;
  try {
    await api('/api/campo', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({campo_id: campoId, accion, valor, quien})});
    await vCola();
    // Quedarse donde estaba: al sacar una fila, la que sigue ocupa su lugar. Volver
    // al principio en cada decisión obligaba a bajar de nuevo cada vez.
    colaEstado.foco = posicion;
    pintarFoco();
    refrescarCuentas();
  } catch (e) { alert('No se pudo guardar: ' + e.message); }
}

document.addEventListener('keydown', e => {
  if (!location.hash.startsWith('#/cola') || e.target.tagName === 'INPUT') return;
  const f = colaEstado.filas[colaEstado.foco];
  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault();
    colaEstado.foco = Math.min(colaEstado.foco + 1, colaEstado.filas.length - 1); pintarFoco();
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault();
    colaEstado.foco = Math.max(colaEstado.foco - 1, 0); pintarFoco();
  } else if (f) {
    const fila = vista.querySelectorAll('.fila')[colaEstado.foco];
    if (!fila) return;
    const botones = [...fila.querySelectorAll('[data-accion]')];
    const kb = botones.find(b => b.querySelector('kbd').textContent.toLowerCase() === e.key.toLowerCase());
    if (kb) { e.preventDefault(); kb.click(); }
  }
});

addEventListener('resize', () => {
  if (location.hash.startsWith('#/cola') && colaEstado.filas[colaEstado.foco]) {
    encuadrar(colaEstado.filas[colaEstado.foco]);
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
  if (!items.length) return vistaVacia('f. 0008', 'Conjetura', 'Interpretación',
    'Todavía no hay hipótesis',
    'Se generan al procesar un lote, cruzando los datos ya extraídos. Cada una viene con ' +
    'los documentos que la sostienen.');
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
  if (!filas.length) return vistaVacia('f. 0011', 'Personas', 'Contratados',
    'Todavía no hay contratados',
    'Las personas se arman al procesar un lote: los contratos con el mismo CUIL se agrupan ' +
    'solos, y el resto queda separado hasta que alguien confirme.');
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

    <div class="consejo">
      <b>Un PDF por contrato es mejor que un PDF con muchos adentro.</b>
      <p>El sistema separa igual los contratos que vengan juntos en un mismo PDF, y
        tarda lo mismo: <span class="mono">25 s</span> contra <span class="mono">28 s</span>
        para los mismos doce contratos. La diferencia aparece cuando se vuelve a escanear
        parte de una pila.</p>
      <p><strong>Con un PDF por contrato</strong>, el sistema reconoce por huella digital
        los que ya tenía, no los vuelve a leer, y no los cuenta dos veces.
        <strong>Con todo en un PDF grande</strong> alcanza una hoja de diferencia para que
        sea un archivo nuevo: se relee entero y los contratos repetidos entran otra vez,
        inflando los acumulados.</p>
      <p class="medido">Medido: doce contratos subidos en dos tandas que se pisan en tres.
        Sueltos → 12 contratos, 0 repetidos. Todo junto → 15 contratos,
        <span class="marca">3 repetidos</span>.</p>
      <p>Si igual conviene escanear de corrido —y muchas veces conviene, porque es más
        rápido en el escáner—, hacelo: el sistema los separa y avisa cuáles quedaron
        repetidos. Sólo que después hay que resolverlos a mano.</p>
    </div>

    <div class="consejo">
      <b>Pedí que escaneen a 300 DPI, en escala de grises.</b>
      <p>Cómo se parte el PDF casi no mueve la aguja. <strong>Con qué calidad se escanea,
        sí, y mucho.</strong> Sobre papel de mala calidad —fotocopia de fotocopia, hoja
        torcida, contraste caído, que es como llega un expediente viejo— la diferencia
        entre escanear a 100 y a 300 DPI es de treinta y un puntos de exactitud.</p>
      <p class="medido">Medido sobre noventa contratos: a <span class="mono">100 DPI</span>
        se lee bien el <span class="marca">52,5 %</span> de los campos;
        a <span class="mono">300 DPI</span>, el <span class="mono">83,9 %</span>.
        Los dos casos, con <strong>cero errores silenciosos</strong>: cuando el escaneo
        es malo el sistema no inventa, deja el campo vacío y lo manda a revisión.</p>
      <p><strong>Más de 300 no hace falta:</strong> de ahí para arriba no se gana nada
        medible y el archivo pesa el doble. Y <strong>evitá el «modo texto»</strong> en
        blanco y negro puro que muchos escáneres traen puesto: lo que cae del lado
        equivocado del umbral se borra para siempre, y no hay software que lo recupere.</p>
      <p>Esto conviene pedirlo <strong>por escrito y antes de que empiecen</strong>.
        Reescanear dos mil fojas porque salieron a 100 DPI es una semana perdida.</p>
    </div>

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


/* ── Cómo funciona ─────────────────────────────────────────────────────── */
/* La pantalla que contesta lo que pregunta cualquiera que ve esto por primera vez:
   de dónde salen los datos, qué pasa si el sistema se equivoca, y qué NO hace. */
/* Estado del sistema: lo que en la terminal serían `diagnostico` y `verificar`, pero
   para alguien que nunca va a abrir una terminal. Sirve el primer día —¿está todo
   instalado?— y después como control periódico de que nada se movió. */
async function vSalud() {
  const s = await api('/api/salud');
  const simbolos = {ok: 'ok', aviso: 'Aviso', falla: 'Falta'};
  const clase = {ok: 'ok', aviso: 'atencion', falla: 'alerta'};

  const veredicto = s.puede_trabajar
    ? `<div class="aviso ${s.avisos ? 'atento' : 'bien'}">
         <span class="sello ${s.avisos ? 'atencion' : 'ok'}" style="flex:none">Listo</span>
         <span>El equipo tiene todo lo necesario para trabajar${
           s.avisos ? `, con ${s.avisos} aviso${s.avisos > 1 ? 's' : ''} que conviene mirar` : ''}.</span></div>`
    : `<div class="aviso"><span class="sello alerta" style="flex:none">Falta</span>
         <span>Todavía no se puede trabajar: faltan ${s.fallas} cosa${s.fallas > 1 ? 's' : ''}.
         Abajo está cada una con lo que hay que instalar.</span></div>`;

  const filas = s.chequeos.map(c => `
    <tr>
      <td><span class="sello ${clase[c.estado]}">${simbolos[c.estado]}</span></td>
      <td><b>${esc(c.nombre)}</b></td>
      <td>${esc(c.detalle)}${c.arreglo && c.estado !== 'ok'
        ? `<div class="arreglo mono">${esc(c.arreglo)}</div>` : ''}</td>
    </tr>`).join('');

  const inv = s.invariantes.length
    ? `<ul class="fallas">${s.invariantes.map(f => `<li>${esc(f)}</li>`).join('')}</ul>`
    : `<div class="aviso bien"><span class="sello ok" style="flex:none">Cumple</span>
         <span>Las reglas del pliego se siguen cumpliendo sobre los datos cargados:
         ningún campo con valor sin ubicación en la imagen, ninguna interpretación sin
         documento que la sostenga, ninguna fusión de identidad aplicada sola.</span></div>`;

  const i = s.integridad;
  const cobertura = i.total
    ? `<p class="prosa">De los <b>${i.total}</b> originales cargados,
        <b>${i.verificados}</b> fueron rehasheados alguna vez y siguen idénticos a como
        entraron.${i.total > i.verificados
          ? ` Faltan ${i.total - i.verificados}: cada comprobación toma un lote empezando
              por los que hace más tiempo que no se miran, así que corriéndola seguido el
              acervo entero queda cubierto.`
          : ' El acervo entero está cubierto.'}
        ${i.mas_viejo ? ` La verificación más antigua es del
          <span class="mono">${esc(String(i.mas_viejo).slice(0, 16).replace('T', ' '))}</span>.` : ''}</p>
       <p class="prosa" style="font-size:13px">Rehashear originales lee del disco archivo
         por archivo, así que no se hace al abrir esta pantalla: se pide.</p>
       <button class="boton" id="b-verificar">Comprobar los originales ahora</button>
       <div id="r-verificar"></div>`
    : `<p class="prosa">Todavía no hay documentos cargados, así que no hay nada que verificar.</p>`;

  vista.innerHTML =
    bloque('f. 0900', 'Equipo', `
      <h2>Estado del sistema</h2>
      <p class="prosa">Esta pantalla contesta dos preguntas distintas. Arriba: si esta
        computadora tiene instalado todo lo que hace falta. Abajo: si lo que ya está cargado
        sigue cumpliendo las reglas con las que se cargó.</p>
      ${veredicto}
      <div class="tabla-env"><table class="salud"><tbody>${filas}</tbody></table></div>`) +

    bloque('f. 0901', 'Reglas', `
      <h2>Las reglas siguen valiendo</h2>
      <p class="prosa">No es una promesa del instructivo: se vuelve a comprobar contra la
        base cada vez que se abre esta pantalla.</p>
      ${inv}`) +

    bloque('f. 0902', 'Originales', `
      <h2>Los originales no cambiaron</h2>
      <p class="prosa">El sistema guarda el hash de cada archivo tal como entró y lo vuelve a
        calcular cada tanto. Si alguien —con permisos de administrador, que es el único que
        puede— tocara un original, esto lo detecta.</p>
      ${cobertura}`);

  const boton = $('#b-verificar');
  if (boton) boton.onclick = async () => {
    boton.disabled = true;
    boton.textContent = 'Leyendo los originales…';
    try {
      const r = await api('/api/verificar', {method: 'POST'});
      $('#r-verificar').innerHTML = r.fallas.length
        ? `<div class="aviso" style="margin-top:12px">
             <span class="sello alerta" style="flex:none">Ojo</span>
             <span>${r.fallas.map(esc).join('<br>')}</span></div>`
        : `<div class="aviso bien" style="margin-top:12px">
             <span class="sello ok" style="flex:none">Intactos</span>
             <span>Se rehashearon <b>${r.revisados}</b> originales y los
             <b>${r.ok}</b> coinciden con el hash con el que entraron.
             Cubiertos hasta ahora: ${r.cubiertos} de ${r.total}.</span></div>`;
    } finally {
      boton.disabled = false;
      boton.textContent = 'Comprobar los originales otra vez';
    }
  };
}

/* Qué entró y no salió. Sin esta pantalla, subir trescientos PDF y que doce no den
   ningún contrato es invisible: el panel muestra 288 y nadie sabe que faltan doce.
   Un documento que se pierde en silencio es lo peor que puede hacer un sistema que
   existe justamente para no perder documentos. */
async function vAfuera() {
  const d = await api('/api/afuera');

  if (!d.afuera) {
    return vista.innerHTML = bloque('f. 0800', 'Control', `
      <h2>Ningún archivo quedó afuera</h2>
      <div class="aviso bien"><span class="sello ok" style="flex:none">Completo</span>
        <span>Los <b>${d.total_archivos}</b> archivos cargados produjeron al menos un
        contrato. No hay nada perdido en el camino.</span></div>
      <p class="prosa">Esta pantalla es un control: cada vez que un PDF entra y no sale
        ningún contrato de él, aparece acá con el motivo. Conviene mirarla después de
        cada lote.</p>`);
  }

  // Agrupadas por motivo: doce archivos con el mismo problema son un solo problema.
  const grupos = {};
  for (const f of d.filas) (grupos[f.clase] ??= []).push(f);

  const secciones = Object.entries(grupos).map(([clase, fs], i) => {
    const g = fs[0];
    return bloque(`f. 08${String(i + 1).padStart(2, '0')}`, `${fs.length} archivo${fs.length > 1 ? 's' : ''}`, `
      <h2>${esc(g.titulo)}</h2>
      <p class="prosa">${esc(g.que_hacer)}</p>
      ${clase === 'perfil_no_aplica' ? `<p class="prosa" style="font-size:13px">
        Formularios que el sistema conoce hoy:
        ${d.perfiles_conocidos.map(p => `<span class="mono">${esc(p)}</span>`).join(', ')}.
        Agregar uno nuevo no requiere programar: se copia un archivo de
        <span class="mono">ufil/perfiles/</span> y se le cambian los rótulos.</p>` : ''}
      ${tabla([
        {t: 'Archivo', k: 'archivo', c: 'mono'},
        {t: 'Fojas', c: 'num', r: f => f.paginas ?? '—'},
        {t: 'Lote', r: f => esc(f.lote || '—')},
        // Un archivo que nunca se pudo abrir no llegó a la etapa de lectura: decir
        // "no se leyó" ahí es ruido, no información.
        {t: 'Se leyó', r: f => f.paginas === null ? '—'
          : f.leido ? '<span class="sello">sí</span>'
          : '<span class="sello alerta">no</span>'},
      ], fs)}`);
  }).join('');

  vista.innerHTML = bloque('f. 0800', 'Control', `
      <h2>Quedaron afuera</h2>
      <div class="aviso"><span class="sello alerta" style="flex:none">Ojo</span>
        <span><b>${d.afuera}</b> de <b>${d.total_archivos}</b> archivos cargados no
        produjeron ningún contrato. No se perdieron —están registrados con su hash—
        pero <b>no entran en ningún cruce ni en ningún acumulado</b>.</span></div>
      <p class="prosa">Que un archivo quede afuera no siempre es un error: una nota de
        elevación o una constancia no son contratos y no tienen por qué producir uno. Lo
        que hay que descartar es lo otro: que sea un contrato que el sistema no supo
        reconocer. Por eso están agrupados por motivo, con qué hacer en cada caso.</p>`)
    + secciones;
}

function vComoFunciona() {
  vista.innerHTML =
    bloque('f. 0100', 'Qué es', `
      <h2>Cómo funciona</h2>
      <p class="prosa">Este sistema lee contratos escaneados y arma con ellos una tabla que
        se puede cruzar. Sirve para <strong>entender rápido un volumen de papel que hoy no se
        puede abarcar</strong> y para decidir dónde mirar.</p>
      <div class="aviso"><span class="sello alerta" style="flex:none">Importante</span>
        <span>No es un sistema de gestión del legajo y no produce piezas procesales.
        <strong>Lo que se incorpora formalmente al legajo se hace después, a mano, sobre la
        documentación original.</strong></span></div>`) +

    bloque('f. 0101', 'La regla', `
      <h2>Dos carriles que nunca se mezclan</h2>
      <p class="prosa">Es la única regla que hay que tener en la cabeza para leer cualquier
        pantalla del sistema.</p>
      <div class="carriles">
        <div class="carril carril--dato">
          <h3><span class="rotulo">Carril de datos</span> <span class="sello">Leído</span></h3>
          <p style="font-size:13px;margin:0 0 10px">Lo que dice el papel. Se muestra en
            <span class="mono">monoespaciada</span> y cada valor sabe de qué archivo, qué
            página y qué parte de la imagen salió.</p>
          <ul style="font-size:13px;margin:0;padding-left:18px">
            <li>No interviene ningún modelo que pueda inventar.</li>
            <li>Lo que no se puede leer se guarda vacío <b>con el motivo</b>, nunca completado.</li>
            <li>Un valor sin ubicación en la imagen no entra en la base.</li>
          </ul>
        </div>
        <div class="carril carril--interp">
          <h3><span class="rotulo">Carril de interpretación</span> <span class="sello">Conjetura</span></h3>
          <p class="interp-texto" style="font-size:14px;margin:0 0 10px">Lo que el sistema
            deduce cruzando esos datos: patrones, anomalías, cosas para mirar. Va en serif
            bastardilla y sobre otro fondo.</p>
          <ul style="font-size:13px;margin:0;padding-left:18px">
            <li>Puede equivocarse, y se presenta como lo que es.</li>
            <li>Cada afirmación linkea a los documentos que la sostienen.</li>
            <li>El sistema no guarda una hipótesis sin fuente: la rechaza.</li>
          </ul>
        </div>
      </div>
      <p class="prosa" style="margin-top:14px">Un fiscal tiene que poder mirar una pantalla y
        saber, sin pensarlo, si lo que está viendo salió de una fecha impresa en un contrato o
        de una conjetura del sistema. <strong>Por eso la tipografía cambia.</strong></p>`) +

    bloque('f. 0102', 'Garantías', `
      <h2>Qué NO puede pasar</h2>
      <p class="prosa">Estas cuatro no dependen de que alguien se acuerde: están puestas en la
        base de datos y hay pruebas automáticas que las verifican.</p>
      <div class="tabla-env"><table>
        <thead><tr><th>Nunca</th><th>Por qué no puede</th></tr></thead><tbody>
        <tr><td><b>Salir a internet</b></td><td>No hay una sola llamada de red en el programa.
          Ni las tipografías: se sirven desde el disco. El servidor escucha sólo en esta
          máquina.</td></tr>
        <tr><td><b>Tocar un original</b></td><td>Se guardan en modo solo lectura y el programa
          los abre sin permiso de escritura. Además se re-verifican solos con su huella
          digital y avisan si alguno cambió.</td></tr>
        <tr><td><b>Inventar un dato</b></td><td>La base rechaza un campo que tenga valor y
          motivo de ausencia a la vez, o ninguno de los dos. Ante la duda se guarda vacío con
          el motivo.</td></tr>
        <tr><td><b>Dar un dato sin respaldo</b></td><td>La base rechaza un valor que no diga
          de qué página y de qué parte de la imagen salió.</td></tr>
      </tbody></table></div>`) +

    bloque('f. 0103', 'El límite', `
      <h2>Dónde interviene una persona</h2>
      <p class="prosa">El sistema lee bien la mayoría de los campos, pero no todos, y eso
        <strong>es el diseño, no una falla</strong>. Preferimos que dude mucho antes que
        equivocarse en silencio: una omisión se corrige en treinta segundos, un monto mal
        leído sin marcar entra en todos los cruces y no lo ve nadie.</p>
      <ul class="prosa">
        <li>Cuando dos lecturas del mismo campo no coinciden, el sistema <strong>no
          elige</strong>: muestra las dos y espera.</li>
        <li>Cuando la lectura es dudosa, el dato se muestra rayado y va a la cola.</li>
        <li>Dos contratos con el mismo CUIL son la misma persona, y eso se resuelve solo. El
          nombre parecido, <strong>nunca</strong>: se propone y lo confirma alguien.</li>
        <li>Cada decisión humana queda registrada con quién y cuándo, y no se pierde si
          después se vuelve a procesar el lote.</li>
      </ul>
      <p class="prosa"><a href="#/cola">Ver la cola de revisión</a> ·
         <a href="#/panel">volver al panel</a></p>`);
}

/* ── ruteo ─────────────────────────────────────────────────────────────── */
const TITULOS = {
  '#/panel':'Panel', '#/ingesta':'Cargar escaneos', '#/buscar':'Buscar',
  '#/contratos':'Contratos', '#/personas':'Personas',
  '#/superposiciones':'Superposiciones', '#/cola':'Cola de revisión',
  '#/identidad':'Identidad', '#/interpretacion':'Interpretación',
  '#/consultas':'Consultas', '#/documento':'Documento', '#/persona':'Ficha',
  '#/como-funciona':'Cómo funciona', '#/salud':'Estado del sistema',
  '#/afuera':'Quedaron afuera',
};

async function refrescarCuentas() {
  try {
    const p = await api('/api/panel');
    const av = document.getElementById('aviso-demo');
    if (av) av.hidden = !p.demostracion;
    document.body.classList.toggle('con-demo', !!p.demostracion);
    const c = $('#n-cola'), f = $('#n-fus'), af = $('#n-afuera');
    c.textContent = p.a_revisar; c.hidden = !p.a_revisar;
    f.textContent = p.fusiones;  f.hidden = !p.fusiones;
    if (af) { af.textContent = p.afuera; af.hidden = !p.afuera; }
    $('#f-lote').textContent = 'lote ' + (p.lote || '—');
    const marca = document.getElementById('marca');
    if (marca) marca.hidden = !p.marca;
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
  [/^#\/cola\/?(\d*)$/,          vCola],
  [/^#\/identidad$/,             vIdentidad],
  [/^#\/interpretacion$/,        vInterpretacion],
  [/^#\/consultas\/?(.*)$/,      vConsultas],
  [/^#\/como-funciona$/,         vComoFunciona],
  [/^#\/afuera$/,                vAfuera],
  [/^#\/salud$/,                 vSalud],
];

async function rutear() {
  const h = location.hash || '#/panel';
  document.querySelectorAll('nav a').forEach(a =>
    a.classList.toggle('activo', h.startsWith(a.getAttribute('href'))));
  const base = '#/' + h.split('/')[1];
  document.title = (TITULOS[base] || 'Análisis documental') + ' · UFIL Paraná';
  vista.innerHTML = '<div class="esqueleto"><i></i><i></i><i></i></div>';
  for (const [re, fn] of rutas) {
    const m = h.match(re);
    if (m) {
      try { return await fn(m[1]); }
      catch (e) {
        // Lo que no existe y lo que se rompió no son lo mismo, y no se muestran igual.
        const cuerpo = e.noEncontrado
          ? `<h2>No se encontró</h2>` + vacio('Eso ya no está', esc(e.message),
              {href:'#/panel', texto:'Volver al panel'})
          : `<h2>Algo falló</h2>
             <div class="aviso"><span class="sello alerta">Error</span>
               <span>${esc(e.message)}</span></div>
             <p class="prosa">Si se repite, mirá la consola donde corre el servidor: el
               detalle completo queda ahí. Mientras tanto podés
               <a href="#/panel">volver al panel</a>.</p>`;
        return vista.innerHTML = bloque('—', e.noEncontrado ? 'Vacío' : 'Error', cuerpo);
      }
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
