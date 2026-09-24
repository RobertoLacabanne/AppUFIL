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
  desconocida:'Sin reconocer', desconocido:'Sin reconocer',
  // Los de una contratación: sin ellos la pantalla mostraba la clave de la base.
  orden_compra:'Orden de compra', orden_pago:'Orden de pago', presupuesto:'Presupuesto',
  oferta:'Oferta', acta_apertura:'Acta de apertura', pliego:'Pliego',
  especificacion:'Especificación técnica', adjudicacion:'Adjudicación',
  dictamen:'Dictamen', cuadro_comparativo:'Cuadro comparativo', pedido:'Pedido',
};
/* Cómo se llama una contratación en pantalla. Las que se armaron sin expediente leído
   se llaman todas «Contratación por verificar» en la base; se las nombra por la pieza
   de la que salen —«Orden de compra, f. 7»— y el archivo va aparte, en chico. */
function nombreContratacion(c) {
  if (!c) return '';
  if (c.ancla && (!c.expediente || /por verificar/i.test(c.nombre || ''))) {
    const tipo = TIPO_DOC[c.ancla.tipo] || (c.ancla.tipo ? String(c.ancla.tipo).replace(/_/g, ' ') : 'Pieza');
    return `${tipo.charAt(0).toUpperCase() + tipo.slice(1)}, f. ${fmtNum.format(c.ancla.pagina)}`;
  }
  return c.nombre || 'Contratación sin nombre';
}
const FAMILIA_DOC = {contrato:'Contrato', comprobante:'Comprobante de pago',
                     acto:'Acto administrativo'};
/* Por qué está esperando este campo. Es lo que se filtra en la cola. */
const CLASE_COLA = {conflicto:'Dos lecturas distintas', nulo:'No se pudo leer',
                    'baja confianza':'Leído con poca seguridad'};
/* Por qué el campo quedó vacío. La base guarda la clave; la pantalla dice la frase. */
/* Cerrar un campo sin valor es una decisión, y el botón tiene que decir qué decisión
   es. Decía «Ø ausente, firme»: la Ø es notación interna del sistema y «firme» es
   vocabulario del modelo de confianza. Nada de eso le dice a alguien qué está por
   afirmar. */
/* El botón dice la ACCIÓN; el diagnóstico ya está arriba, en el lugar del valor.
   Decía «está escrito a mano y no se lee» abajo de un «está escrito a mano»: el mismo
   motivo dos veces en la misma tarjeta, y en un teléfono uno abajo del otro. */
const TEXTO_CIERRE = {
  ausente: 'Confirmar que no está',
  ilegible: 'Confirmar que no se lee',
  ambiguo: 'Confirmar que no se puede saber cuál es',
  manuscrito: 'Confirmar que no se lee',
};

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
/* ── Quién está trabajando ─────────────────────────────────────────────────
   Esto lo usan varias personas de la fiscalía sobre la misma causa, y cada decisión
   queda registrada con quién la tomó: es lo que permite, al firmar un informe, decir
   quién verificó cada campo contra el folio.

   Antes se preguntaba con el `prompt()` del navegador, que aparecía de golpe encima
   de la primera decisión, no explicaba para qué era, y después no había manera de
   corregirlo si alguien tipeaba mal el apellido. Ahora se pide una vez en un diálogo
   propio, se ve siempre en la barra lateral, y se cambia desde ahí. */
let REVISOR = null;
try { REVISOR = localStorage.getItem('ufil.revisor') || null; } catch (e) {}

function revisor() { return REVISOR; }

function fijarRevisor(nombre) {
  REVISOR = (nombre || '').trim() || null;
  try {
    if (REVISOR) localStorage.setItem('ufil.revisor', REVISOR);
    else localStorage.removeItem('ufil.revisor');
  } catch (e) {}
  pintarRevisor();
}

function pintarRevisor() {
  const b = document.querySelector('#b-revisor');
  if (!b) return;
  b.querySelector('.quien').textContent = REVISOR || 'Sin identificar';
  b.classList.toggle('sin-nombre', !REVISOR);
  b.title = REVISOR
    ? `Cada decisión que tomes queda registrada como «${REVISOR}». Tocá para cambiarlo.`
    : 'Todavía no dijiste quién sos. Tocá para identificarte.';
}

/* Pide el nombre y devuelve una promesa con él, o con null si la persona cerró el
   diálogo. Se resuelve ANTES de tocar nada: una decisión sin nombre no se guarda, y
   el servidor la rechaza igual, así que preguntar después sería perder el trabajo. */
function pedirRevisor(yaEstan = []) {
  return new Promise(resolver => {
    const otros = (yaEstan || []).filter(q => q && q !== REVISOR);
    const d = dialogo(`
      <form method="dialog" id="f-revisor">
        <h3>¿Quién está trabajando?</h3>
        <p class="prosa">Cada campo que verifiques, corrijas o cierres queda registrado
          con tu nombre y la fecha. Es lo que permite, al firmar un informe, decir quién
          revisó cada dato contra el folio.</p>
        <p class="prosa">En esta causa trabajan varias personas sobre la misma base: sin
          esto, el trabajo de todos aparece junto y sin autor.</p>
        ${otros.length ? `<p class="rotulo">Ya trabajaron en este legajo</p>
        <div class="fila-suelta abajo" id="quienes-ya">${otros.map(q =>
          `<button type="button" class="chip" data-quien="${esc(q)}">${esc(q)}</button>`
          ).join('')}</div>` : ''}
        <label for="n-revisor">${otros.length ? 'O escribí el tuyo'
                                              : 'Apellido y nombre, o usuario'}</label>
        <!-- El marcador dice el FORMATO, no un nombre. Decía «lacabanne.r», que es un
             usuario perfectamente posible: en gris y en el mismo lugar donde después va
             el valor, se lee como un dato ya cargado, y alguien puede apretar «Listo»
             creyendo que ya está. -->
        <input id="n-revisor" autocomplete="off" spellcheck="false"
               placeholder="apellido.nombre" value="${esc(REVISOR || '')}">
        <div class="botonera">
          <button class="boton gris" value="no" type="submit">Ahora no</button>
          <button class="boton lleno" id="b-soy" type="button">Listo</button>
        </div>
      </form>`);
    const campo = $('#n-revisor', d), ok = $('#b-soy', d);
    let elegido = null;
    // Elegir de la lista es lo mismo que escribirlo, y evita que la misma persona
    // quede anotada como «Perez» y «perez, j» sobre el mismo legajo.
    d.querySelectorAll('[data-quien]').forEach(b => b.onclick = () => {
      campo.value = b.dataset.quien; ok.click();
    });
    const confirmar = () => {
      const v = campo.value.trim();
      if (!v) { campo.focus(); return; }
      elegido = v;
      d.close();
    };
    ok.onclick = confirmar;
    campo.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); confirmar(); } };
    d.addEventListener('close', () => {
      if (elegido) fijarRevisor(elegido);
      resolver(elegido);
    });
    campo.focus();
    campo.select();
  });
}

/* Se llama antes de cualquier acción que quede registrada. Devuelve el nombre, o null
   si la persona decidió no identificarse —y en ese caso no se hace nada—. */
async function conRevisor() {
  return REVISOR || await pedirRevisor();
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
    return `<span class="nulo ${c.nulo_motivo === 'conflicto' ? 'conf' : ''}" title="${esc(MOTIVO_NULO[c.nulo_motivo] || c.nulo_motivo)}">—</span>`;
  const dudoso = c.confianza != null && c.confianza < 0.85 ? ' dudoso' : '';
  return `<span class="mono${dudoso}">${esc(c.valor_literal)}</span>`;
}

/* Una vista entera en estado vacío, con la misma retícula que las demás. */
function vistaVacia(folio, rotulo, titulo, cabeza, texto) {
  // El paso siguiente depende de dónde está parada la persona: sin legajo, cargar
  // escaneos no es el paso siguiente sino el error que se está tratando de evitar; y
  // ofrecer «Cargar escaneos» en cualquier pantalla vacía es mandar a cargar cuando lo
  // que falta, casi siempre, es revisar o procesar.
  let accion = sinLegajo()
    ? {href:'#/legajos', texto:'Elegir o crear un legajo'}
    : (rotulo === 'Datos' ? {href:'#/ingesta', texto:'Cargar escaneos'} : null);

  // Mientras se procesa, una pantalla vacía no está vacía: todavía no llegó. Decir
  // «no hay» en ese momento es afirmar algo que en dos minutos va a ser falso.
  if (typeof TRABAJO !== 'undefined' && TRABAJO && TRABAJO.estado === 'corriendo') {
    cabeza = 'Procesando documentos';
    texto = 'El sistema está extrayendo datos en este momento. Los resultados van a aparecer acá cuando termine.';
    accion = null;
  }

  vista.innerHTML = bloque(folio, rotulo, `
    <h2>${esc(titulo)}</h2>
    ${vacio(cabeza, esc(texto), accion)}
  `);
}

/* Estado vacío: en vez de una grilla de ceros, qué es esto y qué hacer ahora.
   `texto` es HTML: quien llama escapa lo que venga de datos, y puede poner un enlace. */
function vacio(titulo, texto, accion) {
  return `<div class="vacio-env">
    <div class="vacio-icono" aria-hidden="true">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
    </div>
    <div class="vacio-titulo">${esc(titulo)}</div>
    <div class="vacio-texto">${texto}</div>
    ${accion ? `<a class="boton vacio-accion" href="${esc(accion.href)}">${esc(accion.texto)}</a>` : ''}
  </div>`;
}

function bloque(folio, rotulo, html) {
  return `<section class="bloque">
    <div class="marginalia"><span>${esc(folio)}</span><span class="rotulo">${esc(rotulo)}</span></div>
    <div class="cuerpo">${html}</div></section>`;
}

/* La clase de una celda, y cuál de las columnas se lleva el ancho que sobra.

   Dos cosas que faltaban y se veían las dos en la misma pantalla. Una columna de
   números iba alineada a la derecha y su rótulo a la izquierda: en «Trabajo del
   equipo» el rótulo CAMPOS REVISADOS quedaba a un extremo y su `1` al otro, a
   cuatrocientos píxeles, y el ojo no los conecta —parece que el 1 es de otra cosa—.
   El rótulo se alinea como su dato, y para eso el `<th>` tiene que llevar la misma
   clase que el `<td>`.

   Y la tabla repartía el ancho sobrante entre todas: cuatro valores cortos estirados
   sobre 900 px se leen peor que los mismos cuatro juntos a la izquierda. Ahora el
   sobrante se lo lleva UNA columna —la última que no sea de números, porque estirar
   una de números aleja el número de su rótulo otra vez— y las demás miden lo que
   mide su contenido. */
function claseCol(cols, c, i, filas) {
  return ((c.c || '') + (i === cualCrece(cols, filas) ? ' crece' : '')).trim();
}

/* Cuál de las columnas se lleva el ancho que sobra: la de texto MÁS LARGO.
   La primera versión le daba el sobrante a la última que no fuera de números, y en la
   tabla de contratos esa era «Fin» —una fecha de nueve caracteres— que se quedaba con
   doscientos píxeles mientras «Contratado/a» se apretaba y los apellidos caían en dos
   renglones. El sobrante tiene que ir donde hace falta.
   Las de números quedan afuera: estirar una aleja el número de su rótulo, que es
   justo lo que esto vino a arreglar. */
const _crece = new WeakMap();
function cualCrece(cols, filas) {
  if (_crece.has(cols)) return _crece.get(cols);
  let cual = -1, largo = -1, ultimaSuelta = -1;
  const sinEtiquetas = h => String(h).replace(/<[^>]*>/g, '');
  const muestra = (filas || []).slice(0, 40);
  // Las que nunca se parten no compiten: un CUIL, una fecha, un nombre de archivo, un
  // importe o el nombre de una persona son UN token y no bajan de renglón, así que el
  // ancho de más no les cambia nada y se lo sacan a la que sí se estaría partiendo.
  // Medido en la tabla de contratos: el sobrante se lo llevaba «Archivo» —19
  // caracteres que no se cortan— mientras «Contratado/a» partía los apellidos en dos
  // renglones. Hoy «Contratado/a» tampoco se parte —lleva la clase `nombre`— así que
  // también queda afuera del reparto, y el sobrante va a la columna que de verdad lo
  // necesita.
  const noSeParte = c => /(^|\s)(num|mono|fol|nowrap|nombre)(\s|$)/.test(c.c || '');
  cols.forEach((c, i) => {
    if (/(^|\s)num(\s|$)/.test(c.c || '')) return;
    ultimaSuelta = i;
    if (noSeParte(c)) return;
    let max = c.t.length;
    for (const f of muestra) {
      try {
        max = Math.max(max, sinEtiquetas(c.r ? c.r(f) : (f[c.k] ?? '')).trim().length);
      } catch (e) { /* una columna que no se puede medir no compite */ }
    }
    if (max > largo) { largo = max; cual = i; }
  });
  // Si todas son de las que no se parten, igual tiene que sobrar en algún lado: sin
  // esto la tabla vuelve a repartir el sobrante entre todas y se estira entera.
  if (cual < 0) cual = ultimaSuelta;
  _crece.set(cols, cual);
  return cual;
}

function tabla(cols, filas, opts = {}) {
  if (!filas.length) return `<div class="tabla-env"><div class="vacio">Sin resultados.</div></div>`;
  const th = cols.map((c, i) => `<th class="${claseCol(cols, c, i, filas)}">${
    esc(c.t)}</th>`).join('');
  // `data-rotulo` en cada celda: cuando la tabla no entra y la fila se despliega, el
  // encabezado de columna deja de estar arriba y cada valor tiene que decir de qué
  // columna es. Es el mismo texto del `<th>`, así que no hay dos rótulos que
  // mantener sincronizados.
  const tr = filas.map((f, i) => `<tr class="${opts.alClic ? 'clic' : ''}" data-i="${i}"${opts.alClic ? ' tabindex="0"' : ''}>${
    cols.map((c, i) => `<td class="${claseCol(cols, c, i, filas)}" data-rotulo="${esc(c.t)}">${
      c.r ? c.r(f) : esc(f[c.k] ?? '')}</td>`).join('')
  }</tr>`).join('');
  // `lista` marca QUÉ muestra esta tabla. Hace falta cuando una pantalla tiene más de
  // una: enganchar el clic por «la última tabla» funcionaba hasta que se agregó otra
  // debajo, y entonces cada fila abría el documento equivocado.
  const marca = opts.lista ? ` data-lista="${esc(opts.lista)}"` : '';
  return `<div class="tabla-env"><table${marca}><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

/* ── Ninguna tabla muestra un dato cortado ─────────────────────────────────
   `overflow-x:auto` dejaba correr la tabla de costado, y eso alcanzaba mientras lo
   que quedaba afuera fuera una columna que se recupera mirando la fila. No es el
   caso. Medido en 1366×768, en «Superposición temporal»: la tabla pide 976 px y la
   hoja le da 875, así que «Conf.» desaparece entera y de «Suma» se ve `$164.` y
   `$329.`. UN IMPORTE CORTADO NO SE VE CORTADO: `$164.` es un número perfectamente
   plausible, y el que lo lee no tiene cómo saber que le falta la mitad. El sistema
   entero está construido para no decir un dato que no está en el papel, y acá lo
   estaba diciendo mal por una cuestión de ancho.

   Tres cosas, en este orden:

   1. LA MEDIDA, no un punto de corte. Un `@media (max-width: …)` no sabe cuánto
      ocupa el contenido: la misma pantalla con seis columnas entra y con nueve no.
      Acá se compara `scrollWidth` contra `clientWidth` del envoltorio, después de
      pintar, y se vuelve a comparar en cada cambio de tamaño con un `ResizeObserver`.
   2. PRIMERO, EL ANCHO QUE YA HAY. La hoja reserva 112 px a la canaleta —«f. 0005 /
      CRUCE»— más el aire del cuerpo: 138 px que la tabla no está usando. Devolvérselos
      alcanza en la pantalla de la oficina (1366: pedía 976 y pasa a tener 1013) y en
      1440. Es gratis y la tabla sigue siendo una tabla.
   3. RECIÉN AHÍ, DESPLEGAR. Por debajo de ~1280 no entra ni con la canaleta devuelta
      (a 1024 faltan 249 px), y ahí la fila se abre en renglones: cada valor con el
      rótulo de su columna, nada cortado. Es lo que ya hacían a mano `table.salud` y
      `.tabla-legajos` en el teléfono, ahora para cualquier tabla y por medida.

   Una vez que una tabla pidió la hoja entera, se la queda mientras esté en pantalla.
   Devolverle la canaleta al agrandar la ventana obligaría a recordar cuánto medía la
   canaleta para saber si volvería a entrar, y a arriesgar un ida y vuelta entre los
   dos estados con el borde justo. Al cambiar de pantalla se vuelve a medir de cero. */
const _tablasVigiladas = new WeakSet();

/* Dos píxeles de holgura, para los dos lados. Los anchos que devuelve el navegador
   vienen redondeados y un borde de medio píxel alcanza para que una tabla que entra
   justo se declare cortada, se despliegue, y al desplegarse entre —y ahí vuelva a
   plegarse—. Con la holgura hay una banda muerta de cuatro píxeles entre los dos
   estados, y ninguna tabla parpadea en el borde. */
const HOLGURA_TABLA = 2;

function vigilarCortes(raiz) {
  for (const env of (raiz || document).querySelectorAll('.tabla-env')) {
    if (_tablasVigiladas.has(env)) continue;
    // El índice de legajos ya tiene su propia versión desplegada, escrita a mano y con
    // otra tipografía: dos mecanismos sobre la misma tabla se pisan.
    if (env.closest('.tabla-legajos')) continue;
    _tablasVigiladas.add(env);

    /* Cuánto pedía la tabla la última vez que se la vio cortada. Va ANOTADO EN EL
       ELEMENTO y no en una variable de esta función: desplegada no se puede volver a
       medir —desplegada siempre entra— así que este número es lo único con lo que se
       puede decidir si ya vuelve a caber. Guardado afuera del elemento se pierde en
       cuanto algo repinta, y en el DOM además se puede mirar cuando algo no cierra. */
    const pide = () => +env.dataset.pide || 0;

    const mirar = () => {
      if (env.dataset.corte === 'si') {
        if (pide() && env.clientWidth >= pide() + HOLGURA_TABLA) {
          delete env.dataset.corte;
          delete env.dataset.pide;
        }
        return;
      }
      if (env.scrollWidth <= env.clientWidth + HOLGURA_TABLA) return;   // entra
      const hoja = env.closest('.bloque');
      if (hoja && !hoja.classList.contains('ancho')) {
        hoja.classList.add('ancho');
        // Y se vuelve a medir ACÁ MISMO. Leer `scrollWidth` después de tocar la clase
        // obliga al navegador a recalcular la página en el acto, que es justo lo que
        // hace falta. Esperar a que el `ResizeObserver` avise otra vez parecía más
        // prolijo y no funcionaba: si otra tabla de la misma hoja ya la había
        // ensanchado, la clase no cambia nada, no hay cambio de tamaño, no hay aviso,
        // y la tabla se quedaba cortada para siempre. Pasaba en el panel, que tiene
        // dos tablas en la misma hoja.
        if (env.scrollWidth <= env.clientWidth + HOLGURA_TABLA) return;
      }
      env.dataset.pide = env.scrollWidth;
      env.dataset.corte = 'si';
    };

    /* Y se vuelve a medir por DOS motivos distintos, que ninguno cubre al otro:

       · cambia el TAMAÑO —se agranda la ventana, se abre la barra lateral—, y de eso
         avisa el `ResizeObserver`;
       · cambia el CONTENIDO —se filtra la tabla, se ordena, se piden más filas—, y de
         eso el `ResizeObserver` no avisa nada, porque el envoltorio mide lo mismo.
         Filtrar puede dejar afuera justo las filas del nombre más largo, y entonces
         una tabla desplegada vuelve a entrar; o al revés, «ver más filas» trae un
         importe de siete cifras y una tabla que entraba deja de entrar.

       Al cambiar el contenido, lo anotado deja de valer: el ancho que pedía era el de
       las filas de antes. Se borra, se vuelve a plegar y se mide de cero. Lo que NO se
       toca es la hoja ancha —esa traba se queda—: devolverle la canaleta y volver a
       sacársela con cada tecla de la búsqueda haría parpadear la página entera. */
    const tabla = env.querySelector('table');
    if (tabla) {
      new MutationObserver(() => {
        delete env.dataset.corte;
        delete env.dataset.pide;
        mirar();
      }).observe(tabla, {childList: true, subtree: true, characterData: true});
    }

    mirar();
    new ResizeObserver(mirar).observe(env);
  }
}

const CLASE_INTERP = {relevancia: 'Alcance del análisis', patron: 'Patrón', hipotesis: 'Hipótesis',
                      anomalia: 'Posible anomalía', coincidencia: 'Coincidencia'};
function interpHTML(i) {
  const fuentes = (i.fuentes || []).map(f =>
    `<a class="chip" href="#/documento/${f.documento_id}">${esc(f.archivo || f.nota || ('doc ' + f.documento_id))}</a>`).join('');
  // `origen` es el id de la regla que la produjo (`regla:identidad_sin_documento`):
  // sirve para depurar, no para leer. Queda en el título, no en pantalla.
  return `<div class="interp" title="${esc(i.origen || '')}">
    <span class="clase">${esc(CLASE_INTERP[i.clase] || String(i.clase || '').replace(/_/g, ' '))}</span>
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
/* ── La barra lateral, agrupada por lo que la persona vino a hacer ─────────
   Esto era una lista de trece secciones de primer nivel ordenadas por el orden en que
   se fueron implementando. Trece entradas planas no son una jerarquía: son una lista,
   y el orden no le decía nada a quien trabaja porque respondía a cómo se construyó el
   sistema y no a lo que se viene a hacer.

   Peor que el largo era la mezcla. «Foliatura» y «Tablas» —que son trabajo de
   revisión del mismo calibre que la cola— estaban enterradas dentro de «Documentos»,
   donde nadie las busca cuando se sienta a revisar; «Relaciones» estaba sola en primer
   nivel haciendo el mismo trabajo; «Consultas» colgaba de «Hallazgos» siendo una
   herramienta de búsqueda; y «Cargar escaneos» vivía en «Documentos» siendo
   administración del legajo.

   Ahora son cinco grupos nombrados por la pregunta que contestan. El grupo es un
   rótulo, no un destino: no se navega a un grupo. El razonamiento completo, y por qué
   cada cosa se movió a donde se movió, está en docs/NAVEGACION_RONDA_FINAL.md. */
const GRUPOS = [
  {grupo: 'Investigación', entradas: [
    {id: 'panel', rotulo: 'Resumen', hash: '#/panel'},
    {id: 'contrataciones', rotulo: 'Contrataciones', hash: '#/contrataciones', tambien: ['#/contratacion']},
    {id: 'precios', rotulo: 'Ítems y precios', hash: '#/precios', tambien: ['#/renglon']},
    {id: 'proveedores', rotulo: 'Proveedores', items: [
      {hash: '#/proveedores', rotulo: 'Empresas proveedoras'},
      {hash: '#/personas', rotulo: 'Personas'},
      {hash: '#/entidades', rotulo: 'Todas las fichas'}
    ], tambien: ['#/entidad', '#/persona', '#/proveedor']},
    // «Hallazgos» queda con una sola cosa adentro: los hallazgos revisables. Los
    // cruces pasan a «Comparaciones», que es lo que son: análisis transversales que
    // PRODUCEN hallazgos, no hallazgos ellos mismos. Tenerlos adentro hacía que el
    // contador de la sección mezclara «esto hay que mirarlo» con «esta herramienta
    // existe».
    {id: 'hallazgos', rotulo: 'Hallazgos', hash: '#/hallazgos'},
    {id: 'comparaciones', rotulo: 'Comparaciones', items: [
      {hash: '#/cruce',           rotulo: 'Facturado contra contratado'},
      {hash: '#/superposiciones', rotulo: 'Superposiciones'},
      {hash: '#/numeros',         rotulo: 'Números escritos dos veces'},
      {hash: '#/interpretacion',  rotulo: 'Interpretación'},
    ]},
    {id: 'cronologia', rotulo: 'Cronología', hash: '#/cronologia'},
  ]},
  {grupo: 'Documentación', entradas: [
    {id: 'documentos', rotulo: 'Documentos', items: [
      {hash: '#/piezas',       rotulo: 'Todos los documentos'},
      {hash: '#/contratos',    rotulo: 'Contratos'},
      {hash: '#/comprobantes', rotulo: 'Facturas y recibos'},
      {hash: '#/fojas',        rotulo: 'Fojas del expediente'},
      {hash: '#/conjuntos',    rotulo: 'Conjuntos documentales'},
    ], tambien: ['#/documento']},
    {id: 'busqueda', rotulo: 'Búsqueda', items: [
      {hash: '#/buscar',    rotulo: 'Buscar'},
      {hash: '#/guardadas', rotulo: 'Consultas guardadas'},
      // Se muda desde «Hallazgos»: es una herramienta de búsqueda, no un hallazgo.
      {hash: '#/consultas', rotulo: 'Consultas'},
    ]},
    {id: 'colecciones', rotulo: 'Colecciones', hash: '#/colecciones', tambien: ['#/coleccion']},
  ]},
  /* El cambio de fondo de esta ronda. Todo lo que le pide una DECISIÓN a una persona
     vive en un solo lugar, y el grupo lleva la suma de lo que quedó pendiente. Antes
     había que saber que la foliatura se corrige desde «Documentos» y las identidades
     desde «Revisión», que son la misma tarea con dos domicilios. */
  {grupo: 'Revisión', entradas: [
    {id: 'revision', rotulo: 'Cola de revisión', hash: '#/cola', cuenta: 'a_revisar'},
    {id: 'identidad', rotulo: 'Identidades', hash: '#/identidad', cuenta: 'fusiones'},
    {id: 'relaciones', rotulo: 'Relaciones', hash: '#/relaciones'},
    {id: 'foliatura', rotulo: 'Foliatura del papel', hash: '#/foliatura'},
    {id: 'tablas', rotulo: 'Tablas', hash: '#/tablas'},
    {id: 'pendientes', rotulo: 'Otros pendientes', items: [
      {hash: '#/sin-reconocer',  rotulo: 'Todavía sin reconocer'},
      {hash: '#/afuera',         rotulo: 'Quedaron afuera', cuenta: 'afuera'},
      {hash: '#/reasociaciones', rotulo: 'Revisiones desplazadas'},
      {hash: '#/equipo',         rotulo: 'Trabajo del equipo'},
    ]},
  ]},
  /* «Exportaciones» no tiene pantalla propia: hoy vive como acciones dentro de
     Informes y de las listas. No se crea una entrada vacía para que el menú parezca
     completo; entra el día que haya algo detrás. */
  {grupo: 'Salida', entradas: [
    {id: 'informes', rotulo: 'Informes', hash: '#/informes'},
  ]},
  {grupo: 'Administración', entradas: [
    {id: 'ingesta', rotulo: 'Cargar escaneos', hash: '#/ingesta'},
    {id: 'legajos', rotulo: 'Legajos', hash: '#/legajos'},
    {id: 'actualizacion', rotulo: 'Actualizar análisis', hash: '#/actualizacion'},
    {id: 'papelera', rotulo: 'Papelera de archivos', hash: '#/papelera'},
    {id: 'sistema', rotulo: 'Estado del sistema', items: [
      {hash: '#/salud',         rotulo: 'Estado del sistema'},
      {hash: '#/como-funciona', rotulo: 'Cómo funciona'},
    ]},
  ]},
];

/* La lista plana de siempre, derivada de los grupos. Todo lo que ya consultaba
   `SECCIONES` —`seccionDe`, el apagado sin legajo, las pruebas— sigue andando sin
   enterarse de que ahora hay grupos. */
const SECCIONES = GRUPOS.flatMap(g => g.entradas);

/* Las últimas cuentas que devolvió el panel, para pintar los números de la barra. */
let cuentas = {};

const seccionDe = hash => {
  // Sin la query: `#/papelera?desde=100` es la papelera, página 2, y tiene que
  // marcar su sección igual que la página 1.
  const base = '#/' + String(hash || '').split('?')[0].split('/')[1];
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
  /* El resto del juego. Faltaban y todas esas entradas caían en el engranaje de
     «Sistema», que no es neutro: dibuja una tuerca al lado de «Relaciones» y de
     «Proveedores» y las hace parecer configuración. Con veintidós entradas, dieciséis
     tuercas iguales no distinguen nada y encima mienten. Mismo trazo simple y sin
     relleno que las que ya estaban. */
  contrataciones: '<path d="M4.5 3.5h11v13h-11zM7 7h6M7 10h6M7 13h3.5" fill="none"/>',
  precios:        '<path d="M10 3v14M13 6.2c0-1.5-1.3-2.2-3-2.2s-3 .7-3 2.2 1.2 2 3 2.6 3 1.1 3 2.6-1.3 2.4-3 2.4-3-.9-3-2.4" fill="none"/>',
  proveedores:    '<circle cx="7.2" cy="7" r="2.6" fill="none"/><path d="M2.6 16.4a4.6 4.6 0 0 1 9.2 0M13 5.2a2.6 2.6 0 0 1 0 5.2M14.4 16.4a4.6 4.6 0 0 0-1.6-3.5" fill="none"/>',
  comparaciones:  '<path d="M4 15.5V8M8 15.5V4.5M12 15.5v-5M16 15.5V6.5" fill="none"/>',
  cronologia:     '<circle cx="10" cy="10" r="7" fill="none"/><path d="M10 5.6V10l3 1.8" fill="none"/>',
  busqueda:       '<circle cx="8.6" cy="8.6" r="5.1" fill="none"/><path d="M12.4 12.4 17 17" fill="none"/>',
  colecciones:    '<path d="M2.6 6.4 10 3l7.4 3.4-7.4 3.4zM2.6 10.4 10 13.8l7.4-3.4M2.6 14 10 17.4 17.4 14" fill="none"/>',
  informes:       '<path d="M4.5 2.5h8L15.5 6v11.5h-11zM12 2.6V6h3.4M7.5 13.5v-2M10 13.5v-4M12.5 13.5v-6" fill="none"/>',
  identidad:      '<circle cx="6.6" cy="7.4" r="2.5" fill="none"/><circle cx="13.4" cy="7.4" r="2.5" fill="none"/><path d="M2.6 16a4 4 0 0 1 8 0M9.4 16a4 4 0 0 1 8 0" fill="none"/>',
  relaciones:     '<circle cx="5" cy="5.4" r="2.2" fill="none"/><circle cx="15" cy="5.4" r="2.2" fill="none"/><circle cx="10" cy="14.6" r="2.2" fill="none"/><path d="M6.7 6.9 8.9 12.7M13.3 6.9 11.1 12.7M7.2 5.4h5.6" fill="none"/>',
  foliatura:      '<path d="M5.5 2.8h9v14.4h-9zM8 5.6h4M8 8.6h4M11.5 14.6h2" fill="none"/>',
  tablas:         '<path d="M2.8 4.4h14.4v11.2H2.8zM2.8 8.2h14.4M2.8 11.8h14.4M8 4.4v11.2M13 4.4v11.2" fill="none"/>',
  pendientes:     '<circle cx="10" cy="10" r="7" fill="none"/><path d="M10 6v4.6M10 13.4v.1" fill="none"/>',
  legajos:        '<path d="M2.6 5.2h5.2l1.4 1.8h8.2v9.4H2.6zM2.6 5.2V4h5.2" fill="none"/>',
  actualizacion:  '<path d="M16.4 10a6.4 6.4 0 1 1-2-4.6M16.6 3.2v3.4h-3.4" fill="none"/>',
  papelera:       '<path d="M3.8 5.6h12.4M8 5.6V3.6h4v2M5.4 5.6l.8 11.2h7.6l.8-11.2M8.4 8.6v5.4M11.6 8.6v5.4" fill="none"/>',
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

  // Sin legajo abierto, las secciones que necesitan una base detrás se marcan como
  // lo que son: todavía no disponibles. No se esconden —esconder la mitad de la barra
  // deja a la persona sin saber qué hace el sistema—, se apagan y dicen por qué.
  const apagada = s => sinLegajo() &&
    !SIN_LEGAJO_IGUAL_ANDAN.has(s.hash || (s.items && s.items[0] && s.items[0].hash));

  const pintarSeccion = s => {
    const abierta = s === activa;
    const gris = apagada(s) ? ' apagado' : '';
    const porque = apagada(s) ? ' title="Necesita un legajo abierto"' : '';
    // La sección lleva la suma de lo que hay pendiente adentro. Cerrada, es la única
    // manera de enterarse de que adentro quedó trabajo sin hacer.
    const n = (s.items || []).reduce((t, i) => t + (i.cuenta ? num(i.cuenta) : 0), 0);
    const destino = s.hash || s.items[0].hash;
    const cabeza = `<a href="${destino}" class="cabeza ${abierta ? 'activo' : ''}${gris}"
        ${abierta ? 'aria-current="true"' : ''}${porque}>${iconoSeccion(s.id)}
        <span class="txt">${esc(s.rotulo)}</span>${chip(n, 'cosa')}</a>`;
    if (!abierta || !(s.items || []).length) return `<div class="grupo">${cabeza}</div>`;
    const items = s.items.map(i =>
      `<a href="${i.hash}" class="${hash.startsWith(i.hash) ? 'activo' : ''}"
         ${hash.startsWith(i.hash) ? 'aria-current="page"' : ''}
         ><span class="txt">${esc(i.rotulo)}</span>${chip(i.cuenta ? num(i.cuenta) : 0, 'cosa')}</a>`
    ).join('');
    return `<div class="grupo">${cabeza}<div class="items">${items}</div></div>`;
  };

  /* El rótulo del grupo es un encabezado, no un enlace: nombra a qué vino la persona
     y no lleva a ningún lado. Va como `<h2>` para que un lector de pantalla pueda
     saltar de grupo en grupo, que es justo la navegación que el agrupamiento promete. */
  $('#nav-secciones').innerHTML = GRUPOS.map(g =>
    `<div class="nav-grupo">
       <h2 class="nav-grupo-rotulo">${esc(g.grupo)}</h2>
       ${g.entradas.map(pintarSeccion).join('')}
     </div>`).join('');

  /* Con veintidós entradas y cinco grupos, en una pantalla de 768 px de alto la mitad
     de la barra queda abajo del pliegue. Que se desplace está bien; lo que no está
     bien es entrar a una pantalla del final de la lista y no ver marcada ninguna,
     porque la marca quedó fuera de cuadro. Al pintar, la activa se trae a la vista.

     `block:'nearest'` y no `'center'`: si ya se ve, no se mueve nada. Centrar una
     entrada que estaba perfectamente visible hace saltar la barra en cada clic, y eso
     se siente como un error del sistema. */
  const marcada = $('#nav-secciones .cabeza.activo');
  if (marcada) marcada.scrollIntoView({block: 'nearest'});
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
    const foco = destino.querySelector('tr.clic:focus');
    const idxFoco = foco ? foco.dataset.i : null;
    const v = visibles();
    const tanda = v.slice(0, estado.mostradas);
    /* El encabezado de una tabla grande no es un rótulo: es el control con el que se
       ordena. `aria-sort` es lo que se lo dice a un lector de pantalla —la flechita
       dibujada no la lee nadie— y es lo único que ahí distingue la columna que manda
       el orden de las otras siete. */
    const th = cols.map((c, i) => {
      const act = estado.orden === i ? (estado.desc ? ' desc' : ' asc') : '';
      const aria = estado.orden === i
        ? ` aria-sort="${estado.desc ? 'descending' : 'ascending'}"` : '';
      return `<th class="ord${act} ${claseCol(cols, c, i, filas)}" data-col="${i}"${aria}
                title="ordenar por ${esc(c.t)}">${esc(c.t)}</th>`;
    }).join('');
    const tr = tanda.map((f, i) => `<tr class="${opts.alClic ? 'clic' : ''}"
        data-i="${filas.indexOf(f)}"${opts.alClic ? ' tabindex="0"' : ''}>${
      cols.map((c, i) => `<td class="${claseCol(cols, c, i, filas)}" data-rotulo="${esc(c.t)}">${
        c.r ? c.r(f) : esc(f[c.k] ?? '')}</td>`).join('')
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
      ${v.length ? `<div class="tabla-env" data-ordenable="si"${
          estado.orden != null ? ' data-ordenado="si"' : ''}><table${opts.lista ? ` data-lista="${esc(opts.lista)}"` : ''}
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
    // Cada tanda nueva puede traer un valor más largo que los de arriba y cambiar si
    // la tabla entra o no: se vuelve a medir en cada pintada.
    vigilarCortes(destino);
    if (idxFoco != null) {
      const nuevoFoco = destino.querySelector(`tr.clic[data-i="${idxFoco}"]`);
      if (nuevoFoco) nuevoFoco.focus();
    }
  }

  pintar();
}

/* ── Una tabla cuyas filas vienen del servidor, de a una página ────────────
   `tablaBuscable` filtra y ordena en el navegador sobre todo lo que le pasaron. Con
   las listas paginadas del servidor eso ya no sirve: la respuesta trae sólo la
   primera página, y una tabla que pagina en el cliente sobre esa página muestra
   cincuenta filas creyendo que son todas. Ésta pide al servidor cada página, cada
   búsqueda y cada orden, y dice siempre cuántas hay en total.

   Mismo marcado y mismas clases que `tablaBuscable`, para que se vean iguales.
     ruta     la lista, con sus filtros fijos ya puestos (`/api/entidades?clase=x`)
     clave    dónde vienen las filas en la respuesta (`entidades`)
     cols     como en `tabla`; `o` es el campo por el que el servidor ordena esa
              columna (sin `o`, la columna no se ordena)
     opts     limite, placeholder, alClic(fila), lista, vacio (texto sin filas),
              alCargar(respuesta) para pintar lo que venga además de las filas */
function tablaServidor(destino, ruta, clave, cols, opts = {}) {
  const limite = opts.limite || 50;
  const estado = {q: '', orden: opts.orden || null, sentido: opts.sentido || 'asc', desde: 0};
  let pedido = 0, filas = [], total = 0, esperaQ = null;

  const url = () => {
    const [base, qs] = ruta.split('?');
    const p = new URLSearchParams(qs || '');
    p.set('desde', String(estado.desde)); p.set('limite', String(limite));
    if (estado.q) p.set('q', estado.q);
    if (estado.orden) { p.set('orden', estado.orden); p.set('sentido', estado.sentido); }
    return base + '?' + p.toString();
  };

  async function cargar() {
    const este = ++pedido;
    const tabla = destino.querySelector('.tabla-env');
    if (tabla) tabla.classList.add('cargando-tabla');
    let r;
    try { r = await api(url()); }
    catch (e) {
      if (este !== pedido) return;
      destino.innerHTML = `<div class="aviso"><span>No se pudo traer la lista:
        ${esc(e.message || String(e))}</span></div>`;
      return;
    }
    if (este !== pedido) return;          // llegó tarde: ya se pidió otra cosa
    filas = (r && r[clave]) || [];
    total = r && r.total != null ? r.total : filas.length;
    if (opts.alCargar) opts.alCargar(r);
    pintar();
  }

  function pintar() {
    const buscarViejo = destino.querySelector('input[type=search]');
    const conFoco = buscarViejo && document.activeElement === buscarViejo;
    const pos = conFoco ? buscarViejo.selectionStart : null;
    const th = cols.map((c, i) => {
      const act = c.o && estado.orden === c.o ? (estado.sentido === 'desc' ? ' desc' : ' asc') : '';
      const aria = act ? ` aria-sort="${estado.sentido === 'desc' ? 'descending' : 'ascending'}"` : '';
      return `<th class="${c.o ? 'ord' : ''}${act} ${claseCol(cols, c, i, filas)}" data-col="${i}"${aria}
                ${c.o ? `title="ordenar por ${esc(c.t)}"` : ''}>${esc(c.t)}</th>`;
    }).join('');
    const tr = filas.map((f, i) => `<tr class="${opts.alClic ? 'clic' : ''}" data-i="${i}"${
        opts.alClic ? ' tabindex="0"' : ''}>${cols.map((c, j) =>
        `<td class="${claseCol(cols, c, j, filas)}" data-rotulo="${esc(c.t)}">${
          c.r ? c.r(f) : esc(f[c.k] ?? '')}</td>`).join('')}</tr>`).join('');
    const hasta = Math.min(estado.desde + filas.length, total);
    destino.innerHTML = `
      <div class="buscador-tabla">
        <label class="campo-buscar">
          <input type="search" placeholder="${esc(opts.placeholder || 'Buscar…')}"
                 value="${esc(estado.q)}" autocomplete="off">
        </label>
        <span class="cuantas">${total
          ? `${fmtNum.format(estado.desde + 1)}–${fmtNum.format(hasta)} de <b>${fmtNum.format(total)}</b>`
          : 'ninguna'}</span>
        <span class="paginacion">
          ${estado.desde > 0 ? '<button type="button" class="boton gris pag-ant">Anteriores</button>' : ''}
          ${hasta < total ? '<button type="button" class="boton gris pag-sig">Siguientes</button>' : ''}
        </span>
      </div>
      ${filas.length ? `<div class="tabla-env" data-ordenable="si"><table${
          opts.lista ? ` data-lista="${esc(opts.lista)}"` : ''}><thead><tr>${th}</tr></thead>
          <tbody>${tr}</tbody></table></div>`
        : `<div class="tabla-env"><div class="vacio">${estado.q
            ? `Ninguna fila dice «${esc(estado.q)}».`
            : esc(opts.vacio || 'No hay nada para mostrar.')}</div></div>`}`;

    const buscar = destino.querySelector('input[type=search]');
    if (conFoco) { buscar.focus(); buscar.setSelectionRange(pos, pos); }
    // Se espera a que la persona deje de escribir: una consulta por tecla es una
    // consulta por letra, y la respuesta de «pr» puede llegar después que la de «pro».
    buscar.oninput = () => {
      clearTimeout(esperaQ);
      esperaQ = setTimeout(() => { estado.q = buscar.value.trim(); estado.desde = 0; cargar(); }, 250);
    };
    destino.querySelectorAll('th.ord').forEach(th => th.onclick = () => {
      const c = cols[+th.dataset.col];
      estado.sentido = estado.orden === c.o && estado.sentido === 'asc' ? 'desc' : 'asc';
      estado.orden = c.o; estado.desde = 0; cargar();
    });
    const ant = destino.querySelector('.pag-ant'), sig = destino.querySelector('.pag-sig');
    if (ant) ant.onclick = () => { estado.desde = Math.max(0, estado.desde - limite); cargar(); };
    if (sig) sig.onclick = () => { estado.desde += limite; cargar(); };
    if (opts.alClic) destino.querySelectorAll('tbody tr').forEach(tr => {
      tr.onclick = e => { if (!e.target.closest('a, button, input, select, textarea')) opts.alClic(filas[+tr.dataset.i]); };
      tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opts.alClic(filas[+tr.dataset.i]); } };
    });
    vigilarCortes(destino);
  }

  destino.innerHTML = '<div class="cargando">Cargando…</div>';
  cargar();
  return {recargar: () => cargar()};
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

  // Una instalación recién puesta no tiene nada, y eso NO es un estado vacío que haya
  // que explicar con un cartel: es el principio normal del trabajo. Sin legajos, la
  // pantalla directamente es el alta —el formulario primero, sin tabla vacía delante—.
  const primeraVez = !activos.length && !archivados.length;
  const listado = activos.length
    ? `<div class="tabla-legajos">${tabla(cols, activos, {alClic: true})}</div>` : '';

  /* El estado de permanencia de los datos NO se muestra acá.

     Estuvo un rato: un cartel arriba de esta pantalla avisando que todavía no se podía
     confirmar que lo guardado sobreviviera a un reinicio. Es información importante y
     está mal puesta ahí. Esta es la pantalla por la que se pasa todos los días para
     empezar a trabajar, y un cartel de alarma en el camino de todos los días deja de
     leerse a la semana. Vive en Sistema → Estado del sistema, que es donde se va a
     buscar cómo está la instalación. */
  vista.innerHTML =
    bloque('f. 0000', 'Índice de legajos', `
      <h2>${primeraVez ? 'Empezá abriendo un legajo'
                        : '¿Sobre qué legajo vas a trabajar?'}</h2>
      <p class="prosa">Un legajo es una causa. Tiene su propia base de datos: sus
        documentos, sus personas y sus totales viven en un archivo aparte, y mientras
        trabajás en uno el sistema <strong>no puede ver ni sumar</strong> nada de los
        demás. No es un filtro que se pueda olvidar, están en archivos distintos.</p>
      ${!r.activo && activos.length ? `<p class="prosa">Al cerrar el navegador el sistema
        se olvida de cuál tenías abierto —en una máquina compartida una causa no puede
        quedar abierta hasta mañana—, pero <strong>no se pierde nada</strong>: acá está
        todo, con el trabajo que le hiciste a cada uno.</p>` : ''}
      ${listado}` +
      (archivados.length ? `
      <details class="archivados">
        <summary>${plural(archivados.length, 'legajo archivado', 'legajos archivados')}</summary>
        <div class="tabla-legajos">${tabla(cols, archivados, {alClic: true})}</div>
      </details>` : '')) +
    bloque('f. 0000', 'Alta', `
      <h2>${primeraVez ? 'Datos del legajo' : 'Abrir un legajo nuevo'}</h2>
      <form id="f-legajo" class="form-legajo">
        <label>Número de legajo
          <input name="numero" required placeholder="87.933" autocomplete="off"></label>
        <label>Fiscal responsable <span class="opt">(opcional)</span>
          <input name="fiscal" autocomplete="off"></label>
        <label class="ancho">Carátula
          <input name="caratula" required placeholder="Carátula del expediente"
                 autocomplete="off"></label>
        <button class="boton lleno" type="submit">Crear el legajo</button>
      </form>
      <p id="err-legajo" class="aviso" hidden></p>
      <p class="prosa nota">El número queda como nombre de la carpeta
        en disco, para que mirando los archivos se entienda qué hay adentro de cada una.
        ¿Tenés una copia de respaldo de un legajo?
        <a href="#" id="ir-restaurar">Volvé a cargarla acá</a>.</p>
`) +
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
  const irRest = $('#ir-restaurar');
  if (irRest) irRest.onclick = e => { e.preventDefault(); pedirRestaurar(activos); };

  $('#f-legajo').onsubmit = async ev => {
    ev.preventDefault();
    const btn = ev.target.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;
    const d = Object.fromEntries(new FormData(ev.target));
    const err = $('#err-legajo');
    try {
      const nuevo = await api('/api/legajos', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...d, quien: await conRevisor()})});
      abrirLegajo(nuevo.slug);
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    } finally {
      const btn = ev.target.querySelector('button[type="submit"]');
      if (btn) btn.disabled = false;
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

/* ── Volver atrás desde una copia de respaldo ──────────────────────────────
   El respaldo era una calle de una sola mano: se bajaba el archivo y no había forma de
   devolverlo. Sirve para la auditoría y no sirve para lo que de verdad hace falta el
   día que el disco aparece vacío.

   Restaurar PISA la base de un legajo, así que se trata como lo que es: primero se
   mira qué trae el archivo —cuántas revisiones a mano, sobre todo, que es lo único que
   no se puede volver a generar—, y recién con eso a la vista se pide el número del
   legajo para confirmar. */
function pedirRestaurar(activos) {
  if (!activos.length) {
    return toast('Primero creá el legajo donde querés cargar la copia. Después volvé acá.');
  }
  const d = dialogo(`
    <form method="dialog" id="f-restaurar">
      <h3>Volver a cargar una copia de respaldo</h3>
      <p class="prosa">La copia reemplaza la base del legajo que elijas. Lo que había
        <strong>no se borra</strong>: se aparta con fecha, por si la copia no era la que
        pensabas.</p>
      <label for="r-legajo">¿Sobre qué legajo?</label>
      <select id="r-legajo">${activos.map(l =>
        `<option value="${esc(l.slug)}" data-numero="${esc(l.numero)}"
          >${esc(l.numero)} — ${esc(l.caratula)}</option>`).join('')}</select>
      <label for="r-archivo" class="sep-corta">El archivo de la copia
        <span class="opt">(.sqlite)</span></label>
      <input id="r-archivo" type="file" accept=".sqlite">
      <div id="r-contenido"></div>
      <div id="r-confirmar" hidden>
        <label for="conf-restaurar">Escribí el número del legajo para confirmar:
          <b class="mono" id="r-numero"></b></label>
        <input id="conf-restaurar" autocomplete="off" autocapitalize="off"
               spellcheck="false">
      </div>
      <p class="mal" id="err-restaurar" hidden></p>
      <div class="botonera">
        <button class="boton gris" value="no" type="submit">Cancelar</button>
        <button class="boton peligro" id="b-restaurar" type="button" disabled>
          Reemplazar la base</button>
      </div>
    </form>`);

  const archivo = $('#r-archivo', d), ok = $('#b-restaurar', d);
  const err = $('#err-restaurar', d), donde = $('#r-contenido', d);
  const sel = $('#r-legajo', d), caja = $('#r-confirmar', d);
  const campo = $('#conf-restaurar', d);
  let crudo = null;

  // El número que hay que escribir es el del legajo ELEGIDO, así que cambiar de legajo
  // invalida lo escrito: si no, se lee un cartel, se escribe un número, se cambia el
  // destino de la lista y se termina pisando otra base con la confirmación de la
  // anterior todavía puesta.
  const numeroElegido = () => sel.selectedOptions[0].dataset.numero.trim();
  const revisar = () => {
    ok.disabled = !crudo || campo.value.trim() !== numeroElegido();
  };
  campo.oninput = revisar;
  sel.onchange = () => {
    $('#r-numero', d).textContent = numeroElegido();
    campo.value = '';
    revisar();
  };

  const fallar = m => { err.textContent = m; err.hidden = false;
                        donde.innerHTML = ''; caja.hidden = true;
                        ok.disabled = true; crudo = null; };

  archivo.onchange = async () => {
    err.hidden = true; donde.innerHTML = ''; caja.hidden = true;
    ok.disabled = true; crudo = null; campo.value = '';
    const f = archivo.files[0];
    if (!f) return;
    donde.innerHTML = '<p class="prosa">Mirando qué trae…</p>';
    try {
      const buf = await f.arrayBuffer();
      const r = await api('/api/respaldo/mirar', {
        method: 'POST', headers: {'Content-Type': 'application/octet-stream'},
        body: buf});
      // Lo que hay que ver ANTES de pisar nada: cuánto trabajo de personas trae.
      donde.innerHTML = `<div class="aviso bien">${sello('ok', 'La copia se puede leer')}
        <span><strong>${plural(r.documentos, 'documento', 'documentos')}</strong> ·
          <strong>${plural(r.revisiones, 'campo revisado a mano',
                           'campos revisados a mano')}</strong>${r.ultima_revision
            ? ` · la última, del ${esc(fmtFecha(r.ultima_revision))}` : ''}.</span></div>`;
      crudo = buf;
      $('#r-numero', d).textContent = numeroElegido();
      caja.hidden = false;
      campo.focus();
      revisar();
    } catch (e) { fallar(e.message); }
  };

  ok.onclick = async () => {
    const numero = numeroElegido();
    ok.disabled = true; ok.textContent = 'cargando…';
    try {
      const r = await api(`/api/respaldo/restaurar?slug=${encodeURIComponent(sel.value)}`
        + `&confirmacion=${encodeURIComponent(campo.value.trim())}`, {
        method: 'POST', headers: {'Content-Type': 'application/octet-stream'},
        body: crudo});
      d.close();
      // Decir dónde quedó lo que se apartó: si la copia no era la que la persona
      // pensaba, este nombre es el camino de vuelta, y no está en ninguna otra parte.
      toast(`Listo. El legajo ${numero} quedó con ${plural(r.documentos, 'documento',
        'documentos')} y ${plural(r.revisiones, 'campo revisado a mano',
        'campos revisados a mano')}.`
        + (r.apartada ? `\n\nLa base que estaba quedó guardada como:\n`
                        + r.apartada.split('/').pop() : ''));
      abrirLegajo(sel.value);
    } catch (e) {
      fallar(e.message);
      ok.textContent = 'Reemplazar la base';
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
    } catch (e) { toast('No se pudo restaurar: ' + e.message); b.disabled = false; }
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

/* ── Preguntar quién está trabajando, una vez ──────────────────────────────
   El botón de la barra está bien puesto y es lo correcto que esté siempre a la vista,
   pero mientras nadie lo toque TODO lo que se revise queda sin firma, y eso no se
   arregla después: la decisión ya quedó anotada sin autor.

   Se pregunta una sola vez por sesión, al abrir un legajo, y con la lista de quienes
   ya revisaron algo en esta base para no obligar a nadie a escribirse de nuevo. Se
   puede saltear —el sistema tiene que dejar trabajar— pero se pregunta. */
async function preguntarQuienUnaVez(p) {
  if (REVISOR) return;
  try {
    if (sessionStorage.getItem('ufil.ya-pregunte')) return;
    sessionStorage.setItem('ufil.ya-pregunte', '1');
  } catch (e) { return; }        // sin sessionStorage, mejor no insistir nunca
  await pedirRevisor(p.quienes || []);
}

async function vPanel() {
  const p = await api('/api/panel');

  if (!p.documentos) {
    vista.innerHTML = bloque('f. 0001', 'Inicio', `
      <h1>Todavía no hay nada cargado</h1>
      <p class="prosa">AppUFIL lee la documentación de una contratación —pliegos, ofertas,
        órdenes de compra, facturas, remitos, pagos—, reconstruye el procedimiento, compara
        los precios y marca las diferencias con la foja de donde sale cada dato.
        <strong>No modifica los originales y funciona sin conexión.</strong></p>
      ${vacio('Empezá cargando los escaneos del legajo',
        'Arrastrá los PDF a la pantalla de carga. El sistema lee, reconoce los documentos ' +
        'y arma las contrataciones solo; lo que no puede leer con seguridad lo deja marcado ' +
        'para que lo revise una persona.',
        {href:'#/ingesta', texto:'Cargar escaneos'})}
      <p class="prosa nota sep-corta">
        ¿Primera vez? <a href="#/como-funciona">Cómo funciona</a> lo explica en una pantalla.</p>`);
    return;
  }

  /* Lo que el resumen necesita y el panel viejo no trae —contrataciones, hallazgos—
     sale de /api/resumen cuando el servidor lo tiene. Si no, de las listas, que ya
     existen. Ninguna de las dos consultas puede tirar abajo la pantalla: si falla,
     esa parte no se muestra y lo demás sí. */
  const quieto = pr => pr.then(x => x, () => null);
  const [res, lc, lh, lp] = await Promise.all([
    quieto(api('/api/resumen')),
    quieto(api('/api/contrataciones?desde=0&limite=200')),
    quieto(api('/api/hallazgos?desde=0&limite=200')),
    quieto(api('/api/entidades/propuestas?limite=1')),
  ]);
  const propuestas = lp && lp.total ? lp.total : 0;
  const ejemploPropuesta = lp && lp.propuestas && lp.propuestas[0]
    ? (lp.propuestas[0].literales || []).join(' / ') : '';
  if (location.hash && !/^#\/(panel)?$/.test(location.hash.split('?')[0])) return;

  const n = x => fmtNum.format(x || 0);
  const contrataciones = (lc && lc.contrataciones) || [];
  const totalContrataciones = res && res.contrataciones != null ? res.contrataciones
    : lc && lc.total != null ? lc.total : contrataciones.length;
  const hallazgos = ((lh && lh.hallazgos) || []).filter(h => !h.ya_no_se_detecta);
  const hzPendientes = hallazgos.filter(h => ((h.revision || {}).estado || 'pendiente') === 'pendiente');
  const nHzPend = res && res.prioridades
    ? ((res.prioridades.find(x => x.clave === 'hallazgos') || {}).cantidad ?? hzPendientes.length)
    : hzPendientes.length;
  const sinReconocer = res && res.incompleto ? res.incompleto.piezas_sin_reconocer : null;

  /* ── Qué hacer ahora ──────────────────────────────────────────────────────
     Quien entra a las nueve de la mañana necesita saber, en un renglón por cosa, si
     hay trabajo suyo esperando y dónde. Una lista corta, en el orden en que conviene
     hacerla, y sólo con lo que tiene algo: un «0 identidades por confirmar» es ruido. */
  const tareas = [
    nHzPend && {n: nHzPend, que: nHzPend === 1 ? 'hallazgo sin revisar' : 'hallazgos sin revisar',
      por: 'Diferencias de precio, facturas que no coinciden, documentos que faltan. Cada uno con su cuenta y su foja.',
      href: '#/hallazgos?estado=pendiente', accion: 'Revisar hallazgos'},
    p.a_revisar && {n: p.a_revisar, que: p.a_revisar === 1 ? 'dato leído con duda' : 'datos leídos con duda',
      por: `Lecturas que el sistema no pudo sostener solo${p.conflictos
        ? `; ${n(p.conflictos)} con dos lecturas que no coinciden` : ''}. No entran en ningún total hasta que alguien los confirme.`,
      href: '#/cola', accion: 'Ir a la cola'},
    p.fusiones && {n: p.fusiones, que: p.fusiones === 1 ? 'identidad por confirmar' : 'identidades por confirmar',
      por: 'Nombres escritos de maneras distintas que podrían ser la misma persona o empresa.',
      href: '#/identidad', accion: 'Confirmar'},
    propuestas && {n: propuestas, que: propuestas === 1 ? 'nombre por confirmar' : 'nombres por confirmar',
      por: `Formas distintas de escribir a la misma empresa o persona${ejemploPropuesta
        ? ` (por ejemplo, «${ejemploPropuesta}»)` : ''}. Hasta que alguien las confirme, un
        proveedor puede figurar sólo por su CUIT.`,
      href: '#/entidades?ver=propuestas', accion: 'Decidir'},
    sinReconocer && {n: sinReconocer, que: sinReconocer === 1 ? 'documento sin reconocer' : 'documentos sin reconocer',
      por: 'El sistema no supo qué tipo de documento es: hasta que se diga, no entra en ninguna contratación.',
      href: '#/sin-reconocer', accion: 'Clasificar'},
    p.afuera && {n: p.afuera, que: p.afuera === 1 ? 'archivo no produjo documentos' : 'archivos no produjeron documentos',
      por: 'No entran en ninguno de estos números.', href: '#/afuera', accion: 'Ver por qué'},
  ].filter(Boolean);

  const tareasHTML = tareas.length ? `
    <ol class="tareas">
      ${tareas.map(t => `<li class="tarea">
        <span class="tarea-n">${n(t.n)}</span>
        <span class="tarea-que"><b>${esc(t.que)}</b><span>${esc(t.por)}</span></span>
        <a class="boton" href="${t.href}">${esc(t.accion)}</a>
      </li>`).join('')}
    </ol>` : `
    <div class="siguiente-paso">
      <div><b>No queda nada esperando revisión</b>
        <span>Todo lo que el sistema no pudo sostener solo ya lo miró una persona.</span></div>
    </div>`;

  const cifra = (rotulo, valor, nota, href) => `
    <div class="cifra">
      <span class="cifra-rotulo">${esc(rotulo)}</span>
      <span class="cifra-valor">${href ? `<a href="${href}">${valor}</a>` : valor}</span>
      ${nota ? `<span class="cifra-nota">${nota}</span>` : ''}
    </div>`;
  const conPrecios = contrataciones.filter(c => c.hallazgos || (c.etapas && Object.values(c.etapas).some(Boolean)));

  /* ── Contrataciones para empezar ─────────────────────────────────────────
     Las que más material tienen: las que tienen hallazgos primero, y entre ellas
     las que más. Es por dónde se empieza a leer un legajo de cien contrataciones. */
  const etapasDe = c => c.etapas && !Array.isArray(c.etapas)
    ? Object.values(c.etapas).filter(Boolean).length : 0;
  const hzPorContratacion = {};
  hallazgos.forEach(h => { if (h.contratacion_id) hzPorContratacion[h.contratacion_id] = (hzPorContratacion[h.contratacion_id] || 0) + 1; });
  contrataciones.forEach(c => { if (c.hallazgos == null) c.hallazgos = hzPorContratacion[c.id] || 0; });
  const primeras = [...contrataciones]
    .sort((a, b) => (b.hallazgos || 0) - (a.hallazgos || 0) || etapasDe(b) - etapasDe(a))
    .slice(0, 6);
  const contratacionesHTML = primeras.length ? tabla([
    {t: 'Contratación', c: 'crece', r: c => `<a href="#/contratacion?id=${c.id}">${esc(nombreContratacion(c))}</a>
        ${c.objeto ? `<span class="item-normalizado">${esc(c.objeto)}</span>` : ''}`},
    {t: 'Expediente', c: 'fol', r: c => c.expediente ? esc(c.expediente) : ausente('no_consta')},
    {t: 'Hallazgos', c: 'num', r: c => c.hallazgos
        ? `<a class="chip-hallazgos" href="#/hallazgos?contratacion_id=${c.id}">${n(c.hallazgos)}</a>` : ''},
  ], primeras) : '';

  /* ── Hallazgos para mirar primero ────────────────────────────────────────
     Los que tienen una cuenta detrás van antes que los que dicen que algo falta, y
     éstos antes que los renglones ilegibles, que son muchos y dicen más del OCR que de
     la contratación. Si todos son del mismo tipo, se dice cuántos y se lleva a la lista. */
  const PESO = {diferencia_precio: 0, facturado_vs_adjudicado: 1, facturado_vs_entregado: 2,
    subtotal_incorrecto: 3, total_inconsistente: 4, ofertas_identicas: 5, duplicado_potencial: 6,
    variacion_compras: 7, secuencia_temporal: 8, oferente_unico: 9, documento_faltante: 10,
    coincidencia_temporal: 11, precio_sin_rol: 12, precio_ausente: 13};
  const porTipo = new Map();
  hzPendientes.forEach(h => porTipo.set(h.tipo, [...(porTipo.get(h.tipo) || []), h]));
  const tiposOrden = [...porTipo.entries()].sort((a, b) => (PESO[a[0]] ?? 20) - (PESO[b[0]] ?? 20));
  const hallazgosHTML = tiposOrden.length ? `<ul class="lista-motivos">
      ${tiposOrden.map(([tipo, hs]) => `<li>
        <span class="motivo-cuenta">${n(hs.length)}</span>
        <span class="motivo-texto"><a href="#/hallazgos?tipo=${encodeURIComponent(tipo)}&estado=pendiente"
          >${esc(hs[0].titulo || tipo)}</a></span>
        <span class="motivo-ejemplos">${esc(hs[0].descripcion || '')}</span>
      </li>`).join('')}</ul>` : '';

  /* ── La plata que dicen los papeles, por etapa ───────────────────────────
     Suma de los subtotales de los renglones leídos, por etapa y moneda: no el total
     que imprime cada documento. Las etapas no se suman entre sí —la orden de compra y
     su factura son la misma plata vista dos veces— y lo provisional va aparte de lo
     firme. Cada fila dice cuántos renglones tienen importe y cuántos no, porque una
     suma a la que le faltan sumandos no es un total. */
  const ETAPA_PLURAL = {presupuesto: 'Presupuestos', oferta: 'Ofertas', adjudicacion: 'Adjudicaciones',
    orden_compra: 'Órdenes de compra', factura: 'Facturas', remito: 'Remitos',
    orden_pago: 'Órdenes de pago', pago: 'Pagos', otro: 'Otros documentos'};
  const ORDEN_ETAPA = ['presupuesto', 'oferta', 'adjudicacion', 'orden_compra', 'remito',
                       'factura', 'orden_pago', 'pago', 'otro'];
  // Una etapa puede venir partida en dos grupos: los renglones con moneda leída y los
  // que no. Se juntan en una fila —la suma es la de los que tienen importe; el resto
  // cuenta como renglones sin importe— para no mostrar «Remitos» dos veces.
  const juntos = new Map();
  ((res && res.dinero) || []).filter(g => g.renglones).forEach(g => {
    const k = g.etapa + '|' + g.estado + '|' + (g.moneda || '');
    const sinMoneda = g.etapa + '|' + g.estado + '|';
    if (!g.moneda) {
      const x = juntos.get(sinMoneda) || {...g, valor: null, con_valor: 0, renglones: 0};
      x.renglones += g.renglones; juntos.set(sinMoneda, x); return;
    }
    juntos.set(k, {...g});
  });
  for (const [k, g] of [...juntos]) {
    if (g.moneda) continue;
    const conMoneda = [...juntos.entries()].find(([k2, h]) => h.moneda && h.etapa === g.etapa && h.estado === g.estado);
    if (conMoneda) {
      conMoneda[1].renglones += g.renglones;
      if (!conMoneda[1].fecha_desde) { conMoneda[1].fecha_desde = g.fecha_desde; conMoneda[1].fecha_hasta = g.fecha_hasta; }
      juntos.delete(k);
    }
  }
  const dinero = [...juntos.values()]
    .sort((a, b) => ORDEN_ETAPA.indexOf(a.etapa) - ORDEN_ETAPA.indexOf(b.etapa)
                    || String(a.estado).localeCompare(String(b.estado)));
  const dineroHTML = dinero.length ? tabla([
    {t: 'Etapa', c: 'crece', r: g => esc(ETAPA_PLURAL[g.etapa] || String(g.etapa).replace(/_/g, ' '))},
    {t: 'Suma leída', c: 'num', r: g => g.valor != null
        ? `<span class="${g.estado === 'firme' ? '' : 'provisional'}">${esc(
            (g.moneda && g.moneda !== 'ARS' ? g.moneda + ' ' : '$ ') + fmtPlata.format(Number(g.valor)))}</span>`
        : ausente(g.ausencia || 'no_consta')},
    {t: 'Renglones con importe', c: 'num', r: g => `${n(g.con_valor)}<span class="celda-nota">de ${n(g.renglones)}</span>`},
    {t: 'Estado', r: g => g.estado === 'firme' ? sello('ok', 'Firme')
        : sello('neutro', 'Provisional', {titulo: 'Leído por el sistema y todavía sin revisar contra la foja.'})},
    {t: 'Fechas', c: 'fol', r: g => g.fecha_desde
        ? esc(fmtFecha(g.fecha_desde) + (g.fecha_hasta && g.fecha_hasta !== g.fecha_desde ? ' – ' + fmtFecha(g.fecha_hasta) : ''))
        : ausente('no_consta')},
  ], dinero) : '';

  /* ── Lo técnico, al final y en un solo lugar ─────────────────────────────
     Fojas leídas, datos firmes y en conflicto: dice cuánto se puede confiar en lo de
     arriba. Va abajo y apagado porque no es lo que se viene a hacer. */
  const estadoHTML = `
    <div class="cifras cifras-4">
      ${cifra('Documentos', n(p.documentos), `en ${n(p.archivos)} ${p.archivos === 1 ? 'archivo' : 'archivos'}`, '#/fojas')}
      ${cifra('Fojas leídas', `${n(p.paginas_leidas)}<i class="de"> / ${n(p.paginas)}</i>`,
              p.paginas_leidas < p.paginas ? `${n(p.paginas - p.paginas_leidas)} sin leer todavía` : 'todas',
              p.paginas_leidas < p.paginas ? '#/actualizacion' : '')}
      ${cifra('Verificados a mano', n(p.verificados),
              (p.quienes || []).length ? `por ${esc(p.quienes.join(', '))}` : 'nadie revisó todavía')}
      ${cifra('Personas y empresas', n(p.personas), 'identificadas por CUIT o documento', '#/entidades')}
    </div>
    ${p.paginas_enderezadas ? `<p class="nota-seccion sep-corta">${p.paginas_enderezadas === 1
      ? 'Una foja llegó girada' : n(p.paginas_enderezadas) + ' fojas llegaron giradas'} en el
      escaneo; se enderezó la copia de trabajo para poder leerla.</p>` : ''}
    <p class="nota-seccion">El detalle del procesamiento —lecturas, versiones, diagnóstico— está en
      <a href="#/salud">Estado del sistema</a>.</p>`;

  vista.innerHTML =
    bloque('f. 0001', 'Resumen', `
      <header class="ficha-cabeza">
        <h1>Resumen del legajo</h1>
        ${p.lote || p.legajo ? `<p class="ficha-objeto">${esc(
          typeof p.legajo === 'object' && p.legajo ? (p.legajo.nombre || p.legajo.numero || '') : (p.lote || ''))}</p>` : ''}
      </header>
      <div class="cifras cifras-4">
        ${cifra('Contrataciones', n(totalContrataciones),
                conPrecios.length ? `${n(conPrecios.length)} con hallazgos o etapas` : 'reconstruidas de los documentos',
                '#/contrataciones')}
        ${cifra('Hallazgos', n(hallazgos.length),
                hallazgos.length ? `${n(nHzPend)} sin revisar` : 'ninguna diferencia detectada',
                '#/hallazgos')}
        ${cifra('Datos por revisar', n(p.a_revisar),
                p.conflictos ? `${n(p.conflictos)} en conflicto` : 'lecturas con duda', '#/cola')}
        ${cifra('Documentos', n(p.documentos), `${n(p.paginas)} fojas`, '#/fojas')}
      </div>
      <h2>Qué hacer ahora</h2>
      ${tareasHTML}`) +

    (contratacionesHTML || hallazgosHTML || dineroHTML ? bloque('f. 0002', 'Investigación', `
      <h2>Para investigar</h2>
      ${hallazgosHTML ? `<h3>Hallazgos sin revisar, por tipo</h3>
        <p class="nota-seccion">Ninguno es una conclusión: cada uno dice qué se detectó y de
          qué foja sale, para que una persona lo verifique.</p>
        ${hallazgosHTML}` : ''}
      ${dineroHTML ? `<h3>Lo que dicen los papeles, en plata</h3>
        <p class="nota-seccion">Suma de los subtotales de los renglones leídos, por etapa. No
          es el total que imprime cada documento, y las etapas no se suman entre sí: una orden
          de compra y su factura son la misma plata vista dos veces. Lo provisional todavía no
          lo revisó nadie contra la foja.</p>
        ${dineroHTML}` : ''}
      ${contratacionesHTML ? `<h3>Contrataciones para empezar</h3>
        <p class="nota-seccion">Las que tienen más hallazgos. Están las
          ${n(totalContrataciones)} en <a href="#/contrataciones">Contrataciones</a>.</p>
        ${contratacionesHTML}` : ''}`) : '') +

    bloque('f. 0003', 'Legajo', `
      <h2>Estado del legajo</h2>
      ${estadoHTML}`) +

    bloque('f. 0004', 'Salida', `
      <h2>Llevárselo</h2>
      <p class="prosa">Cada afirmación del informe cita el archivo y la foja de donde salió
        el dato, para poder verificarla contra el original. Los informes por contratación,
        proveedor o hallazgo están en <a href="#/informes">Informes</a>.</p>
      <div class="fila-suelta">
        <a class="boton" data-descarga="xlsx" href="/descargar?que=xlsx">Descargar la planilla (.xlsx)</a>
        <a class="boton gris" data-descarga="rtf" href="/descargar?que=rtf">Descargar el informe (.rtf)</a>
        <a class="boton gris" href="/descargar?que=respaldo">Copia de respaldo</a>
      </div>
      <label class="opcion-suelta"><input type="checkbox" id="con-membrete" checked>
        <span>Encabezar con el <strong>${IDENTIDAD ? IDENTIDAD.organismo : 'Ministerio Público Fiscal'}</strong>
        y la unidad. Para un borrador interno se puede sacar.</span></label>
      <p class="prosa nota sep-corta">La copia de respaldo guarda el trabajo de las personas
        —cada dato revisado contra la foja, cada identidad confirmada, con quién y cuándo—,
        que es lo único que no se regenera procesando de nuevo. Conviene bajarla al terminar
        cada jornada y dejarla en otro disco.</p>`);

  const conMembrete = vista.querySelector('#con-membrete');
  if (conMembrete) {
    const pintarMembrete = () => vista.querySelectorAll('a[data-descarga]').forEach(a =>
      a.href = '/descargar?que=' + a.dataset.descarga +
               (conMembrete.checked ? '' : '&membrete=no'));
    conMembrete.onchange = pintarMembrete;
    pintarMembrete();
  }

  // Al final y no al principio: primero se pinta la pantalla y después se pregunta.
  // Al revés, quien entra ve un diálogo sobre un fondo vacío y no sabe ni dónde está.
  preguntarQuienUnaVez(p);
}

async function vContratos() {
  const filas = await api('/api/contratos');
  if (!filas.length) return vistaVacia('f. 0004', 'Datos', 'Contratos',
    'Todavía no hay contratos leídos',
    'Cargá un lote de escaneos y procesalo. Los contratos aparecen acá apenas termina.');
  vista.innerHTML = bloque('f. 0004', 'Datos', `
    <h2>Contratos</h2>
    <p class="prosa">La tabla consolidada. Un campo entra sólo si tiene valor y no tiene conflicto abierto: lo que no se pudo leer aparece vacío, nunca completado.</p>
    <div id="tabla-contratos"></div>`);
  tablaBuscable($('#tabla-contratos'), [
      {t:'Doc', k:'documento_id', c:'fol'},
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', b:f => camaraTexto(f.camara), r:f => f.camara ? esc(camaraTexto(f.camara)) : '<span class="nulo" title="sin cámara">—</span>'},
      {t:'Contratado/a', c:'nombre', b:f => f.nombre_literal,
       r:f => f.nombre_literal ? esc(f.nombre_literal) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Documento', c:'mono', b:f => f.documento_literal,
       r:f => f.documento_literal ? esc(f.documento_literal) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Inicio', c:'mono', b:f => f.inicio,
       r:f => f.inicio ? esc(fmtFecha(f.inicio)) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Fin', c:'mono', b:f => f.fin,
       r:f => f.fin ? esc(fmtFecha(f.fin)) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Monto', c:'num', b:f => f.monto_centavos,
       r:f => f.monto_centavos == null ? '<span class="nulo" title="sin dato">—</span>' : esc(fmtPesos(f.monto_centavos))},
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
    'Acá van las facturas, recibos y remitos que vengan en los escaneos. Se separan de los contratos porque dicen otra cosa: lo que se cobró, no lo que se pactó.');

  const aMano = filas.filter(f => f.monto_centavos == null).length;
  vista.innerHTML = bloque('f. 0004', 'Datos', `
    <h2>Facturas y recibos</h2>
    <p class="prosa">Lo que se cobró. <strong>No se suma con los contratos</strong>: son la misma plata vista de los dos lados, y cuando la factura es el cobro de ese contrato, sumarlas la cuenta dos veces. El cruce está en <a href="#/cruce">Lo facturado contra lo contratado</a>.</p>
    ${aMano ? `<div class="aviso info">
      <span class="sello atencion">A mano</span>
      <span>${plural(aMano, 'comprobante tiene', 'comprobantes tienen')} el importe escrito a mano. <strong>No se lee con OCR</strong> —leerlo mal y no saberlo es peor que no leerlo— así que aparece vacío y espera que una persona lo cargue mirando la foja. Están en <a href="#/cola">la cola de revisión</a>.</span>
    </div>` : ''}
    <div id="tabla-comprobantes"></div>`);
  tablaBuscable($('#tabla-comprobantes'), [
      {t:'Doc', k:'documento_id', c:'fol'},
      {t:'Tipo', b:f => TIPO_DOC[f.tipo] || f.tipo, r:f => esc(TIPO_DOC[f.tipo] || f.tipo)},
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Emisor', b:f => f.nombre_literal,
       r:f => f.nombre_literal ? esc(f.nombre_literal) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'CUIT', c:'mono', b:f => f.documento_literal,
       r:f => f.documento_literal ? esc(f.documento_literal) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Comprobante', c:'mono', b:f => f.comprobante,
       r:f => f.comprobante ? esc(f.comprobante) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Emitida', c:'mono', b:f => f.emitida,
       r:f => f.emitida ? esc(fmtFecha(f.emitida)) : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Importe', c:'num', b:f => f.monto_centavos,
       r:f => f.monto_centavos == null ? '<span class="nulo" title="a mano">—</span>' : esc(fmtPesos(f.monto_centavos))},
      {t:'Conf.', c:'num', b:f => f.confianza_min, r:f => barraConf(f.confianza_min)},
    ], filas, {alClic: f => location.hash = '#/documento/' + f.documento_id,
               placeholder: 'Buscar por emisor, CUIT, número de comprobante…'});
}


/* ── Lo facturado contra lo contratado ─────────────────────────────────────
   El cruce que el caso necesita: cuánto se comprometió a pagar y cuánto se facturó
   contra eso. Une por CUIT ↔ DNI, no por nombre, que se escribe de mil maneras. */
async function vCruce() {
  const r = await api('/api/cruce');
  if (location.hash.split('?')[0] !== '#/cruce') return;
  /* El contrato viejo era de contratos de personal —una fila por persona, CUIL contra
     DNI—; el nuevo es de contrataciones: renglón facturado contra el precio contratado
     u ordenado del mismo ítem. Mientras el servidor sea el viejo, se muestra el viejo. */
  if (!r || !('faltantes' in r)) return vCrucePersonas(r);

  const filas = r.filas || [];
  const faltantes = (r.faltantes && r.faltantes.filas) || [];
  const totalFaltantes = r.faltantes_total ?? faltantes.length;
  if (!filas.length && !faltantes.length) {
    return vistaVacia('f. 0006', 'Cruce', 'Facturado contra contratado',
      'Todavía no hay facturas con renglones legibles',
      'El cruce pone cada renglón facturado al lado del precio que se contrató u ordenó ' +
      'para el mismo ítem, en la misma contratación. Aparece cuando hay facturas y ' +
      'órdenes de compra o adjudicaciones con planillas que el sistema pudo leer.');
  }

  const fuente = (f, texto) => f
    ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(f))}'
          class="enlace-fuente" title="${esc(f.archivo || '')}">${texto}</a>` : texto;
  const foja = f => f && (f.foja ?? f.pagina_nro) != null ? 'f. ' + fmtNum.format(f.foja ?? f.pagina_nro) : '';
  const plano = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const item = x => {
    const d = x.descripcion || {};
    return `<div class="item-desc">
      <span class="item-literal">${d.literal ? esc(d.literal) : ausente('ilegible')}</span>
      ${d.normalizada && plano(d.normalizada) !== plano(d.literal)
        ? `<span class="item-normalizado">${esc(d.normalizada)}</span>` : ''}</div>`;
  };
  const conFecha = (monto, fecha) => monto
    ? `${montoHTML(monto)}${fecha ? `<span class="celda-nota">${esc(fmtFecha(fecha) || fecha)}</span>` : ''}`
    : ausente(monto === null ? 'no_consta' : undefined);
  const CALIDAD = {fuerte: ['ok', 'Comparable'], probable: ['neutro', 'Probable'],
                   dudoso: ['atencion', 'Dudosa'], no_comparable: ['neutro', 'No comparable']};
  const calidad = c => {
    const [tono, txt] = CALIDAD[(c || {}).estado] || ['neutro', 'Sin calificar'];
    return sello(tono, txt, {titulo: ((c || {}).motivos || []).join(' ')});
  };
  const signo = n => Number(n) > 0 ? '+' : Number(n) < 0 ? '−' : '';
  const diferencia = x => x.diferencia_absoluta == null ? ausente('no_consta') : `
    <span class="dif">${signo(x.diferencia_absoluta)}$ ${esc(fmtPlata.format(Math.abs(Number(x.diferencia_absoluta))))}</span>
    ${x.diferencia_porcentual != null ? `<span class="celda-nota">${signo(x.diferencia_porcentual)}${
      esc(fmtNum.format(Math.abs(Number(x.diferencia_porcentual))))} %</span>` : ''}`;
  const contratacion = x => x.contratacion_id
    ? `<a class="celda-corta" href="#/contratacion?id=${x.contratacion_id}">${esc(
        x.contratacion_nombre || 'Contratación ' + x.contratacion_id)}</a>` : ausente('no_consta');
  const proveedor = x => x.proveedor
    ? esc(x.proveedor.nombre || x.proveedor.cuit || '') : ausente('no_consta');

  const cifra = (rotulo, valor, nota) => `<div class="cifra">
      <span class="cifra-rotulo">${esc(rotulo)}</span>
      <span class="cifra-valor">${valor}</span>
      ${nota ? `<span class="cifra-nota">${nota}</span>` : ''}</div>`;
  const motivos = [...new Set(faltantes.map(x => x.motivo || ''))];
  const motivoUnico = motivos.length === 1 && motivos[0] ? motivos[0].replace(/\.$/, '') : '';
  const conDif = filas.filter(x => x.diferencia_absoluta != null && Number(x.diferencia_absoluta) !== 0).length;

  vista.innerHTML = bloque('f. 0006', 'Cruce', `
    <h1>Facturado contra contratado</h1>
    <p class="prosa">Cada renglón facturado al lado del precio que se contrató u ordenó
      para el mismo ítem, en la misma contratación. Arriba las diferencias, de mayor a
      menor; abajo, lo facturado que todavía no tiene con qué compararse. Los precios son
      nominales, cada uno con su fecha: no se ajustan por inflación.</p>
    <div class="cifras cifras-4">
      ${cifra('Renglones comparados', fmtNum.format(r.total ?? filas.length), 'facturado con su referencia')}
      ${cifra('Con diferencia', fmtNum.format(conDif), conDif ? 'distinto de lo contratado' : '')}
      ${cifra('Sin referencia', fmtNum.format(totalFaltantes), 'facturados sin contra qué comparar')}
      ${cifra('Criterio', '<span class="cifra-texto">Precio unitario</span>', esc(r.alcance || ''))}
    </div>

    ${filas.length ? `<h2>Diferencias</h2>
      ${tabla([
        {t: 'Ítem', c: 'crece', r: item},
        {t: 'Contratación', r: contratacion},
        {t: 'Proveedor', r: proveedor},
        {t: 'Contratado', c: 'num', r: x => conFecha(x.contratado, x.fecha_contratado)},
        {t: 'Facturado', c: 'num', r: x => conFecha(x.facturado, x.fecha_facturado)},
        {t: 'Diferencia', c: 'num', r: diferencia},
        {t: 'Comparación', r: x => calidad(x.comparabilidad)},
        {t: 'Fuentes', r: x => (x.fuentes || []).map(f => fuente(f, esc(foja(f)))).join(' ')},
      ], filas)}` : `<p class="nota-seccion">Ningún renglón facturado encontró todavía su
        referencia en la misma contratación, así que no hay diferencias que calcular.</p>`}

    ${faltantes.length ? `<h2>Facturado sin referencia</h2>
      <p class="nota-seccion">Renglones de factura que no tienen un precio contratado u
        ordenado con el que compararse. No es una diferencia: es un cruce que no se pudo
        hacer${motivoUnico ? `. En todos, el motivo es el mismo: <strong>${esc(motivoUnico)}</strong>`
          : ', y el motivo dice por qué'}.</p>
      ${tabla([
        {t: 'Ítem', c: 'crece', r: item},
        {t: 'Contratación', r: contratacion},
        {t: 'Facturado', c: 'num', r: x => conFecha(x.facturado, x.fecha_facturado)},
        // El mismo motivo veintidós veces es una columna que no dice nada: se dice una vez.
        ...(motivoUnico ? [] : [{t: 'Por qué no se compara',
            r: x => `<span class="celda-motivo">${esc(x.motivo || '')}</span>`}]),
        {t: 'Fuente', r: x => (x.fuentes || []).slice(0, 1).map(f => fuente(f, esc(foja(f)))).join('')},
      ], faltantes)}
      ${totalFaltantes > faltantes.length ? `<p class="nota-seccion">Se muestran
        ${fmtNum.format(faltantes.length)} de ${fmtNum.format(totalFaltantes)}.</p>` : ''}` : ''}
  `);
}

/* El cruce de contratos de personal, persona por persona. Queda para los servidores que
   todavía contestan ese contrato; el de contrataciones está arriba. */
async function vCrucePersonas(r) {
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
    <p class="prosa nota sep-corta">
      <strong>Mensual y total no son lo mismo, y no se comparan entre sí.</strong> El
      contrato fija un importe <em>mensual</em>; las facturas se acumulan. El único
      número comparable con lo facturado es el <strong>total contratado</strong>, que el
      contrato dice aparte. Cuando ese total no se pudo leer, la celda queda vacía en
      vez de mostrar un cero o el mensual en su lugar: el sistema no multiplica mensual
      por plazo para llenarla, porque eso sería calcular un número que el papel dice o
      no dice.</p>
    <p class="prosa nota">
      <strong>Una fila por persona, no por contrato.</strong> Una factura no dice a qué
      contrato corresponde, y repartirlas por fecha sería adivinar. Con una fila por
      contrato, quien tiene dos aparecía dos veces y cada fila traía todas sus facturas:
      sumar la columna daba el doble de lo facturado. El detalle contrato por contrato
      está en la ficha de cada persona.</p>
    <p class="prosa nota">
      <strong>Facturado legible</strong> suma sólo los importes impresos que se pudieron
      leer con seguridad. La columna <strong>a mano</strong> cuenta las facturas de
      talonario, donde el importe está manuscrito y el sistema no lo lee: existen y no
      se sabe por cuánto. Mientras esa columna no sea cero, el facturado está incompleto
      y no se puede comparar contra lo pactado como si fuera el total.</p>`);

  tablaBuscable($('#tabla-cruce'), [
      {t:'Contratado/a', c:'nombre', b:f => f.contratado,
       r:f => `<a href="#/persona/${f.persona_id}">${esc(f.contratado)}</a>`},
      {t:'Documento', k:'documento', c:'mono'},
      {t:'Contratos', c:'num', k:'contratos'},
      {t:'Período', c:'mono', b:f => f.contrato_desde, r:f => f.contrato_desde
          ? `${esc(fmtFecha(f.contrato_desde))} → ${esc(fmtFecha(f.contrato_hasta))}`
          : '<span class="nulo" title="sin fechas">—</span>'},
      // Mensual y total son magnitudes distintas y se muestran en columnas distintas.
      // El total es el único comparable con la facturación acumulada de al lado.
      {t:'Mensual pactado', c:'num', b:f => f.mensual_centavos, r:f => f.mensual_centavos
          ? esc(fmtPesos(f.mensual_centavos)) : '<span class="nulo" title="sin dato">—</span>'},
      // Cuando NINGÚN contrato trae el total legible, la celda no muestra $0,00: cero
      // se lee como «no se contrató nada» y lo que pasa es que no se pudo leer.
      {t:'Total contratado', c:'num', b:f => f.contratado_centavos,
       r:f => f.contratos_sin_total_firme >= f.contratos
          ? '<span class="nulo" title="sin leer">—</span>'
          : esc(fmtPesos(f.contratado_centavos)) + (f.contratos_sin_total_firme
              ? ` <span class="sello atencion">faltan ${f.contratos_sin_total_firme}</span>` : '')},
      {t:'Facturas', c:'num', k:'facturas'},
      {t:'Facturado legible', c:'num', b:f => f.facturado_legible_centavos,
       r:f => esc(fmtPesos(f.facturado_legible_centavos))},
      {t:'A mano', c:'num', b:f => f.facturas_a_mano, r:f => f.facturas_a_mano
          ? `<span class="sello atencion">${f.facturas_a_mano}</span>` : '—'},
    ], r.filas, {placeholder: 'Buscar por nombre o documento…'});
}

/* ── El solape, dibujado ───────────────────────────────────────────────────
   La pantalla de superposiciones era cuatro fechas por fila más una columna con los
   días, y para ver que dos períodos se pisan había que hacer la resta en la cabeza,
   fila por fila. El sistema ya tenía las piezas —`--marca` para el contrato,
   `--marca-solape` para lo que se pisa, y la regla escrita en §2 de que el punzó acá
   marca ÚNICAMENTE la superposición— y no se usaban donde más falta.

   El eje es de cada PAR, no del legajo entero: la fila compara dos contratos entre
   sí, y un eje global dejaría todas las barras del tamaño de una uña.

   El gráfico no reemplaza las fechas: las anticipa. Se sigue pudiendo leer el dato
   exacto en mono al lado, que es lo que se cita en un escrito.

   La geometría va en `style` porque sale del dato —es la excepción que §4 declara
   legítima, y la única—. */
function pistaSolape(f) {
  const dia = t => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t || '');
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null; };
  const ia = dia(f.inicio_a), fa = dia(f.fin_a);
  const ib = dia(f.inicio_b), fb = dia(f.fin_b);
  // Sin las cuatro fechas no se dibuja nada. Media barra sería una conjetura, y acá
  // no se conjetura: la fila igual muestra los períodos en texto.
  if ([ia, fa, ib, fb].some(v => v == null)) return '';
  const t0 = Math.min(ia, ib), t1 = Math.max(fa, fb);
  const luz = (t1 - t0) || 1;
  const x = t => ((t - t0) / luz) * 100;
  const ancho = (a, b) => Math.max(((b - a) / luz) * 100, 1.2);   // que nunca sea invisible
  const pi = Math.max(ia, ib), pf = Math.min(fa, fb);
  const hayPisado = pf >= pi;

  const barra = (clase, desde, hasta) =>
    `<i class="${clase}" style="left:${x(desde).toFixed(2)}%;width:${ancho(desde, hasta).toFixed(2)}%"></i>`;

  const dias = f.dias_solapados;
  const rotulo = hayPisado
    ? `Se pisan ${dias} ${dias === 1 ? 'día' : 'días'}, del ${fmtFecha(
        new Date(pi).toISOString().slice(0, 10))} al ${fmtFecha(
        new Date(pf).toISOString().slice(0, 10))}.`
    : 'Los dos períodos no se tocan.';

  /* El número al lado del gráfico y no en una columna aparte. «Se pisan 232 días» es
     la frase que después se escribe en un requerimiento, y en la pantalla de la
     oficina —1366 px— la columna «Días» quedaba fuera del borde derecho junto con
     «Suma» y «Conf.»: había que arrastrar la tabla de costado para ver el número que
     es el hallazgo. El gráfico dice la forma; el número dice el dato, y van juntos. */
  return `<div class="pista-caja">
    <div class="pista-par" role="img" aria-label="${esc(rotulo)}">
      ${barra('carril-a', ia, fa)}${barra('carril-b', ib, fb)}
      ${hayPisado ? barra('pisa-a', pi, pf) + barra('pisa-b', pi, pf) : ''}
    </div>
    ${hayPisado ? `<b class="pista-dias">${fmtNum.format(dias)} ${
      dias === 1 ? 'día' : 'días'}</b>` : ''}
  </div>`;
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
      /* Los dos nombres, elididos por el medio con la misma pieza que la cola.
         El brief pedía sacarle el ancho a «Períodos» y mandar las cuatro fechas al
         `title`. Medido, el ancho no está ahí: «Folios» se lleva el 34 % de la tabla
         con dos nombres enteros y «Períodos» el 15 %. Y un `title` pide puntero —en
         un teléfono no existe— y no se puede citar de un vistazo, que es justo para
         lo que están las fechas en la pantalla central del caso. Se elide acá y las
         fechas se quedan donde se leen. */
      {t:'Folios', c:'fol', r:f =>
        `${nombreArchivo(f.archivo_a)}${nombreArchivo(f.archivo_b)}`},
      {t:'Contratado/a', c:'nombre', r:f => f.contratado ? esc(f.contratado)
          : '<span class="nulo" title="sin nombre">—</span>'},
      {t:'Documento', c:'mono', r:f => f.documento ? esc(f.documento)
          : '<span class="nulo" title="sin dato">—</span>'},
      {t:'Cruce', r:f => f.cruce === 'intercámara' ? `<span class="marca">${esc(f.cruce)}</span>` : esc(f.cruce)},
      /* En formato argentino y sin partirse. La consulta los devuelve unidos y en
         ISO —`2020-03-19 → 2021-01-18`—, que es lo correcto para ordenar y lo
         equivocado para leer: el resto del sistema escribe 19/03/2020, y en una
         columna angosta la fecha ISO se cortaba a la mitad del año. */
      {t:'Períodos', c:'mono nowrap', r:f =>
        `${esc(fmtFecha(f.inicio_a))} → ${esc(fmtFecha(f.fin_a))}<br
         >${esc(fmtFecha(f.inicio_b))} → ${esc(fmtFecha(f.fin_b))}`},
      {t:'Cuánto se pisan', c:'pista', r:f => pistaSolape(f)},
      {t:'Suma', c:'num', r:f => esc(fmtPesos(f.suma_centavos))},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], r.filas, {alClic:true, lista:'superposiciones'})}`);
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
      ? `<button class="ancla boton-ancla" data-campo="${c.id}">f.${c.pagina_nro} · ▣</button>` : '';
    const tocado = c.estado === 'verificado' || c.estado === 'corregido';
    const marca = tocado
      ? ` <span class="sello ok mini-cuno">✓ ${
           c.estado === 'corregido' ? 'cargado a mano' : 'verificado'}</span>` +
        ` <button class="deshacer boton secundario" data-campo="${c.id}"
            title="volver a lo que había leído el sistema">Deshacer</button>` : '';
    const historial = `<button class="historial boton secundario" data-campo="${c.id}"
        title="quién decidió esto, y cuándo">Rastro</button>`;
    return `<div class="campo"><dt>${esc(rotularCampo(c.nombre, doc.familia))}</dt>
      <dd>${celdaValor(c)}${ancla}${marca}${historial}
        <div class="rastro" id="rastro-${c.id}" hidden></div></dd></div>`;
  }).join('');

  const tiras = paginas.map(p =>
    `<button class="foja boton secundario" data-nro="${p.nro}"${p.rotacion ? ' data-girada="1"' : ''}
       title="${p.rotacion ? `esta foja llegó girada ${p.rotacion}° y se enderezó para leerla`
                           : `foja ${p.nro}`}">f. ${p.nro}${p.rotacion ? ' ↻' : ''}</button>`).join('');
  const enderezadas = paginas.filter(p => p.rotacion);

  /* Cuando el PDF trae muchas piezas, se navega entre ellas; no se las lista todas. El
     aviso con los 161 hermanos como enlaces ocupaba media pantalla antes de mostrar la
     foja. Ahora: la anterior, la siguiente, y la lista completa plegada. */
  const hermanos = d.hermanos || [];
  const pos = hermanos.findIndex(h => h.id === doc.id);
  const vecino = h => h ? `<a href="#/documento/${h.id}">${esc(TIPO_DOC[h.tipo] || h.tipo || 'Pieza')},
      f. ${h.pagina_desde}${h.pagina_hasta !== h.pagina_desde ? '–' + h.pagina_hasta : ''}</a>` : '';
  const navegador = varios ? `<nav class="nav-piezas" aria-label="Otras piezas del mismo PDF">
      <span class="nav-piezas-pos">Pieza ${fmtNum.format(doc.orden)} de ${fmtNum.format(hermanos.length)} de este PDF</span>
      ${pos > 0 ? `<span>← ${vecino(hermanos[pos - 1])}</span>` : ''}
      ${pos >= 0 && pos < hermanos.length - 1 ? `<span>${vecino(hermanos[pos + 1])} →</span>` : ''}
      <details class="nav-piezas-todas"><summary>Ver las ${fmtNum.format(hermanos.length)}</summary>
        <ol>${hermanos.map(h => `<li${h.id === doc.id ? ' aria-current="true"' : ''}>${vecino(h)}</li>`).join('')}</ol>
      </details>
    </nav>` : '';
  vista.innerHTML = bloque('f. ' + String(id).padStart(4, '0'), 'Documento', `
    <nav class="migas" aria-label="Estás en"><a href="#/piezas">Documentos</a></nav>
    <h1>${esc(TIPO_DOC[doc.tipo] || String(doc.tipo || 'Documento').replace(/_/g, ' '))}</h1>
    <p class="ficha-objeto">${esc(String(doc.archivo || '').replace(/\.pdf$/i, ''))} · fojas
      ${doc.pagina_desde}${doc.pagina_hasta !== doc.pagina_desde ? '–' + doc.pagina_hasta : ''}</p>
    ${navegador}
    <details class="datos-tecnicos"><summary>Datos técnicos</summary>
      <p class="nota-seccion">${doc.camara ? 'Cámara de ' + esc(camaraTexto(doc.camara)) + ' · ' : ''}perfil
        <span class="mono">${esc(doc.perfil)}</span> · lote ${esc(doc.lote || '—')} ·
        <span class="mono">huella digital ${esc(String(doc.sha256).slice(0, 32))}…</span></p>
    </details>
    ${enderezadas.length ? `<div class="aviso info">${sello('neutro', 'Enderezada')}
      <span>${enderezadas.length === 1 ? 'La foja' : 'Las fojas'}
      ${enderezadas.map(p => `${p.nro} (${p.rotacion}°)`).join(', ')} llegó girada en el escaneo. <strong>El original no se tocó</strong>: se giró la copia de trabajo para poder leerla, y es esa la que ves acá.</span></div>` : ''}
    <div class="visor${d.campos.length ? '' : ' visor-sin-datos'}">
      <div class="datos">
        <div class="entre-extremos">
          <span class="rotulo">Carril de datos — leído del documento</span>
        </div>
        ${d.campos.length ? campos : `<p class="nota-seccion">De esta pieza el sistema
          reconoce qué es, pero todavía no lee sus datos campo por campo. Los renglones
          con precio que se leyeron de ella están en
          <a href="#/precios">Ítems y precios</a>.</p>`}
      </div>
      <div class="lamina">
        ${paginas.length > 1 ? `<div class="fojas-selector">${tiras}</div>` : ''}
        <div class="lienzo" id="lienzo" title="Tocá para ver la foja entera">
          <img id="folio" alt="Foja de ${esc(doc.archivo)}">
          <div class="recuadro" id="recuadro" hidden></div>
        </div>
        <div class="pie-lamina"><span id="pie-campo">tocá una ficha de anclaje</span>
          <span id="pie-xy"></span></div>
        <button class="boton gris" id="abrir-foja-doc" type="button">Ver la foja entera, para leerla</button>
      </div>
    </div>
    <!-- Lo que se viene a ver —los datos y la foja— va primero; las relaciones con
         otras piezas y la continuidad en otras fojas, que son trabajo de revisión,
         después. -->
    <section id="relaciones-documento" class="sep" aria-live="polite">Cargando relaciones...</section>
    <section id="continuidad-pieza" class="nucleo-continuidad" aria-live="polite">Cargando tramos...</section>
    ${d.interpretaciones.length ? `
      <div class="sep">
        <span class="rotulo">Carril de interpretación — conjeturas del sistema</span>
        <p class="prosa nota">Esto no se leyó de ningún papel: son hipótesis armadas cruzando datos. Pueden estar mal. Cada una linkea a los documentos que la sostienen.</p>
        ${d.interpretaciones.map(interpHTML).join('')}
      </div>` : ''}`);

  cargarContinuidad(id, doc.sha256);
  cargarRelacionesDocumento(id);
  vista.querySelectorAll('.deshacer').forEach(b => b.onclick = async () => {
    const quien = await conRevisor(); if (!quien) return;
    if (!await dialogoConfirm('¿Deshacer esta revisión? El campo vuelve a lo que había leído el sistema.')) return;
    try {
      await api('/api/campo', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({campo_id:+b.dataset.campo, accion:'revertir', quien})});
      await vDocumento(id); refrescarCuentas();
    } catch (e) { toast('No se pudo deshacer: ' + e.message); }
  });

  const recuadro = $('#recuadro');
  const folio = $('#folio');

  const cuenta = {};
  anclables.forEach(c => { if (c.pagina_nro) cuenta[c.pagina_nro] = (cuenta[c.pagina_nro] || 0) + 1; });
  const conDatos = Object.keys(cuenta).sort((a, b) => cuenta[b] - cuenta[a])[0];
  let actual = conDatos ? +conDatos : paginas[0].nro;

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

  let ultimoAnclado = null;
  const abrirLaFoja = () => {
    const pag = paginas.find(p => p.nro === actual) || paginas[0];
    const c = (ultimoAnclado && (ultimoAnclado.pagina_nro || paginas[0].nro) === actual)
      ? ultimoAnclado : null;
    abrirFoja({documento_id: id, pagina_nro: actual, archivo: doc.archivo,
               campo: c ? c.nombre : '', familia: doc.familia,
               pagina: {ancho_pt: pag.ancho_pt, alto_pt: pag.alto_pt},
               x0: c && c.x0, y0: c && c.y0, x1: c && c.x1, y1: c && c.y1,
               campo_id: c && c.id});
  };
  $('#abrir-foja-doc').onclick = abrirLaFoja;
  $('#lienzo').onclick = abrirLaFoja;

  vista.querySelectorAll('.ancla').forEach(b => b.onclick = () => {
    const c = anclables.find(x => x.id === +b.dataset.campo);
    if (!c) return;
    ultimoAnclado = c;
    const nro = c.pagina_nro || paginas[0].nro;
    if (nro !== actual) verFoja(nro);
    const pag = paginas.find(p => p.nro === nro) || paginas[0];
    recuadro.style.display = 'block';
    recuadro.style.left   = (100 * c.x0 / pag.ancho_pt) + '%';
    recuadro.style.top    = (100 * c.y0 / pag.alto_pt) + '%';
    recuadro.style.width  = (100 * (c.x1 - c.x0) / pag.ancho_pt) + '%';
    recuadro.style.height = (100 * (c.y1 - c.y0) / pag.alto_pt) + '%';
    $('#pie-campo').textContent = rotularCampo(c.nombre, doc.familia);
    $('#pie-xy').textContent = `[x:${c.x0.toFixed(1)} y:${c.y0.toFixed(1)}]`;
  });
}


/* ── cola de revisión: el folio al lado, sin salir de la pantalla ──────── */
/* Antes cada campo costaba dos navegaciones (ir al folio y volver) y se perdía el
   lugar en la lista. Con 42 campos eso son 84 saltos de pantalla. Acá la foja
   acompaña a la fila que tiene el foco, con una lupa sobre el campo. */
/* ── Cuánto se lleva hecho ─────────────────────────────────────────────────
   «1 de 6» dice dónde está el cursor; no dice nada de la tarea. En una cola de tres
   mil campos —el caso real— alguien revisa cuarenta minutos, ve «1 de 2.847» y no
   tiene forma de saber si avanzó. Eso es lo que agota y lo que hace que se deje por
   la mitad.

   El universo es lo que ALGUNA VEZ necesitó a una persona: lo que espera más lo que
   ya se decidió. Los dos números se mueven juntos —deshacer una decisión devuelve el
   campo a la cola— así que el total no salta solo y la barra no miente.

   Y abajo, quiénes. Son varios los que trabajan la misma causa: que el avance sea del
   equipo y no de cada uno por su lado es la mitad de por qué esto se comparte. */
/* La prosa que explica cómo funciona una pantalla se lee UNA vez. Después es un
   renglón fijo que cuesta lo mismo todos los días: en 768 px de alto, los dos
   renglones de la cola son la mitad de una fila de trabajo. Se recuerda por sesión y
   no para siempre: al día siguiente, o en otra máquina, vuelve a explicarse. */
function explicarUnaVez(pantalla) {
  try {
    const clave = 'ufil.explicado.' + pantalla;
    if (sessionStorage.getItem(clave)) return false;
    sessionStorage.setItem(clave, '1');
    return true;
  } catch (e) { return true; }   // sin sessionStorage, se explica siempre
}

function avanceCola(r) {
  const hechos = r.revisados || 0;
  const universo = hechos + (r.total_sin_filtro || 0);
  if (!universo) return '';
  return `<div class="avance" id="avance">${
    tripasAvance(hechos, universo, r.revisores, 0, r.total)}</div>`;
}

/* Se separa del envoltorio porque hay que volver a pintarla en cada decisión SIN
   volver a pedir la cola: la pantalla saca la fila decidida y sigue, y una barra de
   avance que sólo se mueve al recargar es peor que no tenerla —quien revisa cuarenta
   minutos la ve clavada y concluye que no anda—. */
function tripasAvance(hechos, universo, revisores, donde, cuantos) {
  const pct = Math.round(hechos * 100 / universo);
  const yo = (REVISOR || '').trim();
  const equipo = (revisores || []).filter(x => x.n > 0);
  const otros = yo ? equipo.filter(x => x.quien !== yo) : equipo;
  const suma = otros.reduce((t, x) => t + x.n, 0);
  const mios = yo ? equipo.filter(x => x.quien === yo).reduce((t, x) => t + x.n, 0) : 0;

  // Nombrar a los demás sólo cuando hay demás: trabajando solo, «y 0 del equipo» es
  // ruido y encima suena a que falta alguien. Y sin identificarse no hay «tuyos» que
  // valga: se cuenta todo junto.
  const deLosOtros = otros.length === 1 ? 'de otra persona'
                                       : `entre otras ${fmtNum.format(otros.length)} personas`;
  let detalle = '';
  if (hechos && otros.length && yo && mios) {
    detalle = ` — <strong>${fmtNum.format(mios)}</strong> ${mios === 1 ? 'tuyo' : 'tuyos'} y ` +
      `<strong>${fmtNum.format(suma)}</strong> ${deLosOtros}`;
  } else if (hechos && otros.length && yo) {
    // Todavía no revisaste nada: «0 tuyos y 5 de otra persona» es una cuenta de más
    // para decir lo mismo, y encima empieza marcando un cero.
    detalle = `, todos ${deLosOtros}`;
  } else if (hechos && otros.length > 1 && !yo) {
    detalle = `, entre ${fmtNum.format(otros.length)} personas`;
  }
  /* Dónde estás y cuánto llevás, en el MISMO renglón.
     Eran dos: «0 de 62 campos revisados» arriba a la izquierda y «1 de 62» arriba a
     la derecha, separados por todo el ancho de la pantalla. Uno es avance y el otro
     es posición, pero se leen igual, y en el teléfono quedaban pegados uno al otro,
     donde además se veía que el 0 y el 1 no coinciden. Dos cuentas del mismo total en
     la misma pantalla es una de más. */
  const posicion = cuantos
    ? `<span class="donde">Campo <strong>${fmtNum.format(donde + 1)}</strong> de
        ${fmtNum.format(cuantos)}</span> · ` : '';
  /* Y el total, una sola vez. «Campo 1 de 78 · 0 de 78 campos revisados» pone el 78
     dos veces en el mismo renglón, que en un teléfono es el renglón entero. Cuando
     los dos totales son el mismo número —o sea, sin filtro puesto— alcanza con
     «0 revisados». Con un filtro puesto NO son el mismo número y los dos hacen falta:
     uno es lo que estás recorriendo y el otro es el legajo. */
  const repetido = posicion && universo === cuantos;
  const cuenta = repetido
    ? `<strong>${fmtNum.format(hechos)}</strong> ${hechos === 1 ? 'revisado' : 'revisados'}`
    : `<strong>${fmtNum.format(hechos)}</strong> de ${fmtNum.format(universo)} ${
        universo === 1 ? 'campo revisado' : 'campos revisados'}`;
  return `<div class="riel"><i style="width:${pct}%"></i></div>
    <p>${posicion}${cuenta}${detalle}.</p>`;
}

/* Vuelve a pintar el avance con lo que la pantalla ya sabe, sin ir al servidor. */
function pintarAvance() {
  const caja = $('#avance');
  if (!caja) return;
  const hechos = colaEstado.revisados || 0;
  const universo = hechos + (colaEstado.total_sin_filtro || 0);
  if (!universo) return;
  caja.innerHTML = tripasAvance(hechos, universo, colaEstado.revisores,
                                colaEstado.foco, colaEstado.total);
}

/* Un teléfono, medido y no supuesto: el mismo corte que usa la hoja de estilos. */
const esTelefono = () => window.matchMedia('(max-width:720px)').matches;

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
                revisados: r.revisados || 0, revisores: r.revisores || [],
                // Cuántas filas nos entregó el servidor, que NO es lo mismo que
                // cuántas estamos mostrando: si una llega repetida se descarta, y la
                // próxima página igual tiene que pedirse más adelante. Contando por
                // las mostradas, una página entera de repetidas volvía a pedir la
                // misma página para siempre.
                traidas: filas.length,
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
  const hayFiltro = !!(filtroCola.familia || filtroCola.campo || filtroCola.clase);
  vista.innerHTML = `
    <div class="taller">
      <header class="taller-cabeza">
        <div>
          <!-- El título y «ver la lista» en el mismo renglón. La lista es OTRA manera
               de mirar lo mismo, así que va donde dice qué se está mirando; abajo, al
               lado de los botones de avanzar, le comía a la decisión los píxeles que
               necesita para entrar en la misma pantalla que el recorte. -->
          <div class="cabeza-fila">
            <h2>Cola de revisión</h2>
            <button class="boton gris ficha-lista" id="ficha-lista" type="button"
                    >Ver la lista</button>
          </div>
          <!-- Sin el número acá. Este subtítulo se pinta una sola vez, cuando se
               abre la cola, y la cola baja con cada decisión: a los cinco campos
               revisados decía «6 campos esperan revisión» arriba de un «1 de 4», dos
               cuentas de lo mismo contradiciéndose en la misma pantalla. El número
               vive en la barra de avance de abajo y en el «1 de N» de la derecha, que
               son los dos que sí se actualizan. -->
          ${explicarUnaVez('cola') ? `<p class="taller-sub">Ordenados por lo que más
            daño hace si queda mal. <strong>El folio está a la vista</strong>: no hace
            falta salir de acá.</p>` : ''}
          ${avanceCola(r)}
        </div>
      </header>

      <div class="otros-revisaron" id="otros-revisaron" hidden></div>

      <!-- Plegados en el teléfono. Tres selectores a ancho completo son tres
           renglones de 44 px que hay que pasar CADA VEZ que se entra, y en el caso
           normal —sin filtro— no dicen nada. Abiertos si hay alguno puesto: un filtro
           activo escondido es peor que tres selectores de más. -->
      <!-- Plegados salvo que haya alguno puesto, en TODAS las pantallas y no sólo en
           el teléfono. Medido en 1366×768, que es la pantalla de la oficina: abiertos
           se llevaban 179 px, la quinta parte del alto útil, para decir tres veces
           «todos». Un filtro activo escondido sí sería peor, y por eso se abren solos
           cuando hay uno puesto.

           Y los controles van adentro de un DIV, no sueltos en el DETAILS. Un
           DETAILS con display:flex NO acomoda su contenido en fila: el navegador mete
           todo lo que sigue al SUMMARY adentro de una caja de bloque anónima, y ahí
           los tres selectores se apilan. Es lo que pasó cuando esto se volvió
           plegable por el teléfono, y en la oficina se veía como una columna de
           179 px de alto. -->
      <details class="taller-filtros" id="filtros-cola"${hayFiltro ? ' open' : ''}>
        <summary>Filtros${hayFiltro ? ' · activos' : ''}
          <span class="rotulo">${plural(r.total_sin_filtro, 'campo', 'campos')}</span></summary>
        <div class="filtros-fila">
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
      </details>

      <div class="taller-cuerpo">
        <div class="cola" id="cola"><p class="lista-ayuda">Tocá un campo para ver la
          foja y decidir.</p>${
          !filas.length ? vacio('Ningún campo entra en ese filtro',
            'Hay ' + plural(todas.length, 'campo esperando revisión',
                            'campos esperando revisión') +
            ', pero ninguno cumple lo que pediste.') : ''}${filas.map(filaCola).join('')}
          ${filas.length < r.total ? `<button class="mas-cola" id="mas-cola">Traer
            ${plural(Math.min(POR_PAGINA, r.total - filas.length), 'campo más', 'campos más')}
            <span>quedan ${fmtNum.format(r.total - filas.length)}</span></button>` : ''}</div>
        <aside class="folio-lado" id="folio-lado">
          <!-- De dónde sale lo que estás por decidir. Primero y chiquito, y sólo en
               el teléfono: en el escritorio eso ya lo dice la marginalia de la fila,
               a la izquierda del campo. -->
          <p class="ficha-procedencia mono" id="ficha-procedencia"></p>
          <!-- El recuadro del campo va dibujado sobre el recorte. La lupa muestra el
               renglón Y lo que lo rodea —hace falta para saber que se está mirando el
               renglón correcto—, pero sin nada que lo marque hay que adivinar cuál de
               los renglones a la vista es el campo. -->
          <div class="lupa" id="lupa"><img id="lupa-img" alt="">
            <div id="lupa-marco" hidden></div></div>
          <div class="pie-lamina"><span id="lupa-campo"></span><span id="lupa-xy"></span></div>
          <!-- La hoja entera va OCULTA mientras haya recorte.
               A unos 250 px de ancho no se distingue una sola palabra, y se llevaba la
               mitad del panel: el recorte del campo es lo que se necesita para decidir,
               y el anclaje —foja y coordenadas— ya está escrito arriba, en el pie.
               Se enciende en el único caso donde es lo que hace falta: cuando el
               sistema NO encontró el campo en la foja y hay que buscarlo a mano. -->
          <div class="lienzo" id="lienzo-cola" hidden>
            <img id="folio-cola" alt="">
            <div class="recuadro" id="recuadro-cola" hidden></div>
          </div>
          <!-- Los dos botones decían casi lo mismo: «Abrir la foja entera» y «Ver el
               documento completo». Por el nombre eran el mismo botón dos veces. Y no
               lo son: uno abre EL PAPEL de esta foja a pantalla completa y se vuelve
               con Escape; el otro se va de la cola a la pantalla del documento, donde
               están todos sus campos leídos. Ahora cada uno dice cuál de las dos cosas
               hace, y con eso también dice dónde queda uno después de apretarlo. -->
          <button class="boton" id="abrir-foja" type="button">Abrir la foja entera</button>
          <a class="boton gris" id="ir-doc" href="#/panel">Ver todos los campos del documento</a>
        </aside>
      </div>

      <footer class="taller-pie">
        <!-- Avanzar, en la zona del pulgar y sólo en el teléfono. En el escritorio se
             baja por la lista con J y K y esto no hace falta. -->
        <div class="ficha-avanzar">
          <button class="tecla ficha-mover" id="ficha-antes" type="button"
                  aria-label="Campo anterior">‹</button>
          <span class="ficha-donde" id="ficha-donde"></span>
          <button class="tecla ficha-mover" id="ficha-despues" type="button"
                  aria-label="Campo siguiente">›</button>
        </div>
        <span class="solo-teclado"><kbd>J</kbd>/<kbd>K</kbd> para moverse; las teclas de
          cada fila para decidir. <strong>Ninguna acción es «aceptar todo».</strong></span>
        <div class="deshacer-barra" id="deshacer-barra" hidden></div>
      </footer>
    </div>`;

  engancharFilasCola();
  ponerModoCola(modoCola);
  $('#abrir-foja').onclick = () => abrirFoja(colaEstado.filas[colaEstado.foco]);
  $('#ficha-antes').onclick = () => moverFicha(-1);
  $('#ficha-despues').onclick = () => moverFicha(+1);
  $('#ficha-lista').onclick = () => ponerModoCola(modoCola === 'ficha' ? 'lista' : 'ficha');
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
  if (colaEstado.cargando || colaEstado.traidas >= colaEstado.total) return;
  colaEstado.cargando = true;
  const boton = $('#mas-cola');
  if (boton) boton.textContent = 'buscando…';
  try {
    const p = new URLSearchParams({desde: String(colaEstado.traidas),
                                   limite: String(POR_PAGINA)});
    for (const k of ['familia', 'campo', 'clase']) if (filtroCola[k]) p.set(k, filtroCola[k]);
    const r = await api('/api/cola?' + p);
    // Sin repetir lo que ya está. La página siguiente se pide por posición
    // (`desde`), y la posición se corre cuando alguien decide un campo —el propio o
    // el de otra persona trabajando la misma causa—: ahí una fila puede volver a
    // caer adentro de la página que llega. Que la cuenta dé bien no alcanza; el
    // mismo campo dos veces en la pantalla obliga a decidirlo dos veces.
    const yaEstan = new Set(colaEstado.filas.map(x => String(x.campo_id)));
    const frescas = r.filas.filter(x => !yaEstan.has(String(x.campo_id)));
    colaEstado.traidas += r.filas.length;
    const desde = colaEstado.filas.length;
    colaEstado.filas = colaEstado.filas.concat(frescas);
    colaEstado.total = r.total;
    const cola = $('#cola');
    const nuevas = frescas.map((f, i) => filaCola(f, desde + i)).join('');
    if (boton) boton.remove();
    cola.insertAdjacentHTML('beforeend', nuevas);
    if (colaEstado.traidas < r.total) {
      cola.insertAdjacentHTML('beforeend', `<button class="mas-cola" id="mas-cola">Traer
        ${plural(Math.min(POR_PAGINA, r.total - colaEstado.traidas), 'campo más', 'campos más')}
        <span>quedan ${fmtNum.format(r.total - colaEstado.traidas)}</span></button>`);
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
    colaEstado.foco = +f.dataset.i;
    // En el teléfono la lista existe para SALTAR a un campo, no para trabajar adentro
    // de ella: tocar una fila vuelve a la ficha, que es donde se ve el papel.
    if (modoCola === 'lista' && esTelefono()) return ponerModoCola('ficha');
    pintarFoco();
  });
}

/* ── El nombre del documento, sin partirlo ─────────────────────────────────
   La celda que dice de qué papel salió el campo tenía `overflow-wrap:anywhere`, que
   se puso a propósito para que un nombre largo no se cortara por la izquierda y se
   perdiera. El efecto real era peor: `contrato_A_0013` se leía «contrato_A_001» y
   abajo, solo, un «3». Con quince renglones así en pantalla, decidir sobre el
   documento equivocado es cuestión de tiempo, y es lo más caro que puede pasar acá.

   Se elide por el MEDIO y se conserva el final. Los nombres de un lote comparten
   prefijo —`contrato_A_…`, `contrato_B_…`— así que lo que distingue un documento de
   otro son los últimos caracteres, no los primeros. Cortando por la izquierda se
   pierde justamente lo que identifica.

   No se puede hacer sólo con CSS: `text-overflow:ellipsis` corta por el final. Van
   dos piezas, la cabeza que se encoge y la cola que no, y el navegador pone los
   puntos suspensivos donde corresponde. */
const COLA_NOMBRE = 8;      // caracteres del final que nunca se recortan

function nombreArchivo(nombre) {
  const n = String(nombre || '').replace(/\.pdf$/i, '');
  if (n.length <= COLA_NOMBRE) return `<span class="nombre-doc">${esc(n)}</span>`;
  return `<span class="nombre-doc" title="${esc(n)}"
    ><span class="doc-ini">${esc(n.slice(0, -COLA_NOMBRE))}</span
    ><span class="doc-fin">${esc(n.slice(-COLA_NOMBRE))}</span></span>`;
}

function filaCola(f, i) {
  /* Las opciones SON los valores.

     Decía «tomar ocr_a», «tomar ocr_b»: el nombre del mecanismo, no el dato. Para
     decidir había que mirar la lista de la izquierda, encontrar cuál de los valores
     era el de la ruta A, y recién entonces volver al botón correcto. Dos lecturas y
     un salto de ida y vuelta, cuarenta veces por hora. Y el error que provoca es el
     peor: elegir el botón de al lado.

     Ahora el botón muestra el valor y la ruta va abajo, chica: la ruta es
     procedencia —de dónde salió el dato, que es obligatorio— pero no es lo que se
     decide. Se decide cuál dice el papel. */
  const acciones = [];
  if (f.clase === 'conflicto' && f.variantes) {
    f.variantes.forEach((v, n) => acciones.push({
      tecla: String(n + 1), valor: v.valor, de: v.ruta,
      accion: 'corregir', dato: v.valor}));
    // «Ninguna de las dos» con tres variantes en pantalla es falso, y lo que está
    // mal escrito en un botón lo lee alguien que está decidiendo sobre un legajo.
    acciones.push({tecla: 'N', accion: 'ambiguo', dato: '', clase: 'secundaria',
                   texto: f.variantes.length === 2 ? 'Ninguna de las dos'
                                                   : 'Ninguna de esas'});
  } else if (f.motivo === 'manuscrito') {
    // Confirmar la propuesta es UNA tecla, y queda registrado como corrección humana:
    // el dato entra porque una persona lo miró contra el recorte, no porque lo dijo
    // un modelo.
    if (f.propuesta && !f.propuesta.ilegible && f.propuesta.valor) {
      acciones.push({tecla: '1', valor: f.propuesta.valor,
                     de: 'propuesta · ' + (f.propuesta.modelo || ''),
                     accion: 'corregir', dato: f.propuesta.valor});
    }
    acciones.push({tecla: 'C', texto: 'Escribirlo a mano', accion: 'pedir', dato: ''});
    acciones.push({tecla: 'X', texto: 'Está escrito a mano y no se lee',
                   accion: 'verificar', dato: '', clase: 'secundaria'});
  } else if (f.motivo) {
    acciones.push({tecla: 'C', texto: 'Escribirlo a mano', accion: 'pedir', dato: ''});
    acciones.push({tecla: 'X', texto: TEXTO_CIERRE[f.motivo] || 'Confirmarlo y cerrarlo',
                   accion: 'verificar', dato: '', clase: 'secundaria'});
  } else {
    acciones.push({tecla: 'V', texto: 'Es correcto', accion: 'verificar', dato: '',
                   clase: 'principal'});
    acciones.push({tecla: 'C', texto: 'Corregir', accion: 'pedir', dato: ''});
    acciones.push({tecla: 'X', texto: 'No se lee en el papel', accion: 'ilegible',
                   dato: '', clase: 'secundaria'});
  }

  /* En un conflicto los valores ya están en los botones: repetirlos arriba es hacer
     leer lo mismo dos veces. Lo que queda arriba es el valor cuando hay UNO solo, que
     es lo que hay que juzgar contra la foja. */
  let m_nulo = MOTIVO_NULO[f.motivo] || f.motivo || '';
  if (m_nulo) m_nulo = m_nulo.charAt(0).toUpperCase() + m_nulo.slice(1);
  const cuerpo = (f.clase === 'conflicto' && f.variantes) ? ''
    : `<div class="valor-campo">${f.valor
        ? `<span class="mono">${esc(f.valor)}</span>`
        : `<span class="nulo">${esc(m_nulo)}</span>`
      } ${barraConf(f.confianza)}</div>`;

  /* Cuando otro documento tiene el mismo contratado, el mismo período y el mismo
     importe. Es una SOSPECHA y está dicha como tal: dos contratos con los mismos datos
     también pueden ser dos contratos reales, y el sistema no borra ni fusiona nada.
     Pero quien está revisando tiene que enterarse ahí, no después. */
  const mp = f.mismo_papel;
  const repetido = (mp && mp.otros && mp.otros.length)
    ? `<p class="mismo-papel">${mp.seguro
        ? `Otro documento tiene el mismo contratado, período <strong>e importe</strong>:
           puede ser el mismo papel cargado dos veces.`
        : `Otro documento tiene el mismo contratado y el mismo período.
           <strong>Si el importe también coincide, es el mismo papel cargado dos
           veces</strong>; si no coincide, son dos contratos que se pisan.`}
         ${mp.otros.map(o => `<a href="#/documento/${o.documento_id}"
             >${esc(o.archivo || 'documento ' + o.documento_id)}</a>`).join(', ')}</p>`
    : '';

  const propuesta = (f.propuesta && f.propuesta.ilegible)
    ? `<div class="propuesta ilegible">
         <span class="de-donde">propuesta · ${esc(f.propuesta.modelo)}</span>
         <b>no se lee</b>
         ${f.propuesta.nota ? `<span class="nota">${esc(f.propuesta.nota)}</span>` : ''}
       </div>` : '';

  /* Por qué está esperando este campo, UNA vez. En un campo vacío el motivo ya está
     dicho abajo con tratamiento de estado —«no está en el documento»— y arriba se
     repetía en general: «No se pudo leer» arriba y «no se puede leer» abajo, la misma
     cosa dos veces por fila y sesenta y dos veces en la pantalla. Se va la frase
     general y queda la precisa, que además es la que tiene el color del estado.
     En un conflicto y en una lectura floja no hay repetición: ahí arriba está lo
     único que se dice, porque los valores viven en los botones. */
  const porque = (f.clase === 'nulo' && (MOTIVO_NULO[f.motivo] || f.motivo)) ? ''
    : `<span class="porque">${esc(CLASE_COLA[f.clase] || f.clase)}</span>`;

  const boton = o => `<button class="tecla boton secundario ${o.clase || ''} ${o.valor ? 'opcion' : ''}"
      data-campo="${f.campo_id}" data-accion="${o.accion}" data-valor="${esc(o.dato)}">
      <kbd>${o.tecla}</kbd>
      ${o.valor
        ? `<span class="cuerpo"><span class="valor mono">${esc(o.valor)}</span>
             <span class="de">${esc(o.de)}</span></span>`
        : `<span class="cuerpo">${esc(o.texto)}</span>`}
    </button>`;

  return `<div class="fila" data-i="${i}">
    <div class="med">
      <div class="cabeza-campo">
        <span class="etiqueta-campo ${f.clase === 'conflicto' ? 'alerta' : ''}"
          >${esc(rotularCampo(f.campo, f.familia))}</span>
        ${porque}
        ${f.familia && f.familia !== 'contrato'
          ? `<span class="porque">${esc(FAMILIA_DOC[f.familia])}</span>` : ''}
      </div>
      <div class="doc-campo">${nombreArchivo(f.archivo)}${f.pagina_nro != null ? ` <span>f. ${f.pagina_nro}</span>` : ''}</div>
      ${cuerpo}
      ${repetido}
      ${propuesta}
    </div>
    <div class="acc">${acciones.map(boton).join('')}</div>
  </div>`;
}

/* ── Un campo por pantalla ─────────────────────────────────────────────────
   En el escritorio la cola es lista + panel del papel al costado, y funciona. En un
   teléfono ese modelo no existe, porque no hay costado: el panel es uno solo y la
   lista tiene setenta y ocho filas, así que el recorte del campo que hay que decidir
   nunca puede estar al lado de su decisión. Acomodar el panel no alcanza —arriba de
   la lista tapa la lista, abajo de la lista queda a setenta y ocho tarjetas de
   distancia—: lo que cambia es la unidad de trabajo.

   Modo «ficha»: un campo por pantalla, con el recorte grande arriba y la decisión en
   la zona del pulgar. La lista completa sigue existiendo detrás de «Ver la lista»,
   para saltar a un campo puntual y para filtrar. En el teléfono no se recorre: se
   decide.

   Es una clase en el contenedor y nada más: las filas, los botones, las teclas y
   `decidir` son los mismos. Dos maneras de dibujar el mismo trabajo, no dos colas. */
let modoCola = 'ficha';

/* La ficha existe SÓLO en el teléfono. En el escritorio hay lista y panel al costado,
   y ahí `modoCola` no significa nada: preguntar sólo por el modo dejaba al escritorio
   sin `scrollIntoView`, o sea que bajar con J y K dejaba de mover la lista y el foco
   se iba abajo del borde sin que nada se moviera. */
const enFicha = () => modoCola === 'ficha' && esTelefono();

function ponerModoCola(modo) {
  modoCola = modo;
  const t = vista.querySelector('.taller');
  if (!t) return;
  t.classList.toggle('modo-ficha', modo === 'ficha');
  t.classList.toggle('modo-lista', modo === 'lista');
  const b = $('#ficha-lista');
  if (b) b.textContent = modo === 'ficha' ? 'Ver la lista' : 'Volver a la ficha';
  // Al volver de la lista, arriba de todo: la ficha empieza por el recorte.
  if (modo === 'ficha' && esTelefono()) window.scrollTo({top: 0});
  pintarFoco();
}

function moverFicha(paso) {
  colaEstado.foco = Math.max(0, Math.min(colaEstado.foco + paso,
                                         colaEstado.filas.length - 1));
  pintarFoco();
}

/* ── No se decide sin ver ──────────────────────────────────────────────────
   La regla del README, cumplida acá: un control de decisión no existe si el recorte
   del campo no está a la vista al mismo tiempo. No es una preferencia de diseño; es
   la restricción 4 —todo dato anclado a su origen— del lado de quien decide. Un
   «es correcto» apretado sin mirar el papel es una afirmación sin fundamento con la
   firma de una persona encima, y eso es lo único que este sistema no puede permitir.

   Se aplica sobre lo que el navegador REALMENTE cargó, no sobre lo que la base dice
   que hay: una imagen que no llegó deja la pantalla igual de ciega que un campo sin
   anclaje. */
let hayQueMirar = false;

function pintarSinVer(motivo) {
  hayQueMirar = !motivo;
  const fila = vista.querySelector('.fila.foco');
  if (!fila) return;
  fila.querySelectorAll('[data-accion]').forEach(b => { b.disabled = !!motivo; });
  fila.classList.toggle('sin-ver', !!motivo);
  let aviso = fila.querySelector('.aviso-sin-ver');
  if (!motivo) { if (aviso) aviso.remove(); return; }
  if (!aviso) {
    aviso = document.createElement('p');
    aviso.className = 'aviso-sin-ver';
    (fila.querySelector('.acc') || fila).prepend(aviso);
  }
  aviso.textContent = motivo;
}

/* Campos cuya foja el operador ya abrió entera. Sin recorte que sirva, una página
   completa metida en un panel de 340 px no es «ver»: no se lee un importe ahí, y dar
   por cumplida la regla con esa estampilla era el agujero más grande que le quedaba.
   Abrirla en el visor sí es ver, y eso se recuerda por campo mientras dure la sesión
   de la pantalla. */
const fojasMiradas = new Set();

function vigilarVista(f) {
  const lupa = $('#lupa'), recorte = $('#lupa-img'), hoja = $('#folio-cola');
  if (!lupa) return;
  const sinRecorteUtil = lupa.classList.contains('sin-anclaje');
  const mira = sinRecorteUtil ? hoja : recorte;
  const juzgar = () => {
    if (!mira || !mira.getAttribute('src')) {
      return pintarSinVer(f && f.pagina_nro == null
        ? 'este campo no tiene foja escaneada: no hay con qué verificarlo'
        : 'no hay imagen de la foja para mirar');
    }
    if (!mira.complete) return pintarSinVer('cargando la foja…');
    if (!mira.naturalWidth) return pintarSinVer('no se pudo cargar la imagen de la foja');
    // Con recorte alcanza con que haya cargado. Sin recorte NO alcanza: la hoja
    // entera achicada no muestra el dato, así que hay que abrirla.
    if (sinRecorteUtil && !fojasMiradas.has(String(f.campo_id))) {
      return pintarSinVer('abrí la foja entera para poder decidir: así como está ' +
                          'no se lee el dato');
    }
    pintarSinVer('');
  };
  if (mira) { mira.onload = juzgar; mira.onerror = juzgar; }
  juzgar();
}

/* ── La foja entera, para leerla de verdad ─────────────────────────────────
   Se abre a pantalla completa, al tamaño del escaneo y con desplazamiento. Es el
   destino que faltaba: la miniatura del costado sirve para ver que la hoja existe, no
   para leer un importe. Y es la única manera honesta de habilitar la decisión cuando
   el recorte no sirve —el operador miró el papel—.

   Si el campo tiene coordenadas, aunque sean malas, se dibuja el recuadro igual: ver
   dónde CREE el sistema que está el campo es la mitad de entender por qué falló. */
function fojaDe(f) {
  // La foja del campo; si el sistema no lo encontró en ninguna, la primera del
  // documento. Sin este respaldo, justo los campos sin anclaje —que son los que
  // NECESITAN que se abra la hoja— dejaban el visor sin abrir y la decisión trabada
  // para siempre.
  return f && (f.pagina_nro || (f.pagina_respaldo && f.pagina_respaldo.nro)) || null;
}

function abrirFoja(f) {
  const nro = fojaDe(f);
  if (!nro) return;
  aplicarZoomVisor(); const visor = $('#visor'), img = $('#visor-img'), marco = $('#visor-marco');
  if (!visor) return;
  img.src = `/pagina?doc=${f.documento_id}&nro=${nro}`;
  $('#visor-rotulo').textContent =
    [f.archivo || 'documento', 'f. ' + nro,
     f.campo ? rotularCampo(f.campo, f.familia) : ''].filter(Boolean).join(' · ');
  const pag = f.pagina || f.pagina_respaldo;
  const hayCaja = pag && pag.ancho_pt && f.x0 != null && f.x1 != null;
  marco.hidden = !hayCaja;
  if (hayCaja) {
    marco.style.left = (100 * f.x0 / pag.ancho_pt) + '%';
    marco.style.top = (100 * f.y0 / pag.alto_pt) + '%';
    marco.style.width = (100 * Math.max(f.x1 - f.x0, 2) / pag.ancho_pt) + '%';
    marco.style.height = (100 * Math.max(f.y1 - f.y0, 2) / pag.alto_pt) + '%';
  }
  visor.hidden = false;
  document.body.classList.add('con-visor');
  fojasMiradas.add(String(f.campo_id));
  /* Lo de abajo queda apagado mientras la foja está abierta: no se toca, no se tabula
     y un lector de pantalla no lo lee. Sin esto, tabulando desde el botón de cerrar
     se llega a los botones de decidir que están tapados —se decide un campo sin ver
     lo que se está decidiendo, con la foja de otro encima—. Y al cerrar, el foco
     vuelve a donde estaba: quien navega con teclado no tiene que buscar dónde quedó. */
  volverElFoco = document.activeElement;
  const cuerpo = document.getElementById('cuerpo');
  if (cuerpo) cuerpo.inert = true;
  $('#visor-cerrar').focus();
  /* Y se abre MIRANDO EL CAMPO, no en la esquina de arriba. Una foja de 1.653 px en
     una ventana de 1.366 entra a medias: abierta en el origen, el campo que se venía
     a leer suele quedar abajo del borde y hay que buscarlo. Peor todavía con el velo,
     que oscurece todo lo que no es el recuadro: sin desplazar, la pantalla entera se
     veía gris y el recuadro no estaba a la vista.

     Se espera a que la imagen cargue: antes de eso no tiene tamaño y no hay a dónde
     desplazarse. */
  const alCampo = () => {
    if (marco.hidden) return;
    // Las dos direcciones: con zoom, un campo del borde derecho queda fuera de la
    // vista aunque esté centrado de arriba abajo. `body.con-visor` tiene el scroll
    // apagado, así que esto mueve la hoja y no la página.
    marco.scrollIntoView({block: 'center', inline: 'center'});
  };
  const alCargar = () => { aplicarZoomVisor(); alCampo(); };
  if (img.complete && img.naturalWidth) alCargar();
  else img.onload = alCargar;
}

/* La misma foja a pantalla completa, pero pedida por ARCHIVO y no por documento.
   Un expediente de obra no produce ningún documento —no hay adentro un formulario que
   extraer—, así que pedir su foja 77 por documento no se puede. Sin esto, la pantalla
   donde por fin se ve un expediente no podría abrir una sola de sus fojas, que es lo
   único que sirve de un expediente: mirar el papel. */
function abrirFojaSuelta(sha, nro, rotulo) {
  aplicarZoomVisor(); const visor = $('#visor'), img = $('#visor-img'), marco = $('#visor-marco');
  if (!visor || !sha || !nro) return;
  img.src = `/pagina?sha=${encodeURIComponent(sha)}&nro=${nro}`;
  $('#visor-rotulo').textContent = [rotulo || 'expediente', 'f. ' + nro].join(' · ');
  // Sin campo no hay recuadro que dibujar: acá se abre la foja entera, no un dato.
  marco.hidden = true;
  visor.hidden = false;
  document.body.classList.add('con-visor');
  volverElFoco = document.activeElement;
  const cuerpo = document.getElementById('cuerpo');
  if (cuerpo) cuerpo.inert = true;
  $('#visor-cerrar').focus();
}

let volverElFoco = null;

function cerrarVisor() {
  const visor = $('#visor');
  if (!visor || visor.hidden) return;
  visor.hidden = true;
  document.body.classList.remove('con-visor');
  const cuerpo = document.getElementById('cuerpo');
  if (cuerpo) cuerpo.inert = false;
  if (volverElFoco && document.contains(volverElFoco)) volverElFoco.focus();
  volverElFoco = null;
  // Al volver, el campo ya fue mirado: los controles se encienden solos. Fuera de la
  // cola no hay nada que encender, y `vigilarVista` sale sola si no está la lupa.
  const f = colaEstado.filas[colaEstado.foco];
  if (f) vigilarVista(f);
}

/* El visor se engancha una sola vez, al cargar, y no adentro de una vista: lo abren
   la cola Y la pantalla del documento, y enganchado adentro de `vCola` el botón de
   cerrar no hacía nada en la otra —quedaba sólo `Esc`, que es un atajo y no una
   salida—. */
(function engancharVisor() {
  const visor = document.getElementById('visor');
  if (!visor) return;
  document.getElementById('visor-cerrar').onclick = cerrarVisor;
  visor.onclick = e => { if (e.target.id === 'visor') cerrarVisor(); };
})();

/* Encuadra el campo en la lupa: la foja entera a la derecha se ve chica, y lo que hace
   falta para decidir es leer ESE renglón. */
/* ── ¿Este recuadro sirve para mirar? ──────────────────────────────────────
   Que el campo tenga coordenadas no quiere decir que se pueda ver. Con material real
   —no con el corpus sintético, donde todas las cajas salen bien— aparecen tres cosas
   que pasan el control de «tiene anclaje» y dejan al operador decidiendo sobre nada:

     · la caja DEGENERADA, con x1 y x0 casi iguales. Es lo que devuelve el
       reconocimiento cuando no logró delimitar un manuscrito. El código de antes la
       estiraba a 8 puntos con un `Math.max`, la ampliación se iba al tope, y en la
       lupa entraban dos letras sueltas contra el borde;
     · la caja ENORME, del tamaño de media hoja. La ampliación se desploma y entra la
       página entera, ilegible, del tamaño de una estampilla;
     · la caja FUERA DE LA HOJA. Si las coordenadas no están en la misma unidad que
       `ancho_pt` para ese escaneo, el encuadre se corre entero aunque la caja esté
       perfectamente bien medida. Se nota porque la caja cae afuera del papel.

   Las tres se tratan igual y como lo que son: no hay recorte. Cae en `sin-anclaje`,
   que ya está resuelto —apaga los botones, dice por qué, y muestra la hoja entera
   para poder cargarlo a mano—. El guardián «no se decide sin ver» verificaba que el
   recorte EXISTIERA; esto verifica que SIRVA, que es lo que hacía falta.

   Los números salen en el motivo a propósito: si alguna vez esto rechaza una caja que
   estaba bien, quien lo vea puede decir exactamente cuál era. */
const CAJA_MINIMA = {ancho: 8, alto: 5};   // puntos; menos que esto no es un renglón
const CAJA_MAXIMA_HOJA = 0.5;              // más de media hoja no es un campo
const CAJA_MAS_ALTA_QUE_ANCHA = 4;         // un renglón de texto no es una torre

function cajaUtil(f, pag) {
  const w = f.x1 - f.x0, h = f.y1 - f.y0;
  const medidas = `${Math.round(w)}×${Math.round(h)} pt en una hoja de ` +
                  `${Math.round(pag.ancho_pt)}×${Math.round(pag.alto_pt)}`;
  if (!(w > 0) || !(h > 0) || w < CAJA_MINIMA.ancho || h < CAJA_MINIMA.alto) {
    return `el recuadro del campo quedó demasiado chico para mostrarlo (${medidas})`;
  }
  if (h > w * CAJA_MAS_ALTA_QUE_ANCHA) {
    return `el recuadro del campo tiene una forma imposible para un renglón (${medidas})`;
  }
  if (pag.ancho_pt && pag.alto_pt &&
      w * h > CAJA_MAXIMA_HOJA * pag.ancho_pt * pag.alto_pt) {
    return `el recuadro del campo abarca media hoja: no señala nada (${medidas})`;
  }
  // Fuera del papel. Con media línea de tolerancia, porque un recuadro pegado al
  // margen puede pasarse por redondeo y eso no es un error.
  const fuera = f.x0 < -2 || f.y0 < -2 ||
                (pag.ancho_pt && f.x1 > pag.ancho_pt + 2) ||
                (pag.alto_pt && f.y1 > pag.alto_pt + 2);
  if (fuera) {
    return `el recuadro del campo cae afuera de la hoja (${medidas})`;
  }
  return '';
}

/* Cuando no hay recorte que sirva: la hoja entera, los botones apagados y el motivo.
   Es el mismo camino para «el sistema no encontró el campo» y para «lo encontró pero
   lo que marcó no se puede mirar»: desde donde está el operador son la misma cosa. */
function sinRecorte(f, motivo, comoSeguir) {
  const lupa = $('#lupa'), img = $('#lupa-img');
  lupa.classList.add('sin-anclaje');
  img.removeAttribute('src');
  const marco = $('#lupa-marco');
  if (marco) marco.hidden = true;
  $('#lupa-campo').textContent = motivo;
  $('#lupa-xy').textContent = comoSeguir;
  // La hoja entera SÍ va: es lo único con lo que se puede encontrar el campo a mano,
  // que es lo que el cartel de arriba está pidiendo que se haga.
  const resp = f.pagina_respaldo;
  const hoja = $('#lienzo-cola'), folio0 = $('#folio-cola'), rec0 = $('#recuadro-cola');
  rec0.style.display = 'none';
  // Si el campo dice de qué foja salió, se muestra ESA. El respaldo —la primera del
  // documento— es para cuando no hay ni eso.
  const nro = f.pagina_nro || (resp && resp.nro);
  if (nro) {
    const src0 = `/pagina?doc=${f.documento_id}&nro=${nro}`;
    if (folio0.getAttribute('src') !== src0) folio0.src = src0;
    hoja.hidden = false;
  } else {
    folio0.removeAttribute('src');
    hoja.hidden = true;
  }
  vigilarVista(f);
}

/* Encuadra el campo en la lupa: la foja entera a la derecha se ve chica, y lo que hace
   falta para decidir es leer ESE renglón. */
function encuadrar(f) {
  const lupa = $('#lupa'), img = $('#lupa-img');
  if (!lupa || !img) return;
  const pag = f.pagina;
  if (!pag || f.x0 == null || f.x1 == null) {
    return sinRecorte(f, 'el sistema no encontró este campo en la foja',
                      'mirá el folio y cargalo a mano');
  }
  const roto = cajaUtil(f, pag);
  if (roto) {
    return sinRecorte(f, roto, 'mirá el folio entero y cargalo a mano');
  }

  lupa.classList.remove('sin-anclaje');
  const src = `/pagina?doc=${f.documento_id}&nro=${f.pagina_nro}`;
  if (img.getAttribute('src') !== src) img.src = src;

  /* La hoja entera se apaga ACÁ, ANTES de medir la lupa, y no al final. Con recorte no
     hace falta —el anclaje lo dice el pie, foja y aumento, y una página de 250 px en la
     que no se lee una palabra sólo ocupa lugar—, pero el orden importa: la lupa es
     `flex:1 1 0` y crece cuando la hoja se va. Apagándola después, `r` quedaba medido
     sobre la lupa chica y todo lo que sale de `r` quedaba mal.
     Medido en 1366 con un campo de verdad: la lupa medía 176 px cuando se hizo la
     cuenta y 383 cuando terminó de acomodarse, así que el importe quedaba a 73 px del
     borde de arriba y a 280 del de abajo. Centrado en el ancho —que no cambia— y
     pegado arriba en el alto. Con el orden dado vuelta, la cuenta se hace sobre el
     tamaño final. */
  $('#lienzo-cola').hidden = true;
  /* Y el pie también se escribe antes de medir, por lo mismo: «Monto mensual · ruta
     …» ocupa dos renglones donde «Monto mensual» ocupa uno, y ese renglón sale del
     alto de la lupa. Eran los 25 px que faltaban para que el centrado cerrara. */
  $('#lupa-campo').textContent = `${rotularCampo(f.campo, f.familia)}${
    f.ruta ? ' · ruta ' + f.ruta : ''}`;

  const caja = {w: f.x1 - f.x0, h: f.y1 - f.y0};
  const r = lupa.getBoundingClientRect();
  const aire = 1.5;
  // px mostrados por punto. Con techo, para no ampliar más allá de lo que el escaneo
  // tiene adentro, y con PISO: mostrar el renglón más chico que el propio escaneo es
  // dar por bueno que no se lea. Si con el piso no entra, se desborda y se ve el
  // principio —la lupa recorta— en vez de encogerse hasta la ilegibilidad.
  const natural = 200 / 72;                    // px por punto del escaneo (DPI_RENDER)
  const cabe = Math.min(r.width / (caja.w * aire), r.height / (caja.h * aire * 2.2));
  const escala = Math.max(Math.min(cabe, natural * 2.5), natural);
  img.style.width = (pag.ancho_pt * escala) + 'px';
  img.style.left = -(f.x0 * escala - (r.width - caja.w * escala) / 2) + 'px';
  img.style.top = -(f.y0 * escala - (r.height - caja.h * escala) / 2) + 'px';
  // Y el recuadro encima, en el lugar donde quedó el campo. Como el encuadre lo
  // CENTRA, el recuadro sale de la misma cuenta que centró la imagen: siempre coincide,
  // sin volver a medir nada.
  const marco = $('#lupa-marco');
  if (marco) {
    marco.hidden = false;
    marco.style.left = ((r.width - caja.w * escala) / 2) + 'px';
    marco.style.top = ((r.height - caja.h * escala) / 2) + 'px';
    marco.style.width = (caja.w * escala) + 'px';
    marco.style.height = (caja.h * escala) + 'px';
  }
  $('#lupa-xy').textContent = `f.${f.pagina_nro} · ${(escala / natural).toFixed(1)}×`;

  vigilarVista(f);
}

function pintarFoco() {
  const filas = vista.querySelectorAll('.fila');
  if (!filas.length) return;
  colaEstado.foco = Math.max(0, Math.min(colaEstado.foco, filas.length - 1));
  filas.forEach((f, i) => f.classList.toggle('foco', i === colaEstado.foco));
  // En modo ficha no se desplaza nada: hay UN campo en pantalla y arriba de él está el
  // recorte. Traer la fila «a la vista» empujaba el recorte fuera de la pantalla, que
  // es exactamente lo que este modo existe para impedir.
  if (!enFicha()) filas[colaEstado.foco].scrollIntoView({block: 'nearest'});
  const actual = colaEstado.filas[colaEstado.foco];
  if (actual && location.hash !== '#/cola/' + actual.campo_id) {
    history.replaceState(null, '', '#/cola/' + actual.campo_id);
  }
  const f = colaEstado.filas[colaEstado.foco];
  if (f) {
    encuadrar(f);
    const ir = $('#ir-doc');
    if (ir) ir.href = '#/documento/' + f.documento_id;
    const abrir = $('#abrir-foja');
    if (abrir) {
      abrir.disabled = !fojaDe(f);
      abrir.title = fojaDe(f) ? '' : 'este campo no tiene foja escaneada';
    }
    // De dónde sale: documento, foja y campo, en una línea y en mono.
    const proc = $('#ficha-procedencia');
    // El NOMBRE DEL ARCHIVO va primero, y no la familia. La familia es «Contrato» en
    // las cuarenta y dos filas de la cola: no distingue nada. Lo que distingue es de
    // qué papel salió esto, y sin eso dos campos del mismo tipo se ven idénticos —tres
    // contratos de la misma persona con el mismo importe son tres pantallas iguales— y
    // parece que el sistema muestra el mismo campo una y otra vez.
    if (proc) proc.textContent = [f.archivo || 'Documento',
                                  f.pagina_nro != null ? 'f. ' + f.pagina_nro : '',
                                  rotularCampo(f.campo, f.familia)]
                                 .filter(Boolean).join(' · ');
    const donde = $('#ficha-donde');
    if (donde) donde.textContent = `Campo ${fmtNum.format(colaEstado.foco + 1)} de ${
      fmtNum.format(colaEstado.total || colaEstado.filas.length)}`;
  }
  // Dónde estás. «Cola de revisión» sin número no dice si faltan tres o trescientos, y
  // sin saber eso nadie puede decidir si lo termina hoy.
  // Dónde estás sobre el TOTAL, no sobre lo que llegó. «1 de 400» con 3.892 campos
  // esperando no es una imprecisión: es esconder tres mil cuatrocientos noventa y dos
  // campos de trabajo, y quien termine los 400 va a creer que el legajo está listo.
  // La posición vive en el renglón de avance, que es uno solo y dice las dos cosas.
  pintarAvance();
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
  // No se decide sin ver. El botón ya sale `disabled`, pero una tecla, un lector de
  // pantalla o un `click()` disparado por otro lado no pasan por el botón: la regla
  // se cumple también acá, que es por donde pasan todos los caminos.
  if (!hayQueMirar) return;
  // Se pide el nombre ANTES de tocar nada. Preguntarlo después sería perder la
  // decisión que la persona acaba de tomar, y el servidor la rechaza igual sin él.
  const quien = await conRevisor();
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
    // El campo que salió de la cola entró en el trabajo hecho, y lo hizo esta persona.
    // Se anota acá, con lo que la pantalla ya sabe: pedirle la cola de nuevo al
    // servidor para mover una barra tiraría las páginas ya traídas y volvería arriba.
    colaEstado.revisados = (colaEstado.revisados || 0) + 1;
    const mio = (colaEstado.revisores || []).find(x => x.quien === quien);
    if (mio) mio.n += 1;
    else (colaEstado.revisores = colaEstado.revisores || []).push({quien, n: 1});
    colaEstado.foco = Math.min(posicion, Math.max(0, colaEstado.filas.length - 1));
    pintarFoco();
    pintarAvance();
    mostrarDeshacer();
    refrescarCuentas();
  } catch (e) {
    if (e.estado === 409) {
      // No es un error de quien apretó: el mundo cambió abajo. Se recarga la cola para
      // que vea cómo quedó, y recién ahí decide de nuevo.
      toast(e.message);
      await vCola(); pintarFoco(); refrescarCuentas();
      return;
    }
    toast('No se pudo guardar: ' + e.message);
  }
}

/* Saca una fila de la cola, en la pantalla y en la cuenta. Renumera las que quedan:
   `data-i` es la posición, y si no se renumeran, la fila de abajo responde por el
   índice de la que se fue y se decide sobre el campo equivocado. */
function sacarDeLaCola(campoId) {
  const i = colaEstado.filas.findIndex(f => String(f.campo_id) === String(campoId));
  if (i < 0) return;
  colaEstado.filas.splice(i, 1);
  // También sale de la lista del servidor, así que la posición desde la que hay que
  // pedir la página siguiente retrocede una. Sin esto se saltearía un campo por cada
  // decisión tomada, y son campos que nadie volvería a ver.
  colaEstado.traidas = Math.max(0, (colaEstado.traidas || 0) - 1);
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
    } catch (e) { toast('No se pudo deshacer: ' + e.message); }
  };
}

/* ── Buscar con «/» ────────────────────────────────────────────────────────
   La cola de revisión tiene teclas para decidir y la búsqueda —que es la acción
   principal de todo el sistema— no tenía ninguna. `/` la enfoca desde cualquier
   pantalla y `Esc` sale; la tecla está dicha en el propio campo, porque un atajo que
   no está escrito en ningún lado lo usa quien lo escribió y nadie más.

   No se dispara si ya se está escribiendo en algún lado: dentro de un campo, «/» es
   una barra y tiene que seguir siéndolo. */
document.addEventListener('focusin', e => {
  if (e.target.tagName === 'TR' && e.target.classList.contains('clic')) e.target.setAttribute('aria-selected', 'true');
});
document.addEventListener('focusout', e => {
  if (e.target.tagName === 'TR' && e.target.classList.contains('clic')) e.target.setAttribute('aria-selected', 'false');
});

document.addEventListener('keydown', e => {
  // El visor primero: mientras la foja está abierta a pantalla completa, `Esc` la
  // cierra y ninguna otra tecla decide nada.
  if (!$('#visor')?.hidden) {
    if (e.key === 'Escape') { e.preventDefault(); cerrarVisor(); }
    return;
  }
  const enUnCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)
    || document.activeElement?.isContentEditable;
  
  if (!enUnCampo) {
    if (e.key === 'Enter' || e.key === ' ') {
      const tr = e.target.closest('tr.clic');
      if (tr) { e.preventDefault(); tr.click(); return; }
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const tr = e.target.closest('tr.clic');
      if (tr) {
        e.preventDefault();
        const filas = Array.from(tr.closest('tbody').querySelectorAll('tr.clic'));
        const next = filas[filas.indexOf(tr) + (e.key === 'ArrowDown' ? 1 : -1)];
        if (next) next.focus();
        return;
      }
    }
  }

  if (e.key === '/' && !enUnCampo && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const q = $('#q-rapida');
    if (q) { e.preventDefault(); q.focus(); q.select(); }
    return;
  }
  if (e.key === 'Escape' && document.activeElement === $('#q-rapida')) {
    $('#q-rapida').blur();
    return;
  }
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
  const hash = location.hash, fus = await api('/api/fusiones');
  if (hash !== location.hash) return;
  const ausente = (motivo) => `<span class="nulo" title="${esc(motivo)}">—</span>`;

  vista.innerHTML = bloque('f. 0007', 'Identidad', `
    <div class="cabecera-seccion">
      <h2>¿Son la misma persona?</h2>
      <p class="prosa">CUIT, CUIL y DNI son clave fuerte: dos contratos con el mismo documento
        ya están unidos. <strong>El nombre nunca alcanza.</strong> Estas propuestas requieren
        confirmación humana, ya que una fusión errónea inventa una persona con el doble de contratos.</p>
    </div>
    
    <div class="cola-tarjetas">
      ${fus.length ? fus.map((f, i) => `
      <div class="tarjeta-fusion" data-i="${i}">
        <div class="fusion-cabecera">
          <span class="rotulo">${esc(f.motivo)}</span>
          <span class="confianza" title="Nivel de coincidencia algorítmica">${(f.score * 100).toFixed(0)}% coincidencia</span>
        </div>
        <div class="fusion-cuerpo mono">
          <div class="fusion-entidad">
            <strong>${esc(f.lit_a)}</strong>
            <span class="apagado">${f.doc_a ? esc(f.doc_a) : ausente('Sin documento')}</span>
          </div>
          <div class="fusion-vs">vs</div>
          <div class="fusion-entidad">
            <strong>${esc(f.lit_b)}</strong>
            <span class="apagado">${f.doc_b ? esc(f.doc_b) : ausente('Sin documento')}</span>
          </div>
        </div>
        <div class="fusion-acciones">
          <button class="boton primario" data-fus="${f.id}" data-ok="1">Son la misma persona</button>
          <button class="boton gris" data-fus="${f.id}" data-ok="0">Son distintas</button>
        </div>
      </div>`).join('') : '<div class="vacio">No hay fusiones pendientes para revisar.</div>'}
    </div>
  `);

  vista.querySelectorAll('[data-fus]').forEach(b => b.onclick = async () => {
    const quien = await conRevisor(); if (!quien) return;
    try {
      await api('/api/fusion', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id:+b.dataset.fus, aceptar: b.dataset.ok === '1', quien})});
      await vIdentidad(); refrescarCuentas();
    } catch (e) { toast('No se pudo guardar: ' + e.message); }
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
    <div class="aviso">${sello('atencion', 'Hipótesis del sistema')}
      <span>Nada de esta pantalla se leyó de un documento. Son hipótesis y patrones que el
      sistema arma cruzando los datos. <strong>Pueden estar equivocados.</strong> Cada
      afirmación linkea a los documentos que la sostienen: chequealos antes de usarla.</span></div>
    ${Object.entries(porClase).map(([clase, its]) => `
      <h3>${esc(CLASE_INTERP[clase] || clase)} <span class="rotulo">${fmtNum.format(its.length)}</span></h3>
      ${its.map(interpHTML).join('')}`).join('') || '<div class="vacio">Sin interpretaciones.</div>'}
    <div class="sep-corta"><button class="boton" id="b-regen">Volver a generar</button></div>`);
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
    <div class="fila-suelta abajo">
      ${cat.map(c => `<a class="chip${c.id === activa ? ' activa' : ''}"
        href="#/consultas/${c.id}">${esc(c.id)}</a>`).join('')}
    </div>
    ${r ? `<pre class="sql">${esc(r.sql.trim())}</pre>
      <p class="prosa nota sep-corta">${esc(r.ruta)} · ${r.n} filas</p>
      ${tabla(r.columnas.map(c => ({t:c, k:c, c: /centavos|dias|total|_id|^n$/.test(c) ? 'num' : ''})), r.filas)}`
    : ''}`);
}



/* ── Búsqueda ──────────────────────────────────────────────────────────── */
function resaltar(fragmento) {
  return esc(fragmento).replace(/\[\[/g, '<mark>').replace(/\]\]/g, '</mark>');
}

async function vBuscar(q) {
  q = q ? decodeURIComponent(q) : '';
  const hash = location.hash;
  let r = q ? await api('/api/buscar?q=' + encodeURIComponent(q) + '&limite=60&desde=0') : null;
  if (hash !== location.hash) return;
  /* Sin nada escrito, la pantalla dice qué busca y cómo buscar mejor, en vez de un
     renglón que pide escribir algo. */
  const estadoVacio = `
    <div class="vacio-ilustrado">
      <h3>Qué busca</h3>
      <p>El texto leído de todas las fojas y los datos extraídos: nombres, CUIT, montos,
        números de expediente, de orden de compra o de factura.</p>
      <ul>
        <li>Una palabra dice más que una frase: el OCR corta renglones.</li>
        <li>Los acentos no importan: «benitez» encuentra «BENÍTEZ».</li>
        <li>Un CUIT se encuentra con o sin guiones.</li>
        <li>Lo que no se leyó todavía no se puede encontrar: abajo de cada búsqueda se
          dice sobre cuántas fojas se buscó.</li>
      </ul>
    </div>`;
  vista.innerHTML = bloque('f. 0010', 'Buscar', `<h2>Buscar en el corpus</h2>
    <form id="f-buscar" class="fila-suelta buscar-form"><label class="campo-buscar"><input id="q" type="search" value="${esc(q)}" autocomplete="off" placeholder="Nombre, CUIT, monto, expediente…" aria-label="Buscar"></label><button class="boton">Buscar</button></form>
    ${r ? '<button class="boton gris" id="guardar-busqueda">Guardar como consulta</button>' : ''}
    <div id="resultados-busqueda" aria-live="polite"></div>`);
  $('#f-buscar').onsubmit = e => { e.preventDefault(); location.hash = '#/buscar/' + encodeURIComponent($('#q').value.trim()); };
  const pintar = () => {
    const host = $('#resultados-busqueda');
    host.innerHTML = r ? resultadosHTML(r) + (r.hay_mas ? '<button class="boton" id="mas-busqueda">Traer la p\u00e1gina siguiente</button>' : '') : estadoVacio;
    host.querySelectorAll('tr[data-i]').forEach(tr => tr.onclick = () => { location.hash = '#/documento/' + r.campos[Number(tr.dataset.i)].documento_id; });
    host.querySelectorAll('[data-apartar]').forEach(b => b.onclick = e => { e.stopPropagation(); accionInterfaz(b, () => apartarResultado(b.dataset.apartar, b.dataset.referencia)); });
    const mas = $('#mas-busqueda'); if (mas) mas.onclick = () => accionInterfaz(mas, async () => {
      const siguiente = await api('/api/buscar?q=' + encodeURIComponent(q) + '&limite=' + r.limite + '&desde=' + (r.desde + r.limite));
      if (hash !== location.hash) return;
      r = acumularBusqueda(r, siguiente); pintar();
    });
  };
  pintar();
  const guardar = $('#guardar-busqueda'); if (guardar) guardar.onclick = () => {
    const d = dialogo(`<h3>Guardar consulta</h3><p>Se volver\u00e1 a buscar: los resultados cambian con los datos.</p><form><label>Nombre <input name="nombre" required></label><button class="boton">Guardar</button></form><button class="boton gris" data-cerrar>Cancelar</button>`);
    d.querySelector('[data-cerrar]').onclick = () => d.close();
    const f = d.querySelector('form'); f.onsubmit = e => { e.preventDefault(); accionInterfaz(f.querySelector('button'), async () => {
      const quien = await conRevisor(); if (!quien) return;
      await guardarNucleo('/api/consulta/guardar', {nombre:f.elements.nombre.value.trim(), consulta:q, filtros:{}, quien}); d.close();
    }); };
  };
  if (!q) $('#q').focus();
}

/* ── Sobre cuánto se buscó ─────────────────────────────────────────────────
   Ésta era la única pantalla del sistema que afirmaba una ausencia sin haberla
   verificado. «Sin coincidencias» se leía como «esta palabra no está en el legajo»,
   cuando lo único cierto era «no está en las fojas que el sistema pudo leer».

   Va SIEMPRE, haya resultados o no. Mostrarla sólo en el caso vacío es el mismo
   error con otra ropa: cuatro coincidencias sobre 241 fojas leídas de 260 tampoco es
   lo mismo que cuatro sobre 260. */
function coberturaHTML(c, hallazgos) {
  if (!c || !c.fojas) return '';
  const sobre = `<strong>${fmtNum.format(c.indexadas)}</strong> `
    + (c.indexadas === 1 ? 'foja con lectura utilizable' : 'fojas con lectura utilizable');
  if (!c.fuera) {
    return `<p class="cobertura">${hallazgos} sobre ${sobre}: el sistema pudo leer
      todo lo que hay cargado.</p>`;
  }
  // Dos motivos distintos y dos remedios distintos: la que nunca se procesó se
  // arregla corriendo el proceso; la que se procesó y no dio texto hay que mirarla
  // contra el papel. Decir «ilegibles» de las dos sería inventar sobre las primeras.
  // Concuerdan en número. «1 que se procesaron» se nota, y este es un sistema que
  // tiene un módulo entero de castellano para no escribir así.
  const detalle = [];
  if (c.sin_texto) detalle.push(`${fmtNum.format(c.sin_texto)} que se
    ${c.sin_texto === 1 ? 'procesó' : 'procesaron'} sin sacar texto utilizable`);
  if (c.sin_procesar) detalle.push(`${fmtNum.format(c.sin_procesar)} que todavía no se
    ${c.sin_procesar === 1 ? 'procesó' : 'procesaron'}`);
  return `<p class="cobertura falta">${hallazgos} sobre ${sobre}.
    <strong>${plural(c.fuera, 'foja quedó', 'fojas quedaron')} fuera de esta
    búsqueda</strong>${detalle.length ? ` — ${detalle.join(' y ')}` : ''}.
    <a href="#/afuera">Ver cuáles</a>.</p>`;
}

function resultadosHTML(r) {
  /* La misma foja llegaba varias veces —una por cada ruta de lectura que encontró la
     palabra— con el mismo fragmento: diez renglones iguales seguidos. Una por foja y
     fragmento. */
  const vistas = new Set();
  r = {...r, paginas: (r.paginas || []).filter(p => {
    const k = `${p.sha256}:${p.nro}:${String(p.fragmento || '').replace(/\s+/g, ' ').trim()}`;
    if (vistas.has(k)) return false;
    vistas.add(k); return true;
  })};
  if (r.aviso) return `<div class="aviso"><span class="sello alerta">Atención</span>
    <span>${esc(r.aviso)}</span></div>`;
  const total = (r.campos_total ?? r.campos.length) + (r.paginas_total ?? r.paginas.length);
  const mostrados = r.campos.length + r.paginas.length;
  const hallazgos = total
    ? (mostrados < total ? `Se están mostrando <strong>${fmtNum.format(mostrados)}</strong> de <strong>${plural(total, 'coincidencia', 'coincidencias')}</strong>` : `Hay <strong>${plural(total, 'coincidencia', 'coincidencias')}</strong>`)
    : `<strong>No aparece</strong>`;
  const cob = htmlResumenBusqueda(r) + coberturaHTML(r.cobertura, hallazgos);
  const nada = !r.campos.length && !r.paginas.length;
  // Nunca «Sin coincidencias» a secas. Lo que se puede afirmar es dónde se buscó.
  if (nada) return cob || `<div class="vacio">Sin coincidencias para
    «${esc(r.consulta)}».</div>`;
  return `${cob}
    ${r.campos.length ? `
      <h3>En los datos extraídos <span class="rotulo">(${r.campos.length})</span></h3>
      <p class="prosa nota">Son <strong>datos extra\u00eddos</strong>: el dato ya
        está leído y anclado.</p>
      ${tabla([
        {t:'Apartar', r:f => `<button class="mini" data-apartar="documento" data-referencia="${esc(f.documento_id)}">Apartar en colecci\u00f3n</button>`},
        {t:'Archivo', k:'archivo', c:'fol'},
        {t:'Campo', k:'campo'},
        {t:'Valor leído', c:'mono', r:f => esc(f.valor_literal)},
        {t:'Nombre', c:'nombre', r:f => f.nombre_literal ? esc(f.nombre_literal) : ausente('no_consta')},
        {t:'Período', c:'mono', r:f => f.inicio
            ? `${esc(fmtFecha(f.inicio))} → ${f.fin ? esc(fmtFecha(f.fin)) : '?'}` : '—'},
        {t:'Monto', c:'num', r:f => f.monto_centavos == null ? '—' : esc(fmtPesos(f.monto_centavos))},
      ], r.campos, {alClic:true})}` : ''}
    ${r.paginas.length ? `
      <h3>En el texto de los folios <span class="rotulo">(${r.paginas.length})</span></h3>
      <p class="prosa nota">Esto son <strong>lugares donde mirar</strong>:
        apareció en la página, sin que sea un campo extraído.</p>
      <ol class="res-fojas">${r.paginas.map(p => `
        <li class="res-foja">
          <span class="res-donde">${p.documento_id
            ? `<a href="#/documento/${esc(p.documento_id)}">${esc(String(p.archivo || '').replace(/\.pdf$/i, ''))} · f. ${esc(String(p.nro))}</a>`
            : `${esc(String(p.archivo || '').replace(/\.pdf$/i, ''))} · f. ${esc(String(p.nro))}`}</span>
          <span class="res-frag">${resaltar(p.fragmento)}</span>
          <button class="boton secundario res-apartar" data-apartar="foja" data-referencia="${esc(p.sha256)}:${esc(p.nro)}"
            title="Apartar esta foja en una colección">Apartar</button>
        </li>`).join('')}</ol>` : ''}`;
}

/* ── Personas ──────────────────────────────────────────────────────────── */
async function vPersonas() {
  // /api/documentos es la lista de personas agrupadas por documento; viene paginada.
  const cuenta = await api('/api/documentos?limite=1');
  if (location.hash.split('?')[0] !== '#/personas') return;
  if (!cuenta || !cuenta.total) {
    return vistaVacia('f. 0011', 'Personas', 'Personas',
      'Todavía no hay personas identificadas',
      'Las personas se arman al procesar un lote: los documentos con el mismo CUIL o DNI se agrupan solos.');
  }
  vista.innerHTML = bloque('f. 0011', 'Personas', `
    <h1>Personas</h1>
    <p class="prosa">Agrupadas por documento cuando lo hay. <strong>Las que no tienen documento
      legible aparecen sueltas</strong>: el nombre solo nunca alcanza para decir que dos son la
      misma persona.</p>
    <div id="tabla-personas"></div>`);
  tablaServidor($('#tabla-personas'), '/api/documentos', 'personas', [
    {t: 'Nombre', c: 'crece', o: 'nombre', r: f => f.contratado ? esc(f.contratado) : ausente('no_consta')},
    {t: 'Documento', c: 'fol', r: f => f.documento ? esc(f.documento) : ausente('no_consta')},
    {t: 'Contratos', c: 'num', r: f => fmtNum.format(f.contratos || 0)},
    {t: 'Acumulado firme', c: 'num', o: 'monto', r: f => f.acumulado_centavos == null
        ? ausente('no_consta') : esc(fmtPesos(f.acumulado_centavos))},
  ], {orden: 'monto', sentido: 'desc', placeholder: 'Buscar por nombre o documento…',
      alClic: f => { location.hash = '#/persona/' + f.persona_id; },
      vacio: 'No hay personas que coincidan.'});
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
  const hash = location.hash;
  if (hash !== location.hash) return;
  const t = d.totales;
  const nombre = d.alias[0] ? d.alias[0].nombre_literal : '—';
  const otros = d.alias.slice(1);
  const ausente = (motivo) => `<span class="nulo" title="${esc(motivo)}">—</span>`;

  vista.innerHTML = bloque('f. ' + String(id).padStart(4,'0'), 'Persona', `
    <div class="cabecera-ficha">
      <h2>${esc(nombre) !== '—' ? esc(nombre) : ausente('Sin nombre legible')}</h2>
      <div class="identificadores">
        <span class="mono">${d.persona.clave_fuerte ? `${esc(d.persona.doc_tipo)} ${esc(d.persona.doc_numero)}` : ausente('Sin documento legible')}</span>
      </div>
    </div>
    
    <p class="prosa nota">
      ${d.persona.clave_fuerte
        ? `Los contratos se agruparon por esta clave fuerte.`
        : `Este contratado no se agrupó con ningún otro porque el nombre solo nunca alcanza para garantizar identidad.`}
      ${otros.length ? `<br>También aparece escrito como: ${otros.map(o =>
        `<span class="mono">${esc(o.nombre_literal)}</span>`).join(', ')}.` : ''}
    </p>

    <div class="cifras sep-corta">
      <div class="cifra"><b>${t.contratos}</b><span>contratos</span></div>
      <div class="cifra"><b>${t.acumulado_centavos != null ? esc(fmtPesos(t.acumulado_centavos)) : ausente('No hay montos')}</b><span>mensual acumulado</span></div>
      <div class="cifra ${d.solapes.length ? 'alerta' : ''}"><b>${d.solapes.length}</b><span>superposiciones</span></div>
      <div class="cifra"><b>${t.camaras && t.camaras.length ? esc(t.camaras.map(camaraTexto).join(' + ')) : ausente('Sin cámara')}</b><span>cámaras</span></div>
      <div class="cifra ${t.sin_monto ? 'alerta' : ''}"><b>${t.sin_monto}</b><span>sin monto legible</span></div>
    </div>
    
    ${t.sin_monto || t.sin_fechas ? `<p class="prosa nota">
      El acumulado suma sólo los contratos con monto firme: hay ${t.sin_monto} sin monto y
      ${t.sin_fechas} sin fechas completas. <strong>Es un piso, no un total.</strong></p>` : ''}
    
    ${t.comprobantes ? `
    <div class="cifras sep-corta">
      <div class="cifra facturado"><b>${t.comprobantes}</b><span>facturas y recibos</span></div>
      <div class="cifra facturado"><b>${t.facturado_centavos != null ? esc(fmtPesos(t.facturado_centavos)) : ausente('Sin importe')}</b><span>facturado legible</span></div>
      ${t.comprobantes_sin_importe ? `<div class="cifra alerta">
        <b>${t.comprobantes_sin_importe}</b><span>importes a mano</span></div>` : ''}
    </div>
    <p class="prosa nota">
      <strong>Lo facturado no se suma con lo contratado.</strong> El mensual acumulado es
      lo que dicen los contratos; lo facturado es lo que cobró. Son la misma plata vista de los dos lados${t.comprobantes_sin_importe
        ? `, y el facturado está incompleto: ${plural(t.comprobantes_sin_importe, 'comprobante trae', 'comprobantes traen')} el importe a mano y no se lee` : ''}.</p>` : ''}

    <h3>Cronología</h3>
    ${cronologia(d.contratos, d.solapes)}

    ${d.solapes.length ? `
      <h3>Períodos que se pisan</h3>
      ${tabla([
        {t:'Folios', c:'fol', r:f => `${esc(f.archivo_a)}<br>${esc(f.archivo_b)}`},
        {t:'Cruce', r:f => f.cruce === 'intercámara' ? `<span class="marca">${esc(f.cruce)}</span>` : esc(f.cruce)},
        {t:'Desde', c:'mono', r:f => f.desde ? esc(fmtFecha(f.desde)) : ausente('Falta inicio')},
        {t:'Hasta', c:'mono', r:f => f.hasta ? esc(fmtFecha(f.hasta)) : ausente('Falta fin')},
        {t:'Días', k:'dias', c:'num'},
      ], d.solapes)}` : ''}

    <h3>Contratos</h3>
    ${tabla([
      {t:'Archivo', k:'archivo', c:'fol'},
      {t:'Cámara', r:f => f.camara ? esc(camaraTexto(f.camara)) : ausente('Sin cámara')},
      {t:'Cargo', r:f => f.cargo ? esc(f.cargo) : ausente('Sin cargo')},
      {t:'Inicio', c:'mono', r:f => f.inicio ? esc(fmtFecha(f.inicio)) : ausente('Sin inicio')},
      {t:'Fin', c:'mono', r:f => f.fin ? esc(fmtFecha(f.fin)) : ausente('Sin fin')},
      {t:'Monto', c:'num', r:f => f.monto_centavos != null ? esc(fmtPesos(f.monto_centavos)) : ausente('Sin monto')},
      {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
    ], d.contratos, {alClic:true, lista:'contratos'})}

    ${(d.comprobantes || []).length ? `
      <h3>Facturas y recibos</h3>
      <p class="prosa nota">Emitidos con el mismo documento. El CUIL de la factura lleva adentro el DNI del contrato.</p>
      ${tabla([
        {t:'Archivo', k:'archivo', c:'fol'},
        {t:'Tipo', r:f => f.tipo ? esc(TIPO_DOC[f.tipo] || f.tipo) : ausente('Sin tipo')},
        {t:'Comprobante', c:'mono', r:f => f.comprobante ? esc(f.comprobante) : ausente('Sin comprobante')},
        {t:'Emitida', c:'mono', r:f => f.emitida ? esc(fmtFecha(f.emitida)) : ausente('Sin fecha')},
        {t:'Importe', c:'num', r:f => f.monto_centavos != null ? esc(fmtPesos(f.monto_centavos)) : ausente('Importe a mano')},
        {t:'Conf.', c:'num', r:f => barraConf(f.confianza_min)},
      ], d.comprobantes, {alClic:true, lista:'comprobantes'})}` : ''}

    ${d.interpretaciones && d.interpretaciones.length ? `
      <div class="sep">
        <span class="rotulo">Carril de interpretación</span>
        <p class="prosa nota">Nada de esto se leyó de un papel. Son hipótesis cruzando datos y pueden estar mal.</p>
        ${d.interpretaciones.map(interpHTML).join('')}
      </div>` : ''}
  `);

  vista.querySelectorAll('table[data-lista]').forEach(tabla => {
    const filas = tabla.dataset.lista === 'contratos' ? d.contratos : d.comprobantes;
    tabla.querySelectorAll('tbody tr').forEach(tr =>
      tr.onclick = () => location.hash = '#/documento/' + filas[+tr.dataset.i].documento_id);
  });
}


/* ── Carga de escaneos ─────────────────────────────────────────────────── */
let subiendo = false;

/* En qué está cada archivo. Los cuatro estados salen de comparar tres números —fojas,
   leídas, clasificadas— y están dichos por lo que FALTA, no por lo que hay: un archivo
   con ochenta fojas leídas y ocho sin leer está a medio leer, no leído. */
const ESTADO_CARGA = {
  // Sin leer es trabajo pendiente —ámbar, atención—; a medio leer es una falla —algo
  // cortó el procesamiento— y por eso va en punzó. §2: el rojo se gasta si se usa
  // para lo que simplemente falta hacer.
  sin_leer: sello('atencion', 'sin leer'),
  a_medio_leer: sello('alerta', 'a medio leer'),
  sin_extraer: sello('atencion', 'leído, sin extraer'),
  listo: sello('ok', 'listo'),
};

function resumenCarga(ar) {
  const n = ar.archivos.length;
  const r = ar.resumen || {};
  const listos = r.listo || 0;
  if (listos === n) return `<strong>${fmtNum.format(n)}</strong> ${
    n === 1 ? 'archivo' : 'archivos'} · ${fmtNum.format(ar.fojas)} fojas · todo procesado.`;
  const falta = [
    r.sin_leer ? `${fmtNum.format(r.sin_leer)} sin leer` : '',
    r.a_medio_leer ? `<strong>${fmtNum.format(r.a_medio_leer)} a medio leer</strong>` : '',
    r.sin_extraer ? `${fmtNum.format(r.sin_extraer)} leídos sin extraer` : '',
  ].filter(Boolean).join(', ');
  return `<strong>${fmtNum.format(n)}</strong> ${n === 1 ? 'archivo' : 'archivos'} · ${
    fmtNum.format(ar.fojas)} fojas · ${fmtNum.format(listos)} ${
    listos === 1 ? 'listo' : 'listos'}${falta ? ', ' + falta : ''}.`;
}


// El plan es informativo: abrir esta pantalla nunca inicia una actualizacion.

function htmlReasociaciones(revisiones) {
  if (!revisiones.length) return vacio('No hay revisiones desplazadas',
    'No hay decisiones humanas pendientes de reasociar.');
  const dato = v => v == null ? '\u00d8 Sin registrar' : esc(v);
  return `<h2>Revisiones desplazadas</h2>
    <p class="prosa">Las decisiones se conservaron sin aplicarlas a una pieza incierta.
    Las candidatas est\u00e1n ordenadas de m\u00e1s a menos plausibles: el sistema no sabe cu\u00e1l corresponde.
    Mir\u00e1 el documento antes de elegir.</p>
    ${revisiones.map((r, i) => `<article class="reasociacion" data-revision="${i}">
      <h3 class="mono">${dato(r.archivo)}</h3>
      <dl><dt>Decisi\u00f3n conservada</dt><dd>${dato(r.accion)} sobre ${esc(String(r.campo).replaceAll('_', ' '))}: ${dato(r.valor)}</dd>
      <dt>Qui\u00e9n y cu\u00e1ndo</dt><dd>${dato(r.quien)} · ${esc(fmtFechaHora(r.cuando))}</dd>
      <dt>D\u00f3nde mir\u00f3</dt><dd>Foja ${dato(r.ancla_pagina)} · ${dato(r.ancla_tipo == null ? null : r.ancla_tipo.replaceAll('_', ' '))}
        · Pieza ${dato(r.orden)} · Fojas ${dato(r.ancla_desde)} a ${dato(r.ancla_hasta)}</dd>
      <dt>Por qu\u00e9 qued\u00f3 pendiente</dt><dd>${dato(r.motivo)}</dd></dl>
      ${r.ancla_pagina != null ? '<button class="boton gris" data-ancla>Ver la foja anclada</button>' : ''}
      ${r.candidatas.length ? `<fieldset><legend>Eleg\u00ed la pieza destinataria</legend>
        ${r.candidatas.map(c => `<div class="reasociacion-candidata"><label>
          <input type="radio" name="pieza-${i}" value="${esc(c.documento_id)}" ${c.tiene_el_campo ? '' : 'disabled'}>
          Pieza ${dato(c.orden)} · ${dato(c.tipo.replaceAll('_', ' '))}
          · Fojas ${dato(c.pagina_desde)} a ${dato(c.pagina_hasta)}</label>
          <p>${esc(c.por_que)}</p><p class="mono">${c.tiene_el_campo
            ? `${dato(c.valor_actual)} · ${esc((ESTADO[c.estado_actual] || [c.estado_actual || 'Sin estado'])[0])}`
            : 'Este campo todav\u00eda no se extrajo en esta pieza.'}</p>
          ${!c.tiene_el_campo ? '<p>Puede ser la pieza correcta. Dejala pendiente hasta que tenga el campo.</p>' : ''}
          <a href="#/documento/${esc(c.documento_id)}" target="_blank" rel="noopener">Ver la pieza en otra pesta\u00f1a</a>
        </div>`).join('')}</fieldset>` : '<p>No hay piezas candidatas disponibles en este archivo.</p>'}
      <p>Descartar no borra la decisi\u00f3n: queda registrada y se puede auditar.
        Dejar pendiente tambi\u00e9n registra qui\u00e9n lo decidi\u00f3.</p>
      <div class="reasociacion-acciones">
        ${r.candidatas.some(c => c.tiene_el_campo) ? '<button class="boton" data-resolver="reasociar" disabled>Reasociar a la pieza elegida</button>' : ''}
        <button class="boton gris descarte" data-resolver="descartar">Descartar la decisi\u00f3n</button>
        <button class="boton gris" data-resolver="pendiente">Dejar pendiente</button>
      </div><p role="status" aria-live="polite" data-resultado></p>
    </article>`).join('')}`;
}


function htmlSinReconocer(piezas, tipos) {
  return `<h2>Todav\u00eda sin reconocer</h2>
    <p class="prosa">Son documentos cargados que el sistema todav\u00eda no sabe leer.
    No son un error ni un descarte: es trabajo pendiente del sistema. Van a poder recibir
    un extractor m\u00e1s adelante sin volver a subir nada. Pod\u00e9s decir qu\u00e9 son;
    el cat\u00e1logo puede ampliarse cuando se incorporen nuevos tipos.</p>
    ${piezas.length ? piezas.map(p => `<form class="nucleo-ficha" data-pieza="${p.documento_id}">
      <h3><a class="mono" href="#/documento/${p.documento_id}">${esc(p.archivo)}</a></h3>
      <p class="mono">Fojas ${esc(p.pagina_desde)} a ${esc(p.pagina_hasta)} (${esc(p.fojas)} fojas)</p>
      <p>Tipo registrado: ${esc(tipos.find(t => t.clave === p.tipo)?.nombre || p.tipo || '\u00d8 Sin clasificar')}
      ${p.clasificado_por ? ` · Lo dijo ${esc(p.clasificado_por)}` : ''}</p>
      <label>Qu\u00e9 es esta pieza <select name="tipo" required>
        <option value="">Eleg\u00ed un tipo despu\u00e9s de mirar la pieza</option>
        ${tipos.map(t => `<option value="${esc(t.clave)}">${esc(t.nombre)} (${esc(t.familia)})</option>`).join('')}
      </select></label><button class="boton" type="submit">Registrar clasificaci\u00f3n</button>
    </form>`).join('') : '<p class="prosa">No hay piezas sin reconocer.</p>'}`;
}

async function guardarNucleo(ruta, cuerpo) {
  return api(ruta, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cuerpo)});
}

async function vSinReconocer() {
  // Sólo interesa el catálogo de tipos: se pide una fila, que es el mínimo que acepta
  // el servidor (con `limite=0` contestaba 400 y la pantalla mostraba un error).
  const d = await api('/api/piezas/sin-reconocer?limite=1');
  if (location.hash !== '#/sin-reconocer') return;
  vista.innerHTML = bloque('f. 0000', 'Revisión', `<h2>Todavía sin reconocer</h2>
    <p class="prosa">Son documentos cargados que el sistema todavía no sabe leer...</p>
    <div id="lista-sin-reconocer"></div>`);
  
  tablaServidor($('#lista-sin-reconocer'), '/api/piezas/sin-reconocer', 'piezas', [
    {t: 'Archivo', o: 'archivo', c: 'mono', r: p => `<a href="#/documento/${p.documento_id}">${esc(p.archivo)}</a>`},
    {t: 'Fojas', o: 'foja', c: 'num', r: p => `${esc(p.pagina_desde)} a ${esc(p.pagina_hasta)} (${esc(p.fojas)})`, b: p => p.fojas},
    {t: 'Tipo registrado', r: p => `${esc(TIPO_DOC[p.tipo] || d.tipos.find(t => t.clave === p.tipo)?.nombre || p.tipo || 'Sin clasificar')} ${p.clasificado_por ? `(por ${esc(p.clasificado_por)})` : ''}`},
    {t: 'Clasificar', r: p => `<form class="fila-acciones" data-pieza="${p.documento_id}"><select name="tipo" required><option value="">Elegí un tipo</option>${d.tipos.map(t => `<option value="${esc(t.clave)}">${esc(TIPO_DOC[t.clave] || t.nombre)}</option>`).join('')}</select> <button class="boton" type="submit">Registrar</button></form>`}
  ], {
    placeholder: 'Buscar archivo...',
    vacio: 'No hay piezas sin reconocer.'
  });

  const contenedor = $('#lista-sin-reconocer');
  if (!contenedor.dataset.binded) {
    contenedor.dataset.binded = '1';
    contenedor.addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.closest('form'); if (!f) return;
      const b = f.querySelector('button'); b.disabled = true;
      try {
        const quien = await conRevisor(); if (!quien) return;
        await guardarNucleo('/api/pieza/clasificar', {documento_id:+f.dataset.pieza, tipo:f.elements.tipo.value, quien});
        await vSinReconocer();
      } catch (err) { toast(err.message); } finally { b.disabled = false; }
    });
  }
}


function opcionesArchivos(archivos) {
  return '<option value="">Eleg\u00ed un archivo</option>' + archivos.map(a =>
    `<option value="${esc(a.sha256)}">${esc(a.nombre)} (${esc(a.paginas)} fojas)</option>`).join('');
}

function htmlContinuidad(tramos, vecino, archivos) {
  return `<h3>Tramos de la pieza</h3><p class="prosa">La continuidad la afirma una persona mirando las fojas.</p>
    <ol>${tramos.map((t, i) => `<li class="nucleo-ficha"><span class="mono">${esc(t.archivo)}:
      fojas ${esc(t.pagina_desde)} a ${esc(t.pagina_hasta)}</span>
      <p>${t.principal ? 'Tramo principal' : `Continuidad afirmada por ${esc(t.quien)}`}</p>
      <button class="boton gris" data-mirar-tramo="${i}">Mirar las fojas</button>
      ${t.principal ? '' : `<button class="boton gris" data-separar="${t.id}">Separar continuaci\u00f3n</button>`}</li>`).join('')}</ol>
    ${vecino ? `<aside class="aviso info"><p>Para mirar: <span class="mono">${esc(vecino.nombre)}</span>,
      parte ${esc(vecino.orden)} de ${esc(vecino.conjunto)}. Es la parte siguiente del conjunto;
      eso no confirma que la pieza siga ah\u00ed.</p><button class="boton gris" id="mirar-vecino">Mirar parte siguiente</button></aside>` : ''}
    <form id="continuar-pieza" class="nucleo-form">
      <label>Archivo donde sigue <select name="sha256" required>${opcionesArchivos(archivos)}</select></label>
      <label>Desde la foja <input name="pagina_desde" type="number" min="1" required></label>
      <label>Hasta la foja <input name="pagina_hasta" type="number" min="1" required></label>
      <button type="button" class="boton gris" id="mirar-destino">Mirar antes de afirmar</button>
      <button class="boton" type="submit">Afirmar que la pieza sigue en estas fojas</button>
    </form>`;
}

async function cargarContinuidad(id, sha) {
  const host = $('#continuidad-pieza');
  try {
    const [d, v, a] = await Promise.all([api('/api/pieza/tramos?id='+id),
      api('/api/pieza/vecino?sha256='+encodeURIComponent(sha)), api('/api/archivos')]);
    if (!host.isConnected) return;
    host.innerHTML = htmlContinuidad(d.tramos, v.vecino, a.archivos);
    host.querySelectorAll('[data-mirar-tramo]').forEach(b => b.onclick = () => {
      const t = d.tramos[+b.dataset.mirarTramo]; abrirFojaSuelta(t.sha256, t.pagina_desde, t.archivo);
    });
    if (v.vecino) $('#mirar-vecino', host).onclick = () => abrirFojaSuelta(v.vecino.sha256, 1, v.vecino.nombre);
    const f = $('#continuar-pieza', host);
    $('#mirar-destino', host).onclick = () => {
      const a = f.elements.sha256;
      if (a.value && f.elements.pagina_desde.reportValidity())
        abrirFojaSuelta(a.value, +f.elements.pagina_desde.value, a.selectedOptions[0].textContent);
    };
    f.onsubmit = async e => {
      e.preventDefault(); const b = f.querySelector('[type="submit"]'); b.disabled = true;
      try {
        const quien = await conRevisor(); if (!quien) return;
        await guardarNucleo('/api/pieza/continuar', {documento_id:+id, sha256:f.elements.sha256.value,
          pagina_desde:+f.elements.pagina_desde.value, pagina_hasta:+f.elements.pagina_hasta.value, quien});
        await cargarContinuidad(id, sha);
      } catch (e) { toast(e.message); } finally { b.disabled = false; }
    };
    host.querySelectorAll('[data-separar]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const quien = await conRevisor(); if (!quien) return;
        await guardarNucleo('/api/pieza/separar', {tramo_id:+b.dataset.separar, quien});
        await cargarContinuidad(id, sha);
      } catch (e) { toast(e.message); } finally { b.disabled = false; }
    });
  } catch (e) { if (host.isConnected) host.textContent = e.message; }
}


function htmlConjunto(c, archivos) {
  const partes = c.partes;
  const org = c.organismo ? esc(c.organismo) : '<span class="nulo" title="sin organismo">—</span>';
  const exp = c.expediente ? esc(c.expediente) : '<span class="nulo" title="sin expediente">—</span>';
  const anio = c.anio ? esc(c.anio) : '<span class="nulo" title="sin año">—</span>';
  return `<h3>${esc(c.nombre)}</h3>
    <p>${org} · ${exp} · ${anio}</p>
    ${c.nota ? `<p class="prosa">${esc(c.nota)}</p>` : ''}
    <p>${partes.length} archivos · ${partes.reduce((n,p) => n+p.paginas,0)} fojas · ${partes.reduce((n,p) => n+p.piezas,0)} piezas</p>
    <p class="prosa">El orden se guarda con cada movimiento. Subí o bajá las partes para respetar el orden de la entrega.</p>
    <ol class="lista-partes">${partes.map((p,i) => `<li class="parte-ficha"><span class="mono">${esc(p.nombre)}</span>
      <p>${esc(p.paginas)} fojas · ${esc(p.piezas)} piezas</p>
      <div class="acciones-parte">
        <button class="boton secundario" data-mover="${i}" data-salto="-1" ${i === 0 ? 'disabled' : ''}>Subir</button>
        <button class="boton secundario" data-mover="${i}" data-salto="1" ${i === partes.length-1 ? 'disabled' : ''}>Bajar</button>
        <button class="boton peligro" data-quitar="${i}">Quitar</button>
      </div></li>`).join('')}</ol>
    ${partes.length ? '' : '<p class="estado-vacio">Este conjunto todavía no tiene archivos.</p>'}
    <form id="agregar-parte" class="formulario-estandar"><label>Archivo para sumar
      <select name="sha256" required>${opcionesArchivos(archivos.filter(a => !partes.some(p => p.sha256 === a.sha256)))}</select></label>
      <button class="boton">Sumar al final</button></form>`;
}


async function vConjuntos(elegido) {
  const [d,a] = await Promise.all([api('/api/conjuntos'), api('/api/archivos')]);
  if (location.hash !== '#/conjuntos') return;
  vista.innerHTML = bloque('f. 0005', 'Documentos', `<h2>Conjuntos documentales</h2>
    <p class="prosa">Agrupá los archivos de una entrega y conservá su orden.</p>
    <form id="crear-conjunto" class="formulario-estandar"><label>Nombre <input name="nombre" required></label>
      <label>Organismo <input name="organismo"></label><label>Expediente <input name="expediente"></label>
      <label>Año <input name="anio" type="number"></label><label>Nota <input name="nota"></label>
      <button class="boton">Crear conjunto</button></form>
    ${d.conjuntos.length ? `<label class="selector-conjunto">Conjunto <select id="elegir-conjunto"><option value="">Elegí un conjunto</option>
      ${d.conjuntos.map(c => `<option value="${c.id}">${esc(c.nombre)} (${c.archivos} archivos, ${c.paginas} fojas)</option>`).join('')}</select></label>`
      : '<p class="estado-vacio">No hay conjuntos documentales.</p>'}<section id="detalle-conjunto" aria-live="polite"></section>`);
  $('#crear-conjunto').onsubmit = async e => {
    e.preventDefault(); const f=e.currentTarget, b=f.querySelector('button'); b.disabled=true;
    try {
      const datos = Object.fromEntries(new FormData(f));
      for (const k of ['organismo','expediente','nota']) datos[k] = datos[k].trim() || null;
      datos.anio = datos.anio ? +datos.anio : null;
      const c = await guardarNucleo('/api/conjunto/crear', datos); await vConjuntos(c.id);
    } catch(e) { toast(e.message); } finally { b.disabled=false; }
  };
  const selector = $('#elegir-conjunto');
  if (!selector) return;
  selector.onchange = () => mostrarConjunto(+selector.value, a.archivos);
  if (elegido) { selector.value=String(elegido); await mostrarConjunto(elegido, a.archivos); }
}


async function mostrarConjunto(id, archivos) {
  const host = $('#detalle-conjunto');
  if (!id) { host.innerHTML=''; return; }
  try {
    const c = await api('/api/conjunto?id='+id);
    if (!host.isConnected || +$('#elegir-conjunto').value !== +id) return;
    host.innerHTML = htmlConjunto(c, archivos);
    const cambiar = async (ruta, datos) => {
      host.querySelectorAll('button').forEach(b => b.disabled=true);
      try { await guardarNucleo(ruta, {conjunto_id:+id,...datos}); await vConjuntos(id); }
      catch(e) { toast(e.message); await mostrarConjunto(id, archivos); }
    };
    $('#agregar-parte',host).onsubmit = e => {
      e.preventDefault(); cambiar('/api/conjunto/agregar', {sha256:e.currentTarget.elements.sha256.value});
    };
    host.querySelectorAll('[data-quitar]').forEach(b => b.onclick = () =>
      cambiar('/api/conjunto/quitar',{sha256:c.partes[+b.dataset.quitar].sha256}));
    host.querySelectorAll('[data-mover]').forEach(b => b.onclick = () => {
      const shas=c.partes.map(p => p.sha256), i=+b.dataset.mover, j=i+(+b.dataset.salto);
      [shas[i],shas[j]]=[shas[j],shas[i]];
      cambiar('/api/conjunto/reordenar',{shas});
    });
  } catch(e) { if (host.isConnected) host.textContent=e.message; }
}

async function vReasociaciones() {
  if (location.hash !== '#/reasociaciones') return;
  vista.innerHTML = bloque('REV', 'Revisiones desplazadas', `
    <h2>Revisiones desplazadas</h2>
    <p class="prosa">Decisiones humanas que perdieron su foja de anclaje original.</p>
    <div id="lista-reasoc"></div>
  `);

  tablaServidor($('#lista-reasoc'), '/api/reasociaciones/pendientes', 'revisiones', [
    {t: 'Clase', r: r => esc(r.clase)},
    {t: 'Documento', r: r => `<a href="#/documento/${esc(r.documento_id)}">${esc(r.archivo || 'doc ' + r.documento_id)}</a>`},
    {t: 'Foja', c: 'num', r: r => `<a href="javascript:abrirFojaSuelta('${esc(r.sha256)}', ${r.ancla_pagina}, '${esc(r.archivo)}')">f. ${esc(r.ancla_pagina)}</a>`},
    {t: 'Texto original', c: 'mono', r: r => esc(r.texto)},
    {t: 'Decisin', r: (r, i) => `<div class="fila-acciones" data-revision="${r.id}">
      <label><input type="radio" name="res-${r.id}" value="reasociar"> Reasociar</label>
      <label><input type="radio" name="res-${r.id}" value="descartar"> Descartar</label>
      <button class="boton" data-resolver="ejecutar" disabled>Ejecutar</button>
    </div>`}
  ]);
}


function htmlActualizacion(plan, revisiones) {
  const nombres = new Map(plan.etapas.map(e => [e.clave, e.nombre]));
  const etiqueta = clave => ({paginas_ocr: 'Fojas de OCR', lecturas: 'Lecturas guardadas',
    indice: 'Índice de búsqueda', archivos: 'Archivos', documentos: 'Documentos',
    total: 'Total', preservadas: 'Preservadas',
    requieren_reasociacion: 'Necesitan reasociación'}[clave] || clave.replaceAll('_', ' '));
  const cuentas = datos => `<dl class="lista-definiciones">${Object.entries(datos).map(([k, v]) =>
    `<div><dt>${esc(etiqueta(k))}</dt><dd>${typeof v === 'boolean' ? (v ? 'Sí' : 'No') : esc(fmtNum.format(v))}</dd></div>`).join('')}</dl>`;
  const sinMaterial = plan.etapas.filter(e => e.alcance !== 'legajo').every(e => e.total === 0);
  return `<h2>Actualizar análisis</h2>
    <p class="prosa">${sinMaterial ? 'No hay material cargado para actualizar.' : plan.vigente
      ? 'El análisis está vigente. No hay nada que actualizar.'
      : 'Mirá qué se aprovecha y qué hace falta recalcular antes de empezar.'}</p>
    <div class="actualizacion-cuentas">
      <section><h3>Se reutiliza</h3>${cuentas(plan.reutiliza)}</section>
      <section><h3>Se recalcula</h3>${cuentas(plan.recalcula)}</section>
    </div>
    <p class="prosa nota">Las cuentas de OCR indican las fojas que se aprovechan y las que se vuelven a leer. Las etapas se registran por separado, pero algunas se ejecutan juntas por archivo.</p>
    <h3>Etapas</h3><div class="actualizacion-etapas">${plan.etapas.map(e => `<article class="tarjeta-etapa">
      <h4>${esc(e.nombre)} <span class="sello ${e.estado === 'desactualizada' || e.estado === 'nunca' ? 'atencion' : 'neutro'}">${esc(e.estado)}</span></h4>
      ${e.explica ? `<p>${esc(e.explica)}</p>` : ''}
      ${e.motivo ? `<p>${esc(e.motivo)}</p>` : ''}
      ${e.estado === 'heredada' || e.heredados > 0 ? '<p>Hay resultados heredados aprovechables: se adoptó lo que ya estaba sin volver a leerlo; no se comprobó que coincida.</p>' : ''}
      <p>Aprovechables: ${esc(fmtNum.format(e.vigentes))} · Desactualizados: ${esc(fmtNum.format(e.desactualizados))} · Total: ${esc(fmtNum.format(e.total))} · Costo: ${esc(e.cuesta)}</p>
    </article>`).join('')}</div>
    <h3>Trabajo de las personas</h3>${cuentas(plan.revisiones)}
    <p class="prosa">Las revisiones que necesitan reasociación se conservan. No se aplican solas porque no es seguro a qué pieza corresponden. Necesitan que una persona las mire; no son trabajo perdido.</p>
    ${revisiones.length ? '<p><a href="#/reasociaciones" class="boton secundario">Resolver las revisiones desplazadas</a></p>' : ''}
    ${revisiones.map(r => `<article class="actualizacion-revision"><h4 class="mono">${esc(r.archivo)}</h4>
      <p>${esc(r.campo)}: ${r.valor == null ? '<span class="nulo" title="sin valor">—</span>' : esc(r.valor)}</p>
      <p>${esc(r.quien)} · ${esc(r.cuando)}</p><p>${esc(r.motivo)}</p></article>`).join('')}
    ${plan.archivos.length ? `<h3>Archivos alcanzados</h3><ul class="lista-archivos">${plan.archivos.map(a =>
      `<li><span class="mono">${esc(a.nombre)}</span> · Fojas: ${esc(fmtNum.format(a.paginas))} · ${a.desactualizadas.map(k => esc(nombres.get(k) || k)).join(', ')}</li>`).join('')}</ul>` : ''}
    ${!plan.vigente && !sinMaterial ? '<button class="boton principal" id="b-actualizar">Actualizar análisis</button>' : ''}`;
}

async function vActualizacion() {
  const [plan, pendientes, t] = await Promise.all([
    api('/api/actualizacion'), api('/api/reasociaciones'), api('/api/trabajo')]);
  if (location.hash !== '#/actualizacion') return;
  vista.innerHTML = bloque('ACT', 'Análisis',
    `<div id="plan-actualizacion">${htmlActualizacion(plan, pendientes.revisiones)}</div><div id="progreso" aria-live="polite"></div>`);
  const b = $('#b-actualizar');
  if (b) {
    b.disabled = t.estado === 'corriendo';
    b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await api('/api/actualizar', {method: 'POST',
          headers: {'Content-Type': 'application/json'}, body: '{}'});
        if (!r.ok) { toast(r.motivo); b.disabled = false; return; }
        await seguirTrabajo();
      } catch (e) { toast(e.message); b.disabled = false; }
    };
  }
  pintarTrabajo(t);
  if (t.estado === 'corriendo') seguirTrabajo();
}


async function vIngesta() {
  // El control de arriba ya corta la ruta, pero la carga es la única pantalla que
  // ESCRIBE en disco: se chequea de nuevo acá, contra el servidor y no contra lo que
  // esta pestaña se acuerde. Una pestaña abierta desde ayer cree cualquier cosa.
  const c = await api('/api/cuentas');
  if (!c.legajo && !c.documentos) return vistaSinLegajo('Cargar escaneos');

  const [t, ar] = await Promise.all([api('/api/trabajo'), api('/api/archivos')]);
  const lote = localStorage.getItem('ufil.lote') || '';
  /* Qué falta hacer, dicho por lo que falta y no por lo que hay. «N documentos sin
     leer» contaba archivos sin NINGUNA lectura: un archivo leído a medias no aparecía
     ni como pendiente ni como terminado, y «leído pero sin extraer» no existía. */
  const pendiente = (ar.falta_leer || 0) + (ar.sin_extraer || 0);
  const textoPendiente = [
    ar.falta_leer ? `${fmtNum.format(ar.falta_leer)} ${
      ar.falta_leer === 1 ? 'foja sin leer' : 'fojas sin leer'}` : '',
    ar.sin_extraer ? `${fmtNum.format(ar.sin_extraer)} ${
      ar.sin_extraer === 1 ? 'archivo sin extraer' : 'archivos sin extraer'}` : '',
  ].filter(Boolean).join(' y ');
  vista.innerHTML = bloque('f. 0000', 'Ingesta', `
    <h2>Cargar escaneos</h2>
    <p class="prosa">Arrastrá acá los PDF escaneados, o elegilos. Se guardan tal cual
      llegaron, bajo su propio hash y en solo lectura: <strong>el archivo que subís no se
      vuelve a tocar nunca más</strong>. Si un PDF ya estaba, no se duplica — se anota que
      apareció de nuevo y se sigue.</p>

    <div class="campos-lote">
      <label>Lote <input type="text" id="i-lote" value="${esc(lote)}"
        placeholder="contratos-camara-A-2024"></label>
      <label>Referencia <input type="text" id="i-legajo"
        placeholder="opcional — expediente, actuación"
        title="Sólo queda anotado en la procedencia del archivo. No cambia de legajo."></label>
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

    <div class="fila-suelta">
      <button class="boton" id="b-procesar" ${pendiente ? '' : 'disabled'}>
        ${pendiente ? `Procesar ${textoPendiente}` : 'No queda nada por procesar'}</button>
      <span class="rotulo" id="estado-trabajo"></span>
    </div>
    <div id="progreso"></div>

    ${ar.archivos.length ? `
      <h3>Lo que hay cargado</h3>
      <p class="prosa">${resumenCarga(ar)}</p>
      ${tabla([
        {t:'Archivo', c:'fol', r:f => nombreArchivo(f.nombre)},
        {t:'Fojas', c:'num', r:f => fmtNum.format(f.fojas || 0)},
        {t:'Leídas', c:'num', r:f => f.leidas === f.fojas
          ? fmtNum.format(f.leidas)
          : `<span class="marca">${fmtNum.format(f.leidas || 0)}</span>`},
        {t:'En qué está', r:f => ESTADO_CARGA[f.estado] || f.estado},
        {t:'Lote', r:f => esc(f.lote || '—')},
        {t:'', r:f => f.estado !== 'papelera' ? `<button type="button" class="mini b-quitar-arch" data-sha="${esc(f.sha256)}">Quitar del legajo</button>` : ''}
      ], ar.archivos, {lista:'archivos'})}` : ''}

    <details class="consejo" id="c-escaneo">
      <summary>Qué pedirle a quien escanea</summary>
      <p><strong>300 DPI y escala de grises.</strong> Nunca el «modo texto» en blanco y
        negro que muchos escáneres traen puesto: es la única configuración probada que
        llegó a <strong>guardar un dato falso dándolo por bueno</strong>. Más de 300 no
        hace falta; el archivo pesa el doble y no se gana nada medible.</p>
      <p><strong>Un PDF por contrato, si se puede.</strong> Así el sistema reconoce por
        huella los que ya tenía y no los cuenta dos veces. Si conviene escanear de
        corrido, hacelo igual: los separa solo y avisa cuáles quedaron repetidos.</p>
      <p>Conviene pedirlo <strong>por escrito y antes de que empiecen</strong>.
        Reescanear dos mil fojas porque salieron a 100 DPI es una semana perdida.</p>
      <p class="medido">El detalle de las mediciones está en
        <a href="#/como-funciona">Cómo funciona</a>.</p>
    </details>

    ${t.lotes && t.lotes.length ? `
      <h3>Lotes cargados</h3>
      ${tabla([
        {t:'Lote', k:'lote'},
        {t:'Archivos', k:'archivos', c:'num'},
        {t:'Páginas', k:'paginas', c:'num'},
        {t:'Última carga', c:'fol', r:f => esc(String(f.ultimo || '').slice(0,16).replace('T',' '))},
      ], t.lotes)}` : ''}`);

  vista.querySelectorAll('.b-quitar-arch').forEach(b => {
    b.addEventListener('click', () => {
      const f = ar.archivos.find(a => a.sha256 === b.dataset.sha);
      if (f) pedirQuitarArchivo(f.sha256, f.nombre, f.confirmacion_quitar, f.procesando, f.tiene_revisiones_humanas ? (f.decisiones_humanas !== undefined ? f.decisiones_humanas : (f.revisiones !== undefined ? f.revisiones : -1)) : 0);
    });
  });

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
    try {
      const r = await api('/api/procesar', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({})});
      if (!r.ok) return toast(r.motivo || 'No se pudo arrancar');
      seguirTrabajo();
    } catch (e) {
      // 409 sin legajo: el servidor tiene razón y la pantalla está vieja. Se la manda
      // a elegir uno en vez de mostrarle el texto del error.
      if (e.estado === 409) return vistaSinLegajo('Cargar escaneos');
      toast(e.message);
    }
  };
  if (t.estado === 'corriendo') seguirTrabajo(); else pintarTrabajo(t);
}

async function subir(archivos) {
  if (subiendo || !archivos.length) return;
  const pdfs = archivos.filter(f => /\.pdf$/i.test(f.name) || f.type === 'application/pdf');
  const salteados = archivos.length - pdfs.length;
  if (!pdfs.length) return toast('Ninguno de esos archivos es un PDF.');

  const lote = ($('#i-lote').value || '').trim();
  if (!lote) { $('#i-lote').focus(); return toast('Poné un nombre de lote antes de subir.'); }
  localStorage.setItem('ufil.lote', lote);
  const operador = ($('#i-operador').value || '').trim();
  if (operador) localStorage.setItem('ufil.revisor', operador);

  subiendo = true;
  const caja = $('#subidas');
  caja.innerHTML = `<div class="lista-subida"></div>`;
  const lista = caja.firstElementChild;
  let nuevos = 0, dups = 0, fallos = 0, papel = 0, parciales = 0;

  /* ── Preguntar ANTES de subir ──────────────────────────────────────────────
     Un PDF de un expediente pesa veintidós megabytes. Subirlo entero para que el
     servidor conteste «ya estaba» es tiempo de quien está cargando, y una carpeta de
     trescientos escaneos vuelta a arrastrar es la tarde entera. El SHA-256 se puede
     calcular acá, sin mandar nada, y preguntarlo todo junto.

     Es lo mismo que calcula el servidor: el hash del archivo tal cual. Si el navegador
     no tiene `crypto.subtle` —sin HTTPS y sin localhost no existe— se sigue como
     antes; que falte esto no puede impedir cargar. */
  const yaEstan = new Set();
  try {
    if (crypto.subtle) {
      const shas = [];
      for (const f of pdfs) {
        const h = await crypto.subtle.digest('SHA-256', await f.arrayBuffer());
        f.__sha = [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join('');
        shas.push(f.__sha);
      }
      const r = await api('/api/yaestan?sha=' + shas.join(','));
      (r.estan || []).forEach(x => yaEstan.add(x));
    }
  } catch (e) { /* si no se puede preguntar, se sube y contesta el servidor */ }

  for (const [i, f] of pdfs.entries()) {
    const fila = document.createElement('div');
    fila.className = 'subida';
    fila.innerHTML = `<span class="fol">${i+1}/${pdfs.length}</span>
      <span class="nom">${esc(f.name)}</span><span class="res">subiendo…</span>`;
    lista.appendChild(fila);
    fila.scrollIntoView({block:'nearest'});
    if (f.__sha && yaEstan.has(f.__sha)) {
      dups++;
      fila.querySelector('.res').innerHTML =
        `<span class="nulo">ya estaba — no se subió</span>`;
      continue;
    }
    try {
      const q = new URLSearchParams({nombre: f.name, lote,
        legajo: ($('#i-legajo').value || '').trim(), operador});
      const r = await fetch('/api/subir?' + q, {method:'POST',
        headers:{'Content-Type':'application/pdf'}, body: f});
      const j = await r.json();
      if (!r.ok || !j.ok) { fallos++; fila.querySelector('.res').innerHTML =
        `<span class="marca">${esc(j.error || 'error')}</span>`; }
      else if (j.duplicado && j.motivo === 'papel') {
        /* El mismo documento adentro de otro archivo. Es el caso que no se veía:
           reexportar un PDF cambia su SHA-256 y no cambia una sola foja. Se dice con
           todas las letras, y se dice contra QUÉ, porque quien carga tiene que poder
           ir a mirarlo. */
        papel++;
        fila.querySelector('.res').innerHTML =
          `<span class="marca">es el mismo papel que ${
            esc((j.cotejo && j.cotejo.mismo_que) || 'otro archivo')}</span>`;
      }
      else if (j.duplicado) { dups++; fila.querySelector('.res').innerHTML =
        `<span class="nulo">ya estaba</span>`; }
      else if (j.motivo === 'parcial' && j.cotejo) {
        /* Se guardó. Dos partes de un expediente comparten la foja del empalme y eso
           es correcto en el papel, así que acá el sistema NO decide: avisa y sigue. */
        parciales++; nuevos++;
        fila.querySelector('.res').innerHTML =
          `<span class="ok-txt">${j.paginas} pág.</span> <span class="marca"
            >${j.cotejo.repetidas} de ${j.cotejo.con_huella} fojas ya estaban${
              j.cotejo.archivos[0] ? ' en ' + esc(j.cotejo.archivos[0].archivo) : ''}</span>`;
      }
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
    (papel ? `, <span class="marca">${papel} ${papel===1?'era el mismo papel':'eran el mismo papel'} con otro nombre</span>` : '') +
    (parciales ? `, <span class="marca">${parciales} con fojas repetidas</span>` : '') +
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
      ${t.estado === 'terminado' ? `<p class="prosa nota sep-corta">
         <strong>Listo.</strong> ${esc(t.mensaje)} · ${t.segundos} s.
         <a href="#/panel">Ver el panel</a> · <a href="#/cola">Ir a la cola</a></p>` : ''}
      ${t.estado === 'detenido' ? `<div class="aviso sep-corta">
         <span class="sello atencion">Parado</span>
         <span>${esc(t.mensaje)}</span></div>` : ''}
      ${t.estado === 'error' ? `<div class="aviso sep-corta">
         <span class="sello alerta">Error</span><span>${esc(t.mensaje)}</span></div>` : ''}
      ${(t.errores || []).length ? `<details class="sep-corta"><summary class="rotulo">
         ${plural(t.errores.length, 'documento con problemas', 'documentos con problemas')}</summary>
         <ul class="sep-corta">${t.errores.slice(0,20).map(e =>
           `<li>${esc(e.etapa)}: ${esc(e.detalle)}</li>`).join('')}</ul></details>` : ''}
    </div>`;

  const parar = $('#b-detener');
  if (parar) parar.onclick = async () => {
    parar.disabled = true;
    parar.textContent = 'parando…';
    try { await api('/api/detener', {method: 'POST',
                                     headers: {'Content-Type': 'application/json'},
                                     body: '{}'}); }
    catch (e) { toast('No se pudo parar: ' + e.message); parar.disabled = false; }
  };
}

let temporizador = null;
async function seguirTrabajo() {
  clearTimeout(temporizador);
  const t = await api('/api/trabajo');
  pintarTrabajo(t);
  const b = $('#b-procesar');
  if (b) b.disabled = t.estado === 'corriendo' || !t.sin_leer;
  const actualizar = $('#b-actualizar');
  if (actualizar) actualizar.disabled = t.estado === 'corriendo';
  if (t.estado === 'corriendo') {
    temporizador = setTimeout(seguirTrabajo, 1500);
  } else {
    refrescarCuentas();
    if ($('#plan-actualizacion')) await vActualizacion();
  }
}


/* ── Trabajo del equipo ────────────────────────────────────────────────────
   Sobre una misma causa trabajan varias personas. Sin esta pantalla, cada una ve un
   contador que baja y no sabe si bajó porque alguien más está revisando o porque algo
   se rompió. Y a la hora de firmar, «lo revisó una persona» no alcanza: hay que poder
   decir quién revisó qué, y cuándo.

   Sale de `revision_humana`, que ya se escribe con cada decisión. No hay tabla nueva
   ni nada duplicado: es la misma verdad, mirada por autor. */
const ACCION_EQUIPO = {
  verificar: ['ok', 'lo dio por correcto'],
  corregir: ['ok', 'lo corrigió a mano'],
  ilegible: ['neutro', 'lo cerró como ilegible'],
  ausente: ['neutro', 'lo cerró como ausente'],
  ambiguo: ['neutro', 'lo cerró como ambiguo'],
  revertir: ['atencion', 'deshizo una revisión'],
};

async function vEquipo() {
  const a = await api('/api/actividad');

  if (!a.total) {
    return vista.innerHTML = bloque('f. 0105', 'Equipo', `
      <h2>Trabajo del equipo</h2>
      ${vacio('Todavía nadie revisó nada',
        'Acá va a aparecer quién revisó cada campo y cuándo. Cada decisión que alguien ' +
        'toma en la cola queda registrada con su nombre, y esto lo muestra junto.',
        {href: '#/cola', texto: 'Ir a la cola de revisión'})}`);
  }

  const cuando = v => v ? `${fmtFecha(v)} ${String(v).slice(11, 16)}` : '—';
  const yo = revisor();

  vista.innerHTML =
    bloque('f. 0105', 'Equipo', `
      <h2>Trabajo del equipo</h2>
      <p class="prosa">Todos trabajan sobre la misma base: lo que revisa una persona lo
        ve el resto enseguida. <strong>${plural(a.total, 'decisión tomada a mano',
        'decisiones tomadas a mano')}</strong> en este legajo.</p>
      ${tabla([
        {t:'Quién', c:'nombre', r:f => `<b>${esc(f.quien)}</b>` +
          (f.quien === yo ? ' <span class="apagado">— sos vos</span>' : '')},
        {t:'Campos revisados', c:'num', r:f => fmtNum.format(f.decisiones)},
        {t:'Empezó', c:'mono', r:f => esc(cuando(f.primera))},
        {t:'Última vez', c:'mono', r:f => esc(cuando(f.ultima))},
      ], a.quienes)}`) +

    bloque('f. 0106', 'Últimas', `
      <h2>Lo último que se decidió</h2>
      <p class="prosa">De lo más reciente a lo más viejo. Cada renglón lleva al
        documento, para poder mirar el folio.</p>
      ${tabla([
        {t:'Cuándo', c:'mono', r:f => esc(cuando(f.cuando))},
        {t:'Quién', c:'nombre', r:f => esc(f.quien)},
        {t:'Campo', c:'nowrap', r:f => esc(rotularCampo(f.campo))},
        {t:'Qué hizo', r:f => {
          const [tono, texto] = ACCION_EQUIPO[f.accion] || ['neutro', f.accion];
          return sello(tono, texto);
        }},
        {t:'Valor que quedó', c:'mono', r:f => f.valor
          ? esc(f.valor) : '<span class="apagado">—</span>'},
        {t:'Documento', r:f => f.documento_id
          ? `<a href="#/documento/${f.documento_id}">${esc(f.archivo)}</a>`
          : esc(f.archivo)},
      ], a.ultimas)}`);
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
          <ul class="lista-fiscales">${fiscales.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
        </div>` : ''}
      </div>
      <p class="prosa">Estos nombres son los que salen impresos en la portada de cada planilla y de cada informe que genera el sistema. Se cambian en un solo lugar —<span class="mono">ufil/identidad.py</span>, o un archivo <span class="mono">identidad.json</span> en la carpeta de datos— y cambian en todas partes a la vez.</p>`) +
    bloque('f. 0000', 'Versión', `
      <h2>Qué versión estás usando</h2>
      <table class="tabla-estandar"><tbody>
        <tr><td>${sello('neutro', 'Interfaz')}</td>
            <td class="mono">${esc(VERSION_CARGADA || c.version || '—')}</td>
            <td>La huella del archivo de la interfaz que cargó esta pestaña. Si el servidor pasa a servir otra, aparece un aviso arriba.</td></tr>
        <tr><td>${sello('neutro', 'Legajo abierto')}</td>
            <td class="mono">${esc(c.legajo ? c.legajo.numero : 'ninguno')}</td>
            <td>${c.legajo ? esc(c.legajo.caratula) : 'Cada legajo es una base separada. <a href="#/legajos">Elegir uno</a>.'}</td></tr>
      </tbody></table>
      <p class="prosa">Lo que hace y lo que <strong>no</strong> hace el sistema está contado en <a href="#/como-funciona">Cómo funciona</a>. Si algo no anda, <a href="#/salud">Estado del sistema</a> dice qué falta y cómo se arregla.</p>`);
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

  const version = `<p class="version-app">
    Versión de la interfaz <span class="mono">${esc(s.version)}</span> ·
    esquema de la base <span class="mono">v${esc(s.esquema)}</span>${
      VERSION_CARGADA && VERSION_CARGADA !== s.version
        ? ` · <strong>hay una versión más nueva en el servidor</strong>:
            <a href="#" onclick="location.reload();return false">recargar</a>` : ''}</p>`;

  const veredicto = s.puede_trabajar
    ? `<div class="aviso ${s.avisos ? 'atento' : 'bien'}">
         <span class="sello ${s.avisos ? 'atencion' : 'ok'}">Listo</span>
         <span>El equipo tiene todo lo necesario para trabajar${
           s.avisos ? `, con ${s.avisos} aviso${s.avisos > 1 ? 's' : ''} que conviene mirar` : ''}.</span></div>`
    : `<div class="aviso info"><span class="sello alerta">Falta</span>
         <span>Todavía no se puede trabajar: faltan ${s.fallas} cosa${s.fallas > 1 ? 's' : ''}.
         Abajo está cada una con lo que hay que instalar.</span></div>`;

  const PESO = {falla: 0, aviso: 1, ok: 2};
  const ordenados = [...s.chequeos].sort(
    (a, b) => (PESO[a.estado] ?? 2) - (PESO[b.estado] ?? 2));
  const filas = ordenados.map(c => `
    <tr class="${c.estado !== 'ok' ? 'chequeo-mal' : ''}">
      <td><span class="sello ${clase[c.estado]}">${simbolos[c.estado]}</span></td>
      <td><b>${esc(c.nombre)}</b></td>
      <td>${esc(c.detalle)}${c.arreglo && c.estado !== 'ok'
        ? `<div class="arreglo mono">${esc(c.arreglo)}</div>` : ''}</td>
    </tr>`).join('');

  const inv = s.invariantes.length
    ? `<ul class="fallas">${s.invariantes.map(f => `<li>${esc(f)}</li>`).join('')}</ul>`
    : `<div class="aviso bien"><span class="sello ok">Cumple</span>
         <span>Las reglas del pliego se siguen cumpliendo sobre los datos cargados: ninguna interpretación sin documento que la sostenga.</span></div>`;

  const i = s.integridad;
  const cobertura = i.total
    ? `<p class="prosa">De los <b>${i.total}</b> originales cargados,
        <b>${i.verificados}</b> fueron rehasheados alguna vez y siguen idénticos a como entraron.${i.total > i.verificados
          ? ` Faltan ${i.total - i.verificados}: cada comprobación toma un lote empezando por los que hace más tiempo que no se miran.`
          : ' El acervo entero está cubierto.'}
        ${i.mas_viejo ? ` La verificación más antigua es del <span class="mono">${esc(String(i.mas_viejo).slice(0, 16).replace('T', ' '))}</span>.` : ''}</p>
       <p class="prosa nota">Rehashear originales lee del disco archivo por archivo, así que no se hace al abrir esta pantalla: se pide.</p>
       <button class="boton principal" id="b-verificar">Comprobar originales ahora</button>
       <div id="r-verificar"></div>`
    : `<p class="estado-vacio">Todavía no hay documentos cargados, así que no hay nada que verificar.</p>`;

  vista.innerHTML =
    bloque('f. 0900', 'Equipo', `
      <h2>Estado del sistema</h2>
      <p class="prosa">Esta pantalla contesta dos preguntas. Arriba: si esta computadora tiene instalado todo lo necesario. Abajo: si lo que ya está cargado sigue cumpliendo las reglas con las que se cargó.</p>
      ${veredicto}
      ${version}
      <div class="tabla-env"><table class="tabla-estandar"><tbody>${filas}</tbody></table></div>`) +
    bloque('f. 0901', 'Reglas', `
      <h2>Las reglas siguen valiendo</h2>
      <p class="prosa">No es una promesa del instructivo: se vuelve a comprobar contra la base cada vez que se abre esta pantalla.</p>
      ${inv}`) +
    bloque('f. 0902', 'Originales', `
      <h2>Los originales no cambiaron</h2>
      <p class="prosa">El sistema guarda el hash de cada archivo tal como entró y lo vuelve a calcular cada tanto.</p>
      ${cobertura}`);

  const boton = $('#b-verificar');
  if (boton) boton.onclick = async () => {
    boton.disabled = true;
    boton.textContent = 'Leyendo los originales…';
    try {
      const r = await api('/api/verificar', {method: 'POST'});
      $('#r-verificar').innerHTML = r.fallas.length
        ? `<div class="aviso sep-corta">
             <span class="sello alerta">Ojo</span>
             <span>${r.fallas.map(esc).join('<br>')}</span></div>`
        : `<div class="aviso bien sep-corta">
             <span class="sello ok">Intactos</span>
             <span>Se rehashearon <b>${r.revisados}</b> originales y los <b>${r.ok}</b> coinciden con el hash con el que entraron. Cubiertos hasta ahora: ${r.cubiertos} de ${r.total}.</span></div>`;
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
/* ── El expediente, foja por foja ───────────────────────────────────────────
   Un expediente administrativo no se puede mirar como una pila de documentos. Medido
   sobre el expediente 201.602 —parte 4, 88 páginas escaneadas de una actuación de más
   de 850 fojas—: no produce UN documento, porque no hay adentro un solo formulario.
   Antes de esta pantalla todo ese material entraba y desaparecía: 88 páginas leídas,
   0 documentos, ningún lugar donde mirarlo.

   Lo que hay para mostrar de un expediente es la FOLIATURA: qué es cada foja, cuáles
   son dorsos en blanco y cuáles tienen tinta y no se pueden leer. Y de cualquiera se
   sale a mirar el papel, que es lo único que decide. */
async function vFojas() {
  /* Las fojas de trabajo y las apartadas —dorsos en blanco, fojas sin texto útil— van
     en dos listas. Intercaladas, la de trabajo queda sepultada entre dorsos y hay que
     saltearlos de a uno. Apartadas no es escondidas: se cuentan arriba y se abren con
     un clic, porque si el sistema se equivocó al apartar una, mirarla es lo único que
     lo revela. */
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  const ver = q.get('ver') === 'apartadas' ? 'si' : 'no';
  const [trabajo, apartadas] = await Promise.all([
    api('/api/fojas?limite=1&apartadas=no'), api('/api/fojas?limite=1&apartadas=si')]);
  if (location.hash.split('?')[0] !== '#/fojas') return;
  const total = (trabajo.total || 0) + (apartadas.total || 0);
  if (!total) return vistaVacia('f. 0008', 'Fojas', 'Fojas del expediente',
    'Todavía no hay fojas para mostrar',
    'Cargá los escaneos y corré la lectura: acá va a aparecer qué es cada foja.');

  const pestaña = (clave, texto, n) => `<a class="chip-filtro${(ver === 'si') === (clave === 'apartadas') ? ' activo' : ''}"
      href="#/fojas${clave === 'apartadas' ? '?ver=apartadas' : ''}">${esc(texto)}<span class="chip-n">${fmtNum.format(n)}</span></a>`;
  vista.innerHTML = bloque('f. 0008', 'Fojas', `
    <h2>Fojas del expediente</h2>
    <p class="prosa">Qué es cada foja del escaneo. <strong>${fmtNum.format(trabajo.total)}</strong>
      ${trabajo.total === 1 ? 'foja de trabajo' : 'fojas de trabajo'} y ${fmtNum.format(apartadas.total)}
      fojas apartadas de ${fmtNum.format(total)} escaneadas. Un dorso en blanco no es trabajo
      pendiente; si el sistema apartó una foja por error, en la lista de apartadas se ve.</p>
    <div class="filtros-chips" role="tablist">
      ${pestaña('trabajo', 'De trabajo', trabajo.total)}${pestaña('apartadas', 'Apartadas', apartadas.total)}
    </div>
    <div id="lista-fojas"></div>`);

  // Lo apartado se ve apagado aun dentro de su lista: f.apartada viene del servidor.
  const cuño = f => f.apartada || f.clase === 'desconocida' || !f.clase
    ? `<span class="nulo">${esc(f.etiqueta || 'Sin clasificar')}</span>` : esc(f.etiqueta);
  tablaServidor($('#lista-fojas'), '/api/fojas?apartadas=' + ver, 'fojas', [
    {t: 'Archivo', o: 'archivo', r: f => esc(String(f.archivo || '').replace(/\.pdf$/i, ''))},
    {t: 'Foja', c: 'num', o: 'foja', r: f => fmtNum.format(f.nro)},
    {t: 'Qué es', c: 'crece', o: 'clase', r: cuño},
    {t: '', r: f => `<a href="javascript:void(0)" class="enlace-foja">ver la foja</a>`},
  ], {placeholder: 'Buscar por archivo o clase…',
      alClic: f => abrirFojaSuelta(f.sha256, f.nro),
      vacio: ver === 'si' ? 'No hay fojas apartadas.' : 'No hay fojas de trabajo.'});
}

/* ── Los números que el papel escribe dos veces ─────────────────────────────
   «PESOS OCHO MILLONES TRESCIENTOS DOCE MIL CIENTO UNO CON 91/100 ($8.312.101,91)».
   Un acto administrativo escribe cada cantidad dos veces, y eso es una salvaguarda de
   trescientos años: que un cero de más no pase desapercibido.

   Acá van TODOS los cotejos y no sólo los que fallan. Los que coinciden son la prueba
   de que el importe se leyó bien; una pantalla con sólo las diferencias no deja saber
   si el sistema miró algo o no miró nada. */
async function vNumeros() {
  const filas = await api('/api/numeros');
  if (!filas.length) return vistaVacia('f. 0009', 'Cotejo', 'Números escritos dos veces',
    'Todavía no hay ninguno',
    'Aparecen solos cuando el material trae actos administrativos: un importe en ' +
    'letras con su cifra al lado, o una cantidad con su número entre paréntesis.');

  // Primero lo que hay que mirar: los que no coinciden, después los que no se pudieron
  // cotejar, y al final los que coinciden. Dentro de cada grupo, en orden de foja.
  const peso = f => f.coinciden === 0 ? 0 : f.coinciden === null ? 1 : 2;
  filas.sort((a, b) => peso(a) - peso(b) || String(a.archivo).localeCompare(String(b.archivo))
                       || (a.pagina_nro || 0) - (b.pagina_nro || 0));
  const distintos = filas.filter(f => f.coinciden === 0).length;
  const dudosos = filas.filter(f => f.coinciden === null).length;

  vista.innerHTML = bloque('f. 0009', 'Cotejo', `
    <h2>Números escritos dos veces</h2>
    <p class="prosa">El papel dice la misma cantidad en letras y en dígitos.
      Comparar las dos es <strong>una segunda lectura del propio documento</strong>, sin
      depender de que el sistema lea bien. ${distintos
        ? `<strong>${fmtNum.format(distintos)}</strong> ${
            distintos === 1 ? 'no coincide' : 'no coinciden'}: eso no lo decide el
            sistema, hay que mirar la foja.`
        : 'Por ahora coinciden todos.'}${dudosos
        ? ` En ${fmtNum.format(dudosos)} no se pudo leer una de las dos formas, que no
            es lo mismo que un desacuerdo.` : ''}</p>
    ${tabla([
      {t:'Foja', c:'num', r:f => String(f.pagina_nro)},
      // Las letras parten renglón: sin eso, una cifra en letras de ochenta caracteres
      // no entraba y la hoja entera se iba a ancho completo, sin su margen.
      {t:'Qué dice en letras', c:'crece', r:f => esc(f.letras)},
      {t:'Y en números', c:'mono', r:f => esc(f.digitos)},
      {t:'Cotejo', r:f => f.coinciden === 1 ? sello('ok', 'Coinciden')
        : f.coinciden === 0 ? sello('atencion', 'No coinciden', {titulo: 'Hay que mirar la foja: puede ser el papel o la lectura.'})
        : sello('neutro', 'Una de las dos no se leyó')},
      {t:'Archivo', c:'fol', r:f => nombreArchivo(f.archivo)},
    ], filas, {lista:'numeros'})}`);
}

async function vAfuera() {
  const d = await api('/api/afuera');

  if (!d.afuera) {
    return vista.innerHTML = bloque('f. 0800', 'Control', `
      <h2>Ningún archivo quedó afuera</h2>
      <div class="aviso bien"><span class="sello ok">Completo</span>
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
      ${clase === 'perfil_no_aplica' ? `<p class="prosa nota">
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
      <div class="aviso"><span class="sello alerta">Ojo</span>
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
      <div class="aviso"><span class="sello alerta">Importante</span>
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
          <p class="prosa nota pegada">Lo que dice el papel. Se muestra en
            <span class="mono">monoespaciada</span> y cada valor sabe de qué archivo, qué
            página y qué parte de la imagen salió.</p>
          <ul class="lista-nota">
            <li>No interviene ningún modelo que pueda inventar.</li>
            <li>Lo que no se puede leer se guarda vacío <b>con el motivo</b>, nunca completado.</li>
            <li>Un valor sin ubicación en la imagen no entra en la base.</li>
          </ul>
        </div>
        <div class="carril carril--interp">
          <h3><span class="rotulo">Carril de interpretación</span> <span class="sello">Conjetura</span></h3>
          <p class="interp-texto pegada">Lo que el sistema
            deduce cruzando esos datos: patrones, anomalías, cosas para mirar. Va en serif
            bastardilla y sobre otro fondo.</p>
          <ul class="lista-nota">
            <li>Puede equivocarse, y se presenta como lo que es.</li>
            <li>Cada afirmación linkea a los documentos que la sostienen.</li>
            <li>El sistema no guarda una hipótesis sin fuente: la rechaza.</li>
          </ul>
        </div>
      </div>
      <p class="prosa sep-corta">Un fiscal tiene que poder mirar una pantalla y
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
`) +

    /* Esta sección existe porque la pantalla de carga ahora remite acá. Antes el
       detalle estaba delante del cuadro para soltar los archivos —sesenta líneas de
       prosa antes de lo que la persona vino a hacer— y se sacó de ahí con razón. Pero
       sacarlo y dejar el enlace apuntando a una pantalla que no lo tiene es peor que
       la prosa: es prometer algo y no darlo. */
    bloque('f. 0104', 'El escaneo', `
      <h2>Con qué calidad hay que escanear</h2>
      <p class="prosa">Es el techo de todo lo demás. El sistema no puede leer mejor de lo
        que el escáner dejó en el papel, y una decisión de dos minutos en la oficina que
        escanea vale más que cualquier ajuste posterior.</p>

      <h3>300 DPI, en escala de grises</h3>
      <p class="prosa">Sobre papel de mala calidad —fotocopia de fotocopia, hoja torcida,
        contraste caído, que es como llega un expediente viejo— la resolución mueve la
        exactitud de manera decisiva: <strong>a 100 DPI el sistema deja de servir</strong>.
        De 300 para arriba no se gana nada medible y el archivo pesa el doble.</p>

      <h3>Nunca el «modo texto»</h3>
      <div class="aviso"><span class="sello alerta">Importante</span>
        <span>El blanco y negro puro que muchos escáneres traen puesto es la única
          configuración de todo lo que se probó que llegó a <strong>guardar un dato falso
          dándolo por bueno</strong>. Y eso pasa aunque el número de exactitud
          <em>mejore</em>.</span></div>
      <p class="prosa">El mismo contrato, el mismo campo. En grises, las dos rutas de
        lectura discreparon: conflicto, campo vacío, a la cola —el sistema hizo lo que
        tiene que hacer—. En blanco y negro las dos leyeron
        <span class="mono">ALMADA, Rosa 1</span> —la inicial <span class="mono">I.</span>
        convertida en un <span class="mono">1</span>— y lo aceptó solo, con
        <span class="mono">0,92</span> de confianza. El umbral limpió la mancha del punto,
        las dos rutas coincidieron <span class="marca">en el error</span>, y el sistema se
        quedó sin la señal que usa para saber que no sabe.</p>

      <h3>Un PDF por contrato, si se puede</h3>
      <p class="prosa">Separar los contratos que vienen juntos en un mismo PDF no le cuesta
        nada al sistema y tarda casi lo mismo. La diferencia aparece al <strong>volver a
        escanear parte de una pila</strong>: con un PDF por contrato reconoce por huella
        los que ya tenía y no los cuenta dos veces; con todo en un PDF grande alcanza una
        hoja de diferencia para que sea un archivo nuevo, y los repetidos entran otra vez
        e inflan los acumulados.</p>
      <p class="prosa">Medido con doce contratos subidos en dos tandas que se pisan en
        tres: sueltos → 12 contratos, 0 repetidos; todo junto → 15 contratos,
        <span class="marca">3 repetidos</span>. Si conviene escanear de corrido —y muchas
        veces conviene, porque es más rápido en el escáner— hacelo igual: el sistema los
        separa y avisa cuáles quedaron repetidos, sólo que después hay que resolverlos a
        mano.</p>

      <p class="prosa">Todo esto conviene pedirlo <strong>por escrito y antes de que
        empiecen</strong>. Reescanear dos mil fojas porque salieron a 100 DPI es una
        semana perdida.</p>
      <p class="prosa"><a href="#/cola">Ver la cola de revisión</a> ·
         <a href="#/panel">volver al panel</a></p>`);
}

/* ── ruteo ─────────────────────────────────────────────────────────────── */
const TITULOS = {
  '#/contrataciones': 'Contrataciones',
  '#/contratacion': 'Contratación',
  '#/precios': 'Ítems y precios',
  /* Decía «Posible sobreprecio». Un título es una afirmación: es lo primero que se
     lee, es lo que queda en la pestaña del navegador y es lo que alguien recuerda
     cuando cuenta lo que vio. «Posible sobreprecio», aun con el adverbio, nombra una
     conclusión, y las conclusiones las escribe Fiscalía, no el sistema. Esta pantalla
     no concluye nada: pone al lado el precio analizado y sus referencias, dice de
     dónde salió cada número y cuán comparables son entre sí. Eso es una comparación.
     Si de ahí se sigue una conclusión, la firma una persona. */
  '#/renglon': 'Comparación de precio',
  '#/proveedor': 'Proveedor',
  '#/proveedores': 'Proveedores',
  '#/piezas': 'Documentos',
  '#/hallazgos': 'Hallazgos',
  '#/acerca': 'Acerca del sistema',
  '#/equipo': 'Trabajo del equipo',
  '#/sin-reconocer':'Todavía sin reconocer',
  '#/informes':'Informes',
  '#/foliatura':'Foliatura del papel',
  '#/tablas':'Tablas',
  '#/cronologia':'Cronología',
  '#/conjuntos':'Conjuntos documentales',
  '#/reasociaciones':'Revisiones desplazadas',
  '#/actualizacion':'Actualizar análisis',
  '#/panel':'Panel', '#/ingesta':'Cargar escaneos', '#/buscar':'Buscar',
  '#/contratos':'Contratos', '#/personas':'Personas',
  '#/superposiciones':'Superposiciones', '#/cola':'Cola de revisión',
  '#/identidad':'Identidad', '#/interpretacion':'Interpretación',
  '#/consultas':'Consultas', '#/documento':'Documento', '#/persona':'Ficha',
  '#/como-funciona':'Cómo funciona', '#/salud':'Estado del sistema',
  '#/afuera':'Quedaron afuera', '#/legajos':'Legajos',
  '#/comprobantes':'Facturas y recibos', '#/cruce':'Facturado contra contratado',
  '#/fojas':'Fojas del expediente', '#/numeros':'Números escritos dos veces',
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

/* Pinta el legajo abierto en la barra de arriba.

   Antes también redirigía a `#/legajos` cuando no había ninguno. Se sacó: el salto
   era silencioso —pedías Contratos y te aparecía otra pantalla, sin una palabra— y
   encima sólo pasaba en la primera carga, así que la mitad de las pantallas saltaba
   y la otra mitad no. Ahora todas hacen lo mismo y lo dicen: `vistaSinLegajo` explica
   cuál es el paso que falta y ofrece el botón para darlo. Devuelve siempre false; se
   conserva la firma porque quien la llama todavía mira el valor. */
/* Las comillas de la carátula, en castellano.

   La carátula la escribe una persona al crear el legajo y suele venir con comillas
   rectas —`"NN S/ PECULADO"`—, que es lo que tipea cualquier teclado. Rectas y pegadas
   al número de legajo, la línea del techo se lee como salida de una terminal y no como
   el nombre de una causa. Las comillas latinas son las que corresponden en castellano
   y además separan la carátula del número sin agregar ningún adorno.

   Es SÓLO para mostrar: en la base la carátula queda como la escribieron. Cambiarla
   ahí sería tocar un dato que alguien cargó, y esto es tipografía. */
function comillasLatinas(s) {
  let n = 0;
  return String(s || '').replace(/"/g, () => (n++ % 2 ? '»' : '«'));
}

function pintarLegajo(p) {
  const l = p.legajo;
  HAY_LEGAJO = !!l;
  BASE_SUELTA_CON_MATERIAL = !l && !!p.documentos;
  document.body.classList.toggle('con-legajo', !!l);
  document.body.classList.toggle('sin-legajo', sinLegajo());
  $('#l-numero').textContent = l ? l.numero : '—';
  $('#l-caratula').textContent = l ? comillasLatinas(l.caratula) : 'Ninguno abierto';
  $('#t-legajo').title = l
    ? `Legajo ${l.numero} — ${l.caratula}` + (l.fiscal ? ` · Fiscal: ${l.fiscal}` : '')
      + '\nTocá para cambiar de legajo'
    : 'Elegir un legajo';
  medirTecho();          // aparecer o irse el aviso corre todo lo de abajo
  return false;
}

/* La versión de interfaz que cargó ESTA pestaña. Se fija en el primer refresco y no
   cambia más: si el servidor pasa a informar otra, es que se actualizó abajo mientras
   la pestaña estaba abierta. Quien deja el sistema abierto todo el día seguiría usando
   la anterior sin enterarse. */
let VERSION_CARGADA = null;

/* ¿Hay legajo abierto? Lo sabe `refrescarCuentas()` y lo consultan las vistas antes
   de ofrecer cargar nada. `null` significa «todavía no se preguntó»: la diferencia
   importa, porque «no sé» y «no hay» llevan a pantallas distintas. */
let HAY_LEGAJO = null;
/* La instalación anterior a los legajos: tiene material en la base suelta y sigue
   trabajando ahí. A esa no se le corta la carga. */
let BASE_SUELTA_CON_MATERIAL = false;

const sinLegajo = () => HAY_LEGAJO === false && !BASE_SUELTA_CON_MATERIAL;

/* La pantalla que reemplaza a cualquier vista de datos cuando no hay legajo abierto.
   No es un error: es el paso que falta, dicho con el nombre del paso. */
function vistaSinLegajo(titulo) {
  vista.innerHTML = bloque('f. 0000', 'Sin legajo', `
    <h2>${esc(titulo)}</h2>
    ${vacio('Primero hay que abrir un legajo',
      'Cada legajo es una causa y tiene su propia base de datos: sus documentos, sus ' +
      'personas y sus totales viven en un archivo aparte. Hasta que no haya uno abierto ' +
      'no hay dónde leer ni dónde guardar.',
      {href:'#/legajos', texto:'Elegir o crear un legajo'})}`);
}

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
    ULTIMO_PANEL = p;
    pintarEstadoTecho();
    mirarSiTrabajoElOtro(p);
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

/* Las que tienen sentido sin legajo abierto: elegir uno, y todo lo que explica o
   diagnostica el sistema. El resto necesita una base detrás. */
/* ¿Es la primera pantalla que se pinta desde que se abrió la aplicación? Sirve para
   distinguir «entré y todavía no elegí legajo» —que es lo normal— de «estoy adentro y
   fui a una pantalla que necesita uno», que sí hay que explicar. */
let PRIMERA_PANTALLA = true;

const SIN_LEGAJO_IGUAL_ANDAN = new Set(
  ['#/legajos', '#/acerca', '#/salud', '#/como-funciona', '#/consultas']);

/* ── El trabajo de los demás ───────────────────────────────────────────────
   Sobre una misma causa trabajan varias personas al mismo tiempo, todas contra la
   misma base. El que tiene la cola abierta no se entera de lo que revisó el de al
   lado hasta que recarga, y mientras tanto ve filas que ya no existen.

   Lo que NO se hace: refrescar la lista sola. Arrancarle las filas de abajo del
   cursor a alguien que está a mitad de una decisión es peor que la desactualización
   —el campo que iba a marcar se corre un renglón y marca otro—. Se avisa, y actualiza
   cuando quiere.

   La cuenta es exacta y no hace falta llevar registro de nada: la cola sabe cuántos
   campos le quedan (`total_sin_filtro`, que baja con cada decisión propia) y el
   servidor dice cuántos quedan de verdad. La diferencia es trabajo ajeno. */
function mirarSiTrabajoElOtro(p) {
  const caja = $('#otros-revisaron');
  if (!caja || !colaEstado.filas.length) return;
  const ajenos = colaEstado.total_sin_filtro - Number(p.a_revisar || 0);
  if (ajenos > 0) {
    caja.innerHTML = `${sello('neutro',
      plural(ajenos, 'campo revisado por otra persona', 'campos revisados por otras personas'))}
      <button class="boton gris" id="b-actualizar-cola">Actualizar la lista</button>`;
    caja.hidden = false;
    $('#b-actualizar-cola').onclick = () => vCola();
  } else if (ajenos < 0) {
    // Entró material nuevo: alguien cargó y procesó un lote mientras esto estaba abierto.
    caja.innerHTML = `${sello('atencion',
      plural(-ajenos, 'campo nuevo para revisar', 'campos nuevos para revisar'))}
      <button class="boton gris" id="b-actualizar-cola">Actualizar la lista</button>`;
    caja.hidden = false;
    $('#b-actualizar-cola').onclick = () => vCola();
  } else {
    caja.hidden = true;
  }
}

/* Latido: mientras la pestaña está a la vista, se vuelve a preguntar cada quince
   segundos. Escondida no se pregunta nada —una pestaña olvidada toda la tarde no
   tiene por qué golpear el servidor— y al volver a ella se pregunta enseguida, que es
   justo cuando la persona quiere ver el estado de verdad. */
let LATIDO = null;
function latir() {
  clearTimeout(LATIDO);
  if (document.visibilityState !== 'visible') return;
  LATIDO = setTimeout(() => { refrescarCuentas().finally(latir); }, 15000);
}
addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') { refrescarCuentas(); latir(); }
  else clearTimeout(LATIDO);
});


/* -- La foliatura del papel, al lado de la pagina del PDF ------------------
   Las dos numeraciones juntas y nombradas distinto, a proposito. Es la confusion mas
   cara que tiene este sistema: un escrito que dice "a fojas 47" no habla de la pagina
   47 del archivo, y contestar con la pagina manda a alguien a mirar otro papel.

   Una foja sin foliatura anotada dice "sin detectar", NUNCA "sin foliar". No son lo
   mismo: la segunda es una afirmacion sobre el papel y la hace una persona. */
function selectorArchivo(archivos, sha, base) {
  return `<label>Archivo
    <select id="sel-archivo">${archivos.map(a =>
      `<option value="${esc(a.sha256)}"${a.sha256 === sha ? ' selected' : ''}>
        ${esc(a.nombre)} (${esc(a.fojas)} fojas)</option>`).join('')}</select></label>`;
}

function marcaDeOrigen(f) {
  if (f.origen === 'humano') return `<span class="sello">lo escribi\u00f3 ${esc(f.quien || 'una persona')}</span>`;
  const c = f.confianza == null ? '' : ` (confianza ${esc(f.confianza)})`;
  return `<span class="sello atencion">propuesto por el sistema${c}</span>`;
}

function htmlFoliatura(d) {
  const conAlgo = d.fojas.filter(h => h.foliaturas.length).length;
  return `<p class="prosa">La <strong>foliatura</strong> es el n\u00famero que tiene el
      papel. La <strong>p\u00e1gina</strong> es la posici\u00f3n en el archivo PDF. No son
      lo mismo y por eso se muestran separadas: un escrito que dice "a fojas 47" habla de
      la primera.</p>
    <p class="prosa">${esc(conAlgo)} de ${esc(d.fojas.length)} fojas tienen foliatura
      anotada. Que una foja no la tenga quiere decir que <em>no se detect\u00f3</em>, no
      que el papel no est\u00e9 foliado.</p>
    ${d.saltos.length ? `<h3>Lo que la foliatura muestra</h3>
      <p class="prosa">Son hechos del expediente, no errores del sistema. Una foja que
        falta puede ser una foja sacada; dos fojas con el mismo n\u00famero pueden ser un
        expediente incorporado con su propia numeraci\u00f3n.</p>
      <ul>${d.saltos.map(x => `<li><span class="sello atencion">${esc(x.clase)}</span>
        ${esc(x.detalle)}</li>`).join('')}</ul>` : ''}
    <h3>Foja por foja</h3>
    <div class="tabla-env"><table><thead><tr>
      <th>P\u00e1gina del PDF</th><th>Foliatura del papel</th><th>De d\u00f3nde sale</th>
    </tr></thead><tbody>${d.fojas.map(h => `<tr>
      <td class="mono">${esc(h.pagina_pdf)}</td>
      <td>${h.foliaturas.length
            ? h.foliaturas.map(f => `<span class="mono">${esc(f.literal || f.estado)}</span>${
                f.serie !== 'principal' ? ` <span class="sello">${esc(f.serie)}</span>` : ''}`).join(' ? ')
            : '<span class="apagado">sin detectar</span>'}</td>
      <td>${h.foliaturas.map(marcaDeOrigen).join(' ')}</td></tr>`).join('')}</tbody></table></div>`;
}

async function fetchFoliatura(sha) {
  return await api('/api/foliatura?sha=' + encodeURIComponent(sha));
}
async function fetchArchivos() {
  return await api('/api/archivos');
}

async function vFoliatura(sha) {
  if (location.hash.indexOf('#/foliatura') !== 0) return;
  const d = await fetchArchivos();
  const archivos = d.archivos || [];
  
  if (!archivos.length) {
    vista.innerHTML = bloque('', 'Documentos', '<p class="prosa">No hay archivos cargados todavía.</p>');
    return;
  }
  
  const elegido = sha || archivos[0].sha256;
  const f = await fetchFoliatura(elegido);
  if (location.hash.indexOf('#/foliatura') !== 0) return;
  
  const conAlgo = f.fojas && f.fojas.filter ? f.fojas.filter(h => h.foliaturas && h.foliaturas.length).length : 0;
  
  vista.innerHTML = bloque('', 'Documentos', `
    <div class="encabezado-vista">
      <h2>Foliatura del papel</h2>
      <p class="prosa">${esc(conAlgo)} de ${esc(f.total || (f.fojas && f.fojas.length) || 0)} fojas tienen foliatura anotada.</p>
    </div>
    
    <div class="controles-tabla">
      <div class="filtros-fila">
        ${selectorArchivo(archivos, elegido)}
      </div>
    </div>
    
    ${f.saltos && f.saltos.length ? `<h3>Saltos de foliatura</h3><ul>${f.saltos.map(x => `<li><span class="sello atencion">${esc(x.clase)}</span> ${esc(x.detalle)}</li>`).join('')}</ul>` : ''}
    
    <h3>Foja por foja</h3>
    <div id="lista-foliatura-paginada"></div>
  `);

  const sel = $('#sel-archivo');
  if (sel) sel.onchange = () => { location.hash = '#/foliatura/' + sel.value; };

  tablaServidor($('#lista-foliatura-paginada'), '/api/foliatura?sha=' + encodeURIComponent(elegido), 'fojas', [
    {t: 'Página del PDF', r: h => esc(h.pagina_pdf || h.foja), c: 'mono', o: 'id'},
    {t: 'Foliatura del papel', r: h => h.foliaturas && h.foliaturas.length ? h.foliaturas.map(x => `<span class="mono">${esc(x.nro)}</span>`).join(' o ') : ausente('Sin lectura')},
    {t: 'De dónde sale', r: h => h.foliaturas && h.foliaturas.length ? h.foliaturas.map(x => `<span class="chip">${esc(x.texto)}</span>`).join(' ') : '—'}
  ], {
    placeholder: 'Buscar foja...',
    vacio: 'No se encontraron fojas.',
    alClic: h => {
        if (h.foliaturas && h.foliaturas.length) {
            location.hash = '#/foja/' + encodeURIComponent(h.foliaturas[0].sha256) + '/' + (h.pagina_pdf || h.foja);
        }
    }
  });
}


/* -- Las tablas, como tablas y no como texto -------------------------------
   Una planilla dice lo que dice por renglon. Mostrarla aplanada pierde justamente lo
   que hace falta para comparar lo pactado con lo entregado y con lo facturado.

   Y la continuidad entre fojas se muestra como lo que es: una propuesta, mientras
   nadie la haya confirmado. */
function htmlTabla(t) {
  const filas = {};
  t.celdas.forEach(c => { (filas[c.fila] = filas[c.fila] || []).push(c); });
  const orden = Object.keys(filas).map(Number).sort((a, b) => a - b);
  const union = t.continua_de
    ? (t.union_quien
        ? `<span class="sello">contin\u00faa de otra tabla ? lo confirm\u00f3 ${esc(t.union_quien)}</span>`
        : `<span class="sello atencion">el sistema propone que contin\u00faa de otra tabla,
             y nadie lo confirm\u00f3 todav\u00eda</span>`)
    : '';
  return `<article class="nucleo-ficha">
    <h3>Foja ${esc(t.pagina_nro)} ? ${esc(t.filas)} filas \u00d7 ${esc(t.columnas)} columnas</h3>
    <p>${union} <span class="sello atencion">confianza ${esc(t.confianza)}</span></p>
    <div class="tabla-env"><table><tbody>${orden.map(i => `<tr>${
      filas[i].sort((a, b) => a.columna - b.columna).map(c =>
        c.es_encabezado ? `<th>${esc(c.texto)}</th>` : `<td>${esc(c.texto)}</td>`
      ).join('')}</tr>`).join('')}</tbody></table>
    <p><a href="#/tabla-renglones-${esc(t.id)}" data-renglones="${esc(t.id)}">Ver la tabla
      entera, siguiendo sus continuaciones</a></p>
    <div data-destino="${esc(t.id)}"></div></article>`;
}

// new_vTablas.js
async function obtenerTablasData(sha) {
  const d = await api('/api/archivos');
  const archivos = d.archivos || [];
  if (!archivos.length) return { archivos: [], tablas: [], elegido: null };
  const elegido = sha || archivos[0].sha256;
  const t = await api('/api/tablas?sha=' + encodeURIComponent(elegido));
  return { archivos, tablas: t.tablas || [], elegido };
}

async function vTablas(sha) {
  if (location.hash.indexOf('#/tablas') !== 0) return;
  const { archivos, tablas, elegido } = await obtenerTablasData(sha);
  if (location.hash.indexOf('#/tablas') !== 0) return;

  if (!archivos.length) {
    vista.innerHTML = bloque('', 'Documentos', '<p class="prosa">No hay archivos cargados todavía.</p>');
    return;
  }

  let pagina = 0;
  const porPagina = 50;

  const render = () => {
    const total = tablas.length;
    const inicio = pagina * porPagina;
    const fin = inicio + porPagina;
    const muestra = tablas.slice(inicio, fin);

    let contenido = selectorArchivo(archivos, elegido);
    if (!total) {
      contenido += `<p class="prosa">No se reconoció ninguna tabla en este archivo.</p>`;
      vista.innerHTML = bloque('', 'Documentos', contenido);
    } else {
      contenido += `<p class="prosa">Se detectaron <strong>${total} tablas</strong>. Elegí una para ver sus renglones.</p>`;
      
      const htmlTabla = tabla([
        {t: 'Foja', c: 'num', r: a => esc(a.pagina_nro)},
        {t: 'Tamaño', r: a => `${esc(a.filas)} filas × ${esc(a.columnas)} cols`},
        {t: 'Confianza', r: a => barraConf(a.confianza) + ' ' + fmtPct(a.confianza * 100)},
        {t: 'Continuación', r: a => a.continua_de ? (a.union_quien ? `Sí (por ${esc(a.union_quien)})` : 'Propuesta') : '—'}
      ], muestra, { alClic: true, lista: 'tablas' });

      const controles = total > porPagina ? `<div class="paginacion">
        <button class="boton gris" id="btn-ant" ${pagina === 0 ? 'disabled' : ''}>Anterior</button>
        <span class="paginacion-info">${inicio + 1}–${Math.min(fin, total)} de ${fmtNum.format(total)}</span>
        <button class="boton gris" id="btn-sig" ${fin >= total ? 'disabled' : ''}>Siguiente</button>
      </div>` : '';

      vista.innerHTML = bloque('', 'Documentos', contenido + htmlTabla + controles);

      vista.querySelectorAll('.tabla-env tbody tr').forEach((tr, i) => {
        tr.onclick = () => {
          const t = muestra[i];
          location.hash = `#/tabla-renglones-${t.id}`;
        };
      });

      if (pagina > 0) $('#btn-ant').onclick = () => { pagina--; render(); };
      if (fin < total) $('#btn-sig').onclick = () => { pagina++; render(); };
    }

    const sel = $('#sel-archivo');
    if (sel) sel.onchange = () => { location.hash = '#/tablas/' + sel.value; };
  };

  render();
}


/* -- La cronologia, que no es el orden de las fojas ------------------------
   Un expediente se arma por incorporacion: lo que se agrega ultimo puede relatar lo que
   paso primero. Ordenar por foja y llamarlo cronologia es la forma mas rapida de contar
   mal una historia.

   Cada fecha dice QUE clase de fecha es, porque un acta que relata un hecho de marzo,
   firmada en abril y recibida en mayo, apareceria en el lugar equivocado si se las
   mezclara. */
function htmlCronologia(d, clase) {
  // El servidor manda `linea` y cada clase con `clave` y `que_es`; se aceptan también
  // los nombres viejos, para no depender de la versión del otro lado.
  const filas = d.linea || d.filas || [];
  const cuenta = {};
  filas.forEach(f => { cuenta[f.clase] = (cuenta[f.clase] || 0) + 1; });
  const opts = (d.clases || []).map(c => `<option value="${esc(c.clave)}" ${clase === c.clave ? 'selected' : ''}>${
    esc(c.rotulo || c.que_es || c.clave)}${cuenta[c.clave] ? ` (${fmtNum.format(cuenta[c.clave])})` : ''}</option>`).join('');
  const queEs = Object.fromEntries((d.clases || []).map(c => [c.clave, c.que_es || c.rotulo || c.clave]));
  const evs = filas.map(f => `<div class="evento-timeline">
    <div class="evento-fecha">${esc(fmtFecha(f.fecha) || f.literal || '')}</div>
    <div class="evento-cuerpo">
      <div class="evento-clase">${esc(f.clase_rotulo || f.que_es || queEs[f.clase] || f.clase || '')}${
        f.literal ? ` <span class="celda-nota">«${esc(f.literal)}»</span>` : ''}</div>
      <div class="evento-doc">${esc(f.documento || TIPO_DOC[f.tipo] || f.tipo || '')}${f.archivo ? ` · ${esc(String(f.archivo).replace(/\.pdf$/i, ''))}` : ''}</div>
      ${f.origen === 'humano' ? `<div class="evento-doc">${sello('neutro', 'La cargó ' + (f.quien || 'una persona'))}</div>` : ''}
      ${f.sha256 ? `<a class="evento-fuente" href="javascript:void(0)" onclick="abrirFojaSuelta('${esc(f.sha256)}', ${Number(f.pagina_nro)})">ver foja ${esc(String(f.pagina_nro))}</a>` : ''}
    </div>
  </div>`).join('');
  const total = d.total ?? filas.length;
  return `<h2>Cronología</h2>
    <p class="prosa">Ordenada por <strong>fecha</strong>, no por el orden en que están las fojas.
      Cada hecho dice qué clase de fecha es y de qué foja sale.</p>
    <div class="filtros-fila"><label>Clase de fecha <select id="sel-clase"><option value="">todas</option>${opts}</select></label>
      <span class="cuantas">${fmtNum.format(total)} ${total === 1 ? 'hecho' : 'hechos'}</span></div>
    ${Array.isArray(d.desordenes) && d.desordenes.length ? `<h3>Lo que la cronología muestra</h3>
      <p class="nota-seccion">Un expediente se arma por incorporación: lo que se agregó último
        puede relatar lo que pasó primero. Esto se señala, no se denuncia.</p>
      <ul class="advertencias">${d.desordenes.map(x => `<li>${sello('atencion',
        String(x.clase || '').replace(/_/g, ' '))} ${esc(x.archivo || '')} ${esc(x.detalle || '')}</li>`).join('')}</ul>` : ''}
    ${filas.length ? `<div class="timeline">${evs}</div>` : vacio('Todavía no hay hechos fechados',
      'La línea de tiempo se arma con las fechas ya leídas de los documentos —la de emisión, ' +
      'una firma, una recepción—, y sólo entran las que están en estado firme: una fecha dudosa ' +
      'en una cronología se lee igual que una segura.')}
    ${total > filas.length ? `<p class="nota-seccion">Se muestran los primeros ${fmtNum.format(filas.length)}.</p>` : ''}`;
}
async function vCronologia() {
  const clase = new URLSearchParams(location.hash.split('?')[1] || '').get('clase') || '';
  const d = await api('/api/cronologia?limite=200' + (clase ? '&clase=' + encodeURIComponent(clase) : ''));
  if (location.hash.indexOf('#/cronologia') !== 0) return;
  vista.innerHTML = bloque('f. 0000', 'Investigación', htmlCronologia(d, clase));
  const sel = $('#sel-clase');
  if (sel) sel.onchange = () => {
    location.hash = '#/cronologia' + (sel.value ? '?clase=' + sel.value : '');
    vCronologia();
  };
}


/* Menciones conservan el literal; decisiones conservan su autor. */
function fuenteMencion(m) {
  return `<span class="mono">${esc(m.archivo || '\u00d8 archivo no informado')} \u00b7 foja ${esc(m.pagina_nro ?? '\u00d8 no informada')}</span>
    ${m.documento_id ? `<a href="#/documento/${esc(m.documento_id)}">Ver documento</a>` : ''}
    <span>Fuente: ${esc(m.origen || '\u00d8 no informada')} \u00b7 confianza ${esc(m.confianza ?? '\u00d8 no informada')}</span>`;
}
function htmlMenciones(ms) {
  return ms.length ? `<div class="tabla-env"><table><thead><tr><th>Lo que dice el papel</th><th>Fuente</th></tr></thead><tbody>${ms.map(m => `<tr><td class="mono">${esc(m.literal)}</td><td>${fuenteMencion(m)}</td></tr>`).join('')}</tbody></table></div>` : '<p>No hay menciones para mostrar.</p>';
}
function htmlEntidad(e) {
  return `<h2>${esc(e.nombre)}</h2><p>${esc(e.clase)} \u00b7 Clave fuerte: <span class="mono">${esc(e.clave_fuerte || '\u00d8 sin clave')}</span></p><p>${e.quien ? `Afirmado por ${esc(e.quien)}` : (e.clave_fuerte ? 'Resuelto por el sistema por clave fuerte' : '\u00d8 autor de resoluci\u00f3n no informado')}</p><h3>Todas las formas que dice el papel</h3>${htmlMenciones(e.menciones)}`;
}
function htmlRelaciones(rs, decidir = false) {
  return rs.length ? rs.map(r => {
    const estado = r.estado || 'propuesta';
    return `<article class="${estado === 'confirmada' ? 'revision-confirmada' : 'revision-propuesta'}"><h3>${esc(r.hacia || '')} \u00b7 ${esc(r.que_dice || r.tipo)} \u00b7 ${esc(estado)}</h3><p>${r.desde_doc ? `<a href="#/documento/${esc(r.desde_doc)}">${esc(r.archivo_desde || r.desde_doc)}</a>` : '\u00d8 documento de origen no informado'} \u2192 ${r.hasta_doc ? `<a href="#/documento/${esc(r.hasta_doc)}">${esc(r.archivo_hasta || r.hasta_doc)}</a>` : '\u00d8 documento de destino no informado'}</p><p>Fuente: ${esc(r.fuente || '\u00d8 no informada')} \u00b7 confianza ${esc(r.confianza ?? '\u00d8 no informada')}${r.quien ? ` \u00b7 Decidi\u00f3 ${esc(r.quien)}` : ''}</p><p>${esc(r.nota || '')}</p>${decidir && estado === 'propuesta' ? `<button class="boton" data-relacion="${esc(r.id)}" data-aceptar="true">Confirmar</button> <button class="boton gris" data-relacion="${esc(r.id)}" data-aceptar="false">Rechazar y conservar constancia</button>` : ''}</article>`;
  }).join('') : '<p>No hay relaciones para mostrar.</p>';
}
function htmlTiposRelacion(tipos) {
  return `<label>Tipo <select name="tipo" required><option value="">Eleg\u00ed qu\u00e9 afirma la relaci\u00f3n</option>${tipos.map(t => `<option value="${esc(t.clave)}">${esc(t.que_dice)}</option>`).join('')}</select></label>`;
}
async function accionInterfaz(b, tarea) {
  b.disabled = true;
  try { await tarea(); } catch (e) { toast(e.message); } finally { b.disabled = false; }
}
async function vEntidades() {
  const hash = location.hash;
  const hashParams = new URLSearchParams(hash.split('?')[1] || '');
  const clase = hashParams.get('clase') || '';
  const ver = hashParams.get('ver') || '';
  
  const urlParams = clase ? '?clase=' + encodeURIComponent(clase) : '';
  const d = await api('/api/entidades' + urlParams);
  if (location.hash !== hash) return;

  const tFichas = d.total || 0;
  const tSinResolver = d.sin_resolver_paginacion ? d.sin_resolver_paginacion.total : 0;
  const tPropuestas = d.propuestas_paginacion ? d.propuestas_paginacion.total : 0;

  vista.innerHTML = bloque('f. 0000', 'Revisión', `
    <h1>Todas las fichas</h1>
    <p class="prosa">Cada persona, empresa, organismo o expediente que el sistema identificó, con cuántas veces aparece.</p>
    
    <div class="filtros-chips">
      <a href="#/entidades${clase ? '?clase='+encodeURIComponent(clase) : ''}" class="chip-filtro${!ver ? ' activo' : ''}">
        Fichas <span class="chip-n">${tFichas}</span>
      </a>
      <a href="#/entidades?ver=sin-resolver${clase ? '&clase='+encodeURIComponent(clase) : ''}" class="chip-filtro${ver === 'sin-resolver' ? ' activo' : ''}">
        Menciones sin resolver <span class="chip-n">${tSinResolver}</span>
      </a>
      <a href="#/entidades?ver=propuestas${clase ? '&clase='+encodeURIComponent(clase) : ''}" class="chip-filtro${ver === 'propuestas' ? ' activo' : ''}">
        Propuestas de fusión <span class="chip-n">${tPropuestas}</span>
      </a>
    </div>

    ${!ver ? `
      <div class="filtros-chips">
        <a href="#/entidades" class="chip-filtro${!clase ? ' activo' : ''}">Todas</a>
        ${d.clases.map(c => `<a href="#/entidades?clase=${encodeURIComponent(c.clave)}" class="chip-filtro${clase === c.clave ? ' activo' : ''}">${esc(c.que_es)}</a>`).join('')}
      </div>
      <div id="entidades-es"></div>
    ` : ''}

    ${ver === 'sin-resolver' ? `<div id="entidades-ms"></div>` : ''}
    ${ver === 'propuestas' ? `<div id="entidades-ps"></div>` : ''}
  `);

  if (!ver) {
    const urlE = '/api/entidades' + urlParams;
    tablaServidor($('#entidades-es'), urlE, 'entidades', [
      {t: 'Nombre', o: 'nombre', r: e => `<a href="#/${e.carril === 'persona' ? 'persona' : (e.clase === 'empresa' ? 'proveedor' : 'entidad')}/${esc(e.id)}">${esc(e.nombre || '') || ausente('no_consta')}</a>`, k: 'nombre'},
      {t: 'Clase', o: 'clase', r: e => esc(e.clase).toLowerCase()},
      {t: 'Clave', o: 'documentos', c: 'mono', r: e => esc(e.clave_fuerte || '') || ausente('no_consta')},
      {t: 'Documentos', o: 'documentos', r: e => e.documentos},
      {t: 'Menciones', o: 'menciones', r: e => e.menciones}
    ], {placeholder: 'Buscar entidad...', vacio: vacio('Sin fichas', 'No hay fichas.', ''), orden: 'documentos', sentido: 'desc'});
  } else if (ver === 'sin-resolver') {
    const urlM = '/api/entidades/sin-resolver' + urlParams;
    tablaServidor($('#entidades-ms'), urlM, 'sin_resolver', [
      {t: 'Lo que dice el papel', o: 'nombre', c: 'mono', r: m => esc(m.literal)},
      {t: 'Clase', o: 'clase', r: m => esc(m.clase).toLowerCase()},
      {t: 'Archivo', r: m => `<span class="mono">${esc(m.archivo)}</span>`},
      {t: 'Foja', r: m => m.documento_id ? `<a href="#/documento/${esc(m.documento_id)}">foja ${esc(m.pagina_nro)}</a>` : ausente('no_consta')}
    ], {placeholder: 'Buscar mención...', vacio: vacio('Sin menciones', 'No hay menciones sin resolver.', '')});
  } else if (ver === 'propuestas') {
    const urlP = '/api/entidades/propuestas' + urlParams;
    tablaServidor($('#entidades-ps'), urlP, 'propuestas', [
      {t: 'Clase', o: 'clase', r: p => esc(p.clase).toLowerCase()},
      {t: 'Formas en que aparece', o: 'nombre', r: p => p.literales.map(esc).join(' / ')},
      {t: 'Veces', o: 'veces', r: p => esc(p.veces)},
      {t: 'Decisión', r: p => `<button class="boton" type="button" data-abrir-fusion="${esc(p.norm)}" data-clase="${esc(p.clase)}">Decidir</button>`}
    ], {
      vacio: vacio('Sin propuestas', 'No hay propuestas de fusión.', ''),
      orden: 'veces', sentido: 'desc',
      alCargar: r => {
        vista.querySelectorAll('[data-abrir-fusion]').forEach(b => {
          if (b.dataset.binded) return;
          b.dataset.binded = '1';
          b.onclick = () => {
            const norm = b.dataset.abrirFusion, clase = b.dataset.clase;
            const d = dialogo(`
              <form class="revision-propuesta" data-fusion="${esc(norm)}" data-clase="${esc(clase)}">
                <label>Nombre que afirmás <input name="nombre" required autocomplete="off"></label>
                <div class="fila-acciones">
                  <button class="boton" type="submit">Confirmar con este nombre</button>
                  <button class="boton gris" type="button" data-rechazar-fusion>Rechazar: no volver a preguntar</button>
                </div>
              </form>
            `);
            const f = d.querySelector('form');
            const enviar = async (btn, aceptar) => accionInterfaz(btn, async () => {
              const quien = await conRevisor(); if (!quien) return;
              await guardarNucleo('/api/entidad/' + (aceptar ? 'confirmar' : 'rechazar'), {clase: f.dataset.clase, norm: f.dataset.fusion, nombre: f.elements.nombre.value.trim(), quien});
              d.close();
              await vEntidades();
            });
            f.onsubmit = e => { e.preventDefault(); enviar(f.querySelector('[type="submit"]'), true); };
            f.querySelector('[data-rechazar-fusion]').onclick = e => enviar(e.currentTarget, false);
          };
        });
      }
    });
  }
}

async function vEntidad(id) {
  const hash = location.hash, e = await api('/api/entidad?id=' + id);
  if (hash !== location.hash) return;
  
  const docsCount = e.documentos ? e.documentos.length : (e.menciones ? new Set(e.menciones.map(m => m.documento_id)).size : 0);
  const mencionesCount = e.menciones ? e.menciones.length : 0;
  const contratacionesCount = e.contrataciones ? e.contrataciones.length : 0;

  const ausente = (motivo) => `<span class="nulo" title="${esc(motivo)}">—</span>`;

  vista.innerHTML = bloque('e. ' + String(id).padStart(4,'0'), 'Proveedor', `
    <div class="cabecera-ficha">
      <h2>${esc(e.nombre)}</h2>
      <div class="identificadores">
        <span class="etiqueta">${esc(e.clase)}</span>
        <span class="mono">${e.clave_fuerte ? esc(e.clave_fuerte) : ausente('Sin clave fuerte registrada')}</span>
      </div>
    </div>
    
    <div class="cifras sep-corta">
      <div class="cifra"><b>${docsCount}</b><span>documentos</span></div>
      <div class="cifra"><b>${contratacionesCount}</b><span>contrataciones</span></div>
      <div class="cifra"><b>${mencionesCount}</b><span>menciones</span></div>
    </div>

    <p class="prosa nota">
      ${e.quien ? `Ficha revisada y confirmada por <strong>${esc(e.quien)}</strong>.` : (e.clave_fuerte ? 'Entidad consolidada automáticamente por el sistema coincidiendo su clave fuerte.' : 'Entidad sin validación humana informada.')}
    </p>

    <h3>Apariciones en los documentos</h3>
    <p class="prosa">Cómo aparece escrito el nombre en los distintos papeles originales.</p>
    <div id="entidad-menciones"></div>
  `);
  
  if (e.menciones && e.menciones.length) {
      tablaBuscable($('#entidad-menciones'), [
        {t: 'Mención literal', c: 'mono', r: m => esc(m.literal)},
        {t: 'Fuente', r: m => fuenteMencion(m) || ausente('Sin fuente')}
      ], e.menciones);
  } else {
      $('#entidad-menciones').innerHTML = '<div class="vacio">No hay menciones registradas.</div>';
  }
}

function enlazarDecisionesRelacion(host, refrescar) {
  host.querySelectorAll('[data-relacion]').forEach(b => b.onclick = () => accionInterfaz(b, async () => {
    const quien = await conRevisor(); if (!quien) return;
    await guardarNucleo('/api/relacion/decidir', {id:Number(b.dataset.relacion), aceptar:b.dataset.aceptar === 'true', quien});
    await refrescar();
  }));
}
async function vRelaciones() {
  const hash = location.hash, d = await api('/api/relaciones');
  const docs = await api('/api/contratos');
  if (hash !== location.hash) return;
  
  const opciones = docs.map(c => 
    `<option value="${c.documento_id}">${esc(c.nombre_literal || c.documento_literal || c.archivo || 'Desconocido')} (f. ${c.pagina_desde || '?'})</option>`
  ).join('');

  vista.innerHTML = bloque('', 'Relaciones', `
  <div class="cabecera-seccion">
    <h2>Relaciones entre documentos</h2>
    <p class="prosa">Las relaciones permiten conectar documentos que se referencian mutuamente.</p>
  </div>
  
  <div class="paneles-dobles">
    <div class="panel">
      <h3>Propuestas pendientes</h3>
      <p class="prosa nota">Son propuestas detectadas por el sistema. Rechazar conserva la decisión para no volver a proponerla.</p>
      <div id="relaciones-pendientes" class="lista-relaciones">
        ${typeof htmlRelaciones === 'function' ? (d && d.length ? htmlRelaciones(d) : '<div class="vacio">No hay relaciones propuestas pendientes.</div>') : (d && d.length ? `<div class="vacio">Hay ${d.length} propuestas.</div>` : '<div class="vacio">No hay propuestas.</div>')}
      </div>
    </div>
    
    <div class="panel panel-formulario">
      <h3>Anotar relación manual</h3>
      <form id="anotar-relacion" class="formulario-estilizado">
        <datalist id="lista-docs">${opciones}</datalist>
        
        <div class="campo">
          <label for="desde">Documento origen</label>
          <input id="desde" name="desde" list="lista-docs" autocomplete="off" placeholder="Escribí para buscar documento..." required>
        </div>
        
        <div class="campo">
          <label for="hasta">Documento destino</label>
          <input id="hasta" name="hasta" list="lista-docs" autocomplete="off" placeholder="Escribí para buscar documento..." required>
        </div>
        
        <div class="campo">
          <label for="nota">Nota de respaldo (opcional)</label>
          <textarea id="nota" name="nota" placeholder="Por qué están relacionados..." rows="3"></textarea>
        </div>
        
        <button type="submit" class="boton primario">Registrar relación</button>
      </form>
    </div>
  </div>
  `);
  
  if (typeof enlazarDecisionesRelacion === 'function') {
      enlazarDecisionesRelacion(vista, vRelaciones);
  }
  
  $('#anotar-relacion').onsubmit = e => { 
      e.preventDefault(); 
      const f = e.currentTarget; 
      accionInterfaz(f.querySelector('button'), async () => {
          const quien = await conRevisor(); if (!quien) return;
          await guardarNucleo('/api/relacion/anotar', {
              tipo: f.elements.tipo ? f.elements.tipo.value : 'referencia', 
              desde_doc: Number(f.elements.desde.value), 
              hasta_doc: Number(f.elements.hasta.value), 
              nota: f.elements.nota.value, 
              quien
          });
          await vRelaciones();
      }); 
  };
}


async function cargarRelacionesDocumento(id) {
  const host = $('#relaciones-documento');
  try {
    const d = await api('/api/relaciones/documento?id=' + id);
    if (!host.isConnected) return;
    host.innerHTML = `<h3>Relaciones: sale / llega</h3>${htmlRelaciones(d.relaciones)}<a href="#/relaciones">Revisar o anotar relaciones</a>`;
  } catch(e) { if (host.isConnected) host.textContent = e.message; }
}
/* Consultas se ejecutan otra vez; colecciones solo cambian por una accion. */
function htmlGuardadas(d) {
  return `<h2>Consultas guardadas</h2><p class="prosa">Una consulta guardada vuelve a ejecutar una b\u00fasqueda con sus filtros. Sus resultados cambian cuando cambian los datos. Una colecci\u00f3n contiene lo apartado a mano y no cambia sola.</p>${d.consultas.length ? d.consultas.map(c => `<article class="revision-confirmada"><h3>${esc(c.nombre)}</h3><p>${esc(c.consulta)} \u00b7 Guard\u00f3 ${esc(c.quien)}</p><p>Filtros: ${esc(JSON.stringify(c.filtros))}</p><button class="boton" data-ejecutar="${esc(c.id)}">Volver a buscar</button> <button class="boton gris" data-borrar-consulta="${esc(c.id)}">Borrar consulta guardada</button></article>`).join('') : '<p>No hay consultas guardadas. Guard\u00e1 una desde Buscar.</p>'}`;
}
function htmlColecciones(d) {
  return `<h2>Colecciones</h2><p class="prosa">Una colecci\u00f3n es una selecci\u00f3n manual: no cambia sola al cargar documentos. Una consulta guardada vuelve a buscar y sus resultados pueden cambiar.</p>${d.colecciones.length ? d.colecciones.map(c => `<article class="revision-confirmada"><h3><a href="#/coleccion/${esc(c.id)}">${esc(c.nombre)}</a></h3><p>${esc(c.items)} elementos \u00b7 Apart\u00f3 ${esc(c.quien)}</p><p>${esc(c.nota || '')}</p></article>`).join('') : '<p>No hay colecciones. Pod\u00e9s crear una para apartar material.</p>'}<form id="crear-coleccion"><label>Nombre <input name="nombre" required></label><label>Nota <textarea name="nota"></textarea></label><button class="boton">Crear colecci\u00f3n</button></form>`;
}
function htmlColeccion(c) {
  return `<h2>${esc(c.nombre)}</h2><p>Colecci\u00f3n manual: no cambia sola. Cre\u00f3 ${esc(c.quien)}.</p><p>${esc(c.nota || '')}</p>${c.items.length ? `<div class="tabla-env"><table><thead><tr><th>Elemento</th><th>Fuente</th><th>Qui\u00e9n y nota</th><th>Acci\u00f3n</th></tr></thead><tbody>${c.items.map((i,n) => `<tr><td>${esc(i.clase)} \u00b7 ${esc(i.nombre || i.que_es)} \u00b7 ${esc(i.referencia)}</td><td>${esc(i.archivo || '\u00d8 sin archivo')} \u00b7 fojas ${esc(i.fojas || '\u00d8 no corresponde')}</td><td>${esc(i.quien)} \u00b7 ${esc(i.nota || '')}</td><td><button class="mini" data-quitar-item="${n}">Quitar de la colecci\u00f3n</button></td></tr>`).join('')}</tbody></table></div>` : '<p>Esta colecci\u00f3n no tiene elementos.</p>'}`;
}
async function vGuardadas() {
  const hash = location.hash, d = await api('/api/consultas-guardadas'); if (hash !== location.hash) return;
  vista.innerHTML = bloque('', 'Consultas guardadas', htmlGuardadas(d));
  vista.querySelectorAll('[data-ejecutar]').forEach(b => b.onclick = () => {
    const c = d.consultas.find(c => String(c.id) === b.dataset.ejecutar);
    if (Object.keys(c.filtros || {}).length) { toast('El servidor de b\u00fasqueda no expone filtros todav\u00eda. No se ejecutar\u00e1 una consulta distinta de la guardada.'); return; }
    location.hash = '#/buscar/' + encodeURIComponent(c.consulta);
  });
  vista.querySelectorAll('[data-borrar-consulta]').forEach(b => b.onclick = () => accionInterfaz(b, async () => { await guardarNucleo('/api/consulta/borrar', {id:Number(b.dataset.borrarConsulta)}); await vGuardadas(); }));
}
async function vColecciones() {
  const hash = location.hash, d = await api('/api/colecciones'); if (hash !== location.hash) return;
  vista.innerHTML = bloque('', 'Colecciones', htmlColecciones(d));
  $('#crear-coleccion').onsubmit = e => { e.preventDefault(); const f = e.currentTarget; accionInterfaz(f.querySelector('button'), async () => {
    const quien = await conRevisor(); if (!quien) return;
    const c = await guardarNucleo('/api/coleccion/crear', {nombre:f.elements.nombre.value.trim(), nota:f.elements.nota.value, quien}); location.hash = '#/coleccion/' + c.id;
  }); };
}
async function vColeccion(id) {
  const hash = location.hash, c = await api('/api/coleccion?id=' + id); if (hash !== location.hash) return;
  vista.innerHTML = bloque('', 'Colecci\u00f3n', htmlColeccion(c));
  vista.querySelectorAll('[data-quitar-item]').forEach(b => b.onclick = () => accionInterfaz(b, async () => {
    const i = c.items[Number(b.dataset.quitarItem)];
    await guardarNucleo('/api/coleccion/quitar', {coleccion_id:Number(id), clase:i.clase, referencia:i.referencia}); await vColeccion(id);
  }));
}
async function apartarResultado(clase, referencia) {
  const d = await api('/api/colecciones');
  if (!d.clases.includes(clase)) throw new Error('El servidor no permite apartar esta clase de resultado.');
  const modal = dialogo(`<h3>Apartar en una colecci\u00f3n</h3><p>Selecci\u00f3n manual: no cambia sola.</p>${d.colecciones.length ? `<form id="apartar"><label>Colecci\u00f3n <select name="coleccion" required><option value="">Eleg\u00ed una colecci\u00f3n</option>${d.colecciones.map(c => `<option value="${esc(c.id)}">${esc(c.nombre)}</option>`).join('')}</select></label><label>Nota <textarea name="nota"></textarea></label><button class="boton">Apartar</button></form>` : '<p>No hay colecciones. <a href="#/colecciones">Cre\u00e1 una primero</a>.</p>'}<button class="boton gris" data-cerrar>Cerrar</button>`);
  modal.querySelector('[data-cerrar]').onclick = () => modal.close();
  const enlace = modal.querySelector('a'); if (enlace) enlace.onclick = () => modal.close();
  const f = modal.querySelector('form'); if (f) f.onsubmit = e => { e.preventDefault(); accionInterfaz(f.querySelector('button'), async () => {
    const quien = await conRevisor(); if (!quien) return;
    await guardarNucleo('/api/coleccion/agregar', {coleccion_id:Number(f.elements.coleccion.value), clase, referencia:String(referencia), quien, nota:f.elements.nota.value}); modal.close();
  }); };
}
function htmlResumenBusqueda(r) {
  const total = (r.campos_total ?? r.campos.length) + (r.paginas_total ?? r.paginas.length);
  return `<p class="prosa">Total: ${esc(total)} coincidencias (${esc(r.campos_total ?? r.campos.length)} en datos; ${esc(r.paginas_total ?? r.paginas.length)} en fojas). Mostradas: ${r.campos.length + r.paginas.length}.</p>${total < 10 && r.variantes?.length ? `<p>Buscaste <span class="mono">${esc(r.consulta)}</span>; el OCR pudo haber le\u00eddo lo mismo como: ${r.variantes.map(v => `<a href="#/buscar/${encodeURIComponent(v)}">${esc(v)}</a>`).join(' \u00b7 ')}. Son variantes de lectura, no equivalencias confirmadas.</p>` : ''}`;
}
function acumularBusqueda(previa, siguiente) {
  if (siguiente.desde <= previa.desde) throw new Error('El servidor repiti\u00f3 la p\u00e1gina. No se agregaron duplicados; quedan resultados sin traer.');
  const unir = (a,b,clave) => { const vistos = new Set(a.map(clave)); return a.concat(b.filter(x => { const k = clave(x); if (vistos.has(k)) return false; vistos.add(k); return true; })); };
  return {...siguiente, campos:unir(previa.campos, siguiente.campos, x => JSON.stringify([x.documento_id,x.campo,x.valor_literal,x.pagina_nro])), paginas:unir(previa.paginas, siguiente.paginas, x => JSON.stringify([x.sha256,x.nro]))};
}


/* -- Informes: lo que se adjunta a un escrito ------------------------------
   Todo lo que sale lleva de donde salio: archivo, foja y, cuando corresponde, el
   recuadro. Una planilla con importes que no se puede volver a atar al papel no sirve
   para ofrecer prueba: del otro lado van a preguntar de donde salio cada numero, y
   "del sistema" no es una respuesta.

   Los informes ordenan y describen. No concluyen. Eso se dice en la pantalla y va
   tambien en el pie de cada archivo que sale. */
function htmlInformes(informes, colecciones) {
  return `<p class="prosa">Estos informes <strong>ordenan y describen</strong> lo que el
      sistema ley\u00f3 de los originales. No sacan conclusiones sobre responsabilidad,
      intenci\u00f3n ni licitud: eso lo escribe quien firma. Cada fila dice el archivo y
      la foja de donde sale, para poder verificarla contra el papel.</p>
    ${informes.map(i => `<article class="nucleo-ficha">
      <h3>${esc(i.nombre)}</h3>
      ${i.descripcion ? `<p class="prosa nota explicacion-informe">${esc(i.descripcion)}</p>` : ''}
      ${i.necesita === 'coleccion_id' ? (colecciones.length
        ? `<label>Colecci\u00f3n
             <select data-coleccion-de="${esc(i.clave)}">${colecciones.map(c =>
               `<option value="${esc(c.id)}">${esc(c.nombre)} (${esc(c.items)})</option>`
             ).join('')}</select></label>`
        : '<p class="apagado">Todav\u00eda no hay ninguna colecci\u00f3n armada.</p>') : ''}
      ${i.necesita === 'documento_ids'
        ? '<p class="apagado">Se arma desde una colecci\u00f3n o desde la b\u00fasqueda.</p>'
        : `<p class="botonera">${i.formatos.map(f =>
            `<button class="boton" data-informe="${esc(i.clave)}" data-formato="${esc(f)}"
               ${i.necesita === 'coleccion_id' && !colecciones.length ? 'disabled' : ''}
             >Sacar en ${esc(f.toUpperCase())}</button>`).join(' ')}</p>`}
    </article>`).join('')}
    <div id="salida-informe"></div>`;
}

async function vInformes() {
  const [d, c] = await Promise.all([api('/api/informes'), api('/api/colecciones')]);
  if (location.hash !== '#/informes') return;
  const colecciones = c.colecciones || [];
  vista.innerHTML = bloque('', 'Documentos', htmlInformes(d.informes, colecciones));
  vista.querySelectorAll('[data-informe]').forEach(b => b.onclick = async () => {
    const clave = b.dataset.informe;
    const sel = vista.querySelector(`[data-coleccion-de="${clave}"]`);
    b.disabled = true;
    const salida = $('#salida-informe');
    try {
      const r = await api('/api/informe', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({clave, formato: b.dataset.formato,
                              coleccion_id: sel ? +sel.value : undefined})});
      salida.innerHTML = `<p class="prosa">Qued\u00f3
        <span class="mono">${esc(r.archivo)}</span> en
        <span class="mono">${esc(r.carpeta)}</span>.</p>`;
    } catch (e) {
      salida.innerHTML = `<p class="prosa">${esc(e.message)}</p>`;
    } finally { b.disabled = false; }
  });
}

const rutas = [
  [/^#\/contrataciones$/, vContrataciones],
  [/^#\/contratacion\?id=(\d+)$/, vContratacion],
  [/^#\/precios$/, vPrecios],
  [/^#\/renglon\?id=(\d+)$/, vRenglon],
  [/^#\/hallazgos(\?.*)?$/, vHallazgosContrataciones],
  [/^#\/entidades(\?.*)?$/, vEntidades],
  [/^#\/entidad\/(\d+)$/, vEntidad],
  [/^#\/proveedor\/(\d+)$/, vProveedor],
  [/^#\/proveedores(\?.*)?$/, vProveedores],
  [/^#\/piezas(\?.*)?$/, vPiezas],
  [/^#\/relaciones$/, vRelaciones],
  [/^#\/guardadas$/, vGuardadas],
  [/^#\/colecciones$/, vColecciones],
  [/^#\/informes$/, vInformes],
  [/^#\/coleccion\/(\d+)$/, vColeccion],
  [/^#\/sin-reconocer$/, vSinReconocer],
  [/^#\/foliatura\/?(.*)$/, vFoliatura],
  [/^#\/tablas\/?(.*)$/, vTablas],
  [/^#\/cronologia(\?.*)?$/, vCronologia],
  [/^#\/conjuntos$/, vConjuntos],
  [/^#\/legajos$/,               vLegajos],
  [/^#\/papelera(\?.*)?$/,              vPapelera],
  [/^#\/panel$/,                 vPanel],
  [/^#\/reasociaciones$/,       vReasociaciones],
  [/^#\/actualizacion$/,         vActualizacion],
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
  [/^#\/equipo$/,                vEquipo],
  [/^#\/afuera$/,                vAfuera],
  [/^#\/fojas$/,                 vFojas],
  [/^#\/numeros$/,               vNumeros],
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
  /* Sin legajo abierto hay dos situaciones distintas y no se contestan igual.

     ABRIR LA APLICACIÓN sin legajo es lo NORMAL, no un error: la sesión anterior se
     cerró y la cookie que recuerda el legajo muere con el navegador, a propósito —en
     una máquina compartida una causa no puede quedar abierta hasta mañana—. Ahí lo
     que corresponde es empezar donde se elige con qué trabajar. Contestar con un
     cartel de «primero hay que abrir un legajo» en el medio de una pantalla vacía se
     lee como una falla del sistema, y hace pensar que los legajos se perdieron cuando
     están todos ahí, a un clic.

     IR A UNA PANTALLA que necesita un legajo, con la aplicación ya abierta, sí merece
     la explicación: pediste algo puntual y hace falta un paso previo.

     La diferencia es si esta es la primera pantalla de la sesión. */
  if (sinLegajo() && !SIN_LEGAJO_IGUAL_ANDAN.has(base)) {
    if (PRIMERA_PANTALLA) {
      PRIMERA_PANTALLA = false;
      location.hash = '#/legajos';
      return;                        // el cambio de hash vuelve a entrar acá
    }
    return vistaSinLegajo(TITULOS[base] || 'Análisis documental');
  }
  PRIMERA_PANTALLA = false;
  vista.innerHTML = '<div class="esqueleto"><i></i><i></i><i></i></div>';
  for (const [re, fn] of rutas) {
    // Una ruta que no contempla parámetros igual tiene que aceptar la página siguiente:
    // `#/precios?desde=50` no coincidía con `^#/precios$` y «Siguientes» no llevaba a
    // ninguna pantalla. Si no coincide con la consulta, se prueba sin ella; la vista
    // lee la consulta de `location.hash` como siempre.
    const m = h.match(re) || h.split('?')[0].match(re);
    if (m) {
      /* La red de abajo, para las vistas que no traen la guarda puesta.

         Sólo seis de las cuarenta y pico comprueban, después de esperar al servidor,
         que la persona siga en la pantalla que pidió. Las otras pintan lo que trajeron
         sin mirar dónde están, y con una consulta lenta eso significa tapar la pantalla
         que se está leyendo con el contenido de otra. Poner la guarda en cada vista
         una por una arregla las de hoy y no las que se escriban mañana.

         Acá no se puede evitar que la vista tardía pinte —ya pintó—, pero sí que quede
         puesta: si mientras esperábamos cambió el hash, se vuelve a rutear y gana lo
         que la persona pidió último, que es lo que tiene que estar en pantalla.
         Converge porque cada vuelta arranca del hash actual. */
      try {
        const pedido = h;
        const hecho = await fn(m[1]);
        if (location.hash !== pedido) return rutear();
        vigilarCortes(vista);
        return hecho;
      }
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
$('#b-revisor').onclick = pedirRevisor;
pintarRevisor();
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

/* Antes de imprimir, sellar la hoja: qué legajo y cuándo se emitió. Se hace en
   `beforeprint` y no al cargar, porque una pestaña abierta desde la mañana imprimiría
   la hora de la mañana, y esa hoja se agrega a un legajo. */
addEventListener('beforeprint', () => {
  const l = $('#membrete-legajo'), f = $('#membrete-fecha');
  if (l) {
    const n = $('#l-numero')?.textContent?.trim();
    const c = $('#l-caratula')?.textContent?.trim();
    l.textContent = n && n !== '—' ? `Legajo ${n}${c ? ' · ' + c : ''}` : '';
  }
  if (f) f.textContent = 'Emitido el ' + fmtFechaHora(new Date().toISOString());
});

/* ── Quién firma ───────────────────────────────────────────────────────────
   Los nombres de la casa vienen del servidor (ufil/identidad.py), no escritos acá:
   cambiar de fiscal no puede obligar a tocar seis archivos. */
async function pintarIdentidad() {
  try {
    const d = await api('/api/identidad');
    IDENTIDAD = d;
    $('#m-unidad').textContent = d.unidad;
    // El área va en un renglón y no se parte; si el nombre configurado no entra, se
    // elide, y entonces el nombre entero tiene que quedar en algún lado.
    $('#m-area').textContent = d.area;
    $('#m-area').title = d.area;
    $('#m-organismo').textContent = d.linea_organismo;
    // El membrete de impresión sale de la misma fuente: cambiar de unidad no puede
    // dejar una hoja impresa con el nombre viejo.
    const mo = $('#membrete-organismo'), mu = $('#membrete-unidad');
    if (mo) mo.textContent = `${d.organismo} · ${d.jurisdiccion}`;
    if (mu) mu.textContent = `${d.unidad} — ${d.area}`;
    const oficial = $('#identidad-oficial');
    if (oficial) oficial.alt = d.linea_organismo;
    // Los fiscales, abajo del organismo y en cuerpo menor: es una firma institucional,
    // no un dato de la pantalla, y nunca compite con lo que se está mirando.
    const f = $('#m-fiscales'), nombres = d.fiscales || [];
    if (f) {
      f.hidden = !nombres.length;
      f.innerHTML = nombres.length
        ? `<span class="rotulo-fiscales">${esc(nombres.length > 1
              ? (d.rotulo_fiscales || 'Fiscales') : 'Fiscal')}</span>`
          + nombres.map(n => `<span class="nombre-fiscal">${esc(n)}</span>`).join('')
        : '';
    }
    document.title = document.title.replace(/· .*$/, '· ' + d.unidad);
  } catch (e) { /* la barra ya trae los valores de la casa escritos en el HTML */ }
}
let IDENTIDAD = null;

/* ── El isotipo oficial, y el ícono de la pestaña ──────────────────────────
   Quién decide si están: el navegador, cargándolos. No el servidor contestando «hay
   marca» en cada consulta del panel —eran cuatro `stat()` por sondeo para responder
   algo que no cambia— ni una comprobación al abrir un legajo, porque entonces el
   índice de legajos, que no tiene panel, se quedaba con el monograma mientras el
   resto de la aplicación mostraba el isotipo.

   Si el archivo está, el isotipo entra y el monograma se va: son dos maneras de
   decir lo mismo y una sola tiene que quedar. Si no está, no pasa nada y la barra
   funciona igual, que es la condición de todo esto. */
(function marcaInstitucional() {
  const iso = document.getElementById('identidad-oficial');
  const mono = document.getElementById('monograma');
  if (iso) {
    const decidir = () => {
      const hay = iso.complete && iso.naturalWidth > 0;
      iso.hidden = !hay;
      if (mono) mono.hidden = hay;
    };
    // Los dos eventos Y una decisión ahora mismo: app.js se carga al final del cuerpo,
    // así que cuando llega acá la imagen puede estar cargada hace rato y el `load` ya
    // pasó. Escuchando solamente, el isotipo no aparecía nunca —y lo peor es que
    // aparecía en la máquina lenta, que es donde uno prueba—.
    iso.addEventListener('load', decidir);
    iso.addEventListener('error', decidir);
    decidir();
  }
  // El ícono de pestaña no se declara en el HTML: sin archivo, ese `<link>` dejaría
  // la pestaña sin ningún ícono. Se prueba primero y se pone después; mientras
  // tanto manda el monograma embebido, que no depende de nada.
  const prueba = new Image();
  prueba.addEventListener('load', () => {
    const l = document.querySelector('link[rel="icon"]');
    if (l) l.href = '/marca?que=icono';
  });
  prueba.src = '/marca?que=icono';
})();

/* El orden importa. Antes se pintaba la pantalla y DESPUÉS se preguntaba qué legajo
   había: sobre una instalación recién puesta eso mostraba el panel entero en cero y
   recién ahí saltaba a elegir legajo. El parpadeo se ve como si algo hubiera fallado.
   Ahora se pregunta primero y se pinta una sola vez, la pantalla que corresponde. */
medirTecho();
/* Cambiar de pantalla cierra la foja abierta. El visor vive AFUERA de `#vista` —tiene
   que taparlo todo—, así que un cambio de ruta repinta lo de abajo y la foja quedaba
   flotando encima de otra pantalla, tapándola entera. */
addEventListener('hashchange', () => { cerrarVisor(); rutear(); });
pintarIdentidad();
refrescarCuentas().then(rutear);
vigilarTrabajo();
latir();


async function vPapelera() {
  const c = await api('/api/cuentas');
  if (!c.legajo && !c.documentos) return vistaSinLegajo('Papelera de archivos');

  const limite = 100;
  const q = location.hash.split('?')[1] || '';
  const desde = parseInt(new URLSearchParams(q).get('desde') || '0', 10);
  const d = await api(`/api/papelera/archivos?limite=${limite}&desde=${desde}`);
  if (!d.archivos) {
    return vistaVacia('f. 0000', 'Error', 'Papelera de archivos', 'No se pudo cargar la papelera', 'El servidor devolvió una respuesta incompleta.');
  }
  const archivos = d.archivos;

  if (!archivos.length) {
    if (d.total > 0 && desde > 0) {
      return vistaVacia('f. 0000', 'Papelera', 'Papelera de archivos', 'No hay archivos en esta página', 'Volvé a la <a href="#/papelera">primera página</a>.');
    }
    return vistaVacia('f. 0000', 'Papelera', 'Papelera de archivos', 'La papelera está vacía', 'Los archivos que quites del legajo van a aparecer acá.');
  }

  const tamano = bytes => {
    if (!bytes) return '—';
    return (bytes / 1024 / 1024).toFixed(1).replace('.', ',') + ' MB';
  };

  vista.innerHTML = bloque('f. 0000', 'Papelera', `<div id="papelera-env">
    <h2>Papelera de archivos</h2>
    <p class="prosa">Estos archivos fueron quitados del legajo. Ya no participan en el análisis, pero se conservan acá por si fue un error.</p>
    <div class="paginacion-env">
      ${d.total !== undefined ? `Mostrando ${desde + 1}–${Math.min(desde + limite, d.total)} de ${fmtNum.format(d.total)}` : ''}
      ${desde > 0 ? `<a href="#/papelera?desde=${Math.max(0, desde - limite)}" class="paginacion-link">Anterior</a>` : ''}
      ${(d.total !== undefined && desde + limite < d.total) || (d.total === undefined && archivos.length === limite) ? `<a href="#/papelera?desde=${desde + limite}" class="paginacion-link">Siguiente</a>` : ''}
    </div>
    ${tabla([
      {t:'Archivo', c:'mono fol', r:f => esc(f.nombre)},
      {t:'Fecha de baja', c:'fol', r:f => f.quitado_en ? esc(fmtFechaHora(f.quitado_en)) : '—'},
      {t:'Páginas', c:'num', r:f => f.paginas != null ? fmtNum.format(f.paginas) : '—'},
      {t:'Documentos', c:'num', k:'documentos'},
      {t:'Lote', r:f => esc(f.lote || '—')},
      {t:'Revisiones', c:'num', r:f => f.tiene_revisiones_humanas ? (f.decisiones_humanas !== undefined ? esc(fmtNum.format(f.decisiones_humanas)) + ' ' + plural(f.decisiones_humanas, 'revisión', 'revisiones') : (f.revisiones !== undefined ? esc(fmtNum.format(f.revisiones)) + ' ' + plural(f.revisiones, 'revisión', 'revisiones') : 'decisiones humanas')) : '—'},
      {t:'Tamaño', c:'num', r:f => tamano(f.bytes)},
      {t:'Acciones', r:f => `
        <div class="acciones-fila">
          <button type="button" class="mini b-restaurar" data-sha="${esc(f.sha256)}">Restaurar</button>
          <button type="button" class="mini peligro b-destruir" data-sha="${esc(f.sha256)}">Destruir definitivamente</button>
        </div>
      `}
    ], archivos)}
  </div>`);

  vista.querySelectorAll('.b-restaurar').forEach(b => {
    b.addEventListener('click', () => pedirRestaurarArchivo(b.dataset.sha));
  });
  vista.querySelectorAll('.b-destruir').forEach(b => {
    b.addEventListener('click', () => {
      const arch = archivos.find(a => a.sha256 === b.dataset.sha);
      if (arch) pedirDestruirArchivo(arch.sha256, arch.nombre, arch.confirmacion_destruir);
    });
  });
}

/* La acción ya se hizo; lo que puede fallar después es volver a pedir la pantalla. Eso
   se dice, y se dice sin dar a entender que la acción falló. Va en un diálogo nuevo: el
   de la acción ya se cerró, y un error escrito ahí no lo ve nadie. */
async function redibujarTrasAccion(hecho, redibujar) {
  try {
    await redibujar();
  } catch (e) {
    dialogo(`
      <form method="dialog">
        <h3>${esc(hecho)}</h3>
        <div class="aviso">${sello('atencion', 'Atención')}<span>Pero no se pudo actualizar la pantalla: ${esc(e.message)}</span></div>
        <div class="botonera separador-arriba">
          <button class="boton" type="submit">Cerrar</button>
        </div>
      </form>
    `);
  }
}

function mostrarErrorDialogo(d, error) {
  d.innerHTML = `
    <form method="dialog">
      <h3>No se pudo completar la acción</h3>
      <div class="aviso">${sello('alerta', 'Error')}<span>${esc(error.message)}</span></div>
      <p class="prosa separador-arriba">Si es un conflicto de estado (409), el sistema evitó el cambio porque podría pisar información actual o reutilizar referencias.</p>
      <div class="botonera separador-arriba">
        <button class="boton" type="submit">Cerrar</button>
      </div>
    </form>
  `;
}

let quitarProcesando = false;
async function pedirQuitarArchivo(sha, nombre, confirmacion_quitar, procesando, revisiones_humanas) {
  if (procesando) {
    const d = dialogo(`
      <form method="dialog">
        <h3>Archivo en procesamiento</h3>
        <p class="prosa">El archivo <strong class="mono">${esc(nombre)}</strong> está siendo procesado en este momento.</p>
        <div class="aviso">${sello('atencion', 'Bloqueado')}<span>Esperá a que el sistema termine de leerlo antes de quitarlo.</span></div>
        <div class="botonera separador-arriba">
          <button class="boton" type="submit">Cerrar</button>
        </div>
      </form>
    `);
    return;
  }

  let msjRev = '';
  if (revisiones_humanas !== 0) {
     const strRev = revisiones_humanas > 0 ? `${esc(fmtNum.format(revisiones_humanas))} ${plural(revisiones_humanas, 'revisión', 'revisiones')}` : 'decisiones humanas';
     msjRev = `<div class="aviso separador-arriba">${sello('atencion', 'Hay decisiones humanas')}<span>Este archivo tiene ${strRev}. Se conservarán en la papelera y volverán si restaurás el archivo.</span></div>`;
  }

  const d = dialogo(`
    <form method="dialog" id="f-quitar-arch">
      <h3>Quitar archivo</h3>
      <p class="prosa">Vas a quitar el archivo <strong class="mono">${esc(nombre)}</strong>.</p>
      <div class="aviso">${sello('atencion', 'Atención')}
        <span>Este archivo dejará de participar en el legajo y sus resultados derivados dejarán de mostrarse. El original se conservará en la papelera y podrá restaurarse.</span>
      </div>
      ${msjRev}
      <div class="botonera separador-arriba">
        <button class="boton gris" value="no" type="submit">Cancelar</button>
        <button class="boton peligro" id="b-quitar" type="button">Quitar del legajo</button>
      </div>
    </form>
  `);

  d.querySelector('#b-quitar').onclick = async () => {
    if (quitarProcesando) return;
    quitarProcesando = true;
    d.querySelector('#b-quitar').disabled = true;
    const currentHash = location.hash;
    try {
      const r = await api('/api/archivo/quitar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sha256: sha, confirmacion: confirmacion_quitar})
      });
      d.close();
      if (location.hash === currentHash)
        await redibujarTrasAccion('El archivo se quitó del legajo',
                                  location.hash === '#/ingesta' ? vIngesta : rutear);
    } catch (e) {
      mostrarErrorDialogo(d, e);
    } finally {
      quitarProcesando = false;
    }
  };
}

let procesandoAccion = false;
async function pedirRestaurarArchivo(sha) {
  if (procesandoAccion) return;
  procesandoAccion = true;
  const d = dialogo(`
    <form method="dialog">
      <h3>Restaurando archivo...</h3>
      <p class="prosa">Por favor esperá...</p>
    </form>
  `);

  try {
    const r = await api('/api/archivo/restaurar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sha256: sha})
    });
    d.close();
    if (location.hash.split('?')[0] === '#/papelera')
      await redibujarTrasAccion('El archivo se restauró', vPapelera);
  } catch (e) {
    mostrarErrorDialogo(d, e);
  } finally {
    procesandoAccion = false;
  }
}

async function pedirDestruirArchivo(sha, nombre, confirmacion_destruir) {
  const d = dialogo(`
    <form method="dialog" id="f-destruir-arch">
      <h3>Destruir archivo definitivamente</h3>
      <p class="prosa">Vas a destruir el archivo <strong class="mono">${esc(nombre)}</strong> para siempre.</p>
      <div class="aviso">${sello('alerta', 'Destrucción física')}
        <span>Esta acción no se puede deshacer. El archivo se borrará del disco y todo su trabajo asociado se perderá.</span>
      </div>
      <p class="prosa separador-arriba"><label for="conf-destruir">Para confirmar, escribí DESTRUIR:</label></p>
      <input type="text" id="conf-destruir" autocomplete="off" class="campo-buscar" >
      <div class="botonera separador-arriba">
        <button class="boton gris" value="no" type="submit">Cancelar</button>
        <button class="boton peligro" id="b-destruir" type="button" disabled>Destruir para siempre</button>
      </div>
    </form>
  `);

  const input = d.querySelector('#conf-destruir');
  const btn = d.querySelector('#b-destruir');

  input.oninput = () => {
    btn.disabled = input.value !== 'DESTRUIR';
  };

  let destruirProcesando = false;
  btn.onclick = async () => {
    if (destruirProcesando) return;
    destruirProcesando = true;
    btn.disabled = true;
    try {
      const r = await api('/api/archivo/destruir', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sha256: sha, confirmacion: confirmacion_destruir})
      });
      d.close();
      if (location.hash.split('?')[0] === '#/papelera')
        await redibujarTrasAccion('El archivo se destruyó', vPapelera);
    } catch (e) {
      mostrarErrorDialogo(d, e);
    } finally {
      destruirProcesando = false;
    }
  };
}

let visorZoom = 1;
function aplicarZoomVisor() {
  const img = $('#visor-img');
  const lienzo = document.querySelector('.visor-lienzo');
  if (!img || !lienzo) return;
  
  if ($('#visor-zoom-texto')) {
    $('#visor-zoom-texto').textContent = Math.round(visorZoom * 100) + '%';
  }

  // Si no está cargada, esperamos.
  if (!img.naturalWidth) {
    img.addEventListener('load', aplicarZoomVisor, {once: true});
    return;
  }

  if (visorZoom === 1) {
    lienzo.style.width = '';
    lienzo.style.height = '';
    img.style.width = '';
    img.style.height = '';
  } else {
    lienzo.style.width = (img.naturalWidth * visorZoom) + 'px';
    lienzo.style.height = (img.naturalHeight * visorZoom) + 'px';
    img.style.width = '100%';
    img.style.height = '100%';
  }
  img.style.transform = '';
  
  const marco = $('#visor-marco');
  if (marco) marco.style.transform = '';
}

if ($('#visor-zoom-in')) {
  $('#visor-zoom-in').onclick = () => { visorZoom += 0.25; aplicarZoomVisor(); };
}
if ($('#visor-zoom-out')) {
  $('#visor-zoom-out').onclick = () => { visorZoom = Math.max(0.25, visorZoom - 0.25); aplicarZoomVisor(); };
}


function abrirDosFojas(f1, f2) {
  if (!f1) return;
  const nro1 = fojaDe(f1);
  if (!nro1) return;
  const nro2 = f2 ? fojaDe(f2) : null;
  
  aplicarZoomVisor(); 
  const visor = document.getElementById('visor'), img1 = document.getElementById('visor-img'), marco1 = document.getElementById('visor-marco');
  const img2 = document.getElementById('visor-img-2'), marco2 = document.getElementById('visor-marco-2'), lienzo2 = document.getElementById('visor-lienzo-2');
  
  if (!visor) return;
  img1.src = '/pagina?doc=' + f1.documento_id + '&nro=' + nro1;
  document.getElementById('visor-rotulo').textContent =
    [f1.archivo || 'documento', 'f. ' + nro1,
     f1.etiqueta || ''].filter(Boolean).join(' · ');
  
  const pag1 = f1.pagina || f1.pagina_respaldo;
  const hayCaja1 = pag1 && pag1.ancho_pt && f1.region && f1.region.x0 != null && f1.region.x1 != null;
  marco1.hidden = !hayCaja1;
  if (hayCaja1) {
    marco1.style.left = (100 * f1.region.x0 / pag1.ancho_pt) + '%';
    marco1.style.top = (100 * f1.region.y0 / pag1.alto_pt) + '%';
    marco1.style.width = (100 * Math.max(f1.region.x1 - f1.region.x0, 2) / pag1.ancho_pt) + '%';
    marco1.style.height = (100 * Math.max(f1.region.y1 - f1.region.y0, 2) / pag1.alto_pt) + '%';
  }

  if (f2 && nro2) {
    lienzo2.hidden = false;
    img2.src = '/pagina?doc=' + f2.documento_id + '&nro=' + nro2;
    document.getElementById('visor-rotulo-2').textContent = [f2.archivo || 'documento', 'f. ' + nro2, f2.etiqueta || ''].filter(Boolean).join(' · ');
    const pag2 = f2.pagina || f2.pagina_respaldo;
    const hayCaja2 = pag2 && pag2.ancho_pt && f2.region && f2.region.x0 != null && f2.region.x1 != null;
    marco2.hidden = !hayCaja2;
    if (hayCaja2) {
      marco2.style.left = (100 * f2.region.x0 / pag2.ancho_pt) + '%';
      marco2.style.top = (100 * f2.region.y0 / pag2.alto_pt) + '%';
      marco2.style.width = (100 * Math.max(f2.region.x1 - f2.region.x0, 2) / pag2.ancho_pt) + '%';
      marco2.style.height = (100 * Math.max(f2.region.y1 - f2.region.y0, 2) / pag2.alto_pt) + '%';
    }
  } else {
    if (lienzo2) lienzo2.hidden = true;
  }

  visor.hidden = false;
  document.body.classList.add('con-visor');
}
let catalogoContrataciones = null;
async function cargarCatalogoContrataciones() {
  if (!catalogoContrataciones) {
    catalogoContrataciones = await api('/api/catalogo/contrataciones');
  }
  return catalogoContrataciones;
}

/* ── Plata ─────────────────────────────────────────────────────────────────
   Decía `ARS 5.087,3`, y eso está mal de dos maneras a la vez. La moneda va con su
   signo —`$ 5.087,30`, como se escribe en un expediente— y no con el código ISO, que
   es para un sistema contable, no para leer. Y los centavos van siempre los dos: sin
   la segunda decimal, `5.087,3` obliga a preguntarse si son treinta centavos o tres,
   y una columna donde unas filas traen dos decimales y otras una es una columna que
   no se puede recorrer con la vista.

   Sólo se nombra la moneda cuando NO es peso: un legajo con importes en dólares y en
   pesos mezclados sin marca es exactamente la manera de sumar cosas que no se suman. */
const fmtPlata = new Intl.NumberFormat('es-AR',
  {minimumFractionDigits: 2, maximumFractionDigits: 2});

function formatearMonto(monto) {
  const val = monto == null ? NaN : parseFloat(monto.valor);
  if (isNaN(val)) return null;
  const t = '$ ' + fmtPlata.format(val);
  return monto.moneda && monto.moneda !== 'ARS' ? `${monto.moneda} ${t}` : t;
}

/* ── Un importe, y sus tres estados ────────────────────────────────────────
   Esto decía «no consta» cada vez que el backend no traía un `valor` numérico, sin
   mirar si traía el literal. Y lo traía: sobre el legajo real, el renglón 1 viene con

       precio_unitario: {literal: "5,087.30", valor: null, moneda: "ARS"}

   o sea, el papel dice 5.087,30, el sistema lo leyó bien, y la columna mostraba «NO
   CONSTA». Medido en una sola página de cien renglones: 448 veces. Eso no es una
   celda fea: es el sistema afirmando que un dato no está cuando está, y afirmándolo
   sobre la prueba de una causa. Es el error más grave que puede cometer esta
   aplicación, porque convierte una omisión en una negación.

   (Por qué `valor` viene en null habiendo literal es un defecto aparte, del lado del
   normalizador, y lo está mirando quien corresponde. Pero la pantalla no puede
   esperar a eso para dejar de mentir.)

   Tres estados, y se ven distintos porque son distintos:

     FIRME        hay número normalizado. Se muestra formateado y se puede sumar.
     EN EL PAPEL  no hay número, pero sí el literal leído. Se muestra el literal tal
                  como está, marcado como provisional: sirve para leer y para ir a la
                  foja, y NO entra en ningún total.
     AUSENTE      no hay nada. Una raya, y el motivo en el título. */
function montoHTML(monto) {
  const formateado = formatearMonto(monto);
  const conFuente = (texto, clase) => monto && monto.fuente
    ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(monto.fuente))}'
          class="enlace-fuente${clase ? ' ' + clase : ''}">${texto}</a>`
    : `<span class="${clase || ''}">${texto}</span>`;

  if (formateado !== null) return conFuente(esc(formateado));

  if (monto && monto.literal) {
    // El literal va tal cual lo trajo el papel. Normalizarlo acá a mano sería
    // adivinar —«5,087.30» puede ser cinco mil con treinta centavos o cinco con
    // ochenta y siete mil— y adivinar un importe es justo lo que no se hace.
    return conFuente(esc(String(monto.literal)), 'provisional') +
      ` <span class="marca-provisional" title="Está en el papel pero el sistema no lo pudo` +
      ` convertir a número, así que no se suma ni se compara hasta que alguien lo confirme."` +
      ` aria-label="valor provisional">≈</span>`;
  }

  return ausente(monto && monto.ausencia);
}

/* La raya. Un dato que no está se dice una vez, bajito, y explica por qué si lo sabe.
   Antes cada ausencia era un cartel en mayúsculas, y en pantallas con muchas
   columnas vacías el resultado era un muro que tapaba los datos que sí estaban. */
const MOTIVO_AUSENCIA = {
  no_consta:  'No consta en la documentación cargada.',
  ilegible:   'Está en el papel pero no se pudo leer.',
  no_cargado: 'El documento que lo traería todavía no se cargó.',
  pendiente:  'Falta que una persona lo revise.',
  conflicto:  'Las dos lecturas no coincidieron.',
};
const ausente = (motivo) =>
  `<span class="ausente" title="${esc(MOTIVO_AUSENCIA[motivo] ||
     'No consta en la documentación cargada.')}">—</span>`;

/* Una pantalla cuyo backend todavía no llegó a esta instalación: se dice, en vez de
   mostrar un error. El servidor contesta 404 «ruta desconocida» cuando la ruta no existe
   —sin `no_encontrado`, que es lo que contesta cuando lo que no existe es la cosa—. */
async function apiOPendiente(ruta, rotulo, titulo) {
  try {
    return await api(ruta);
  } catch (e) {
    if (e.estado === 404 && !e.noEncontrado) {
      vistaVacia('f. 0000', rotulo, titulo, 'Todavía no disponible en esta versión',
        'Esta parte del análisis se está terminando. Las piezas, las tablas y los precios ' +
        'ya se pueden consultar.');
      return null;
    }
    throw e;
  }
}

async function vContrataciones() {
  const cat = await cargarCatalogoContrataciones();
  const desde = parseInt(new URLSearchParams(location.hash.split('?')[1] || '').get('desde') || '0', 10);
  const limite = 100;
  const d = await apiOPendiente(`/api/contrataciones?desde=${desde}&limite=${limite}`, 'Contrataciones', 'Contrataciones');
  if (!d) return;
  
  if (!d.contrataciones || !d.contrataciones.length) {
    return vistaVacia('f. 0000', 'Contrataciones', 'Contrataciones',
      'Todavía no se reconstruyó ninguna contratación',
      'Una contratación se arma sola cuando el sistema encuentra documentos que se ' +
      'refieren al mismo expediente o al mismo procedimiento. Si ya cargaste el ' +
      'material, puede que falte procesarlo o que los documentos todavía no tengan ' +
      'número de expediente legible.');
  }

  const etapasCat = cat.etapas || [];
  const hasta = Math.min(desde + limite, d.total ?? (desde + d.contrataciones.length));
  const hayMas = d.total !== undefined
    ? desde + limite < d.total
    : d.contrataciones.length === limite;

  /* ── El riel de etapas ───────────────────────────────────────────────────
     Esto era una fila de sellos: un ✓ por cada etapa que consta y un Ø por cada una
     que no. Con siete etapas y cien contrataciones en pantalla eso da setecientos
     cuños, y medido sobre el legajo real la pantalla pintaba 1.776 marcas de ausencia
     —el número más alto de toda la aplicación—. Dejaba de ser una tabla de
     contrataciones para ser un muro de Ø con algunos datos escondidos adentro.

     Y el Ø además dice mal lo que pasa. Un procedimiento sin factura cargada no es un
     procedimiento con un agujero: es un procedimiento del que todavía no tenemos la
     factura. La diferencia importa, porque una es una observación sobre el expediente
     y la otra es una observación sobre lo que alcanzamos a cargar, y sólo la segunda
     es cierta.

     Queda un riel: una marca por etapa, en el orden en que ocurren. Llena la que
     consta, hueca la que no. Se lee de un vistazo como una barra de progreso del
     procedimiento —que es lo que es— y el detalle está en el título de cada marca.
     Cuando una etapa tiene más de un documento lleva el número, porque tres ofertas y
     una oferta no son lo mismo. */
  const riel = c => {
    /* Que el backend no haya mandado las etapas NO es que las etapas no consten.
       Ésa era justamente la vieja trampa en otra forma: sin `c.etapas`, el código
       anterior armaba un diccionario vacío y pintaba los siete casilleros huecos, o
       sea afirmaba que ninguna etapa constaba, en las ciento veinticuatro filas. Lo
       que pasaba en realidad es que la lista no trae ese dato —sólo lo trae la ficha
       de cada contratación—.

       Una pantalla no puede decir «no consta» sobre algo que no preguntó. Mientras el
       listado no traiga las etapas, se dice que hay que entrar a la ficha para verlas,
       que es lo que de verdad ocurre. */
    /* El listado trae un resumen compacto, {pliego: 1, ofertas: 0, …}: cantidad de
       documentos por etapa, cero si no consta en lo cargado. Se dibuja en ese orden,
       que es el del procedimiento. */
    if (c.etapas && !Array.isArray(c.etapas) && typeof c.etapas === 'object') {
      const NOMBRE = {pliego: 'Pliego', ofertas: 'Ofertas', adjudicacion: 'Adjudicación',
        orden_compra: 'Orden de compra', factura: 'Factura', remito: 'Remito', pago: 'Pago'};
      const claves = Object.keys(NOMBRE).filter(k => k in c.etapas)
        .concat(Object.keys(c.etapas).filter(k => !(k in NOMBRE)));
      const marcas = claves.map(k => {
        const n = Number(c.etapas[k]) || 0;
        const nombre = NOMBRE[k] || k.replace(/_/g, ' ');
        const titulo = n ? `${nombre}: ${n > 1 ? `${n} documentos` : 'consta'}`
                         : `${nombre}: no consta en lo cargado`;
        return `<span class="etapa ${n ? 'hay' : 'falta'}" title="${esc(titulo)}"
          >${n > 1 ? fmtNum.format(n) : ''}</span>`;
      }).join('');
      const hay = claves.filter(k => Number(c.etapas[k])).length;
      return `<span class="riel-etapas" role="img"
        aria-label="${hay} de ${claves.length} etapas con documentación">${marcas}</span>`;
    }
    if (!Array.isArray(c.etapas))
      return `<a class="etapas-pendiente" href="#/contratacion?id=${c.id}"
                 title="Las etapas de esta contratación se ven en su ficha."
              >ver etapas</a>`;
    const suyas = Object.fromEntries(c.etapas.map(e => [e.clave, e]));
    const marcas = etapasCat.map(ec => {
      const e = suyas[ec.clave] || {};
      const n = e.cantidad ?? (e.documentos ? e.documentos.length : 0);
      const titulo = e.presente
        ? `${ec.nombre}: ${n > 1 ? `${n} documentos` : 'consta'}`
        : `${ec.nombre}: no consta en lo cargado`;
      return `<span class="etapa ${e.presente ? 'hay' : 'falta'}" title="${esc(titulo)}"
        >${e.presente && n > 1 ? fmtNum.format(n) : ''}</span>`;
    }).join('');
    const hay = etapasCat.filter(ec => (suyas[ec.clave] || {}).presente).length;
    return `<span class="riel-etapas" role="img"
      aria-label="${hay} de ${etapasCat.length} etapas con documentación">${marcas}</span>`;
  };

  vista.innerHTML = bloque('f. 0000', 'Contrataciones', `
    <h1>Contrataciones</h1>
    <p class="prosa">Cada procedimiento que el sistema pudo reconstruir a partir de los
      documentos cargados. El riel muestra de qué etapas hay documentación: lleno
      cuando consta, hueco cuando todavía no apareció en lo que se cargó — que no es
      lo mismo que decir que no existió.</p>

    <div class="tabla-cabecera">
      <span class="tabla-cuenta">${
        d.total !== undefined
          ? `${fmtNum.format(desde + 1)}–${fmtNum.format(hasta)} de ${fmtNum.format(d.total)} contrataciones`
          : `${fmtNum.format(d.contrataciones.length)} contrataciones`}</span>
      <span class="paginacion">
        ${desde > 0
          ? `<a class="boton gris" href="#/contrataciones?desde=${Math.max(0, desde - limite)}">Anteriores</a>`
          : ''}
        ${hayMas ? `<a class="boton gris" href="#/contrataciones?desde=${desde + limite}">Siguientes</a>` : ''}
      </span>
    </div>

    ${tabla([
      // El identificador interno no era una columna: era ruido con aspecto de dato.
      // Lo que identifica una contratación en un expediente es el expediente. El
      // nombre lleva el enlace, que es donde la mano va a ir igual.
      {t:'Contratación', c:'crece', r: c => `<div class="item-desc">
          <a class="item-literal" href="#/contratacion?id=${c.id}">${esc(nombreContratacion(c))}</a>
          ${c.objeto ? `<span class="item-normalizado">${esc(c.objeto)}</span>`
            : c.ancla ? `<span class="item-normalizado">Sin expediente leído · ${esc(String(c.ancla.archivo || '').replace(/\.pdf$/i, ''))}</span>` : ''}
        </div>`},
      // `ausencias` viene del backend y dice POR QUÉ falta cada campo: no_consta,
      // ilegible, no_cargado, pendiente. Se usa para el título de la raya, así que la
      // explicación es la del sistema y no una que invente la pantalla.
      {t:'Expediente', c:'fol', r: c => c.expediente
          ? esc(c.expediente) : ausente((c.ausencias || {}).expediente)},
      // Proveedor y adjudicado sólo si el listado los trae: dos columnas vacías de punta
      // a punta no dicen «no consta», dicen que la pantalla pidió algo que no sabe.
      ...(d.contrataciones.some(c => Array.isArray(c.proveedores)) ? [
      {t:'Proveedor', r: c => {
         // Lo mismo que con las etapas: el listado todavía no trae los proveedores.
         // Decir «—» acá sería afirmar que la contratación no tiene ninguno.
         if (!Array.isArray(c.proveedores)) return '';
         const p = c.proveedores;
         if (!p.length) return ausente('no_consta');
         // Con muchos oferentes, la lista entera rompe el ancho de la fila y no se
         // lee ninguno. Va el primero, y el resto contados.
         const resto = p.length > 1
           ? ` <span class="mas" title="${esc(p.slice(1).map(x => x.nombre).join(', '))}"
                >+${p.length - 1}</span>` : '';
         return esc(p[0].nombre) + resto;
       }}] : []),
      {t:'Etapas', r: riel},
      ...(d.contrataciones.some(c => c.totales) ? [
      {t:'Adjudicado', c:'num', r: c => !c.totales ? ''
          : c.totales.adjudicado ? montoHTML(c.totales.adjudicado) : ausente('no_consta')}] : []),
      // «0 hallazgos» no es información: lo normal es que no haya. Sólo se dice
      // cuando hay algo que mirar, y entonces se dice cuánto.
      {t:'Hallazgos', c:'num', r: c => c.hallazgos
          ? `<a class="chip-hallazgos" href="#/hallazgos?contratacion_id=${c.id}"
              >${fmtNum.format(c.hallazgos)}</a>` : ''},
    ], d.contrataciones)}
  `);
}

async function vContratacion() {
  const id = new URLSearchParams(location.hash.split('?')[1] || '').get('id');
  if (!id) return;
  const d = await apiOPendiente(`/api/contratacion/${id}`, 'Contratación', 'Contratación');
  if (!d) return;
  const c = d.contratacion;
  const etapas = d.etapas || [];
  const conDocs = etapas.filter(e => e.presente);
  const sinDocs = etapas.filter(e => !e.presente);
  const documentos = conDocs.reduce((n, e) => n + (e.documentos || []).length, 0);
  const matriz = d.matriz || {columnas: [], filas: []};
  const hallazgos = (d.hallazgos || []).filter(h => !h.ya_no_se_detecta);
  const oferentes = d.oferentes || [];

  const fuente = (f, texto) => f
    ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(f))}'
          class="enlace-fuente" title="${esc(f.archivo || '')}">${texto}</a>`
    : texto;
  const foja = f => f && (f.foja ?? f.pagina_nro) != null
    ? 'f. ' + fmtNum.format(f.foja ?? f.pagina_nro) : 'ver';
  // Una fecha puede venir suelta o como {valor, literal}: se muestra la normalizada
  // y, si no la hay, lo que dice el papel.
  const fecha = v => v == null ? '' : typeof v === 'object'
    ? (fmtFecha(v.valor) || v.literal || '') : (fmtFecha(v) || String(v));
  // «Otro documento relacionado», nueve veces seguidas, no distingue nada: el enlace
  // lleva el tipo del documento, que es lo que la persona busca con la vista.
  const tipoDoc = doc => TIPO_DOC[doc.tipo] || TIPO_DOC[(doc.fuente || {}).tipo_documento]
    || ((doc.tipo || '').replace(/_/g, ' ').replace(/^./, m => m.toUpperCase())) || 'Documento';

  /* ── Quién es cada columna de la matriz ──────────────────────────────────
     El backend titula la columna con la clave de la etapa y el proveedor pegados
     («orden_compra: sin atribuir»). Eso es el nombre de una variable, no un rótulo.
     Se arma con lo que la persona reconoce: el tipo de documento y a nombre de quién
     está; y si todavía no se sabe de quién es, se dice así, sin guiones bajos. */
  // Cómo se escribe cada identificador en un expediente.
  const ROTULO_ID = {cuit: 'CUIT', expediente: 'Expte.', resolucion: 'Res.', decreto: 'Dec.',
    orden_compra: 'O. C.', orden_pago: 'O. P.', factura: 'Fact.', remito: 'Rem.',
    licitacion: 'Lic.', concurso: 'Conc.'};
  const oferentePorId = Object.fromEntries(oferentes.map(o => [o.entidad_id, o]));
  const nombreEtapa = Object.fromEntries(etapas.map(e => [e.clave, e.nombre]));
  const tituloColumna = col => {
    const [clave, resto] = String(col.titulo || '').split(':').map(s => s.trim());
    const o = oferentePorId[col.entidad_id];
    const quien = o ? (o.nombre && o.nombre !== o.cuit ? o.nombre : `CUIT ${o.cuit}`)
                    : (resto && resto !== 'sin atribuir' ? resto : 'proveedor sin identificar');
    const que = nombreEtapa[clave] || TIPO_DOC[clave] || (clave || '').replace(/_/g, ' ');
    return `${que} · ${quien}`;
  };

  /* ── La cabecera ─────────────────────────────────────────────────────────
     Decía «Expediente: no consta · Procedimiento: desconocido»: dos negaciones
     seguidas antes de cualquier dato. Lo que consta va en la línea; lo que no, no
     ocupa lugar. En esta ficha la falta de un dato no es noticia: es lo normal de un
     procedimiento que se está reconstruyendo de a pedazos. */
  const meta = [
    c.expediente && ['Expediente', esc(c.expediente)],
    c.organismo && ['Organismo', esc(c.organismo)],
    c.procedimiento && c.procedimiento !== 'desconocido'
      && ['Procedimiento', esc(c.procedimiento.replace(/_/g, ' '))],
  ].filter(Boolean);
  const estado = c.estado === 'confirmada'
    ? sello('ok', 'Confirmada por una persona')
    : c.estado === 'rechazada' ? sello('alerta', 'Descartada')
    : sello('neutro', 'Propuesta por el sistema', {titulo:
        'El sistema agrupó estos documentos porque comparten expediente o ' +
        'identificadores. Nadie lo confirmó todavía.'});

  /* ── Las cifras ──────────────────────────────────────────────────────────
     Cuatro conteos que el sistema sabe con certeza. Los importes de adjudicación,
     facturación y pago van aparte y sólo si hay alguno: tres rayas seguidas en la
     tira más visible de la pantalla eran tres «no consta» gritados. */
  const cifra = (rotulo, valor, nota) => `
    <div class="cifra">
      <span class="cifra-rotulo">${esc(rotulo)}</span>
      <span class="cifra-valor">${valor}</span>
      ${nota ? `<span class="cifra-nota">${nota}</span>` : ''}
    </div>`;
  const tot = d.totales || c.totales || {};
  const importes = [['Adjudicado', tot.adjudicado], ['Facturado', tot.facturado],
                    ['Pagado', tot.pagado]].filter(([, m]) => m);
  const pendientes = hallazgos.filter(h => (h.revision || {}).estado === 'pendiente').length;
  const cifrasHTML = `
    <div class="cifras cifras-4">
      ${cifra('Documentos', fmtNum.format(documentos),
              `en ${fmtNum.format(conDocs.length)} de ${fmtNum.format(etapas.length)} etapas`)}
      ${cifra('Ítems', fmtNum.format(matriz.filas.length),
              matriz.columnas.length > 1
                ? `en ${fmtNum.format(matriz.columnas.length)} documentos` : '')}
      ${cifra('Oferentes', fmtNum.format(oferentes.length),
              oferentes.some(o => o.adjudicado) ? 'con adjudicatario identificado' : '')}
      ${cifra('Hallazgos', hallazgos.length
                ? `<a href="#/hallazgos?contratacion_id=${c.id}">${fmtNum.format(hallazgos.length)}</a>`
                : '0',
              hallazgos.length ? `${fmtNum.format(pendientes)} sin revisar`
                               : 'ninguna diferencia detectada')}
    </div>
    ${importes.length ? `<div class="cifras cifras-4">
      ${importes.map(([r, m]) => cifra(r, montoHTML(m))).join('')}</div>` : ''}`;

  /* ── Qué se compró ───────────────────────────────────────────────────────
     Un renglón por ítem, una columna por documento con precios. El literal del papel
     arriba y lo que entendió el sistema abajo, siempre los dos; cada importe lleva a
     su foja. */
  const matrizHTML = matriz.filas.length ? tabla([
    {t: 'Ítem', c: 'crece', r: f => {
      const lit = f.descripcion && f.descripcion.literal;
      const norm = f.descripcion && f.descripcion.normalizada;
      return `<div class="item-desc">
        <span class="item-literal">${lit ? esc(lit) : ausente('ilegible')}</span>
        ${norm && lit && norm.toLowerCase() !== lit.toLowerCase()
          ? `<span class="item-normalizado">${esc(norm)}</span>` : ''}
      </div>`;
    }},
    ...matriz.columnas.map(col => ({
      t: tituloColumna(col), c: 'num',
      r: f => {
        const val = f.valores[col.clave];
        if (!val) return `<span class="ausente" title="No hay precio leído para este ítem en este documento.">—</span>`;
        const h = montoHTML(val);
        return f.menor === col.clave
          ? `<span class="precio-menor" title="El menor precio de la fila">${h}</span>` : h;
      }
    }))
  ], matriz.filas) : `<p class="nota-seccion">No se leyó ningún renglón con precios en
      los documentos de esta contratación. Si hay una orden de compra o una oferta, puede
      que su planilla todavía no se haya reconocido como tabla.</p>`;

  /* ── El procedimiento ────────────────────────────────────────────────────
     Eran trece sellos apilados, la mayoría «FALTA …» con doble filete: una pantalla
     que empezaba por lo que no hay. Ahora van las etapas con documentación, en orden,
     cada una con sus documentos y su foja; las demás se nombran juntas, en una línea
     y en tinta apagada. Que no consten en lo cargado no quiere decir que no hayan
     existido, y la línea lo dice. */
  const etapasHTML = `
    <ol class="proc-etapas">
      ${conDocs.map(e => `
        <li class="proc-etapa">
          <span class="proc-nombre">${esc(e.nombre)}</span>
          <ul class="proc-docs">
            ${(e.documentos || []).map(doc => `<li>
              ${fuente(doc.fuente, esc(tipoDoc(doc)))}
              ${fecha(doc.fecha) ? `<span class="proc-dato">${esc(fecha(doc.fecha))}</span>` : ''}
              <span class="proc-dato">${esc(foja(doc.fuente))}</span>
              ${(doc.identificadores || []).slice(0, 2).map(i =>
                `<span class="proc-id" title="${esc(i.literal || '')}">${esc(
                  ROTULO_ID[i.clase] || (i.clase || '').replace(/_/g, ' '))} ${esc(i.valor)}</span>`).join('')}
            </li>`).join('')}
          </ul>
        </li>`).join('')}
    </ol>
    ${sinDocs.length ? `<p class="proc-faltan">Sin documentación en lo cargado:
      ${sinDocs.map(e => esc(e.nombre.toLowerCase())).join(', ')}. Puede estar en fojas
      que todavía no se cargaron o que no se reconocieron.</p>` : ''}`;

  /* ── Hallazgos, agrupados ────────────────────────────────────────────────
     Veinticuatro «Renglón sin precio», uno debajo del otro, son un solo hallazgo
     repetido. Se cuentan por tipo, con el enlace a la lista filtrada. */
  const porTipo = new Map();
  hallazgos.forEach(h => {
    if (!porTipo.has(h.tipo)) porTipo.set(h.tipo, []);
    porTipo.get(h.tipo).push(h);
  });
  const hallazgosHTML = porTipo.size ? `<ul class="lista-motivos">
      ${[...porTipo.values()].sort((a, b) => b.length - a.length).map(hs => `<li>
        <span class="motivo-cuenta">${fmtNum.format(hs.length)}</span>
        <span class="motivo-texto"><a href="#/hallazgos?contratacion_id=${c.id}&tipo=${
          encodeURIComponent(hs[0].tipo)}">${esc(hs[0].titulo || hs[0].tipo)}</a></span>
        <span class="motivo-ejemplos">${esc(hs[0].descripcion || '')}</span>
      </li>`).join('')}
    </ul>` : '';

  const oferentesHTML = oferentes.length ? tabla([
    {t: 'Oferente', c: 'crece', r: o => o.nombre && o.nombre !== o.cuit
        ? `<a href="#/proveedor/${o.entidad_id}">${esc(o.nombre)}</a>`
        : `<a href="#/proveedor/${o.entidad_id}">Razón social no leída</a>`},
    {t: 'CUIT', c: 'fol', r: o => o.cuit ? esc(o.cuit) : ausente('no_consta')},
    {t: 'Resultado', r: o => o.adjudicado ? sello('ok', 'Adjudicado') : ''},
  ], oferentes) : '';

  const crono = d.cronologia || [];
  const cronoHTML = crono.length ? `<ol class="crono-lineal">
      ${crono.map(ev => `<li>
        <span class="crono-fecha">${esc(fecha(ev.fecha))}</span>
        <span class="crono-que">${esc(ev.etiqueta || nombreEtapa[ev.etapa] || ev.etapa)}</span>
        <span class="crono-fuente">${fuente(ev.fuente, esc(foja(ev.fuente)))}</span>
      </li>`).join('')}</ol>` : '';

  vista.innerHTML = bloque('f. 0000', 'Contratación', `
    <nav class="migas" aria-label="Estás en"><a href="#/contrataciones">Contrataciones</a></nav>
    <header class="ficha-cabeza">
      <h1>${esc(nombreContratacion(c))}</h1>
      ${c.objeto ? `<p class="ficha-objeto">${esc(c.objeto)}</p>` : ''}
      <div class="ficha-meta">
        ${meta.map(([k, v]) => `<span class="meta-par"><span class="meta-k">${k}</span> ${v}</span>`).join('')}
        ${estado}
      </div>
    </header>
    ${cifrasHTML}

    <h2>Qué se compró</h2>
    ${matrizHTML}

    <h2>Procedimiento</h2>
    ${etapasHTML}

    ${hallazgosHTML ? `<h2>Diferencias detectadas</h2>
      <p class="nota-seccion">Lo que el sistema marcó para revisar. No son conclusiones:
        cada una lleva su cálculo y su fuente en la lista de hallazgos.</p>
      ${hallazgosHTML}` : ''}
    ${oferentesHTML ? `<h2>Oferentes</h2>${oferentesHTML}` : ''}
    ${cronoHTML ? `<h2>Fechas</h2>${cronoHTML}` : ''}
  `);
}

/* ── Todos los documentos ─────────────────────────────────────────────────
   «¿Dónde está el papel?». Las listas que había eran de contratos de personal y de
   comprobantes; en un legajo de contrataciones hacen falta todas las piezas, por tipo:
   órdenes de compra, presupuestos, remitos, resoluciones. Chips con la cuenta de cada
   tipo arriba, y la tabla pide cada página al servidor. */
async function vPiezas() {
  const tipo = new URLSearchParams(location.hash.split('?')[1] || '').get('tipo') || '';
  const cat = await api('/api/piezas?limite=1');
  if (location.hash.split('?')[0] !== '#/piezas') return;
  const total = (cat.tipos || []).reduce((n, x) => n + x.cantidad, 0);
  const nombre = k => TIPO_DOC[k] || String(k || 'Sin tipo').replace(/_/g, ' ');
  const chip = (href, texto, n, activo) => `<a class="chip-filtro${activo ? ' activo' : ''}" href="${href}"
      ${activo ? 'aria-current="true"' : ''}>${esc(texto)}<span class="chip-n">${fmtNum.format(n)}</span></a>`;
  vista.innerHTML = bloque('f. 0000', 'Documentación', `
    <h1>Documentos</h1>
    <p class="prosa">Cada pieza que el sistema separó en los escaneos, con su tipo, el archivo,
      las fojas y la contratación en la que entró. Un clic abre la pieza con sus datos y la foja.</p>
    <div class="filtros-chips" role="group" aria-label="Tipo de documento">
      ${chip('#/piezas', 'Todos', total, !tipo)}
      ${(cat.tipos || []).map(x => chip('#/piezas?tipo=' + encodeURIComponent(x.tipo), nombre(x.tipo),
          x.cantidad, tipo === x.tipo)).join('')}
    </div>
    <div id="lista-piezas"></div>`);
  tablaServidor($('#lista-piezas'), '/api/piezas' + (tipo ? '?tipo=' + encodeURIComponent(tipo) : ''), 'piezas', [
    {t: 'Documento', c: 'crece', o: 'tipo', r: d => `<a class="item-literal" href="#/documento/${d.id}">${esc(nombre(d.tipo))}</a>`},
    {t: 'Archivo', o: 'archivo', r: d => esc(String(d.archivo || '').replace(/\.pdf$/i, ''))},
    {t: 'Fojas', c: 'num', o: 'foja', r: d => d.pagina_desde === d.pagina_hasta
        ? `f. ${fmtNum.format(d.pagina_desde)}`
        : `f. ${fmtNum.format(d.pagina_desde)}–${fmtNum.format(d.pagina_hasta)}`},
    {t: 'Contratación', c: 'nowrap', r: d => d.contratacion_id
        ? `<a href="#/contratacion?id=${d.contratacion_id}">Ver contratación</a>` : ''},
    {t: 'Lectura', r: d => d.estado === 'sin_perfil'
        ? sello('neutro', 'Sólo el tipo', {titulo: 'El sistema reconoció qué es, pero todavía no lee sus datos campo por campo.'})
        : sello('ok', 'Datos leídos')},
  ], {placeholder: 'Buscar por archivo…', alClic: d => { location.hash = '#/documento/' + d.id; },
      vacio: 'No hay documentos de este tipo.'});
}

/* ── Proveedores ──────────────────────────────────────────────────────────
   La puerta para buscar un proveedor. «Todas las fichas» mezcla personas, empresas,
   organismos y expedientes, y ordenada por nombre abre con personas sin nombre: para
   la pregunta «¿a quién se le compró?» no sirve. Acá van sólo las empresas, las que
   más documentos tienen primero, y cada una lleva a su ficha. */
function formatoCuit(c) {
  const d = String(c || '').replace(/\D/g, '');
  return d.length === 11 ? `${d.slice(0, 2)}-${d.slice(2, 10)}-${d.slice(10)}` : String(c || '');
}
async function vProveedores() {
  vista.innerHTML = bloque('f. 0000', 'Proveedores', `
    <h1>Proveedores</h1>
    <p class="prosa">Las empresas que aparecen en el legajo, identificadas por su CUIT. Las
      que más documentos tienen van primero. Cada una lleva a su ficha: qué se le compró, a
      qué precio, cuánto se le ordenó y facturó, y qué diferencias hay.</p>
    <div id="lista-proveedores"></div>
    <p class="nota-seccion">Personas, organismos y el resto de las fichas están en
      <a href="#/entidades">Todas las fichas</a>.</p>`);
  const sinNombre = e => !e.nombre || String(e.nombre).replace(/\D/g, '') === String(e.clave_fuerte || '');
  tablaServidor($('#lista-proveedores'), '/api/entidades?clase=empresa', 'entidades', [
    {t: 'Proveedor', c: 'crece', o: 'nombre', r: e => sinNombre(e)
        ? `<div class="item-desc"><a class="item-literal" href="#/proveedor/${e.id}">CUIT ${esc(formatoCuit(e.clave_fuerte))}</a>
             <span class="item-normalizado">Razón social no leída en ningún documento</span></div>`
        : `<div class="item-desc"><a class="item-literal" href="#/proveedor/${e.id}">${esc(e.nombre)}</a></div>`},
    {t: 'CUIT', c: 'fol', r: e => e.clave_fuerte ? esc(formatoCuit(e.clave_fuerte)) : ausente('no_consta')},
    {t: 'Documentos', c: 'num', o: 'documentos', r: e => fmtNum.format(e.documentos || 0)},
    {t: 'Menciones', c: 'num', o: 'menciones', r: e => fmtNum.format(e.menciones || 0)},
    {t: 'Contrataciones', r: e => e.con_contrataciones ? sello('ok', 'Con contrataciones') : ''},
  ], {orden: 'documentos', sentido: 'desc', placeholder: 'Buscar por nombre o CUIT…',
      alClic: e => { location.hash = '#/proveedor/' + e.id; },
      vacio: 'Todavía no se identificó ninguna empresa. Aparecen cuando el sistema lee un CUIT en un documento.'});
}

/* ── Ficha de proveedor ────────────────────────────────────────────────────
   La pregunta de la investigación, de un lado: ¿con quién se contrató, qué le
   compraron, a qué precio, cuánto se facturó y qué diferencias hay? Todo sale de
   renglones y documentos con el proveedor identificado por su CUIT: nada se le
   atribuye por un nombre parecido ni por estar cerca en la foja. */
async function vProveedor(id) {
  const d = await apiOPendiente(`/api/proveedor/${id}?limite=200`, 'Proveedor', 'Proveedor');
  if (!d) return;
  if (location.hash.split('?')[0] !== '#/proveedor/' + id) return;
  const p = d.proveedor || {};
  const cuit = p.clave_fuerte && /^\d{11}$/.test(p.clave_fuerte)
    ? `${p.clave_fuerte.slice(0, 2)}-${p.clave_fuerte.slice(2, 10)}-${p.clave_fuerte.slice(10)}` : p.clave_fuerte;
  // Cuando la razón social no se leyó, el «nombre» de la entidad es el CUIT: se dice.
  const sinNombre = !p.nombre || (p.clave_fuerte && p.nombre.replace(/\D/g, '') === p.clave_fuerte);
  const lista = (x, k) => (x && x[k]) || [];
  const total = x => (x && x.total != null) ? x.total : 0;
  const contrataciones = lista(d.contrataciones, 'contrataciones');
  const precios = lista(d.historial_precios, 'renglones');
  const hallazgos = lista(d.hallazgos, 'hallazgos');
  const facturas = lista(d.facturas, 'documentos');
  const remitos = lista(d.remitos, 'documentos');

  const fuente = (f, texto) => f ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(f))}'
      class="enlace-fuente" title="${esc(f.archivo || '')}">${texto}</a>` : texto;
  const foja = f => f && f.pagina_nro != null ? 'f. ' + fmtNum.format(f.foja ?? f.pagina_nro) : '';
  const cifra = (rotulo, valor, nota) => `<div class="cifra">
      <span class="cifra-rotulo">${esc(rotulo)}</span>
      <span class="cifra-valor">${valor}</span>
      ${nota ? `<span class="cifra-nota">${nota}</span>` : ''}</div>`;
  const plata = grupos => {
    const con = (grupos || []).filter(g => g.valor != null);
    if (!con.length) return null;
    return con.map(g => `${g.moneda && g.moneda !== 'ARS' ? g.moneda + ' ' : '$ '}${fmtPlata.format(Number(g.valor))}`).join(' · ');
  };
  const ord = plata(d.monto_ordenado), fac = plata(d.monto_facturado), adj = plata(d.monto_adjudicado);

  const plano = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const preciosHTML = precios.length ? tabla([
    {t: 'Ítem', c: 'crece', r: r => `<div class="item-desc"><span class="item-literal">${
        esc((r.descripcion || {}).literal || '')}</span>${r.descripcion && r.descripcion.normalizada
        && plano(r.descripcion.normalizada) !== plano(r.descripcion.literal)
        ? `<span class="item-normalizado">${esc(r.descripcion.normalizada)}</span>` : ''}</div>`},
    {t: 'Documento', c: 'nowrap', r: r => esc(TIPO_DOC[r.etapa] || String(r.etapa || '').replace(/_/g, ' '))},
    {t: 'Fecha', c: 'fol', r: r => r.fecha ? esc(fmtFecha(r.fecha.valor) || r.fecha.literal) : ausente('no_consta')},
    {t: 'Cantidad', c: 'num', r: r => r.cantidad ? esc(r.cantidad.literal) : ausente('no_consta')},
    {t: 'Precio unitario', c: 'num', r: r => montoHTML(r.precio_unitario)},
    {t: 'Contratación', r: r => r.contratacion ? `<a class="celda-corta" href="#/contratacion?id=${
        r.contratacion.id}">${esc(r.contratacion.nombre)}</a>` : ausente('no_consta')},
    {t: 'Comparar', r: r => r.precio_unitario && r.precio_unitario.valor != null
        ? `<a class="enlace-comparar" href="#/renglon?id=${r.id}">Ver comparación</a>` : ''},
  ], precios) : '';

  const porTipo = new Map();
  hallazgos.forEach(h => porTipo.set(h.tipo, [...(porTipo.get(h.tipo) || []), h]));
  const hallazgosHTML = porTipo.size ? `<ul class="lista-motivos">${[...porTipo.values()]
      .sort((a, b) => b.length - a.length).map(hs => `<li>
        <span class="motivo-cuenta">${fmtNum.format(hs.length)}</span>
        <span class="motivo-texto"><a href="#/hallazgos?tipo=${encodeURIComponent(hs[0].tipo)}">${esc(hs[0].titulo || hs[0].tipo)}</a></span>
        <span class="motivo-ejemplos">${esc(hs[0].descripcion || '')}</span></li>`).join('')}</ul>` : '';

  const docsHTML = (docs, tipo) => docs.length ? `<p class="lista-fojas">${docs.map(x =>
      fuente(x.fuente, esc(`${tipo} ${foja(x.fuente)}`))).join(' · ')}</p>` : '';

  vista.innerHTML = bloque('f. 0000', 'Proveedor', `
    <nav class="migas" aria-label="Estás en"><a href="#/proveedores">Proveedores</a></nav>
    <header class="ficha-cabeza">
      <h1>${sinNombre ? `CUIT ${esc(cuit || '')}` : esc(p.nombre)}</h1>
      <div class="ficha-meta">
        ${!sinNombre && cuit ? `<span class="meta-par"><span class="meta-k">CUIT</span> ${esc(cuit)}</span>` : ''}
        ${sinNombre ? `<span class="nota-dato">La razón social no se leyó en ningún documento.</span>` : ''}
        <a href="#/entidad/${esc(id)}">Ver todas las menciones</a>
      </div>
    </header>
    <div class="cifras cifras-4">
      ${cifra('Contrataciones', fmtNum.format(total(d.contrataciones)), 'con documentos a su nombre')}
      ${cifra('Ítems', fmtNum.format(d.cantidad_items || 0), `${fmtNum.format(total(d.historial_precios))} renglones con su nombre`)}
      ${cifra('Ordenado', ord ? esc(ord) : '—', ord ? 'suma de renglones de órdenes de compra' : 'sin importes a su nombre')}
      ${cifra('Facturado', fac ? esc(fac) : '—', fac ? 'suma de renglones de facturas' : 'sin importes a su nombre')}
    </div>
    ${adj ? `<p class="nota-seccion">Adjudicado, por suma de renglones: ${esc(adj)}.</p>` : ''}
    <p class="nota-seccion">${esc(d.cobertura || '')} Las sumas son de los renglones leídos, no los
      totales que imprime cada documento, y lo ordenado y lo facturado no se suman entre sí.</p>

    ${contrataciones.length ? `<h2>Contrataciones</h2>${tabla([
      {t: 'Contratación', c: 'crece', r: c => `<a class="item-literal" href="#/contratacion?id=${c.id}">${esc(nombreContratacion(c))}</a>`},
      {t: 'Expediente', c: 'fol', r: c => c.expediente ? esc(c.expediente) : ausente('no_consta')},
      {t: 'Procedimiento', r: c => c.procedimiento && c.procedimiento !== 'desconocido'
          ? esc(c.procedimiento.replace(/_/g, ' ').replace(/^./, m => m.toUpperCase())) : ausente('no_consta')},
    ], contrataciones)}` : ''}

    ${preciosHTML ? `<h2>Qué se le compró, a qué precio</h2>${preciosHTML}` : ''}

    ${hallazgosHTML ? `<h2>Diferencias detectadas</h2>
      <p class="nota-seccion">En documentos a su nombre. No son conclusiones: cada una lleva su cuenta y su fuente.</p>
      ${hallazgosHTML}` : ''}

    ${facturas.length || remitos.length ? `<h2>Facturas y remitos</h2>
      ${docsHTML(facturas, 'Factura')}${docsHTML(remitos, 'Remito')}` : ''}
  `);
}

async function vPrecios() {
  const desde = parseInt(new URLSearchParams(location.hash.split('?')[1] || '').get('desde') || '0', 10);
  // Cincuenta: con cien la tabla medía seis mil píxeles y la paginación, arriba, ya
  // no se veía cuando hacía falta.
  const limite = 50;
  /* De qué pantalla es esta respuesta. Esta consulta es la más lenta del sistema por
     dos órdenes de magnitud —medida sobre el legajo real: 13,4 s con cien renglones
     contra 0,02 s de casi todo lo demás—, así que es la que más tiempo pasa en el
     aire, y en ese rato da tiempo de sobra a irse a otra pantalla.

     Sin esta guarda, la respuesta llegaba tarde y pintaba los ítems y precios ENCIMA
     de la pantalla que la persona estaba mirando. Verificado en el barrido: la
     captura rotulada «Superposiciones» mostraba, en realidad, la tabla de ítems y
     precios. En una herramienta que se usa para leer un expediente, creer que se
     está mirando una pantalla y estar mirando otra no es un defecto cosmético. */
  const pedido = location.hash;
  const d = await api(`/api/precios?desde=${desde}&limite=${limite}`);
  if (pedido !== location.hash) return;

  if (!d.renglones || !d.renglones.length) {
    return vistaVacia('f. 0000', 'Ítems y precios', 'Ítems y precios',
      'Todavía no hay ítems con precio',
      'Los ítems aparecen acá cuando el sistema reconoce renglones con cantidad y ' +
      'precio dentro de un presupuesto, una orden de compra o una factura. Si ya ' +
      'cargaste esos documentos, puede que falte procesarlos.');
  }

  const hasta = Math.min(desde + limite, d.total ?? (desde + d.renglones.length));
  const hayMas = d.total !== undefined
    ? desde + limite < d.total
    : d.renglones.length === limite;

  /* La descripción del ítem, con sus dos caras. El literal es lo que dice el papel y
     manda; el normalizado es lo que el sistema entendió, y está abajo en chico porque
     es lo que permite comparar. Nunca uno en lugar del otro: reemplazar el literal por
     el normalizado sería perder la prueba y quedarse con la interpretación. */
  const descripcion = r => {
    const lit = `<span class="item-literal">${esc(r.descripcion.literal)}</span>`;
    // Si lo normalizado es lo mismo en minúsculas, repetirlo abajo es ruido: una fila
    // de ciento cincuenta dice lo mismo dos veces.
    const plano = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
    const norm = r.descripcion.normalizada &&
                 plano(r.descripcion.normalizada) !== plano(r.descripcion.literal)
      ? `<span class="item-normalizado" title="Así lo entendió el sistema para poder
           compararlo. El texto de arriba es el que dice el papel."
           >${esc(r.descripcion.normalizada)}</span>` : '';
    return `<div class="item-desc">${lit}${norm}</div>`;
  };

  /* La comparación no se presenta como un veredicto sino como una invitación a mirar
     la evidencia. Y su calidad viaja con ella: una comparación dudosa mostrada igual
     que una firme es exactamente la manera de que alguien la cite como si fuera
     firme. */
  const CALIDAD = {fuerte: 'Comparable', probable: 'Probable',
                   dudoso: 'Dudosa', no_comparable: 'No comparable'};
  const comparacion = r => {
    if (!r.comparacion) return ausente('no_consta');
    const estado = r.comparacion.estado || r.comparacion.nivel || '';
    const rotulo = CALIDAD[estado] || 'Ver comparación';
    return `<a class="enlace-comparar" href="#/renglon?id=${r.id}"
       >${esc(rotulo)}</a>`;
  };

  vista.innerHTML = bloque('f. 0000', 'Ítems y precios', `
    <h1>Ítems y precios</h1>
    <p class="prosa">Cada renglón que el sistema pudo leer de un presupuesto, una orden
      de compra o una factura, con lo que dice el papel y de qué foja salió. Los
      importes en bastardilla con <span class="marca-provisional">≈</span> están en el
      papel pero todavía no se pudieron convertir a número, así que no se suman.</p>

    <div class="tabla-cabecera">
      <span class="tabla-cuenta">${
        d.total !== undefined
          ? `${fmtNum.format(desde + 1)}–${fmtNum.format(hasta)} de ${fmtNum.format(d.total)} renglones`
          : `${fmtNum.format(d.renglones.length)} renglones`}</span>
      <span class="paginacion">
        ${desde > 0
          ? `<a class="boton gris" href="#/precios?desde=${Math.max(0, desde - limite)}">Anteriores</a>`
          : ''}
        ${hayMas ? `<a class="boton gris" href="#/precios?desde=${desde + limite}">Siguientes</a>` : ''}
      </span>
    </div>

    ${tabla([
      {t:'Ítem', c:'crece', r: descripcion},
      {t:'Proveedor', r: r => r.proveedor ? (r.proveedor.entidad_id
          ? `<a href="#/proveedor/${r.proveedor.entidad_id}">${esc(r.proveedor.nombre)}</a>`
          : esc(r.proveedor.nombre)) : ausente('no_consta')},
      {t:'Fecha', c:'fol', r: r => r.fecha ? esc(fmtFecha(r.fecha.valor) || r.fecha.literal)
                                           : ausente('no_consta')},
      {t:'Cantidad', c:'num', r: r => r.cantidad ? esc(r.cantidad.literal) : ausente('no_consta')},
      {t:'Unidad', r: r => r.unidad ? esc(r.unidad.literal) : ausente('no_consta')},
      {t:'Precio unitario', c:'num', r: r => montoHTML(r.precio_unitario)},
      {t:'Total', c:'num', r: r => montoHTML(r.subtotal)},
      {t:'Contratación', r: r => r.contratacion
          ? `<a class="celda-corta" href="#/contratacion?id=${r.contratacion.id}"
               title="${esc(r.contratacion.nombre)}">${esc(r.contratacion.nombre)}</a>`
          : ausente('no_consta')},
      {t:'Comparación', r: comparacion},
      // La fuente es la columna que sostiene todo lo demás: sin ella ninguno de los
      // números de la fila es afirmable. Por eso está siempre, y siempre al final,
      // donde la vista termina de recorrer la fila.
      // `pagina` no es el número de página: es un objeto con las medidas de la hoja.
      // El número está en `pagina_nro`, y la foja —cuando el expediente está foliado—
      // en `foja`. Pedirle el número a `pagina` imprimía «f. [object Object]» en las
      // ciento cincuenta y cuatro filas.
      {t:'Fuente', r: r => r.fuente
          ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(r.fuente))}'
                class="enlace-fuente" title="${esc(r.fuente.archivo || '')}"
             >f. ${esc(String(r.fuente.foja ?? r.fuente.pagina_nro ?? '?'))}</a>`
          : ausente('no_consta')},
    ], d.renglones)}
  `);
}

async function vRenglon() {
  const id = new URLSearchParams(location.hash.split('?')[1] || '').get('id');
  if (!id) return;
  // Las referencias y los descartes vienen paginados: se piden doscientos, que es el
  // máximo, y los totales se toman del servidor, no del largo de lo que llegó.
  const d = await api(`/api/renglon/${id}/comparacion?niveles=A,B,C,D,E&limite=200`);
  const r = d.renglon;
  
  /* Cada referencia con lo que la hace comparable o no, dicho como se diría: «unidad:
     metro contra rollo». El estado va en el mismo sello que en el resto del sistema. */
  const TONO_COMP = {fuerte: ['ok', 'Comparable'], probable: ['neutro', 'Probable'],
                     dudoso: ['atencion', 'Dudosa'], no_comparable: ['alerta', 'No comparable']};
  const renderMotivos = motivos => (motivos || []).map(m => `<span class="hz-motivo">${
    esc(String(m.atributo || '').replace(/_/g, ' '))}: ${esc(m.a ?? '—')} contra ${esc(m.b ?? '—')}${
    m.efecto ? ` <span class="celda-nota">${esc(m.efecto)}</span>` : ''}</span>`).join('');
  const renderRefs = refs => tabla([
    {t:'Ítem', c:'crece', r: x => `<div class="item-desc"><span class="item-literal">${
        esc((x.renglon.descripcion || {}).literal || '')}</span>${x.renglon.contratacion
        ? `<a class="item-normalizado" href="#/contratacion?id=${x.renglon.contratacion.id}">${
            esc(x.renglon.contratacion.nombre)}</a>` : ''}</div>`},
    {t:'Fecha', c:'fol', r: x => x.renglon.fecha
        ? esc(fmtFecha(x.renglon.fecha.valor) || x.renglon.fecha.literal) : ausente('no_consta')},
    {t:'Proveedor', r: x => x.renglon.proveedor ? esc(x.renglon.proveedor.nombre) : ausente('no_consta')},
    {t:'Precio', c:'num', r: x => montoHTML(x.renglon.precio_unitario)},
    {t:'Comparabilidad', r: x => {
       const [tono, txt] = TONO_COMP[(x.comparabilidad || {}).estado] || ['neutro', 'Sin calificar'];
       return sello(tono, txt) + renderMotivos((x.comparabilidad || {}).motivos);
     }}
  ], refs);

  const refsPorNivel = {};
  (d.referencias || []).forEach(ref => {
    if (!refsPorNivel[ref.nivel]) refsPorNivel[ref.nivel] = [];
    refsPorNivel[ref.nivel].push(ref);
  });
  
  const nivelesHTML = Object.keys(refsPorNivel).sort().map(nivel => `
    <h3>Nivel ${esc(nivel)}</h3>
    ${renderRefs(refsPorNivel[nivel])}
  `).join('');
  
  /* La tabla de excluidas se fue: con el legajo real son ciento cincuenta y tres
     filas, y una lista de ciento cincuenta y tres renglones descartados no la lee
     nadie. Ahora van agrupadas por motivo, más abajo. */

  const ads = (d.advertencias || []).map(a => `<li>${sello('atencion', a)}</li>`).join('');

  /* ── Las cifras, arriba y juntas ─────────────────────────────────────────
     Estaban como párrafos sueltos: «n: 3», «Mediana: ...», «Diferencia porcentual:
     ...%». Eso es el volcado de una estructura de datos, no una pantalla: obliga a
     leer seis renglones seguidos para armarse en la cabeza la comparación que la
     pantalla tendría que mostrar hecha.

     Van las cuatro que contestan la pregunta, en el orden en que se piensan: qué
     precio estamos mirando, contra qué, cuánto se aparta, y cuánto vale esa
     comparación. Ninguna dice si eso está bien o mal. */
  const cifra = (rotulo, valor, nota) => `
    <div class="cifra">
      <span class="cifra-rotulo">${esc(rotulo)}</span>
      <span class="cifra-valor">${valor}</span>
      ${nota ? `<span class="cifra-nota">${nota}</span>` : ''}
    </div>`;

  const est = d.estadisticas, dif = d.diferencia;
  // El signo va siempre: una diferencia de −7 millones escrita sin el menos se lee como
  // un precio siete millones más caro, que es exactamente lo contrario.
  const signo = n => (Number(n) > 0 ? '+' : Number(n) < 0 ? '−' : '');
  /* Una comparación de calidad baja —referencias aproximadas, una sola referencia— no
     se presenta como una cifra firme. Se muestra, porque esconderla sería decidir por
     la persona, pero apagada y con el motivo arriba: sirve para saber que hay que
     buscar mejores referencias, no para afirmar una diferencia. */
  const floja = (d.calidad && d.calidad.nivel === 'baja') || (est && (est.nivel === 'E' || est.n < 2));
  const nombreOperando = n => {
    const m = /^referencia_(\d+)$/.exec(n || '');
    if (m) return `referencia (renglón ${m[1]})`;
    return ({analizado: 'precio analizado', mediana: 'mediana', segunda_oferta: 'segunda oferta'})[n]
      || String(n || '').replace(/_/g, ' ');
  };
  const cifras = est ? `
    ${floja ? `<div class="aviso aviso-floja">
      ${sello('atencion', 'Comparación de calidad baja')}
      <span>${est.n < 2 ? 'Hay una sola referencia' : `Hay ${fmtNum.format(est.n)} referencias`}${
        est.nivel === 'E' ? ', y es aproximada (nivel E)' : ''}. La diferencia de abajo no alcanza
        para afirmar nada sobre este precio: dice que hacen falta referencias mejores —el
        mismo producto, con la misma unidad y de fecha cercana—.</span></div>` : ''}
    <div class="cifras cifras-4${floja ? ' cifras-flojas' : ''}">
      ${cifra('Precio analizado', montoHTML(r.precio_unitario),
              r.fecha ? esc(fmtFecha(r.fecha.valor) || r.fecha.literal) : '')}
      ${cifra('Mediana de las referencias',
              esc('$ ' + fmtPlata.format(Number(est.mediana))),
              `${fmtNum.format(est.n)} ${est.n === 1 ? 'referencia' : 'referencias'} · nivel ${esc(est.nivel)}`)}
      ${cifra('Diferencia',
              dif ? esc(signo(dif.absoluta) + '$ ' + fmtPlata.format(Math.abs(Number(dif.absoluta)))) : '—',
              dif ? esc(signo(dif.porcentual) + fmtNum.format(Math.abs(Number(dif.porcentual))) + ' %') : '')}
      ${cifra('Calidad de la comparación',
              `<span class="calidad ${esc(d.calidad ? d.calidad.nivel : 'desconocida')}"
                 >${esc(d.calidad ? d.calidad.nivel : 'desconocida')}</span>`,
              d.calidad && d.calidad.motivos ? esc(d.calidad.motivos[0] || '') : '')}
    </div>` : '';

  /* Ciento cincuenta y tres renglones descartados, uno debajo del otro, no son
     información: son una lista que nadie va a leer. Agrupados por motivo sí lo son.
     Sobre el legajo real da: 71 sin precio utilizable, 37 por la etapa documental, 23
     del mismo documento, 22 no comparables por descripción. Eso se lee en cinco
     segundos y dice qué haría falta para poder comparar. */
  const porMotivo = new Map();
  (d.excluidas || []).forEach(x => {
    const k = x.motivo || 'Sin motivo registrado.';
    if (!porMotivo.has(k)) porMotivo.set(k, []);
    porMotivo.get(k).push(x);
  });
  const motivos = [...porMotivo.entries()].sort((a, b) => b[1].length - a[1].length);
  const htmlExcluidas = motivos.length ? `
    <details class="descartes">
      <summary>Por qué no se usaron los otros ${fmtNum.format(
        (d.excluidas_paginacion || {}).total ?? (d.excluidas || []).length)} renglones${
        (d.excluidas_paginacion || {}).total > (d.excluidas || []).length
          ? ` <span class="celda-nota">(agrupados los primeros ${fmtNum.format((d.excluidas || []).length)})</span>` : ''}</summary>
      <ul class="lista-motivos">
        ${motivos.map(([motivo, xs]) => `
          <li>
            <span class="motivo-cuenta">${fmtNum.format(xs.length)}</span>
            <span class="motivo-texto">${esc(motivo)}</span>
            <span class="motivo-ejemplos">${
              xs.slice(0, 3).map(x => esc(x.renglon.descripcion.literal)).join(' · ')
            }${xs.length > 3 ? ' …' : ''}</span>
          </li>`).join('')}
      </ul>
    </details>` : '';

  const sinReferencias = !est && !(d.referencias || []).length;

  vista.innerHTML = bloque('f. 0000', 'Comparación de precio', `
    <h1>${esc(r.descripcion.literal)}</h1>
    <p class="prosa">Este precio, al lado de los otros precios del mismo ítem que hay
      en el legajo. El sistema no dice si está bien o mal: muestra las referencias que
      encontró, cuán comparables son y de qué foja salió cada número.</p>

    ${sinReferencias ? `
      <div class="aviso">
        <span class="sello atencion">Sin referencias</span>
        <span>No hay ningún otro precio en el legajo que se pueda comparar con éste,
          así que no hay diferencia que calcular. Abajo está el detalle de por qué
          quedó afuera cada candidato.</span>
      </div>
      <div class="cifras cifras-4">
        ${cifra('Precio analizado', montoHTML(r.precio_unitario),
                r.fecha ? esc(fmtFecha(r.fecha.valor) || r.fecha.literal) : '')}
        ${cifra('Cantidad', r.cantidad ? esc(r.cantidad.literal) : '—',
                r.unidad ? esc(r.unidad.literal) : '')}
        ${cifra('Contratación', r.contratacion
                  ? `<a href="#/contratacion?id=${r.contratacion.id}">${esc(r.contratacion.nombre)}</a>`
                  : '—', r.expediente ? 'Expediente ' + esc(r.expediente) : '')}
        ${cifra('Fuente', r.fuente
                  ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(r.fuente))}'
                        class="enlace-fuente">f. ${esc(String(r.fuente.foja ?? r.fuente.pagina_nro ?? '?'))}</a>`
                  : '—', r.fuente ? esc(r.fuente.etiqueta || '') : '')}
      </div>
    ` : cifras}

    ${ads && !sinReferencias ? `<ul class="advertencias">${ads}</ul>` : ''}

    ${d.calculo ? `
      <h2>De dónde sale el número</h2>
      <details class="formula-completa"><summary>Ver la fórmula completa</summary>
        <p class="formula mono">${esc(d.calculo.formula)}</p></details>
      <ul class="operandos">
        ${d.calculo.operandos.map(op => `<li><span class="op-nombre">${esc(nombreOperando(op.nombre))}</span>
          ${op.fuente
            ? `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(op.fuente))}'
                  class="enlace-fuente">${esc(op.valor)}</a>`
            : esc(op.valor)}</li>`).join('')}
      </ul>` : ''}

    ${nivelesHTML ? `<h2>Referencias usadas</h2>${nivelesHTML}` : ''}
    ${htmlExcluidas}
  `);
}

async function vHallazgosContrataciones() {
  const cat = await cargarCatalogoContrataciones();
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  const tipo = q.get('tipo') || '';
  const estado = q.get('estado') || '';
  const contratacion = q.get('contratacion_id') || '';
  const pagina = Math.max(0, parseInt(q.get('pagina') || '0', 10) || 0);
  const POR_PAGINA = 25;

  /* Los filtros viajan al servidor —cuando el servidor los entiende, el total que
     devuelve ya es el filtrado— y además se aplican acá, que es idempotente: una
     versión del servidor que todavía no los entiende no hace que la pantalla muestre
     de más. */
  const params = new URLSearchParams({desde: '0', limite: '200'});
  if (tipo) params.set('tipo', tipo);
  if (estado) params.set('estado_revision', estado);
  if (contratacion) params.set('contratacion_id', contratacion);
  const d = await apiOPendiente(`/api/hallazgos?${params}`, 'Hallazgos', 'Hallazgos');
  if (!d) return;
  if (location.hash.split('?')[0] !== '#/hallazgos') return;

  const tipos = cat.hallazgos || [];
  const tipoDe = Object.fromEntries(tipos.map(t => [t.clave, t]));
  const revisiones = cat.revision || [];
  const revisionDe = Object.fromEntries(revisiones.map(r => [r.clave, r]));

  const todos = (d.hallazgos || []).filter(h => !h.ya_no_se_detecta)
    .filter(h => !contratacion || String(h.contratacion_id) === contratacion);
  const cuentaTipo = new Map();
  todos.forEach(h => cuentaTipo.set(h.tipo, (cuentaTipo.get(h.tipo) || 0) + 1));
  const cuentaEstado = new Map();
  todos.forEach(h => {
    const e = (h.revision || {}).estado || 'pendiente';
    cuentaEstado.set(e, (cuentaEstado.get(e) || 0) + 1);
  });
  const filtrados = todos
    .filter(h => !tipo || h.tipo === tipo)
    .filter(h => !estado || ((h.revision || {}).estado || 'pendiente') === estado);

  /* El orden es el de lo que más importa mirar: primero las diferencias con una
     cuenta detrás (precio, facturado contra adjudicado o entregado, sumas que no
     dan), después los faltantes, y al final los renglones que no se pudieron leer,
     que son muchos y dicen más del OCR que de la contratación. */
  const PESO = {diferencia_precio: 0, facturado_vs_adjudicado: 1, facturado_vs_entregado: 2,
    subtotal_incorrecto: 3, total_inconsistente: 4, ofertas_identicas: 5,
    duplicado_potencial: 6, variacion_compras: 7, secuencia_temporal: 8,
    oferente_unico: 9, documento_faltante: 10, coincidencia_temporal: 11,
    precio_sin_rol: 12, precio_ausente: 13};
  filtrados.sort((a, b) => (PESO[a.tipo] ?? 20) - (PESO[b.tipo] ?? 20) || a.id - b.id);

  const total = filtrados.length;
  const pag = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const enlace = cambios => {
    const n = new URLSearchParams({tipo, estado, contratacion_id: contratacion,
                                   pagina: '0', ...cambios});
    for (const [k, v] of [...n.entries()]) if (!v || (k === 'pagina' && v === '0')) n.delete(k);
    const s = n.toString();
    return '#/hallazgos' + (s ? '?' + s : '');
  };

  const fuente = (f, texto) => `<a href="javascript:void(0)" data-fuente='${esc(JSON.stringify(f))}'
      class="enlace-fuente" title="${esc(f.archivo || '')}">${texto}</a>`;
  const foja = f => (f.foja ?? f.pagina_nro) != null ? 'f. ' + fmtNum.format(f.foja ?? f.pagina_nro) : 'fuente';
  const tonoEstado = e => e === 'relevante' ? 'atencion' : e === 'descartado' ? 'neutro' : 'trabajando';
  const nombreEstado = e => e === 'pendiente' ? 'Sin revisar'
    : (revisionDe[e] ? revisionDe[e].nombre.replace(' para la investigación', '') : e);

  if (!todos.length) {
    return vistaVacia('f. 0000', 'Hallazgos', 'Hallazgos',
      contratacion ? 'Esta contratación no tiene hallazgos' : 'Todavía no hay hallazgos',
      'Un hallazgo es una diferencia que el sistema encontró al comparar documentos: un ' +
      'precio lejos de sus referencias, una factura que no coincide con la orden de ' +
      'compra, una suma que no da. Aparecen cuando hay contrataciones reconstruidas con ' +
      'renglones y precios legibles. Si ya cargaste el material, revisá «Contrataciones» ' +
      'e «Ítems y precios».');
  }

  /* Los filtros son chips con su cuenta, no un formulario: se ve de un vistazo qué
     hay y se entra con un clic. La cuenta es sobre lo que hay, no sobre lo filtrado,
     para que cambiar de filtro no esconda las otras opciones. */
  const chip = (href, texto, n, activo) =>
    `<a class="chip-filtro${activo ? ' activo' : ''}" href="${href}"
        ${activo ? 'aria-current="true"' : ''}>${esc(texto)}<span class="chip-n">${fmtNum.format(n)}</span></a>`;
  const chipsTipo = [chip(enlace({tipo: ''}), 'Todos', todos.length, !tipo),
    ...[...cuentaTipo.entries()].sort((a, b) => (PESO[a[0]] ?? 20) - (PESO[b[0]] ?? 20))
      .map(([k, n]) => chip(enlace({tipo: k}), (tipoDe[k] || {}).nombre || k, n, tipo === k))].join('');
  const chipsEstado = [chip(enlace({estado: ''}), 'Cualquier estado', todos.length, !estado),
    ...['pendiente', 'relevante', 'descartado'].filter(e => cuentaEstado.get(e))
      .map(e => chip(enlace({estado: e}), nombreEstado(e), cuentaEstado.get(e), estado === e))].join('');

  /* Qué dice ESTE hallazgo. La descripción del backend es la del tipo, igual para
     todos: siete filas seguidas decían «Cantidad o producto de la factura no
     coinciden con el remito asociado» y no había forma de saber cuál era cuál. Con los
     datos de cada uno se dice cuál: qué producto, qué etapa falta, qué renglón. */
  const etapaDe = Object.fromEntries((cat.etapas || []).map(e => [e.clave, e.nombre]));
  const etapa = k => (etapaDe[k] || TIPO_DOC[k] || String(k).replace(/_/g, ' ')).toLowerCase();
  const plata = v => v == null || isNaN(Number(v)) ? String(v ?? '') : '$ ' + fmtPlata.format(Number(v));
  const especifico = h => {
    const x = h.datos || {};
    switch (h.tipo) {
      case 'facturado_vs_entregado':
      case 'facturado_vs_adjudicado':
        return `${x.atributo === 'cantidad' ? 'Cantidad' : x.atributo === 'precio' ? 'Precio'
          : x.atributo === 'proveedor' ? 'Proveedor' : 'Producto'} que no coincide${
          x.descripcion ? `: «${esc(x.descripcion)}»` : ''}`;
      case 'documento_faltante':
        return x.etapas_no_encontradas && x.etapas_no_encontradas.length
          ? `Hay ${esc(etapa(x.etapa_presente || 'documentación'))}, pero no ${
              x.etapas_no_encontradas.map(k => esc(etapa(k))).join(' ni ')}`
          : esc(h.descripcion || '');
      case 'precio_ausente':
        return `${x.renglon_id ? `<a href="#/renglon?id=${esc(x.renglon_id)}">Renglón</a>` : 'Renglón'}
          ${x.motivo === 'ilegible' ? 'con el precio ilegible en el papel'
            : x.motivo === 'ausente' ? 'sin precio en el papel' : 'con el precio sin leer'}`;
      case 'subtotal_incorrecto': {
        const ops = Object.fromEntries(((h.calculo || {}).operandos || []).map(o => [o.nombre, o.valor]));
        return ops.cantidad && ops.precio_unitario
          ? `${fmtNum.format(Number(ops.cantidad))} × ${esc(plata(ops.precio_unitario))} da ${esc(
              plata(h.calculo.resultado))}; el papel dice ${esc(plata(x.impreso))}`
          : `El subtotal impreso (${esc(plata(x.impreso))}) no da la cuenta`;
      }
      case 'precio_sin_rol':
        return `${fmtNum.format(x.renglones || 0)} importes impresos sin decir si son
          por unidad o por renglón`;
      case 'oferente_unico':
        return `Se encontró ${fmtNum.format(x.ofertas || 1)} oferta en lo cargado`;
      case 'diferencia_precio':
        return x.diferencia_pct != null
          ? `${fmtNum.format(Number(x.diferencia_pct))} % sobre la mediana de las referencias
             (${esc(plata(x.analizado))} contra ${esc(plata(x.referencia))})`
          : esc(h.descripcion || '');
      default:
        return esc(h.descripcion || '');
    }
  };

  const fila = h => {
    const t = tipoDe[h.tipo] || {};
    const rev = h.revision || {};
    const est = rev.estado || 'pendiente';
    const fuentes = h.fuentes || [];
    const revOpciones = revisiones.map(rc =>
      `<option value="${esc(rc.clave)}" ${est === rc.clave ? 'selected' : ''}>${esc(rc.nombre)}</option>`).join('');
    const calculo = h.calculo ? `
      <div class="hz-bloque">
        <span class="hz-rotulo">Cálculo</span>
        <p class="formula mono">${esc(h.calculo.formula || '')}${h.calculo.resultado != null
          ? ` = ${esc(String(h.calculo.resultado))}` : ''}</p>
        ${(h.calculo.operandos || []).length ? `<ul class="operandos">${h.calculo.operandos.map(op =>
          `<li><span class="op-nombre">${esc(String(op.nombre || '').replace(/_/g, ' '))}</span>
           ${op.fuente ? fuente(op.fuente, esc(String(op.valor))) : esc(String(op.valor))}</li>`).join('')}</ul>` : ''}
      </div>` : '';
    return `<details class="hz" data-hallazgo="${esc(h.id)}">
      <summary class="hz-fila">
        <span class="hz-tipo">${esc(t.nombre || h.titulo || h.tipo)}</span>
        <span class="hz-desc">${especifico(h)}</span>
        <span class="hz-donde">${h.contratacion_id
          ? `<a href="#/contratacion?id=${h.contratacion_id}">Contratación ${esc(
              String(h.contratacion_nombre || h.contratacion_id))}</a>` : ''}</span>
        <span class="hz-fuente">${fuentes.length ? fuente(fuentes[0], esc(foja(fuentes[0])))
          + (fuentes.length > 1 ? ` <span class="mas">+${fuentes.length - 1}</span>` : '') : ''}</span>
        <span class="hz-estado">${sello(tonoEstado(est), nombreEstado(est),
          {titulo: rev.quien ? `${rev.quien}${rev.cuando ? ', ' + fmtFechaHora(rev.cuando) : ''}` : ''})}</span>
      </summary>
      <div class="hz-detalle">
        <div class="hz-col">
          ${t.explicacion ? `<div class="hz-bloque"><span class="hz-rotulo">Qué se detectó</span>
            <p>${esc(t.explicacion)}</p></div>` : ''}
          ${calculo}
          <div class="hz-bloque"><span class="hz-rotulo">Confianza</span>
            <p><span class="calidad ${esc((h.confianza || {}).nivel || '')}">${esc(
              (h.confianza || {}).nivel || 'sin calificar')}</span>
            ${((h.confianza || {}).motivos || []).map(m => `<span class="hz-motivo">${esc(m)}</span>`).join('')}</p>
          </div>
          ${fuentes.length ? `<div class="hz-bloque"><span class="hz-rotulo">Fuentes</span>
            <ul class="hz-fuentes">${fuentes.map(f => `<li>${fuente(f, esc(
              (TIPO_DOC[f.tipo_documento] || f.etiqueta || 'Documento') + ' · ' + foja(f)))}
              <span class="proc-dato">${esc(f.archivo || '')}</span></li>`).join('')}</ul></div>` : ''}
        </div>
        <form class="hz-revision" onsubmit="return false">
          <span class="hz-rotulo">Revisión</span>
          <label>Estado <select id="rev-estado-${h.id}">${revOpciones}</select></label>
          <label>Nota <textarea id="rev-nota-${h.id}" rows="3"
            placeholder="Qué se verificó contra la fuente, o por qué se descarta">${esc(rev.nota || '')}</textarea></label>
          <button type="button" class="boton" data-guardar-hallazgo="${esc(h.id)}">Guardar revisión</button>
        </form>
      </div>
    </details>`;
  };

  const paginas = Math.ceil(total / POR_PAGINA);
  const paginador = paginas > 1 ? `<nav class="paginador" aria-label="Páginas">
      ${pagina > 0 ? `<a class="boton gris" href="${enlace({pagina: String(pagina - 1)})}">Anteriores</a>` : ''}
      <span>${fmtNum.format(pagina * POR_PAGINA + 1)}–${fmtNum.format(Math.min(total, (pagina + 1) * POR_PAGINA))}
        de ${fmtNum.format(total)}</span>
      ${pagina + 1 < paginas ? `<a class="boton gris" href="${enlace({pagina: String(pagina + 1)})}">Siguientes</a>` : ''}
    </nav>` : '';

  vista.innerHTML = bloque('f. 0000', 'Hallazgos', `
    ${contratacion ? `<nav class="migas" aria-label="Estás en"><a href="#/contrataciones">Contrataciones</a><a
        href="#/contratacion?id=${esc(contratacion)}">Contratación</a></nav>` : ''}
    <h1>Hallazgos</h1>
    <p class="prosa">Diferencias que el sistema encontró al comparar documentos. Ninguna es
      una conclusión: cada una dice qué se detectó, con qué cuenta y de qué foja sale, para
      que una persona la verifique y decida si es relevante.</p>
    <div class="filtros-chips" role="group" aria-label="Tipo">${chipsTipo}</div>
    <div class="filtros-chips" role="group" aria-label="Estado de revisión">${chipsEstado}
      ${contratacion ? `<a class="chip-filtro activo" href="${enlace({contratacion_id: ''})}"
         title="Quitar el filtro">Sólo esta contratación ✕</a>` : ''}</div>
    ${pag.length ? `<div class="hz-lista">
      <div class="hz-cabeza" aria-hidden="true"><span>Tipo</span><span>Qué</span>
        <span>Dónde</span><span>Fuente</span><span>Revisión</span></div>
      ${pag.map(fila).join('')}</div>`
      : `<p class="nota-seccion">Ningún hallazgo con estos filtros.</p>`}
    ${paginador}
    ${d.total > (d.hallazgos || []).length ? `<p class="nota-seccion">Se trajeron los primeros
      ${fmtNum.format((d.hallazgos || []).length)} de ${fmtNum.format(d.total)}: usá los filtros
      de arriba para ver el resto.</p>` : ''}
  `);
}

document.addEventListener('click', async e => {
  if (e.target.classList.contains('enlace-fuente')) {
    const fuente = JSON.parse(e.target.dataset.fuente);
    abrirDosFojas(fuente);
  }
});

// Un clic, como cualquier botón. Estaba en `dblclick`: con un clic no se guardaba nada.
document.addEventListener('click', async e => {
  const boton = e.target.closest ? e.target.closest('[data-guardar-hallazgo]') : null;
  if (boton) {
    const id = boton.dataset.guardarHallazgo;
    const select = document.getElementById('rev-estado-' + id);
    const nota = document.getElementById('rev-nota-' + id);
    if (boton.disabled) return;
    boton.disabled = true;
    try {
      await api(`/api/hallazgo/${id}/revision`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({estado: select.value, nota: nota.value})
      });
      await redibujarTrasAccion('Revisión guardada', vHallazgosContrataciones);
    } catch (err) {
      toast('Falló: ' + err.message);
    } finally {
      boton.disabled = false;
    }
  }
});

function toast(msj) {
  let t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msj;
  document.body.appendChild(t);
  setTimeout(() => { t.classList.add('fadeout'); setTimeout(() => t.remove(), 300); }, 3000);
}

function dialogoConfirm(msj) {
  return new Promise(resolve => {
    const d = document.createElement('dialog');
    d.innerHTML = `<p>${esc(msj)}</p><div class="acciones-fila"><button type="button" class="boton" id="d-ok">Aceptar</button><button type="button" class="boton gris" id="d-no">Cancelar</button></div>`;
    document.body.appendChild(d);
    d.querySelector('#d-ok').onclick = () => { d.close(); d.remove(); resolve(true); };
    d.querySelector('#d-no').onclick = () => { d.close(); d.remove(); resolve(false); };
    d.showModal();
  });
}
