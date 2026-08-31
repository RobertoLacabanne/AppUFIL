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

/* Fechas en formato argentino. La base guarda ISO —2016-07-01— porque es lo que
   ordena bien y no depende de dónde corra; la pantalla muestra 01/07/2016, que es lo
   que se escribe en un expediente. Se convierte acá, en un solo lugar. */
const fmtFecha = v => {
  if (!v) return '';
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return String(v);
  return `${m[3]}/${m[2]}/${m[1]}`;
};
/* Con hora, para sellos de tiempo: 30/08/2026 21:14 */
const fmtFechaHora = v => {
  if (!v) return '';
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : fmtFecha(v);
};
/* Plural sin paréntesis: «1 archivo», «3 archivos», y no «1 archivo(s)». */
const fmtPct = v => fmtNum.format(Math.round(v * 10) / 10) + '%';
const plural = (n, uno, muchos) => `${fmtNum.format(n)} ${n === 1 ? uno : muchos}`;

/* Nombres legibles de los campos. En la interfaz operativa nunca se muestra el nombre
   técnico: quien revisa lee «Fecha de inicio», no `fecha_inicio`. */
const NOMBRE_CAMPO = {
  nombre: 'Contratado', documento: 'Documento', cargo: 'Cargo',
  fecha_inicio: 'Fecha de inicio', fecha_fin: 'Fecha de finalización',
  fecha_contrato: 'Fecha del contrato', monto: 'Monto mensual',
  monto_total: 'Monto total', monto_total_letras: 'Monto total en letras',
  plazo_meses: 'Plazo en meses', comprobante: 'Número de comprobante',
};
/* En una factura los mismos campos dicen otra cosa: `nombre` no es el contratado sino
   quien la emitió, y `fecha_inicio` no es el inicio de nada sino la fecha de emisión.
   Rotularlos igual que en un contrato es afirmar algo que el papel no dice. */
const NOMBRE_CAMPO_POR_FAMILIA = {
  comprobante: {
    nombre: 'Emisor', documento: 'CUIT del emisor', fecha_inicio: 'Fecha de emisión',
    monto: 'Importe', fecha_fin: 'Sin uso en comprobantes',
  },
  // Un decreto no tiene contratado ni fecha de inicio: tiene una referencia y una
  // fecha. Dejarle el rótulo de contrato afirma algo que el documento no dice.
  acto: {
    nombre: 'Título o referencia', documento: 'Número o identificador',
    fecha_inicio: 'Fecha', fecha_fin: 'Sin uso en actos', monto: 'Importe',
  },
};
const rotularCampo = (c, familia) =>
  ((NOMBRE_CAMPO_POR_FAMILIA[familia] || {})[c])
  || NOMBRE_CAMPO[c] || String(c || '').replace(/_/g, ' ');

/* Estados de confianza: etiqueta y explicación. Es el mismo modelo que está en
   ufil/confianza.py; si se agrega uno allá, se agrega acá. */
const ESTADO = {
  automatico_alta:     ['Automático',          'ok'],
  pendiente_baja:      ['Pendiente',           'atencion'],
  conflicto:           ['Conflicto',           'alerta'],
  verificado:          ['Verificado',          'ok'],
  corregido:           ['Corregido',           'ok'],
  ilegible_confirmado: ['Ilegible confirmado', 'neutro'],
  ausente_confirmado:  ['Ausente confirmado',  'neutro'],
  no_revisado:         ['Sin revisar',         'atencion'],
};

/* Los íconos de los estados. Cinco trazos, sin relleno, del tamaño de la letra.

   No son adorno: son la segunda manera de decir lo mismo. Una fila que informa su
   estado sólo con color no le informa nada a quien no distingue el rojo del verde
   —entre el 5 y el 8 % de los varones—, ni a nadie cuando esto sale impreso en
   blanco y negro, que es como llega a una audiencia. Cada estado se dice tres
   veces: forma, palabra y color, en ese orden de importancia. */
const ICONO = {
  ok:      '<path d="M3 8.3l3.4 3.4L13 4.6" fill="none" stroke="currentColor" ' +
           'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
  atencion:'<path d="M8 1.9 15 13.8H1z" fill="none" stroke="currentColor" ' +
           'stroke-width="1.6" stroke-linejoin="round"/>' +
           '<path d="M8 6.2v3.3M8 11.6v.1" stroke="currentColor" stroke-width="1.7" ' +
           'stroke-linecap="round"/>',
  alerta:  '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" ' +
           'stroke-width="1.6"/><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" ' +
           'stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  neutro:  '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" ' +
           'stroke-width="1.6"/><path d="M4.8 8h6.4" stroke="currentColor" ' +
           'stroke-width="1.7" stroke-linecap="round"/>',
  trabajando:'<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" ' +
           'stroke-width="1.6" opacity=".35"/><path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" ' +
           'fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
};

/* El sello de estado, único para todo el sistema: ícono + palabra + color.
   `tono` es uno de ok / atencion / alerta / neutro / trabajando. */
const sello = (tono, texto, opts = {}) =>
  `<span class="estado estado--${tono}${opts.relleno ? ' estado--relleno' : ''}` +
  `${opts.gira ? ' estado--gira' : ''}"${opts.titulo ? ` title="${esc(opts.titulo)}"` : ''}>` +
  `<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">` +
  `${ICONO[tono] || ICONO.neutro}</svg>${esc(texto)}</span>`;

/* Pinta un sello ADENTRO de un nodo que ya existe, sin reemplazarlo: el nodo del
   techo se pinta en cada refresco y cambiarlo por otro le hace perder el id, los
   escuchadores y el lugar en el orden de tabulación. */
function pintarSello(el, tono, texto, opts = {}) {
  if (!el) return;
  el.className = `estado estado--${tono}${opts.relleno ? ' estado--relleno' : ''}`
    + (opts.gira ? ' estado--gira' : '');
  el.innerHTML = `<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"
    >${ICONO[tono] || ICONO.neutro}</svg>${esc(texto)}`;
  if (opts.titulo) el.title = opts.titulo; else el.removeAttribute('title');
  el.hidden = false;
}

const badgeEstado = e => {
  const [txt, tono] = ESTADO[e] || [e || '—', 'neutro'];
  return sello(tono, txt);
};

/* Los tipos de documento, en castellano. La clave es la que usa la base. */
const TIPO_DOC = {
  contrato_obra:'Contrato de obra', contrato_personal:'Contrato de personal',
  contrato_locacion:'Contrato de locación', factura:'Factura', recibo:'Recibo',
  remito:'Remito', decreto:'Decreto', resolucion:'Resolución', rendicion:'Rendición',
  caratula:'Carátula', nota:'Nota', continuacion:'Continuación',
  desconocida:'Sin reconocer',
};
const FAMILIA_DOC = {contrato:'Contrato', comprobante:'Comprobante de pago',
                     acto:'Acto administrativo'};
/* Por qué está esperando este campo. Es lo que se filtra en la cola. */
const CLASE_COLA = {conflicto:'Dos lecturas distintas', nulo:'No se pudo leer',
                    'baja confianza':'Leído con poca seguridad'};
/* Por qué el campo quedó vacío. La base guarda la clave; la pantalla dice la frase. */
const MOTIVO_NULO = {
  ilegible:'no se puede leer', ausente:'no está en el documento',
  ambiguo:'dice dos cosas distintas', conflicto:'dos lecturas no coinciden',
  manuscrito:'está escrito a mano', fuera_de_rango:'el valor no es posible',
};
/* La base guarda «A» y «B» porque así lo escribe el perfil de extracción. En pantalla
   eso no dice nada: «Cámara A» obliga a acordarse de cuál es cuál, y el que lee un
   informe no tiene por qué saberlo. */
const CAMARA = {A:'Diputados', B:'Senadores'};
const camaraTexto = c => c ? (CAMARA[c] || c) : '';

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
  // `lista` marca QUÉ muestra esta tabla. Hace falta cuando una pantalla tiene más de
  // una: enganchar el clic por «la última tabla» funcionaba hasta que se agregó otra
  // debajo, y entonces cada fila abría el documento equivocado.
  const marca = opts.lista ? ` data-lista="${esc(opts.lista)}"` : '';
  return `<div class="tabla-env"><table${marca}><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
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

/* ── La navegación, en dos niveles ─────────────────────────────────────────
   Dieciséis enlaces en una barra plana: en 1024 se partía en dos renglones y en un
   teléfono en cinco, y encontrar algo era leerlos todos. Ahora hay seis secciones
   arriba y, debajo, lo que hay adentro de la que está abierta.

   Dos barras y no un menú desplegable, a propósito. Un desplegable esconde: hay que
   saber qué hay adentro para ir a buscarlo, no anda con el dedo igual que con el
   mouse, y el que no lo encuentra concluye que el sistema no lo tiene. Acá lo de la
   sección abierta está siempre a la vista.

   Las cuentas de trabajo pendiente suben a la sección: si «Revisión» esconde 88 campos
   esperando, la barra tiene que decir 88 sin que haya que entrar. */
const SECCIONES = [
  {id: 'panel',    rotulo: 'Panel',           hash: '#/panel'},
  {id: 'ingesta',  rotulo: 'Cargar escaneos', hash: '#/ingesta'},
  {id: 'documentos', rotulo: 'Documentos', items: [
    {hash: '#/contratos',     rotulo: 'Contratos'},
    {hash: '#/comprobantes',  rotulo: 'Facturas y recibos'},
    {hash: '#/personas',      rotulo: 'Personas'},
    {hash: '#/buscar',        rotulo: 'Buscar'},
  ], tambien: ['#/documento', '#/persona']},
  {id: 'hallazgos', rotulo: 'Hallazgos', items: [
    {hash: '#/superposiciones', rotulo: 'Superposiciones'},
    {hash: '#/cruce',           rotulo: 'Facturado vs. contratado'},
    {hash: '#/interpretacion',  rotulo: 'Interpretación'},
    {hash: '#/consultas',       rotulo: 'Consultas'},
  ]},
  {id: 'revision', rotulo: 'Revisión', items: [
    {hash: '#/cola',      rotulo: 'Cola de revisión', cuenta: 'a_revisar'},
    {hash: '#/identidad', rotulo: 'Identidad',        cuenta: 'fusiones'},
    {hash: '#/afuera',    rotulo: 'Quedaron afuera',  cuenta: 'afuera'},
  ]},
  {id: 'sistema', rotulo: 'Sistema', items: [
    {hash: '#/legajos',       rotulo: 'Legajos'},
    {hash: '#/como-funciona', rotulo: 'Cómo funciona'},
    {hash: '#/salud',         rotulo: 'Estado del sistema'},
  ]},
];

/* Las últimas cuentas que devolvió el panel, para pintar los números de la barra. */
let cuentas = {};

const seccionDe = hash => {
  const base = '#/' + String(hash || '').split('/')[1];
  return SECCIONES.find(s => s.hash === base
      || (s.items || []).some(i => i.hash === base)
      || (s.tambien || []).includes(base));
};

/* Un ícono por sección. Trazo simple, sin relleno: al lado de una tipografía nítida,
   un ícono relleno pesa más que la palabra y se lleva la lectura. */
const ICONO_SECCION = {
  panel:      '<path d="M2.5 9.5 10 3l7.5 6.5M4.5 8.6V17h11V8.6" fill="none"/>',
  ingesta:    '<path d="M10 13.5V3.5M6 7.2 10 3.2l4 4M3.5 13v3.5h13V13" fill="none"/>',
  documentos: '<path d="M4.5 2.5h8L15.5 6v11.5h-11zM12 2.6V6h3.4M7 10h6M7 13h4" fill="none"/>',
  hallazgos:  '<circle cx="8.6" cy="8.6" r="5.1" fill="none"/><path d="M12.4 12.4 17 17" fill="none"/>',
  revision:   '<path d="M3 5.4 5 7.4 8.4 4M3 13.4l2 2 3.4-3.4M11 5.6h6M11 13.6h6" fill="none"/>',
  sistema:    '<circle cx="10" cy="10" r="2.6" fill="none"/><path d="M10 2.6v2.2M10 15.2v2.2M2.6 10h2.2M15.2 10h2.2M4.8 4.8l1.6 1.6M13.6 13.6l1.6 1.6M15.2 4.8l-1.6 1.6M6.4 13.6l-1.6 1.6" fill="none"/>',
};
const iconoSeccion = id =>
  `<svg class="ico" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
        stroke="currentColor" stroke-width="1.5" stroke-linecap="round"
        stroke-linejoin="round">${ICONO_SECCION[id] || ICONO_SECCION.sistema}</svg>`;

function pintarNav(hash) {
  // Sin `|| SECCIONES[0]`: una pantalla que no está en ninguna sección —«Acerca del
  // sistema»— no puede dejar «Panel» marcado como si estuvieras ahí. Estar en un
  // lugar y que la barra diga otro es peor que no marcar nada.
  const activa = seccionDe(hash);
  const num = clave => Number(cuentas[clave] || 0);
  const chip = (n, que) => n
    ? ` <span class="cuenta" title="${esc(plural(n, que + ' pendiente', que + 's pendientes'))}"
        >${fmtNum.format(n)}</span>` : '';

  // Lo del pie también se marca: es a donde va a parar quien no está en ninguna
  // sección, y sin marca esa pantalla no aparece en ningún lado de la barra.
  document.querySelectorAll('.lateral-pie a').forEach(a => {
    const acá = hash.startsWith(a.getAttribute('href'));
    a.classList.toggle('activo', acá);
    if (acá) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });

  $('#nav-secciones').innerHTML = SECCIONES.map(s => {
    const abierta = s === activa;
    // La sección lleva la suma de lo que hay pendiente adentro. Cerrada, es la única
    // manera de enterarse de que adentro quedó trabajo sin hacer.
    const n = (s.items || []).reduce((t, i) => t + (i.cuenta ? num(i.cuenta) : 0), 0);
    const destino = s.hash || s.items[0].hash;
    const cabeza = `<a href="${destino}" class="cabeza ${abierta ? 'activo' : ''}"
        ${abierta ? 'aria-current="true"' : ''}>${iconoSeccion(s.id)}
        <span class="txt">${esc(s.rotulo)}</span>${chip(n, 'cosa')}</a>`;
    if (!abierta || !(s.items || []).length) return `<div class="grupo">${cabeza}</div>`;
    const items = s.items.map(i =>
      `<a href="${i.hash}" class="${hash.startsWith(i.hash) ? 'activo' : ''}"
         ${hash.startsWith(i.hash) ? 'aria-current="page"' : ''}
         ><span class="txt">${esc(i.rotulo)}</span>${chip(i.cuenta ? num(i.cuenta) : 0, 'cosa')}</a>`
    ).join('');
    return `<div class="grupo">${cabeza}<div class="items">${items}</div></div>`;
  }).join('');
  medirTecho();
}

/* ── Tabla grande: buscar, ordenar y traer de a poco ───────────────────────
   Con 1.500 contratos, una tabla suelta no sirve para nada: son 52.000 px de alto y no
   hay forma de encontrar a alguien salvo desplazarse leyendo. Medido en un legajo del
   tamaño de una causa de verdad, la de facturas pintaba 3.047 filas, 51.085 nodos y
   106.400 px de alto — cien metros de página.

   Tres cosas, y ninguna esconde nada:
     · un campo que filtra sobre TODAS las filas, no sobre las pintadas;
     · orden por columna, haciendo clic en el encabezado;
     · se pintan de a 150 y el resto se trae con un botón que dice cuántas faltan.

   El filtro busca sobre el texto de la fila sin tildes ni mayúsculas: quien busca
   «peres» tiene que encontrar a Pérez, porque el nombre puede venir de un OCR y no se
   sabe cómo quedó escrito. */
const POR_TANDA = 150;

const sinTildes = s => String(s ?? '')
  .normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function tablaBuscable(destino, cols, filas, opts = {}) {
  const estado = {q: '', orden: null, desc: false, mostradas: POR_TANDA};

  // El texto por el que se busca cada fila: los valores crudos, no el HTML pintado.
  // Sobre el HTML, buscar «span» encontraría todas.
  const textoDe = f => sinTildes(cols.map(c => c.k ? f[c.k] : (c.b ? c.b(f) : '')).join(' ')
                                 + ' ' + Object.values(f).join(' '));
  filas.forEach(f => { f.__texto = textoDe(f); });

  const valorDe = (f, c) => {
    if (c.b) return c.b(f);                 // `b` = valor para ordenar y buscar
    if (c.k) return f[c.k];
    return null;
  };

  function visibles() {
    let v = filas;
    if (estado.q) {
      const t = sinTildes(estado.q);
      v = v.filter(f => f.__texto.includes(t));
    }
    if (estado.orden != null) {
      const c = cols[estado.orden];
      v = [...v].sort((a, b) => {
        const x = valorDe(a, c), y = valorDe(b, c);
        if (x == null && y == null) return 0;
        if (x == null) return 1;            // lo que falta va al final, siempre
        if (y == null) return -1;
        const n = (typeof x === 'number' && typeof y === 'number')
          ? x - y : String(x).localeCompare(String(y), 'es');
        return estado.desc ? -n : n;
      });
    }
    return v;
  }

  function pintar() {
    const v = visibles();
    const tanda = v.slice(0, estado.mostradas);
    const th = cols.map((c, i) => {
      const act = estado.orden === i ? (estado.desc ? ' desc' : ' asc') : '';
      return `<th class="ord${act}" data-col="${i}" title="ordenar por ${esc(c.t)}"
                >${esc(c.t)}</th>`;
    }).join('');
    const tr = tanda.map((f, i) => `<tr class="${opts.alClic ? 'clic' : ''}"
        data-i="${filas.indexOf(f)}">${
      cols.map(c => `<td class="${c.c || ''}">${c.r ? c.r(f) : esc(f[c.k] ?? '')}</td>`).join('')
    }</tr>`).join('');

    destino.innerHTML = `
      <div class="buscador-tabla">
        <label class="campo-buscar">
          <input type="search" placeholder="${esc(opts.placeholder || 'Buscar en la tabla…')}"
                 value="${esc(estado.q)}" autocomplete="off">
        </label>
        <span class="cuantas">${v.length === filas.length
          ? plural(filas.length, 'fila', 'filas')
          : `<b>${fmtNum.format(v.length)}</b> de ${fmtNum.format(filas.length)}`}</span>
        ${estado.q || estado.orden != null
          ? `<button class="boton gris limpiar-tabla">Quitar filtro y orden</button>` : ''}
      </div>
      ${v.length ? `<div class="tabla-env"><table${opts.lista ? ` data-lista="${esc(opts.lista)}"` : ''}
          ><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`
        : `<div class="tabla-env"><div class="vacio">Ninguna fila dice
             «${esc(estado.q)}».</div></div>`}
      ${tanda.length < v.length ? `<button class="mas-tabla">Ver
        ${plural(Math.min(POR_TANDA, v.length - tanda.length), 'fila más', 'filas más')}
        <span>quedan ${fmtNum.format(v.length - tanda.length)}</span></button>` : ''}`;

    const buscar = destino.querySelector('input[type=search]');
    // Se repinta al escribir, pero conservando el foco y el cursor: repintar el campo
    // debajo de los dedos hace que se pierdan letras.
    buscar.oninput = () => {
      const pos = buscar.selectionStart;
      estado.q = buscar.value;
      estado.mostradas = POR_TANDA;
      pintar();
      const nuevo = destino.querySelector('input[type=search]');
      nuevo.focus();
      nuevo.setSelectionRange(pos, pos);
    };
    destino.querySelectorAll('th.ord').forEach(th => th.onclick = () => {
      const i = +th.dataset.col;
      estado.desc = estado.orden === i ? !estado.desc : false;
      estado.orden = i;
      estado.mostradas = POR_TANDA;
      pintar();
    });
    const limpiar = destino.querySelector('.limpiar-tabla');
    if (limpiar) limpiar.onclick = () => {
      estado.q = ''; estado.orden = null; estado.desc = false;
      estado.mostradas = POR_TANDA; pintar();
    };
    const mas = destino.querySelector('.mas-tabla');
    if (mas) mas.onclick = () => { estado.mostradas += POR_TANDA; pintar(); };
    if (opts.alClic) destino.querySelectorAll('tbody tr').forEach(tr =>
      tr.onclick = () => opts.alClic(filas[+tr.dataset.i]));
  }

  pintar();
}

/* ── vistas ────────────────────────────────────────────────────────────── */
/* ── legajos ───────────────────────────────────────────────────────────────
   La portada. Se entra por acá y recién después se ve nada más.

   Cada legajo es una base separada: mientras uno está abierto, el sistema no tiene
   forma de ver los otros. Por eso esta pantalla no es un filtro ni un selector
   decorativo — es el único lugar donde los legajos conviven, y es a propósito. */
async function vLegajos() {
  const r = await api('/api/legajos');
  const activos = r.legajos.filter(l => l.estado === 'activo');
  const archivados = r.legajos.filter(l => l.estado !== 'activo');
  const papelera = r.papelera || [];

  const filaFecha = f => f.ultima_actividad ? fmtFecha(f.ultima_actividad) : '—';
  const cols = [
    {t:'Número', c:'mono', r:f => `<b>${esc(f.numero)}</b>`},
    {t:'Carátula', r:f => esc(f.caratula) + (f.demostracion
        ? ' ' + sello('alerta', 'datos de prueba') : '')},
    // Vacío de verdad cuando no hay fiscal cargado: en la tabla de escritorio el CSS
    // le pone la raya, y en el teléfono —donde cada renglón cuesta— no aparece nada.
    {t:'Fiscal responsable', r:f => esc(f.fiscal || '')},
    {t:'Documentos', c:'num', r:f => f.documentos
        ? fmtNum.format(f.documentos) : '<span class="apagado">sin material</span>'},
    // Un legajo vacío no está «al día»: no hay nada revisado porque no hay nada cargado.
    // Poner el sello verde ahí sería decir que está terminado un trabajo que no empezó.
    {t:'Revisiones pendientes', c:'num', r:f => !f.documentos ? '—' : (f.pendientes
        ? sello('atencion', plural(f.pendientes, 'campo', 'campos'))
        : sello('ok', 'al día'))},
    {t:'Última actividad', c:'mono', r:filaFecha},
    // La eliminación vive en su propia columna y no en el renglón que se toca para
    // abrir. Un botón de borrar adentro de una fila entera clicable es un accidente
    // esperando la mano apurada de un martes.
    {t:'', c:'acciones', r:f =>
      `<button class="mini peligro" data-borrar="${esc(f.slug)}"
               title="Eliminar el legajo ${esc(f.numero)}">Eliminar</button>`},
  ];

  const listado = activos.length
    ? `<div class="tabla-legajos">${tabla(cols, activos, {alClic: true})}</div>`
    : vacio('Todavía no hay ningún legajo',
        'Un legajo es una causa: sus documentos, sus personas y sus totales viven en un ' +
        'archivo aparte y no se cruzan con los de ninguna otra. Creá el primero acá abajo.');

  vista.innerHTML =
    bloque('f. 0000', 'Índice de legajos', `
      <h2>¿Sobre qué legajo vas a trabajar?</h2>
      <p class="prosa">Cada legajo tiene su propia base de datos. Mientras trabajás en uno,
        el sistema <strong>no puede ver ni sumar</strong> nada de los demás: no es un filtro
        que se pueda olvidar, están en archivos distintos.</p>
      ${listado}` +
      (archivados.length ? `
      <details class="archivados">
        <summary>${plural(archivados.length, 'legajo archivado', 'legajos archivados')}</summary>
        <div class="tabla-legajos">${tabla(cols, archivados, {alClic: true})}</div>
      </details>` : '')) +
    bloque('f. 0000', 'Alta', `
      <h2>Abrir un legajo nuevo</h2>
      <form id="f-legajo" class="form-legajo">
        <label>Número de legajo
          <input name="numero" required placeholder="87.933" autocomplete="off"></label>
        <label>Carátula
          <input name="caratula" required placeholder="Contratos Legislatura"
                 autocomplete="off"></label>
        <label>Fiscal responsable <span class="opt">(opcional)</span>
          <input name="fiscal" autocomplete="off"></label>
        <button class="boton" type="submit">Crear el legajo</button>
      </form>
      <p id="err-legajo" class="aviso" hidden></p>
      <p class="prosa" style="font-size:13px">El número queda como nombre de la carpeta en
        disco, para que mirando los archivos se entienda qué hay adentro de cada una.</p>`) +
    papeleraHTML(papelera);

  vista.querySelectorAll('tbody tr').forEach(tr => tr.onclick = ev => {
    if (ev.target.closest('button')) return;      // los botones hacen lo suyo
    const lista = tr.closest('details') ? archivados : activos;
    abrirLegajo(lista[+tr.dataset.i].slug);
  });
  vista.querySelectorAll('[data-borrar]').forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    const l = r.legajos.find(x => x.slug === b.dataset.borrar);
    if (l) pedirEliminar(l);
  });
  engancharPapelera(papelera);

  $('#f-legajo').onsubmit = async ev => {
    ev.preventDefault();
    const d = Object.fromEntries(new FormData(ev.target));
    const err = $('#err-legajo');
    try {
      const nuevo = await api('/api/legajos', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...d, quien: revisor()})});
      abrirLegajo(nuevo.slug);
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    }
  };
}

/* ── Eliminar un legajo ─────────────────────────────────────────────────────
   Lo que se elimina no se borra: la carpeta entera —base, imágenes de página y los
   PDF que se subieron— se mueve a la papelera y se puede traer de vuelta completa.
   Eso hay que DECIRLO en el cartel, porque de un botón rojo que dice «Eliminar»
   cualquiera supone lo peor y no lo toca ni cuando corresponde.

   Y para confirmar hay que escribir el número del legajo. No es una molestia
   gratuita: una casilla que se tilda se tilda mirando el cartel, y el número obliga
   a mirar CUÁL es el legajo que se está por sacar de la lista. */
const pesoLegible = b => {
  if (!b) return '—';
  const u = ['B', 'kB', 'MB', 'GB'];
  let i = 0, n = b;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i ? n.toFixed(1) : Math.round(n)} ${u[i]}`;
};

function dialogo(html) {
  const d = document.createElement('dialog');
  d.className = 'dialogo';
  d.innerHTML = html;
  document.body.appendChild(d);
  d.addEventListener('close', () => d.remove());
  d.showModal();
  return d;
}

function pedirEliminar(l) {
  const d = dialogo(`
    <form method="dialog" id="f-borrar">
      <h3>Eliminar el legajo ${esc(l.numero)}</h3>
      <p class="prosa">${esc(l.caratula)}</p>
      <div class="aviso">${sello('atencion', 'Se puede deshacer')}
        <span>El legajo sale de la lista y su carpeta entera —la base, las imágenes de
          página y los PDF que se subieron— se guarda en la papelera. Desde ahí se
          puede traer de vuelta con todo adentro.
          ${l.documentos ? `Son <strong>${fmtNum.format(l.documentos)}</strong>
            ${l.documentos === 1 ? 'documento' : 'documentos'}
            ${l.pendientes ? `y <strong>${fmtNum.format(l.pendientes)}</strong>
              ${l.pendientes === 1 ? 'campo revisado a mano' : 'campos revisados a mano'}` : ''}.`
            : 'No tiene material cargado.'}</span></div>
      <label for="conf-borrar">Escribí el número del legajo para confirmar:
        <b class="mono">${esc(l.numero)}</b></label>
      <input id="conf-borrar" autocomplete="off" autocapitalize="off" spellcheck="false">
      <p class="mal" id="err-borrar" hidden></p>
      <div class="botonera">
        <button class="boton gris" value="no" type="submit">No, dejalo</button>
        <button class="boton peligro" id="b-confirmar" type="button" disabled>
          Eliminar el legajo</button>
      </div>
    </form>`);

  const campo = $('#conf-borrar', d), ok = $('#b-confirmar', d);
  // El botón se prende sólo cuando lo escrito coincide. Un botón prendido que después
  // rechaza es un botón que enseña a apretar sin leer.
  campo.oninput = () => { ok.disabled = campo.value.trim() !== l.numero.trim(); };
  campo.focus();
  ok.onclick = async () => {
    ok.disabled = true;
    ok.textContent = 'eliminando…';
    try {
      const res = await api('/api/legajo/eliminar', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({slug: l.slug, confirmacion: campo.value})});
      d.close();
      // Si era el que estaba abierto, la cookie ya no vale: recargar es lo único
      // honesto, porque en pantalla quedaron datos de un legajo que ya no está.
      if (res.cerrado) { location.hash = '#/legajos'; return location.reload(); }
      vLegajos();
    } catch (e) {
      const err = $('#err-borrar', d);
      err.textContent = e.message; err.hidden = false;
      ok.disabled = false; ok.textContent = 'Eliminar el legajo';
    }
  };
}

function papeleraHTML(p) {
  if (!p.length) return '';
  const total = p.reduce((t, x) => t + (x.bytes || 0), 0);
  const cols = [
    {t:'Número', c:'mono', r:f => esc(f.numero)},
    {t:'Eliminado', c:'mono', r:f => esc(fechaDeMarca(f.eliminado_en))},
    {t:'Documentos', c:'num', r:f => f.documentos ? fmtNum.format(f.documentos) : '—'},
    {t:'Ocupa', c:'num mono', r:f => esc(pesoLegible(f.bytes))},
    {t:'', c:'acciones', r:f =>
      `<button class="mini" data-restaurar="${esc(f.marca)}">Restaurar</button>
       <button class="mini peligro" data-destruir="${esc(f.marca)}">Borrar del disco</button>`},
  ];
  return bloque('f. 0000', 'Papelera', `
    <h2>Legajos eliminados</h2>
    <p class="prosa">Están completos y se pueden restaurar${total
      ? `, y siguen ocupando <strong>${esc(pesoLegible(total))}</strong> de disco: si
         hace falta lugar, acá se libera` : ''}.
      <strong>Borrarlos del disco no tiene vuelta atrás.</strong></p>
    <div class="tabla-legajos">${tabla(cols, p)}</div>`);
}

/* La marca guarda la fecha como `20260831-141203`, que es un buen nombre de carpeta y
   una mala cosa para leer. */
function fechaDeMarca(m) {
  const g = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(m || '');
  return g ? `${g[3]}/${g[2]}/${g[1]} ${g[4]}:${g[5]}` : (m || '—');
}

function engancharPapelera(p) {
  vista.querySelectorAll('[data-restaurar]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      await api('/api/papelera/restaurar', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({marca: b.dataset.restaurar})});
      vLegajos();
    } catch (e) { alert('No se pudo restaurar: ' + e.message); b.disabled = false; }
  });
  vista.querySelectorAll('[data-destruir]').forEach(b => b.onclick = () => {
    const f = p.find(x => x.marca === b.dataset.destruir);
    if (!f) return;
    const d = dialogo(`
      <form method="dialog">
        <h3>Borrar del disco el legajo ${esc(f.numero)}</h3>
        <div class="aviso alerta">${sello('alerta', 'Sin vuelta atrás')}
          <span>Se borran la base, las imágenes de página y <strong>los PDF que se
            subieron</strong>. Si esos PDF no están copiados en otro lado, esta es la
            última copia. Se liberan ${esc(pesoLegible(f.bytes))}.</span></div>
        <label for="conf-destruir">Escribí el número del legajo para confirmar:
          <b class="mono">${esc(f.numero)}</b></label>
        <input id="conf-destruir" autocomplete="off" spellcheck="false">
        <p class="mal" id="err-destruir" hidden></p>
        <div class="botonera">
          <button class="boton gris" value="no" type="submit">Mejor no</button>
          <button class="boton peligro" id="b-destruir" type="button" disabled>
            Borrar definitivamente</button>
        </div>
      </form>`);
    const campo = $('#conf-destruir', d), ok = $('#b-destruir', d);
    campo.oninput = () => { ok.disabled = campo.value.trim() !== f.numero.trim(); };
    campo.focus();
    ok.onclick = async () => {
      ok.disabled = true; ok.textContent = 'borrando…';
      try {
        await api('/api/papelera/destruir', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({marca: f.marca, confirmacion: campo.value})});
        d.close(); vLegajos();
      } catch (e) {
        const err = $('#err-destruir', d);
        err.textContent = e.message; err.hidden = false;
        ok.disabled = false; ok.textContent = 'Borrar definitivamente';
      }
    };
  });
}

/* Abrir un legajo cambia la base entera: se recarga la página en vez de repintar.
   Es deliberado — así no queda ni un dato del legajo anterior en pantalla. */
async function abrirLegajo(slug) {
  await api('/api/legajo/abrir', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({slug})});
  location.hash = slug ? '#/panel' : '#/legajos';
  location.reload();
}

async function vPanel() {
  const p = await api('/api/panel');
  // `cargo` se saca: no aporta al estado de lectura y alarga la tabla. `fecha_fin` de
  // un comprobante también: una factura no tiene período, el campo se declara sólo para
  // que el registro tenga la misma forma, y siempre está vacío.
  const cob = p.cobertura.filter(c =>
    c.campo !== 'cargo' && !(c.familia === 'comprobante' && c.campo === 'fecha_fin'));

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
  const t = p.totales || {};
  const destacados = p.destacados.map(d => `
    <a class="destacado-fila" href="#/persona/${d.persona_id}">
      <span class="dias mono">${d.dias}</span>
      <span class="quien">${esc(d.contratado)}</span>
      <span class="cruce ${d.cruce === 'intercámara' ? 'marca' : ''}">${esc(d.cruce)}</span>
      <span class="fol">${esc(d.archivo_a)} · ${esc(d.archivo_b)}</span>
    </a>`).join('');

  // LO PRIMERO DE TODO: qué hacer ahora. El panel abría con un resumen de lo que
  // encontró, que es lo interesante pero no es lo accionable; quien entra a las nueve
  // de la mañana necesita saber en un renglón si hay trabajo suyo esperando y dónde.
  const pendiente = p.a_revisar + p.fusiones;
  const paso = pendiente ? `
    <div class="siguiente-paso hay-trabajo">
      <div>
        <b>${plural(pendiente, 'cosa esperando que la mires', 'cosas esperando que las mires')}</b>
        <span>${[p.a_revisar ? plural(p.a_revisar, 'campo dudoso', 'campos dudosos') : '',
                 p.fusiones ? plural(p.fusiones, 'identidad por confirmar', 'identidades por confirmar') : '']
                .filter(Boolean).join(' · ')}. Nada de eso entra en los totales de abajo
          hasta que alguien lo decida.</span>
      </div>
      <a class="boton" href="${p.a_revisar ? '#/cola' : '#/identidad'}">Ir a revisar</a>
    </div>` : `
    <div class="siguiente-paso">
      <div>
        <b>No queda nada esperando revisión</b>
        <span>Todo lo que el sistema no pudo sostener solo ya lo miró una persona.
          Los totales de abajo son los que se pueden llevar a un informe.</span>
      </div>
    </div>`;

  vista.innerHTML =
    bloque('f. 0001', 'Resumen', paso + `
      <h2>Qué encontró el sistema</h2>
      <p class="prosa resumen">
        Sobre <strong>${plural(p.contratos, 'contrato leído', 'contratos leídos')}</strong>${
          p.comprobantes ? ` y <strong>${plural(p.comprobantes, 'comprobante', 'comprobantes')}</strong>` : ''}
        del lote «${esc(p.lote)}»:
        <strong>${plural(p.personas_ambas_camaras, 'persona figura', 'personas figuran')}</strong>
        en las dos cámaras y
        <strong>${plural(p.superposiciones, 'par de contratos se pisa', 'pares de contratos se pisan')}</strong>
        en el tiempo${p.fechas_imposibles ? `, y <strong>${
          plural(p.fechas_imposibles, 'contrato tiene', 'contratos tienen')}</strong>
        fechas imposibles` : ''}.
        De los <strong>${plural(p.campos_criticos_total, 'campo crítico', 'campos críticos')}</strong>
        de los contratos, <strong>${n(p.campos_criticos_firmes)}</strong>
        ${p.campos_criticos_firmes === 1 ? 'está firme' : 'están firmes'}
        (${fmtPct(p.cobertura_pct)}) y <strong>${n(p.a_revisar)}</strong>
        ${p.a_revisar === 1 ? 'espera' : 'esperan'} revisión${p.excluidos ? `, y
        <strong>${plural(p.excluidos, 'contrato queda afuera', 'contratos quedan afuera')}
          del cruce</strong> por faltarle${p.excluidos === 1 ? '' : 's'} algún dato firme` : ''}.
      </p>
      ${(p.contratos_repetidos || p.archivos_con_varios) ? `
        <div class="aviso" style="margin-top:14px">
          <span class="sello alerta" style="flex:none">Revisar</span>
          <span>${p.archivos_con_varios ? `<strong>${plural(p.archivos_con_varios,
              'archivo trae varios documentos adentro', 'archivos traen varios documentos adentro')
            }</strong> y se separaron solos. ` : ''}
            ${p.contratos_repetidos ? `<strong>${plural(p.contratos_repetidos,
              'contrato aparece más de una vez', 'contratos aparecen más de una vez')
            }</strong> y ${p.contratos_repetidos === 1 ? 'estaría' : 'estarían'} contándose
            doble en los acumulados:
            <a href="#/consultas/08_contratos_repetidos">ver cuáles</a>.` : ''}</span>
        </div>` : ''}
      ${p.afuera ? `
        <div class="aviso" style="margin-top:14px">
          <span class="sello alerta" style="flex:none">Afuera</span>
          <span><strong>${plural(p.afuera, 'archivo no produjo ningún documento',
              'archivos no produjeron ningún documento')}</strong> y
            por lo tanto no ${p.afuera === 1 ? 'entra' : 'entran'} en ninguno de estos números:
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
        <div class="cifra ok"><b>${n(p.campos_criticos_firmes)}</b>
          <span>campos firmes de ${n(p.campos_criticos_total)}</span></div>
        <div class="cifra ${p.a_revisar ? 'alerta' : 'ok'}"><b>${n(p.a_revisar)}</b><span>esperan revisión</span></div>
        <div class="cifra ${p.conflictos ? 'alerta' : 'ok'}"><b>${n(p.conflictos)}</b><span>en conflicto</span></div>
        <div class="cifra"><b>${n(p.verificados)}</b><span>verificados por una persona</span></div>
        <div class="cifra"><b>${n(p.personas)}</b><span>personas identificadas</span></div>
        ${p.paginas_enderezadas ? `<div class="cifra"><b>${n(p.paginas_enderezadas)}</b>
          <span>fojas enderezadas</span></div>` : ''}
      </div>

      <h3 style="margin-top:22px">Lo contratado</h3>
      <div class="cifras totales">
        <div class="cifra ancha firme">
          <b>${esc(fmtPesos(t.total_firme_centavos))}</b>
          <span>firme · ${plural(t.contratos_con_monto_firme, 'contrato', 'contratos')}</span></div>
        <div class="cifra ancha provisional">
          <b>${esc(fmtPesos(t.total_provisional_centavos))}</b>
          <span>provisional · ${plural(t.contratos_con_monto_provisional, 'contrato sin revisar', 'contratos sin revisar')}</span></div>
      </div>
      <div class="cifras">
        <div class="cifra ${t.montos_pendientes_sin_valor ? 'alerta' : ''}">
          <b>${n(t.montos_pendientes_sin_valor)}</b><span>montos sin número leído</span></div>
        <div class="cifra ${t.contratos_sin_monto_firme ? 'alerta' : ''}">
          <b>${n(t.contratos_sin_monto_firme)}</b><span>contratos sin monto firme</span></div>
      </div>
      ${t.comprobantes ? `
      <h3 style="margin-top:22px">Lo facturado</h3>
      <div class="cifras totales">
        <div class="cifra ancha facturado">
          <b>${esc(fmtPesos(t.total_facturado_firme_centavos))}</b>
          <span>firme · ${plural(t.comprobantes_con_monto_firme, 'comprobante', 'comprobantes')}
            de ${n(t.comprobantes)}</span></div>
        <div class="cifra ancha ${t.comprobantes_sin_importe_legible ? 'alerta' : ''}">
          <b>${n(t.comprobantes_sin_importe_legible)}</b>
          <span>sin importe legible · escritos a mano</span></div>
      </div>
      <p class="prosa" style="font-size:12.5px;margin-top:10px">
        <strong>Lo facturado no se suma con lo contratado.</strong> El contrato dice
        cuánto se pactó pagar y la factura dice cuánto se cobró: cuando la factura es el
        cobro de ese mismo contrato, sumarlos cuenta la misma plata dos veces. Para ver
        uno contra otro, persona por persona, está
        <a href="#/cruce">Lo facturado contra lo contratado</a>.</p>` : ''}
      ${t.documentos_sin_familia ? `
      <div class="aviso" style="margin-top:12px">
        <span class="sello atencion" style="flex:none">Sin clasificar</span>
        <span>${plural(t.documentos_sin_familia, 'documento', 'documentos')} no se
          reconoce${t.documentos_sin_familia === 1 ? '' : 'n'} como contrato ni como
          comprobante, así que no entra${t.documentos_sin_familia === 1 ? '' : 'n'} en
          ningún total. Están en <a href="#/afuera">Quedaron afuera</a>.</span>
      </div>` : ''}
      <p class="prosa" style="font-size:12.5px;margin-top:10px">
        <strong>El total firme</strong> suma únicamente los montos que el sistema leyó con
        confianza alta o que una persona verificó contra el documento. <strong>El
        provisional</strong> son montos leídos que todavía están esperando revisión: se
        muestran para que se vea que existen, y <strong>no entran en ningún cruce ni en
        ningún acumulado</strong> hasta que alguien los mire.
        ${t.ultima_revision ? `Última revisión: <span class="mono">${esc(fmtFecha(t.ultima_revision))}</span>.` : ''}
        ${p.paginas_enderezadas ? `
        ${p.paginas_enderezadas === 1 ? 'Una foja llegó' : n(p.paginas_enderezadas) + ' fojas llegaron'}
        girada en el escaneo y se enderezó la copia de trabajo para poder leerla.` : ''}</p>
      ${(p.perfiles || []).length > 1 ? `
        <p class="prosa" style="font-size:12.5px">
          Se reconocieron <strong>${p.perfiles.length} formatos de formulario</strong> distintos:
          ${p.perfiles.map(f => `<span class="mono">${esc(f.perfil)}</span> (${f.n})`).join(', ')}.</p>` : ''}`) +

    bloque('f. 0003', 'Cobertura', `
      <h2>Qué se pudo leer</h2>
      <p class="prosa">El denominador honesto, campo por campo y por tipo de documento.
        <strong>Firme</strong> es lo que puede sumarse y cruzarse: lo leyó el sistema con
        confianza alta, o lo verificó una persona contra el documento. Todo lo demás
        existe y se ve, pero no entra en ningún total. Una cola larga no es una falla: es
        el sistema prefiriendo dudar antes que equivocarse callado.</p>
      <p class="prosa" style="font-size:12.5px">Van separados por tipo de documento
        porque el mismo campo dice cosas distintas: en un contrato <em>Contratado</em> es
        quien fue contratado, y en una factura es quien la emitió.</p>
      ${tabla([
        {t:'Documento', r:f => esc(FAMILIA_DOC[f.familia] || 'Sin clasificar')},
        {t:'Campo', r:f => esc(rotularCampo(f.campo, f.familia))},
        {t:'Total', k:'total', c:'num'},
        {t:'Firmes', c:'num', r:f => `<b>${fmtNum.format(f.firmes)}</b>`},
        {t:'Esperando', c:'num', r:f => {
          const n = f.pendientes_baja_confianza + f.conflictos + f.sin_revisar;
          return n ? `<span class="marca">${fmtNum.format(n)}</span>` : '0';
        }},
        {t:'Cerrados sin valor', c:'num',
         r:f => fmtNum.format(f.ilegibles_confirmados + f.ausentes_confirmados)},
        {t:'% firme', c:'num', r:f => fmtPct(f.pct_firme_sobre_total)},
      ], cob)}
      <details class="detalle-cobertura">
        <summary>Abrir el detalle: cuántos resolvió el sistema y cuántos una persona</summary>
        ${tabla([
          {t:'Documento', r:f => esc(FAMILIA_DOC[f.familia] || 'Sin clasificar')},
          {t:'Campo', r:f => esc(rotularCampo(f.campo, f.familia))},
          {t:'Automáticos firmes', k:'automaticos_firmes', c:'num'},
          {t:'Verificados por una persona', k:'verificados_por_persona', c:'num'},
          {t:'Pendientes por baja confianza', k:'pendientes_baja_confianza', c:'num'},
          {t:'En conflicto', k:'conflictos', c:'num'},
          {t:'Sin revisar', k:'sin_revisar', c:'num'},
          {t:'Ilegibles confirmados', k:'ilegibles_confirmados', c:'num'},
          {t:'Ausentes confirmados', k:'ausentes_confirmados', c:'num'},
        ], cob)}
      </details>
      ${p.excluidos ? `<p class="prosa" style="font-size:13px;margin-top:12px">
        <strong>${plural(p.excluidos, 'contrato quedó fuera del cruce',
                          'contratos quedaron fuera del cruce')}</strong> por faltarle${
          p.excluidos === 1 ? '' : 's'} algún dato firme:
        <a href="#/consultas/06_excluidos_del_cruce">ver cuáles y por qué</a>.</p>` : ''}`) +

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
        sale de acá debería incorporarse a un legajo sin cotejarlo contra el original.</p>
      <h3 style="margin-top:22px">Y guardar una copia</h3>
      <p class="prosa">Los PDF originales están en su carpeta y las imágenes de página se
        rehacen procesando de nuevo. Lo que <strong>no</strong> se regenera es el trabajo
        de las personas: cada campo revisado contra el folio, cada identidad confirmada,
        con quién y cuándo. Eso vive en un solo archivo.</p>
      <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:12px">
        <a class="boton" href="/descargar?que=respaldo">Descargar una copia de respaldo</a>
      </div>
      <p class="prosa" style="font-size:12.5px;margin-top:12px">La copia se hace con el
        sistema andando, sin pedirle a nadie que deje de trabajar. Conviene bajarla al
        terminar cada jornada de revisión y dejarla en otro disco.</p>`);
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
    <div id="tabla-contratos"></div>`);
  tablaBuscable($('#tabla-contratos'), [
      {t:'Doc', k:'documento_id', c:'fol'},
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', b:f => camaraTexto(f.camara), r:f => esc(camaraTexto(f.camara))},
      {t:'Contratado/a', b:f => f.nombre_literal,
       r:f => f.nombre_literal ? esc(f.nombre_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Documento', c:'mono', b:f => f.documento_literal,
       r:f => f.documento_literal ? esc(f.documento_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Inicio', c:'mono', b:f => f.inicio,
       r:f => f.inicio ? esc(fmtFecha(f.inicio)) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Fin', c:'mono', b:f => f.fin,
       r:f => f.fin ? esc(fmtFecha(f.fin)) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Monto', c:'num', b:f => f.monto_centavos,
       r:f => f.monto_centavos == null ? '<span class="nulo">Ø sin dato</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', b:f => f.confianza_min, r:f => barraConf(f.confianza_min)},
    ], filas, {alClic: f => location.hash = '#/documento/' + f.documento_id,
               placeholder: 'Buscar por nombre, documento, archivo…'});
}

/* ── Comprobantes ──────────────────────────────────────────────────────────
   El otro carril. Separado de los contratos porque dice otra cosa: el contrato es lo
   que se pactó pagar, el comprobante es lo que se cobró. */
async function vComprobantes() {
  const filas = await api('/api/comprobantes');
  if (!filas.length) return vistaVacia('f. 0004', 'Datos', 'Facturas y recibos',
    'Todavía no hay comprobantes leídos',
    'Acá van las facturas, recibos y remitos que vengan en los escaneos. Se separan de ' +
    'los contratos porque dicen otra cosa: lo que se cobró, no lo que se pactó.');

  const aMano = filas.filter(f => f.monto_centavos == null).length;
  vista.innerHTML = bloque('f. 0004', 'Datos', `
    <h2>Facturas y recibos</h2>
    <p class="prosa">Lo que se cobró. <strong>No se suma con los contratos</strong>: son
      la misma plata vista de los dos lados, y cuando la factura es el cobro de ese
      contrato, sumarlas la cuenta dos veces. El cruce está en
      <a href="#/cruce">Lo facturado contra lo contratado</a>.</p>
    ${aMano ? `<div class="aviso">
      <span class="sello atencion" style="flex:none">A mano</span>
      <span>${plural(aMano, 'comprobante tiene', 'comprobantes tienen')} el importe
        escrito a mano. <strong>No se lee con OCR</strong> —leerlo mal y no saberlo es
        peor que no leerlo— así que aparece vacío y espera que una persona lo cargue
        mirando la foja. Están en <a href="#/cola">la cola de revisión</a>.</span>
    </div>` : ''}
    <div id="tabla-comprobantes"></div>`);
  tablaBuscable($('#tabla-comprobantes'), [
      {t:'Doc', k:'documento_id', c:'fol'},
      {t:'Tipo', b:f => TIPO_DOC[f.tipo] || f.tipo, r:f => esc(TIPO_DOC[f.tipo] || f.tipo)},
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Emisor', b:f => f.nombre_literal,
       r:f => f.nombre_literal ? esc(f.nombre_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'CUIT', c:'mono', b:f => f.documento_literal,
       r:f => f.documento_literal ? esc(f.documento_literal) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Comprobante', c:'mono', b:f => f.comprobante,
       r:f => f.comprobante ? esc(f.comprobante) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Emitida', c:'mono', b:f => f.emitida,
       r:f => f.emitida ? esc(fmtFecha(f.emitida)) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Importe', c:'num', b:f => f.monto_centavos,
       r:f => f.monto_centavos == null ? '<span class="nulo">Ø a mano</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', b:f => f.confianza_min, r:f => barraConf(f.confianza_min)},
    ], filas, {alClic: f => location.hash = '#/documento/' + f.documento_id,
               placeholder: 'Buscar por emisor, CUIT, número de comprobante…'});
}

/* ── Lo facturado contra lo contratado ─────────────────────────────────────
   El cruce que el caso necesita: cuánto se comprometió a pagar y cuánto se facturó
   contra eso. Une por CUIT ↔ DNI, no por nombre, que se escribe de mil maneras. */
async function vCruce() {
  const r = await api('/api/cruce');
  if (!r.filas.length) return vistaVacia('f. 0006', 'Cruce', 'Lo facturado contra lo contratado',
    'Todavía no hay con qué cruzar',
    'Hace falta al menos un contrato con documento leído. Las facturas se le enganchan ' +
    'solas: el CUIL lleva adentro el DNI del contrato.');

  vista.innerHTML = bloque('f. 0006', 'Cruce', `
    <h2>Lo facturado contra lo contratado</h2>
    <p class="prosa">Qué se comprometió a pagar y qué se facturó contra eso, persona por
      persona. Se unen por el documento y no por el nombre: <strong>el CUIL de la
      factura lleva adentro el DNI del contrato</strong>, así que se cruzan solos aunque
      el nombre esté escrito distinto en cada foja.</p>
    <div id="tabla-cruce"></div>
    <p class="prosa" style="font-size:12.5px;margin-top:12px">
      <strong>Mensual y total no son lo mismo, y no se comparan entre sí.</strong> El
      contrato fija un importe <em>mensual</em>; las facturas se acumulan. El único
      número comparable con lo facturado es el <strong>total contratado</strong>, que el
      contrato dice aparte. Cuando ese total no se pudo leer, la celda queda vacía en
      vez de mostrar un cero o el mensual en su lugar: el sistema no multiplica mensual
      por plazo para llenarla, porque eso sería calcular un número que el papel dice o
      no dice.</p>
    <p class="prosa" style="font-size:12.5px">
      <strong>Una fila por persona, no por contrato.</strong> Una factura no dice a qué
      contrato corresponde, y repartirlas por fecha sería adivinar. Con una fila por
      contrato, quien tiene dos aparecía dos veces y cada fila traía todas sus facturas:
      sumar la columna daba el doble de lo facturado. El detalle contrato por contrato
      está en la ficha de cada persona.</p>
    <p class="prosa" style="font-size:12.5px">
      <strong>Facturado legible</strong> suma sólo los importes impresos que se pudieron
      leer con seguridad. La columna <strong>a mano</strong> cuenta las facturas de
      talonario, donde el importe está manuscrito y el sistema no lo lee: existen y no
      se sabe por cuánto. Mientras esa columna no sea cero, el facturado está incompleto
      y no se puede comparar contra lo pactado como si fuera el total.</p>`);

  tablaBuscable($('#tabla-cruce'), [
      {t:'Contratado/a', b:f => f.contratado,
       r:f => `<a href="#/persona/${f.persona_id}">${esc(f.contratado)}</a>`},
      {t:'Documento', k:'documento', c:'mono'},
      {t:'Contratos', c:'num', k:'contratos'},
      {t:'Período', c:'mono', b:f => f.contrato_desde, r:f => f.contrato_desde
          ? `${esc(fmtFecha(f.contrato_desde))} → ${esc(fmtFecha(f.contrato_hasta))}`
          : '<span class="nulo">Ø sin fechas</span>'},
      // Mensual y total son magnitudes distintas y se muestran en columnas distintas.
      // El total es el único comparable con la facturación acumulada de al lado.
      {t:'Mensual pactado', c:'num', b:f => f.mensual_centavos, r:f => f.mensual_centavos
          ? esc(fmtPesos(f.mensual_centavos)) : '<span class="nulo">Ø sin dato</span>'},
      // Cuando NINGÚN contrato trae el total legible, la celda no muestra $0,00: cero
      // se lee como «no se contrató nada» y lo que pasa es que no se pudo leer.
      {t:'Total contratado', c:'num', b:f => f.contratado_centavos,
       r:f => f.contratos_sin_total_firme >= f.contratos
          ? '<span class="nulo">Ø sin leer</span>'
          : esc(fmtPesos(f.contratado_centavos)) + (f.contratos_sin_total_firme
              ? ` <span class="sello atencion">faltan ${f.contratos_sin_total_firme}</span>` : '')},
      {t:'Facturas', c:'num', k:'facturas'},
      {t:'Facturado legible', c:'num', b:f => f.facturado_legible_centavos,
       r:f => esc(fmtPesos(f.facturado_legible_centavos))},
      {t:'A mano', c:'num', b:f => f.facturas_a_mano, r:f => f.facturas_a_mano
          ? `<span class="sello atencion">${f.facturas_a_mano}</span>` : '—'},
    ], r.filas, {placeholder: 'Buscar por nombre o documento…'});
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
      return `<div class="campo"><dt>${esc(rotularCampo(c.nombre, doc.familia))}</dt><dd><div class="conflicto">${
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
    // Cada campo puede contar su historia. Va atrás de un botón y no siempre abierto:
    // lo normal es que un campo tenga una línea, y catorce fichas desplegadas serían
    // ruido; pero cuando alguien pregunta «¿quién puso esto?», la respuesta está a un
    // clic y no depende de que nadie se acuerde.
    const historial = `<button class="historial" data-campo="${c.id}"
        title="quién decidió esto, y cuándo">rastro</button>`;
    return `<div class="campo"><dt>${esc(rotularCampo(c.nombre, doc.familia))}</dt>
      <dd>${celdaValor(c)}${ancla}${marca}${historial}
        <div class="rastro" id="rastro-${c.id}" hidden></div></dd></div>`;
  }).join('');

  const tiras = paginas.map(p =>
    `<button class="foja" data-nro="${p.nro}"${p.rotacion ? ' data-girada="1"' : ''}
       title="${p.rotacion ? `esta foja llegó girada ${p.rotacion}° y se enderezó para leerla`
                           : `foja ${p.nro}`}">f. ${p.nro}${p.rotacion ? ' ↻' : ''}</button>`).join('');
  const enderezadas = paginas.filter(p => p.rotacion);

  vista.innerHTML = bloque('f. ' + String(id).padStart(4, '0'), 'Visor', `
    <h2>${esc(doc.archivo)}${varios
        ? ` <span class="rotulo">documento ${doc.orden} de ${d.hermanos.length}</span>` : ''}</h2>
    <p class="tipo-doc"><span class="sello">${esc(TIPO_DOC[doc.tipo] || doc.tipo)}</span></p>
    <p class="prosa" style="font-size:13px">
      ${doc.camara ? 'Cámara de ' + esc(camaraTexto(doc.camara)) + ' · ' : ''}perfil <span class="mono">${esc(doc.perfil)}</span> ·
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
      <span>Este PDF trae <strong>${plural(d.hermanos.length, 'documento', 'documentos')}</strong>
      adentro. Estás viendo el número ${doc.orden}, que ocupa las fojas
      ${doc.pagina_desde} a ${doc.pagina_hasta}. Los otros:
      ${d.hermanos.filter(h => h.id !== doc.id).map(h =>
        `<a href="#/documento/${h.id}">#${h.orden} ${esc(TIPO_DOC[h.tipo] || h.tipo || '')}
          (f. ${h.pagina_desde}–${h.pagina_hasta})</a>`
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

  vista.querySelectorAll('.historial').forEach(b =>
    b.onclick = () => verRastro(+b.dataset.campo));

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

/* Qué filtros hay puestos. Vive afuera de la vista para sobrevivir al repintado que
   hace cada decisión: filtrar por «montos de contratos», decidir uno y que se te
   borre el filtro es peor que no tener filtros. */
let filtroCola = {familia: '', campo: '', clase: ''};
/* Cuántas filas se traen por vez. Es el mismo número que usa el servidor; acá se
   declara para pedirlo explícito y que la pantalla sepa cuántas más quedan. */
const POR_PAGINA = 200;

async function vCola(campoId) {
  // El filtrado y el corte los hace el SERVIDOR. Antes llegaban 400 filas cortadas sin
  // decirlo y la pantalla filtraba sobre esas: con 3.892 campos esperando, la cola
  // mostraba «1 de 400» y filtrar por «facturas» filtraba sobre las 400 que habían
  // llegado, no sobre la cola.
  const p = new URLSearchParams({limite: String(POR_PAGINA)});
  for (const k of ['familia', 'campo', 'clase']) if (filtroCola[k]) p.set(k, filtroCola[k]);
  const r = await api('/api/cola?' + p);
  const filas = r.filas;
  const todas = {length: r.total_sin_filtro};
  // Se puede enlazar un campo puntual: #/cola/123 abre la cola parada en ese campo.
  // Sirve para decirle a un compañero "mirá este" sin explicarle dónde está.
  const pedido = campoId ? filas.findIndex(f => String(f.campo_id) === String(campoId)) : -1;
  colaEstado = {filas, foco: pedido >= 0 ? pedido : 0,
                total: r.total, total_sin_filtro: r.total_sin_filtro,
                opciones: r.opciones, cargando: false};
  if (!r.total_sin_filtro) {
    vista.innerHTML = bloque('f. 0006', 'Cola', `<h2>Cola de revisión</h2>
      ${vacio('No queda nada por revisar',
        'Todos los campos están resueltos o verificados. Cuando entre un lote nuevo, ' +
        'lo que el sistema no pueda sostener va a aparecer acá.',
        {href:'#/panel', texto:'Volver al panel'})}`);
    return;
  }
  const porDoc = new Set(filas.map(f => f.documento_id)).size;
  // Las opciones las cuenta el servidor sobre la cola ENTERA. Contadas acá salían de la
  // página que llegó: ofrecer «facturas» porque justo hay una en las doscientas que
  // vinieron —o no ofrecerlas porque no las hay— es un filtro que miente.
  const opciones = (clave, rotular) => (colaEstado.opciones[clave] || [])
    .map(o => `<option value="${esc(o.valor ?? '')}">${esc(rotular(o.valor))} (${
      fmtNum.format(o.n)})</option>`).join('');

  /* La cola no es una página: es un puesto de trabajo, y por eso no se pinta dentro
     del bloque con marginalia como el resto. Ocupa el alto entero de la ventana y se
     parte en cuatro fajas —encabezado, filtros, los dos paneles, pie—, donde las tres
     que no son los paneles quedan quietas.

     Lo que se arregla con eso: antes la página tenía su propio desplazamiento Y la
     lista tenía el suyo adentro, uno al lado del otro, y cuál de los dos se movía
     dependía de dónde había quedado el puntero. La rueda del mouse hacía dos cosas
     distintas a un centímetro de diferencia. Y el «1 de 42» y los filtros se iban para
     arriba en cuanto bajabas tres filas, justo cuando más falta hacen: revisando el
     campo treinta, saber que vas por el treinta es la mitad del sentido de la tarea.

     Ahora se mueve una sola cosa: la lista. La foja de al lado entra entera en su
     panel, escalada, sin desplazamiento propio. */
  document.body.classList.add('taller-abierto');
  vista.innerHTML = `
    <div class="taller">
      <header class="taller-cabeza">
        <div>
          <h2>Cola de revisión</h2>
          <p class="taller-sub">${plural(r.total_sin_filtro, 'campo espera', 'campos esperan')}
            revisión, ordenados por lo que más daño hace si queda mal. <strong>El folio
            está a la vista</strong>: no hace falta salir de acá.</p>
        </div>
        <div class="posicion" id="posicion"></div>
      </header>

      <div class="taller-filtros">
        <label>Documento
          <select id="f-familia"><option value="">todos (${todas.length})</option>
            ${opciones('familia', v => FAMILIA_DOC[v] || 'sin clasificar')}</select></label>
        <label>Campo
          <select id="f-campo"><option value="">todos</option>
            ${opciones('campo', v => rotularCampo(v))}</select></label>
        <label>Motivo
          <select id="f-clase"><option value="">todos</option>
            ${opciones('clase', v => CLASE_COLA[v] || v)}</select></label>
        ${filtroCola.familia || filtroCola.campo || filtroCola.clase
          ? `<button class="boton gris" id="f-limpiar">Quitar los filtros</button>` : ''}
      </div>

      <div class="taller-cuerpo">
        <div class="cola" id="cola">${
          !filas.length ? vacio('Ningún campo entra en ese filtro',
            'Hay ' + plural(todas.length, 'campo esperando revisión',
                            'campos esperando revisión') +
            ', pero ninguno cumple lo que pediste.') : ''}${filas.map(filaCola).join('')}
          ${filas.length < r.total ? `<button class="mas-cola" id="mas-cola">Traer
            ${plural(Math.min(POR_PAGINA, r.total - filas.length), 'campo más', 'campos más')}
            <span>quedan ${fmtNum.format(r.total - filas.length)}</span></button>` : ''}</div>
        <aside class="folio-lado" id="folio-lado">
          <div class="lupa" id="lupa"><img id="lupa-img" alt=""></div>
          <div class="pie-lamina"><span id="lupa-campo"></span><span id="lupa-xy"></span></div>
          <div class="lienzo" id="lienzo-cola">
            <img id="folio-cola" alt="">
            <div class="recuadro" id="recuadro-cola" style="display:none"></div>
          </div>
          <a class="chip" id="ir-doc" href="#/panel">ver el documento completo</a>
        </aside>
      </div>

      <footer class="taller-pie">
        <span class="solo-teclado"><kbd>J</kbd>/<kbd>K</kbd> para moverse; las teclas de
          cada fila para decidir. <strong>Ninguna acción es «aceptar todo».</strong></span>
        <div class="deshacer-barra" id="deshacer-barra" hidden></div>
      </footer>
    </div>`;

  engancharFilasCola();
  [['f-familia','familia'], ['f-campo','campo'], ['f-clase','clase']].forEach(([id, clave]) => {
    const sel = $('#' + id);
    sel.value = filtroCola[clave];
    sel.onchange = () => { filtroCola[clave] = sel.value; vCola(); };
  });
  if ($('#f-limpiar')) $('#f-limpiar').onclick = () => {
    filtroCola = {familia: '', campo: '', clase: ''}; vCola();
  };
  if ($('#mas-cola')) $('#mas-cola').onclick = () => traerMasCola();
  pintarFoco();
}

/* Trae la página siguiente y la agrega abajo, sin repintar lo que ya está. Repintar
   perdería el lugar donde estabas, que es lo único que la cola tiene que respetar. */
async function traerMasCola() {
  if (colaEstado.cargando || colaEstado.filas.length >= colaEstado.total) return;
  colaEstado.cargando = true;
  const boton = $('#mas-cola');
  if (boton) boton.textContent = 'buscando…';
  try {
    const p = new URLSearchParams({desde: String(colaEstado.filas.length),
                                   limite: String(POR_PAGINA)});
    for (const k of ['familia', 'campo', 'clase']) if (filtroCola[k]) p.set(k, filtroCola[k]);
    const r = await api('/api/cola?' + p);
    const desde = colaEstado.filas.length;
    colaEstado.filas = colaEstado.filas.concat(r.filas);
    colaEstado.total = r.total;
    const cola = $('#cola');
    const nuevas = r.filas.map((f, i) => filaCola(f, desde + i)).join('');
    if (boton) boton.remove();
    cola.insertAdjacentHTML('beforeend', nuevas);
    if (colaEstado.filas.length < r.total) {
      cola.insertAdjacentHTML('beforeend', `<button class="mas-cola" id="mas-cola">Traer
        ${plural(Math.min(POR_PAGINA, r.total - colaEstado.filas.length), 'campo más', 'campos más')}
        <span>quedan ${fmtNum.format(r.total - colaEstado.filas.length)}</span></button>`);
      $('#mas-cola').onclick = () => traerMasCola();
    }
    engancharFilasCola();
    pintarFoco();
  } finally { colaEstado.cargando = false; }
}

/* Los manejadores de las filas. Se llama al pintar y cada vez que llegan más: las filas
   nuevas nacen sin eventos, y una fila de la cola que no responde al clic es una fila
   que parece rota. */
function engancharFilasCola() {
  vista.querySelectorAll('[data-accion]').forEach(b => b.onclick = () => {
    colaEstado.foco = +b.closest('.fila').dataset.i;
    decidir(+b.dataset.campo, b.dataset.accion, b.dataset.valor);
  });
  vista.querySelectorAll('.fila').forEach(f => f.onclick = e => {
    if (e.target.closest('[data-accion]')) return;
    colaEstado.foco = +f.dataset.i; pintarFoco();
  });
}

function filaCola(f, i) {
  const acciones = [];
  if (f.clase === 'conflicto' && f.variantes) {
    f.variantes.forEach((v, n) => acciones.push(
      [String(n + 1), `tomar ${v.ruta}`, 'corregir', v.valor]));
    acciones.push(['N', 'ninguna, Ø ambiguo', 'ambiguo', '']);
  } else if (f.motivo === 'manuscrito') {
    // Confirmar la propuesta es UNA tecla, y queda registrado como corrección humana:
    // el dato entra porque una persona lo miró contra el recorte, no porque lo dijo
    // un modelo. Sin propuesta, se tipea, que es lo que había antes.
    if (f.propuesta && !f.propuesta.ilegible && f.propuesta.valor) {
      acciones.push(['1', `confirmar ${f.propuesta.valor}`, 'corregir', f.propuesta.valor]);
    }
    acciones.push(['C', 'cargar a mano', 'pedir', '']);
    acciones.push(['X', 'Ø no se lee, firme', 'verificar', '']);
  } else if (f.motivo) {
    acciones.push(['C', 'cargar a mano', 'pedir', '']);
    acciones.push(['X', `Ø ${f.motivo}, firme`, 'verificar', '']);
  } else {
    acciones.push(['V', 'es correcto', 'verificar', '']);
    acciones.push(['C', 'corregir', 'pedir', '']);
    acciones.push(['X', 'Ø ilegible', 'ilegible', '']);
  }
  // La propuesta del lector de manuscrita. Va SEPARADA del valor y dice de dónde
  // salió: quien revisa tiene que poder distinguir de un vistazo entre «esto lo leyó
  // el sistema del papel» y «esto lo propuso un modelo y lo estás confirmando vos».
  const propuesta = f.propuesta ? (f.propuesta.ilegible
    ? `<div class="propuesta ilegible">
         <span class="de-donde">propuesta · ${esc(f.propuesta.modelo)}</span>
         <b>no se lee</b>
         ${f.propuesta.nota ? `<span class="nota">${esc(f.propuesta.nota)}</span>` : ''}
       </div>`
    : `<div class="propuesta">
         <span class="de-donde">propuesta · ${esc(f.propuesta.modelo)}</span>
         <b class="mono">${esc(f.propuesta.valor)}</b>
         ${f.propuesta.nota ? `<span class="nota">${esc(f.propuesta.nota)}</span>` : ''}
       </div>`) : '';

  const cuerpo = (f.clase === 'conflicto' && f.variantes)
    ? `<div class="conflicto">${f.variantes.map(v =>
        `<div class="ruta"><span>${esc(v.ruta)}</span><span>${esc(v.valor)}</span></div>`).join('')}</div>`
    : `<div class="mono" style="font-size:13px">${f.valor
        ? esc(f.valor)
        : `<span class="nulo">Ø ${esc(MOTIVO_NULO[f.motivo] || f.motivo)}</span>`
      } ${barraConf(f.confianza)}</div>`;

  return `<div class="fila" data-i="${i}">
    <div class="marginalia"><span>${esc(f.archivo.replace('.pdf', ''))}</span>
      <span>f. ${f.pagina_nro ?? '—'}</span></div>
    <div class="med">
      <div style="display:flex;gap:9px;align-items:baseline;margin-bottom:7px;flex-wrap:wrap">
        <span class="rotulo">${esc(CLASE_COLA[f.clase] || f.clase)}</span>
        <span class="etiqueta-campo ${f.clase === 'conflicto' ? 'alerta' : ''}"
          >${esc(rotularCampo(f.campo, f.familia))}</span>
        ${f.familia && f.familia !== 'contrato'
          ? `<span class="rotulo">${esc(FAMILIA_DOC[f.familia])}</span>` : ''}
      </div>
      ${cuerpo}
      ${propuesta}
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
  // Dónde estás. «Cola de revisión» sin número no dice si faltan tres o trescientos, y
  // sin saber eso nadie puede decidir si lo termina hoy.
  // Dónde estás sobre el TOTAL, no sobre lo que llegó. «1 de 400» con 3.892 campos
  // esperando no es una imprecisión: es esconder tres mil cuatrocientos noventa y dos
  // campos de trabajo, y quien termine los 400 va a creer que el legajo está listo.
  const pos = $('#posicion');
  if (pos) {
    const filtrado = colaEstado.total !== colaEstado.total_sin_filtro;
    pos.innerHTML = colaEstado.total
      ? `<b>${fmtNum.format(colaEstado.foco + 1)}</b> de ${fmtNum.format(colaEstado.total)}` +
        (filtrado ? ` <span class="de-todo">(${fmtNum.format(colaEstado.total_sin_filtro)}
           en la cola entera)</span>` : '')
      : '';
  }
  // Al acercarse al final de lo cargado, se trae la página siguiente. Que bajar con J
  // se termine en la fila 200 de 3.892 sería el mismo tope de antes con otra cara.
  if (colaEstado.foco >= colaEstado.filas.length - 5) traerMasCola();
}

/* La última decisión, para poder deshacerla. Una sola: deshacer en cadena obligaría a
   recordar un orden que la cola ya cambió abajo, y lo que hace falta es corregir el
   error que acabás de cometer, no rebobinar la jornada. Lo anterior se deshace desde
   la ficha del documento, que muestra el historial completo. */
let ultimaDecision = null;

/* El rastro de un campo: todo lo que le pasó, en orden y sin editar. */
const ACCION_RASTRO = {
  verificar: 'confirmó que estaba bien', corregir: 'cargó el valor a mano',
  ilegible: 'marcó que no se puede leer', ausente: 'marcó que no está en el documento',
  ambiguo: 'marcó que dice dos cosas distintas', revertir: 'deshizo su decisión',
};

async function verRastro(campoId) {
  const caja = $('#rastro-' + campoId);
  if (!caja) return;
  if (!caja.hidden) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.innerHTML = '<span class="rotulo">buscando…</span>';
  try {
    const filas = await api('/api/auditoria', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({campo_id: campoId})});
    caja.innerHTML = filas.length ? filas.map(r => `
      <div class="paso">
        <span class="cuando mono">${esc(fmtFechaHora(r.cuando))}</span>
        <span class="quien">${esc(r.quien || '—')}</span>
        <span class="que">${esc(ACCION_RASTRO[r.accion] || r.accion)}${
          r.valor_nuevo ? `: <span class="mono">${esc(r.valor_nuevo)}</span>` : ''}${
          r.valor_anterior && r.valor_anterior !== r.valor_nuevo
            ? ` <span class="antes">antes decía <span class="mono">${esc(r.valor_anterior)}</span></span>` : ''}
          ${r.observacion ? `<span class="nota">${esc(r.observacion)}</span>` : ''}</span>
      </div>`).join('')
      : `<div class="paso vacio">Nadie lo tocó todavía: es como lo leyó el sistema.</div>`;
  } catch (e) {
    caja.innerHTML = `<div class="paso vacio">No se pudo leer el rastro: ${esc(e.message)}</div>`;
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
  // El estado en que ESTA pantalla vio el campo. Si otra persona lo decidió mientras
  // tanto, el servidor rechaza y avisa en vez de dejar que gane el último en apretar.
  const fila = colaEstado.filas.find(f => String(f.campo_id) === String(campoId));
  try {
    await api('/api/campo', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({campo_id: campoId, accion, valor, quien,
                            estado_esperado: fila ? fila.estado : null})});
    ultimaDecision = fila ? {campo_id: campoId, quien, antes: fila} : null;
    // Se saca ESA fila y nada más. Antes se volvía a pedir la cola entera en cada
    // decisión: con doscientas filas eso ya costaba un parpadeo, y ahora que la cola
    // pagina significaría perder todas las páginas que habías traído y volver arriba.
    // El campo salió de la cola porque alguien lo decidió; eso lo sabemos acá sin
    // preguntarle de nuevo al servidor.
    sacarDeLaCola(campoId);
    colaEstado.foco = Math.min(posicion, Math.max(0, colaEstado.filas.length - 1));
    pintarFoco();
    mostrarDeshacer();
    refrescarCuentas();
  } catch (e) {
    if (e.estado === 409) {
      // No es un error de quien apretó: el mundo cambió abajo. Se recarga la cola para
      // que vea cómo quedó, y recién ahí decide de nuevo.
      alert(e.message);
      await vCola(); pintarFoco(); refrescarCuentas();
      return;
    }
    alert('No se pudo guardar: ' + e.message);
  }
}

/* Saca una fila de la cola, en la pantalla y en la cuenta. Renumera las que quedan:
   `data-i` es la posición, y si no se renumeran, la fila de abajo responde por el
   índice de la que se fue y se decide sobre el campo equivocado. */
function sacarDeLaCola(campoId) {
  const i = colaEstado.filas.findIndex(f => String(f.campo_id) === String(campoId));
  if (i < 0) return;
  colaEstado.filas.splice(i, 1);
  colaEstado.total = Math.max(0, colaEstado.total - 1);
  colaEstado.total_sin_filtro = Math.max(0, colaEstado.total_sin_filtro - 1);
  const filas = [...vista.querySelectorAll('.fila')];
  if (filas[i]) filas[i].remove();
  vista.querySelectorAll('.fila').forEach((f, n) => f.dataset.i = n);
  if (!colaEstado.filas.length) vCola();      // se vació: mostrar el estado vacío
}

/* Deshacer lo último. Vuelve el campo a como estaba y QUEDA REGISTRADO: la auditoría
   es append-only, así que deshacer no borra la decisión anterior — agrega una línea
   más que dice que se revirtió, quién y cuándo. */
function mostrarDeshacer() {
  const barra = $('#deshacer-barra');
  if (!barra || !ultimaDecision) return;
  const a = ultimaDecision.antes;
  barra.hidden = false;
  barra.innerHTML = `<span>Decidiste
    <b>${esc(rotularCampo(a.campo, a.familia))}</b> de
    <span class="fol">${esc(a.archivo)}</span>.</span>
    <button class="boton gris" id="b-deshacer">Deshacer</button>`;
  $('#b-deshacer').onclick = async () => {
    try {
      await api('/api/campo', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({campo_id: ultimaDecision.campo_id, accion: 'revertir',
                              quien: ultimaDecision.quien,
                              observacion: 'deshecho desde la cola'})});
      ultimaDecision = null;
      barra.hidden = true;
      await vCola(); pintarFoco(); refrescarCuentas();
    } catch (e) { alert('No se pudo deshacer: ' + e.message); }
  };
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
        {t:'Período', c:'mono', r:f => f.inicio
            ? `${esc(fmtFecha(f.inicio))} → ${f.fin ? esc(fmtFecha(f.fin)) : '?'}` : '—'},
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
    <div id="tabla-personas"></div>`);
  tablaBuscable($('#tabla-personas'), [
      {t:'Contratado/a', k:'contratado'},
      {t:'Documento', c:'mono', b:f => f.documento,
       r:f => f.documento ? esc(f.documento) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Contratos', k:'contratos', c:'num'},
      {t:'Sin monto', c:'num', b:f => f.contratos_sin_monto,
       r:f => f.contratos_sin_monto ? `<span class="marca">${f.contratos_sin_monto}</span>` : '0'},
      {t:'Acumulado', c:'num', b:f => f.acumulado_centavos,
       r:f => esc(fmtPesos(f.acumulado_centavos))},
      // Vienen como «A,B» de un GROUP_CONCAT. Se traducen y se separan legible.
      {t:'Cámaras',
       b:f => (f.camaras || '').split(',').filter(Boolean).map(camaraTexto).join(' + '),
       r:f => esc((f.camaras || '').split(',').filter(Boolean)
          .map(camaraTexto).join(' + ')) || '—'},
      {t:'Desde', c:'mono', b:f => f.primer_inicio,
       r:f => f.primer_inicio ? esc(fmtFecha(f.primer_inicio)) : '—'},
      {t:'Hasta', c:'mono', b:f => f.ultimo_fin,
       r:f => f.ultimo_fin ? esc(fmtFecha(f.ultimo_fin)) : '—'},
      {t:'Conf.', c:'num', b:f => f.confianza_min, r:f => barraConf(f.confianza_min)},
    ], filas, {alClic: f => location.hash = '#/persona/' + f.persona_id,
               placeholder: 'Buscar por nombre o documento…'});
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
        <span>${esc(camaraTexto(c.camara) || 'sin cámara')}</span>
        <span class="fol">${esc(c.archivo.replace('.pdf',''))}</span>
      </div>
      <div class="tramo-pista">
        ${anios.map(n => `<i class="guia" style="left:${n.izq}%"></i>`).join('')}
        <a class="tramo${solapa ? ' solapa' : ''}" href="#/documento/${c.documento_id}"
           style="left:${x(i)}%; width:${Math.max(x(f) - x(i), 0.7)}%"
           title="${esc(c.inicio)} → ${esc(c.fin)} · ${dias} días · ${esc(c.cargo || 'sin cargo')}${
             c.monto_centavos != null ? ' · ' + fmtPesos(c.monto_centavos) : ''}"></a>
      </div>
      <div class="tramo-dato mono">${esc(fmtFecha(c.inicio))} → ${esc(fmtFecha(c.fin))}</div>
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
      <div class="cifra"><b>${esc(fmtPesos(t.acumulado_centavos) || '—')}</b><span>mensual acumulado</span></div>
      <div class="cifra ${d.solapes.length ? 'alerta' : ''}"><b>${d.solapes.length}</b><span>superposiciones</span></div>
      <div class="cifra"><b>${esc((t.camaras || []).map(camaraTexto).join(' + ') || '—')}</b><span>cámaras</span></div>
      <div class="cifra ${t.sin_monto ? 'alerta' : ''}"><b>${t.sin_monto}</b><span>sin monto legible</span></div>
    </div>
    ${t.sin_monto || t.sin_fechas ? `<p class="prosa" style="font-size:12.5px">
      El acumulado suma sólo los contratos con monto firme: hay ${t.sin_monto} sin monto y
      ${t.sin_fechas} sin fechas completas. <strong>Es un piso, no un total.</strong></p>` : ''}
    ${t.comprobantes ? `
    <div class="cifras" style="margin:10px 0 4px">
      <div class="cifra facturado"><b>${t.comprobantes}</b><span>facturas y recibos</span></div>
      <div class="cifra facturado"><b>${esc(fmtPesos(t.facturado_centavos) || '—')}</b><span>facturado legible</span></div>
      ${t.comprobantes_sin_importe ? `<div class="cifra alerta">
        <b>${t.comprobantes_sin_importe}</b><span>importes a mano, sin leer</span></div>` : ''}
    </div>
    <p class="prosa" style="font-size:12.5px">
      <strong>Lo facturado no se suma con lo contratado.</strong> El mensual acumulado es
      lo que dicen los contratos por mes; lo facturado es lo que esta persona cobró. Son
      la misma plata vista de los dos lados${t.comprobantes_sin_importe
        ? `, y el facturado además está incompleto: ${plural(t.comprobantes_sin_importe,
            'comprobante trae el importe a mano', 'comprobantes traen el importe a mano')}
           y el sistema no lo lee` : ''}.</p>` : ''}

    <h3 style="margin-top:24px">Cronología</h3>
    ${cronologia(d.contratos, d.solapes)}

    ${d.solapes.length ? `
      <h3 style="margin-top:26px">Períodos que se pisan</h3>
      ${tabla([
        {t:'Folios', c:'fol', r:f => `${esc(f.archivo_a)}<br>${esc(f.archivo_b)}`},
        {t:'Cruce', r:f => f.cruce === 'intercámara' ? `<span class="marca">${esc(f.cruce)}</span>` : esc(f.cruce)},
        {t:'Desde', c:'mono', r:f => esc(fmtFecha(f.desde))},
        {t:'Hasta', c:'mono', r:f => esc(fmtFecha(f.hasta))},
        {t:'Días', k:'dias', c:'num'},
      ], d.solapes)}` : ''}

    <h3 style="margin-top:26px">Contratos</h3>
    ${tabla([
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', r:f => esc(camaraTexto(f.camara))},
      {t:'Cargo', r:f => esc(f.cargo || '—')},
      {t:'Inicio', c:'mono', r:f => f.inicio ? esc(fmtFecha(f.inicio)) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Fin', c:'mono', r:f => f.fin ? esc(fmtFecha(f.fin)) : '<span class="nulo">Ø sin dato</span>'},
      {t:'Monto', c:'num', r:f => f.monto_centavos == null ? '<span class="nulo">Ø sin dato</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], d.contratos, {alClic:true, lista:'contratos'})}

    ${(d.comprobantes || []).length ? `
      <h3 style="margin-top:26px">Facturas y recibos</h3>
      <p class="prosa" style="font-size:12.5px">Emitidos con el mismo documento. El CUIL de
        la factura lleva adentro el DNI del contrato, así que se enganchan solos.</p>
      ${tabla([
        {t:'Archivo', k:'archivo', c:'fol'},
        {t:'Tipo', r:f => esc(TIPO_DOC[f.tipo] || f.tipo)},
        {t:'Comprobante', c:'mono', r:f => f.comprobante ? esc(f.comprobante) : '<span class="nulo">Ø sin dato</span>'},
        {t:'Emitida', c:'mono', r:f => f.emitida ? esc(fmtFecha(f.emitida)) : '<span class="nulo">Ø sin dato</span>'},
        {t:'Importe', c:'num', r:f => f.monto_centavos == null
            ? '<span class="nulo">Ø a mano</span>' : esc(fmtPesos(f.monto_centavos))},
        {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
      ], d.comprobantes, {alClic:true, lista:'comprobantes'})}` : ''}

    ${d.interpretaciones.length ? `
      <div style="margin-top:26px">
        <span class="rotulo">Carril de interpretación</span>
        <p class="prosa" style="font-size:13px;margin:6px 0 12px">Nada de esto se leyó de un
          papel. Son hipótesis armadas cruzando los datos de arriba, y pueden estar mal.</p>
        ${d.interpretaciones.map(interpHTML).join('')}
      </div>` : ''}`);

  // OJO: antes esto tomaba «la última tabla» y le enganchaba los contratos. Con la de
  // comprobantes abajo, cada fila de una factura abría el contrato del mismo índice.
  // Ahora cada tabla se marca con lo que muestra y el clic va a lo que dice la fila.
  vista.querySelectorAll('table[data-lista]').forEach(tabla => {
    const filas = tabla.dataset.lista === 'contratos' ? d.contratos : d.comprobantes;
    tabla.querySelectorAll('tbody tr').forEach(tr =>
      tr.onclick = () => location.hash = '#/documento/' + filas[+tr.dataset.i].documento_id);
  });
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
      <p class="medido">La cifra exacta se está volviendo a medir: el generador de prueba
        tenía motas de fotocopia de un píxel, y como el píxel es más grande a baja
        resolución, castigaba al escaneo de 100 DPI por una razón que en el papel no
        existe. Lo que ya no cambia: <strong>a 100 DPI el sistema deja de servir</strong>,
        y en todos los casos con <strong>cero errores silenciosos</strong> —cuando el
        escaneo es malo el sistema no inventa, deja el campo vacío y lo manda a
        revisión—.</p>
      <p><strong>Más de 300 no hace falta:</strong> de ahí para arriba no se gana nada
        medible y el archivo pesa el doble.</p>
      <p><strong>Y nunca el «modo texto»</strong> en blanco y negro puro que muchos
        escáneres traen puesto, aunque el número de exactitud mejore. Es la única
        configuración de todo lo que probamos que <strong>guardó un dato falso dándolo
        por bueno</strong>.</p>
      <p class="medido">El mismo contrato, el mismo campo. En grises, las dos rutas de
        lectura discreparon: conflicto, campo vacío, a la cola.
        En blanco y negro leyeron las dos <span class="mono">ALMADA, Rosa 1</span>
        —la inicial <span class="mono">I.</span> convertida en un
        <span class="mono">1</span>— y el sistema lo aceptó solo con
        <span class="mono">0,92</span> de confianza. El umbral limpió la mancha del
        punto, las dos rutas coincidieron <span class="marca">en el error</span>, y el
        sistema se quedó sin la señal que usa para saber que no sabe.</p>
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
      ${t.estado === 'corriendo' ? `<div class="pie-progreso">
         <button class="boton gris" id="b-detener">Parar</button>
         <span>Se termina la página que está en curso y ahí frena. Lo leído queda
           guardado: al procesar de nuevo retoma donde iba.</span></div>` : ''}
      ${t.estado === 'terminado' ? `<p class="prosa" style="font-size:13px;margin:10px 0 0">
         <strong>Listo.</strong> ${esc(t.mensaje)} · ${t.segundos} s.
         <a href="#/panel">Ver el panel</a> · <a href="#/cola">Ir a la cola</a></p>` : ''}
      ${t.estado === 'detenido' ? `<div class="aviso" style="margin-top:10px">
         <span class="sello atencion" style="flex:none">Parado</span>
         <span>${esc(t.mensaje)}</span></div>` : ''}
      ${t.estado === 'error' ? `<div class="aviso" style="margin-top:10px">
         <span class="sello alerta">Error</span><span>${esc(t.mensaje)}</span></div>` : ''}
      ${(t.errores || []).length ? `<details style="margin-top:10px"><summary class="rotulo">
         ${plural(t.errores.length, 'documento con problemas', 'documentos con problemas')}</summary>
         <ul style="margin-top:8px">${t.errores.slice(0,20).map(e =>
           `<li>${esc(e.etapa)}: ${esc(e.detalle)}</li>`).join('')}</ul></details>` : ''}
    </div>`;

  const parar = $('#b-detener');
  if (parar) parar.onclick = async () => {
    parar.disabled = true;
    parar.textContent = 'parando…';
    try { await api('/api/detener', {method: 'POST',
                                     headers: {'Content-Type': 'application/json'},
                                     body: '{}'}); }
    catch (e) { alert('No se pudo parar: ' + e.message); parar.disabled = false; }
  };
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


/* ── Acerca del sistema ────────────────────────────────────────────────────
   Quién firma esto y qué versión se está usando. Es la pantalla que se abre cuando
   alguien pregunta «¿esto de dónde salió?» —en una audiencia, en una reunión— y hay
   que contestar sin buscar en ningún lado. Los nombres salen de ufil/identidad.py:
   acá no hay ninguno escrito. */
async function vAcerca() {
  const d = IDENTIDAD || await api('/api/identidad');
  const c = await api('/api/cuentas').catch(() => ({}));
  const fiscales = (d.fiscales || []);

  vista.innerHTML =
    bloque('f. 0000', 'Identidad', `
      <h2>${esc(d.sistema)}</h2>
      <div class="ficha-identidad">
        <div class="jerarquia">
          <div class="nivel n1">${esc(d.linea_organismo)}</div>
          <div class="nivel n2">${esc(d.unidad_larga)}</div>
          <div class="nivel n3">${esc(d.area)}</div>
          <div class="nivel n4">${esc(d.sistema)}</div>
        </div>
        ${fiscales.length ? `<div class="fiscales">
          <div class="rotulo">${esc(fiscales.length > 1 ? d.rotulo_fiscales : 'Fiscal')}</div>
          <ul>${fiscales.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
        </div>` : ''}
      </div>
      <p class="prosa">Estos nombres son los que salen impresos en la portada de cada
        planilla y de cada informe que genera el sistema. Se cambian en un solo lugar
        —<span class="mono">ufil/identidad.py</span>, o un archivo
        <span class="mono">identidad.json</span> en la carpeta de datos— y cambian en
        todas partes a la vez.</p>`) +
    bloque('f. 0000', 'Versión', `
      <h2>Qué versión estás usando</h2>
      <table class="salud"><tbody>
        <tr><td>${sello('neutro', 'Interfaz')}</td>
            <td class="mono">${esc(VERSION_CARGADA || c.version || '—')}</td>
            <td>La huella del archivo de la interfaz que cargó esta pestaña. Si el
              servidor pasa a servir otra, aparece un aviso arriba.</td></tr>
        <tr><td>${sello('neutro', 'Legajo abierto')}</td>
            <td class="mono">${esc(c.legajo ? c.legajo.numero : 'ninguno')}</td>
            <td>${c.legajo ? esc(c.legajo.caratula)
              : 'Cada legajo es una base separada. <a href="#/legajos">Elegir uno</a>.'}</td></tr>
      </tbody></table>
      <p class="prosa">Lo que hace y lo que <strong>no</strong> hace el sistema está
        contado en <a href="#/como-funciona">Cómo funciona</a>. Si algo no anda,
        <a href="#/salud">Estado del sistema</a> dice qué falta y cómo se arregla.</p>`);
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

  // Qué versión se está viendo. Existe porque hubo que averiguarlo a mano: se
  // desplegó una versión nueva, el servidor la estaba sirviendo, y desde afuera no
  // había forma de saber si lo que aparecía en pantalla era esa o una guardada en el
  // navegador. Con este número la pregunta se contesta mirando.
  const version = `<p class="version-app">
    Versión de la interfaz <span class="mono">${esc(s.version)}</span> ·
    esquema de la base <span class="mono">v${esc(s.esquema)}</span>${
      VERSION_CARGADA && VERSION_CARGADA !== s.version
        ? ` · <strong>hay una versión más nueva en el servidor</strong>:
            <a href="#" onclick="location.reload();return false">recargar</a>` : ''}</p>`;

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
    ${version}
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
  '#/acerca': 'Acerca del sistema',
  '#/panel':'Panel', '#/ingesta':'Cargar escaneos', '#/buscar':'Buscar',
  '#/contratos':'Contratos', '#/personas':'Personas',
  '#/superposiciones':'Superposiciones', '#/cola':'Cola de revisión',
  '#/identidad':'Identidad', '#/interpretacion':'Interpretación',
  '#/consultas':'Consultas', '#/documento':'Documento', '#/persona':'Ficha',
  '#/como-funciona':'Cómo funciona', '#/salud':'Estado del sistema',
  '#/afuera':'Quedaron afuera', '#/legajos':'Legajos',
  '#/comprobantes':'Facturas y recibos', '#/cruce':'Facturado contra contratado',
};

/* ── Cuánto ocupa la barra de arriba ───────────────────────────────────────
   Lo que se pega más abajo —la lupa de la cola de revisión— tiene que empezar donde
   termina el techo.

   Eso estuvo escrito a mano en el CSS y estaba mal: el encabezado medía 71 px y el
   CSS decía 59, así que las pestañas se le montaban 12 px encima. Y ningún número
   fijo podía acertar, porque las pestañas entraban en uno o dos renglones según el
   ancho de la ventana.

   Con la navegación al costado quedó una sola tira arriba y su alto ya no depende del
   ancho, pero se sigue midiendo: es una línea de código contra un defecto que ya
   apareció una vez. */
function medirTecho() {
  const e = document.querySelector('#techo');
  const alto = e && !e.hidden ? Math.round(e.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty('--h-techo', alto + 'px');
}
addEventListener('resize', medirTecho);

/* Si el servidor pasó a servir otra versión, se avisa y se ofrece recargar. No se
   recarga solo: alguien puede estar a mitad de un valor tipeado en la cola, y perderlo
   por una actualización sería peor que seguir con la versión de antes un rato más. */
function avisarSiHayVersionNueva(version) {
  if (!VERSION_CARGADA || !version || version === VERSION_CARGADA) return;
  if ($('#aviso-version')) return;
  const barra = document.createElement('div');
  barra.id = 'aviso-version';
  barra.innerHTML = `<span class="sello atencion">Actualizado</span>
    <span>Se instaló una versión nueva del sistema mientras tenías esto abierto.
      <button class="boton gris" id="b-recargar">Recargar</button></span>`;
  document.body.insertBefore(barra, document.body.firstChild);
  $('#b-recargar').onclick = () => location.reload();
  medirTecho();
}

/* Pinta la cinta de legajo y decide si hay que mandar a elegir uno. Devuelve true
   cuando redirigió, para que quien la llame no siga pintando datos que no van. */
function pintarLegajo(p) {
  const l = p.legajo;
  document.body.classList.toggle('con-legajo', !!l);
  $('#l-numero').textContent = l ? l.numero : '—';
  $('#l-caratula').textContent = l ? l.caratula : 'Ninguno abierto';
  $('#t-legajo').title = l
    ? `Legajo ${l.numero} — ${l.caratula}` + (l.fiscal ? ` · Fiscal: ${l.fiscal}` : '')
      + '\nTocá para cambiar de legajo'
    : 'Elegir un legajo';
  medirTecho();          // aparecer o irse el aviso corre todo lo de abajo
  // Sin legajo abierto, a elegir uno. Vale tanto para la instalación recién puesta
  // —donde lo primero que hay que hacer es abrir la causa, no cargar escaneos en una
  // base suelta— como para el que acaba de cerrar la que tenía.
  //
  // La excepción es la instalación anterior a los legajos, que tiene material en la
  // base suelta y sigue trabajando ahí: a esa no se la manda a ningún lado.
  if (!l && !p.documentos && !location.hash.startsWith('#/legajos')) {
    location.hash = '#/legajos';
    return true;
  }
  return false;
}

/* La versión de interfaz que cargó ESTA pestaña. Se fija en el primer refresco y no
   cambia más: si el servidor pasa a informar otra, es que se actualizó abajo mientras
   la pestaña estaba abierta. Quien deja el sistema abierto todo el día seguiría usando
   la anterior sin enterarse. */
let VERSION_CARGADA = null;

async function refrescarCuentas() {
  try {
    // `/api/cuentas` y no `/api/panel`: el panel entero corre nueve consultas de
    // análisis y en un legajo de 1.500 contratos tarda casi un segundo. Esto se llama
    // al abrir cualquier pantalla y después de CADA decisión de la cola; revisar cien
    // campos costaba cien segundos repartidos en pedacitos.
    const p = await api('/api/cuentas');
    if (VERSION_CARGADA === null) VERSION_CARGADA = p.version;
    avisarSiHayVersionNueva(p.version);
    pintarLegajo(p);
    const av = document.getElementById('aviso-demo');
    if (av) av.hidden = !p.demostracion;
    document.body.classList.toggle('con-demo', !!p.demostracion);
    cuentas = {a_revisar: p.a_revisar, fusiones: p.fusiones, afuera: p.afuera};
    pintarNav(location.hash || '#/panel');
    // El lote sólo cuando hay uno. «lote —» es una etiqueta sin dato: ocupa el mismo
    // lugar que algo útil y no dice nada.
    $('#f-lote').textContent = p.lote || '';
    $('#t-lote').hidden = !p.lote;
    const marca = document.getElementById('identidad-oficial');
    if (marca) marca.hidden = !p.marca;

    ULTIMO_PANEL = p;
    pintarEstadoTecho();
  } catch (e) { /* base todavía vacía */ }
}

/* ── Qué está pasando, arriba a la derecha ─────────────────────────────────
   Un solo sello dice lo único que importa saber sin ir a buscarlo: si el sistema
   está leyendo escaneos en este momento y por dónde va, o —si no está haciendo
   nada— cuánto queda por revisar.

   Que el avance se vea desde cualquier pantalla no es un lujo: procesar un lote de
   trescientas fojas tarda minutos, y hasta ahora la única manera de saber si seguía
   era volver a la pantalla de carga. Quien se iba a mirar contratos no tenía forma
   de enterarse de que había terminado. */
let ULTIMO_PANEL = null;
let TRABAJO = null;

function pintarEstadoTecho() {
  const el = $('#sello-estado');
  const p = ULTIMO_PANEL;
  if (TRABAJO && TRABAJO.estado === 'corriendo') {
    const pct = TRABAJO.total ? Math.round(100 * TRABAJO.hecho / TRABAJO.total) : 0;
    return pintarSello(el, 'trabajando', `Leyendo ${pct}%`, {gira: true,
      titulo: `${TRABAJO.etapa || 'procesando'} · ${TRABAJO.hecho} de ${TRABAJO.total}`});
  }
  if (!p) { el.hidden = true; return; }
  // «Al día» sobre una base vacía es afirmar terminado un trabajo que no empezó.
  // Sin documentos no hay estado que informar, y decirlo así es lo honesto.
  if (!p.documentos) return pintarSello(el, 'neutro', 'Sin documentos');
  if (p.a_revisar) return pintarSello(el, 'atencion',
    plural(p.a_revisar, 'campo a revisar', 'campos a revisar'), {relleno: true});
  pintarSello(el, 'ok', 'Todo revisado');
}

/* Mientras hay algo corriendo se pregunta cada dos segundos; cuando no hay nada, no
   se pregunta más y se espera al próximo refresco. Un temporizador que sigue latiendo
   sobre una pestaña abierta toda la tarde es tráfico que no sirve a nadie. */
let vigilando = null;
async function vigilarTrabajo() {
  clearTimeout(vigilando);
  try {
    const t = await api('/api/trabajo');
    const terminaba = TRABAJO && TRABAJO.estado === 'corriendo';
    TRABAJO = t;
    pintarEstadoTecho();
    if (t.estado === 'corriendo') vigilando = setTimeout(vigilarTrabajo, 2000);
    else if (terminaba) refrescarCuentas();   // terminó: los números cambiaron
  } catch (e) { TRABAJO = null; }
}

const rutas = [
  [/^#\/legajos$/,               vLegajos],
  [/^#\/panel$/,                 vPanel],
  [/^#\/ingesta$/,               vIngesta],
  [/^#\/contratos$/,             vContratos],
  [/^#\/comprobantes$/,          vComprobantes],
  [/^#\/cruce$/,                 vCruce],
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
  [/^#\/acerca$/,                vAcerca],
  [/^#\/afuera$/,                vAfuera],
  [/^#\/salud$/,                 vSalud],
];

async function rutear() {
  const h = location.hash || '#/panel';
  pintarNav(h);
  const base = '#/' + h.split('/')[1];
  document.title = (TITULOS[base] || 'Análisis documental')
    + ' · ' + (IDENTIDAD ? IDENTIDAD.unidad : 'UFIL Paraná');
  // La cola ocupa el alto entero de la ventana y apaga el desplazamiento de la
  // página. Al salir de ahí hay que devolverlo, o el resto del sistema queda con el
  // pie cortado y sin manera de bajar.
  document.body.classList.remove('taller-abierto');
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

/* ── El tema ───────────────────────────────────────────────────────────────
   Decía «Tema», que no es ni una pregunta ni una respuesta: no se sabe si dice en
   qué tema estás o qué tema vas a poner. Ahora dice qué va a pasar si lo tocás.

   Sin elección guardada manda la preferencia del sistema, que es lo que la persona
   ya configuró una vez y no tiene por qué repetir acá. */
const temaDelSistema = () =>
  matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
const temaPuesto = () => document.documentElement.dataset.tema || temaDelSistema();

const ICONO_TEMA = {
  oscuro: '<circle cx="9" cy="9" r="3.6" fill="none"/><path d="M9 1.4v2M9 14.6v2' +
          'M1.4 9h2M14.6 9h2M3.6 3.6 5 5M13 13l1.4 1.4M14.4 3.6 13 5M5 13l-1.4 1.4"/>',
  claro:  '<path d="M15.3 10.6A6.6 6.6 0 0 1 7.4 2.7a6.9 6.9 0 1 0 7.9 7.9z" fill="none"/>',
};

function pintarBotonTema() {
  const proximo = temaPuesto() === 'oscuro' ? 'claro' : 'oscuro';
  const b = $('#b-tema');
  b.innerHTML = `<svg viewBox="0 0 18 18" width="15" height="15" aria-hidden="true"
      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"
      >${ICONO_TEMA[proximo]}</svg><span>Activar modo ${proximo}</span>`;
  b.setAttribute('aria-pressed', String(temaPuesto() === 'oscuro'));
}

$('#b-tema').onclick = () => {
  const nuevo = temaPuesto() === 'oscuro' ? 'claro' : 'oscuro';
  document.documentElement.dataset.tema = nuevo;
  try { localStorage.setItem('ufil.tema', nuevo); } catch (e) {}
  pintarBotonTema();
};
try { const t = localStorage.getItem('ufil.tema'); if (t) document.documentElement.dataset.tema = t; } catch (e) {}
// Quien no eligió sigue al sistema, y lo sigue también cuando el sistema cambia solo
// —muchos escritorios pasan a oscuro al anochecer—.
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pintarBotonTema);
pintarBotonTema();

/* ── El cajón de la barra lateral, en pantallas chicas ─────────────────────
   Se cierra con Escape, tocando el velo, y sola cuando se elige a dónde ir: dejarla
   abierta tapando lo que la persona acaba de pedir es hacerle tocar dos veces. */
const lateral = $('#lateral'), velo = $('#velo'), bMenu = $('#b-menu');
function cajon(abrir) {
  lateral.classList.toggle('abierta', abrir);
  velo.hidden = !abrir;
  bMenu.setAttribute('aria-expanded', String(abrir));
  if (abrir) lateral.querySelector('a, button')?.focus();
}
bMenu.onclick = () => cajon(!lateral.classList.contains('abierta'));
velo.onclick = () => cajon(false);
lateral.addEventListener('click', e => { if (e.target.closest('a')) cajon(false); });
addEventListener('keydown', e => {
  if (e.key === 'Escape' && lateral.classList.contains('abierta')) { cajon(false); bMenu.focus(); }
});

/* ── La búsqueda de arriba ─────────────────────────────────────────────────
   Es la misma pantalla de búsqueda de siempre; lo único que cambia es que se puede
   empezar desde cualquier lado sin ir a buscarla. */
$('#t-buscar').onsubmit = e => {
  e.preventDefault();
  const q = $('#q-rapida').value.trim();
  if (q) location.hash = '#/buscar/' + encodeURIComponent(q);
};
// «/» para empezar a buscar, como en cualquier otra herramienta de texto. No se roba
// la tecla si la persona está escribiendo en otro campo.
addEventListener('keydown', e => {
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
  const a = document.activeElement;
  if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return;
  e.preventDefault();
  $('#q-rapida').focus();
  $('#q-rapida').select();
});

/* ── Quién firma ───────────────────────────────────────────────────────────
   Los nombres de la casa vienen del servidor (ufil/identidad.py), no escritos acá:
   cambiar de fiscal no puede obligar a tocar seis archivos. */
async function pintarIdentidad() {
  try {
    const d = await api('/api/identidad');
    IDENTIDAD = d;
    $('#m-unidad').textContent = d.unidad;
    $('#m-area').textContent = d.area;
    $('#m-organismo').textContent = d.linea_organismo;
    const oficial = $('#identidad-oficial');
    if (oficial) oficial.alt = d.linea_organismo;
    document.title = document.title.replace(/· .*$/, '· ' + d.unidad);
  } catch (e) { /* la barra ya trae los valores de la casa escritos en el HTML */ }
}
let IDENTIDAD = null;

medirTecho();
addEventListener('hashchange', rutear);
pintarIdentidad();
rutear();
refrescarCuentas();
vigilarTrabajo();
