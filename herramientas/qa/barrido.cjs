// Recorre todas las rutas de AppUFIL en un Chrome real por CDP.
// Captura pantalla, errores de consola y un diagnóstico del DOM por pantalla.
const fs = require('fs');
const path = require('path');

const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const ORIGEN = process.env.ORIGEN || 'http://127.0.0.1:8799';
const SALIDA = process.env.SALIDA || './qa';
const ANCHO = Number(process.env.ANCHO || 1920);
const ALTO = Number(process.env.ALTO || 1080);
const SOLO = (process.env.SOLO || '').split(',').filter(Boolean);

const RUTAS = [
  ['panel', '#/panel'],
  ['legajos', '#/legajos'],
  ['ingesta', '#/ingesta'],
  ['contrataciones', '#/contrataciones'],
  ['contratacion', '#/contratacion?id=14'],
  ['precios', '#/precios'],
  ['renglon', '#/renglon?id=1'],
  ['hallazgos', '#/hallazgos'],
  ['superposiciones', '#/superposiciones'],
  ['cruce', '#/cruce'],
  ['interpretacion', '#/interpretacion'],
  ['numeros', '#/numeros'],
  ['consultas', '#/consultas'],
  ['entidades', '#/entidades'],
  ['entidad', '#/entidad/1'],
  ['personas', '#/personas'],
  ['persona', '#/persona/1'],
  ['sin-reconocer', '#/sin-reconocer'],
  ['conjuntos', '#/conjuntos'],
  ['contratos', '#/contratos'],
  ['comprobantes', '#/comprobantes'],
  ['fojas', '#/fojas'],
  ['foliatura', '#/foliatura'],
  ['tablas', '#/tablas'],
  ['documento', '#/documento/1'],
  ['cronologia', '#/cronologia'],
  ['relaciones', '#/relaciones'],
  ['buscar', '#/buscar'],
  ['guardadas', '#/guardadas'],
  ['colecciones', '#/colecciones'],
  ['informes', '#/informes'],
  ['cola', '#/cola'],
  ['identidad', '#/identidad'],
  ['afuera', '#/afuera'],
  ['reasociaciones', '#/reasociaciones'],
  ['equipo', '#/equipo'],
  ['actualizacion', '#/actualizacion'],
  ['papelera', '#/papelera'],
  ['como-funciona', '#/como-funciona'],
  ['salud', '#/salud'],
  ['acerca', '#/acerca'],
];

const pausa = ms => new Promise(r => setTimeout(r, ms));

const DIAG = `(() => {
  const v = document.querySelector('#vista');
  const txt = (v.innerText || '');
  const cs = getComputedStyle;
  const anchoDoc = document.documentElement.scrollWidth;
  const desborde = anchoDoc > window.innerWidth + 1;
  const salidos = [...v.querySelectorAll('*')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.right > window.innerWidth + 2;
  }).slice(0, 8).map(e => e.tagName.toLowerCase() +
      (typeof e.className === 'string' && e.className ? '.' + e.className.split(/\\s+/).slice(0,3).join('.') : ''));
  const mono = [...v.querySelectorAll('*')].filter(e =>
      /mono|Courier/i.test(cs(e).fontFamily) && e.children.length === 0 && e.textContent.trim()).length;
  const conteos = {};
  for (const sel of ['table','.ficha','.tarjeta','.aviso','.sello','.boton','button','input','select','.vacio','.prosa','.cuenta'])
    conteos[sel] = v.querySelectorAll(sel).length;
  const noConsta = (txt.match(/NO CONSTA|NO EST\\u00c1|NO LE\\u00cdDO|SIN DATOS|SIN FECHAS|\\u00d8/gi) || []).length;
  const mayusculas = (txt.match(/\\b[A-Z\\u00c1\\u00c9\\u00cd\\u00d3\\u00da\\u00d1]{4,}\\b/g) || []).length;
  return {
    alto: v.scrollHeight, anchoDoc, desborde, salidos, mono, noConsta, mayusculas,
    conteos, vacio: txt.trim().length < 80,
    titulo: ((v.querySelector('h1,h2') || {}).innerText || '').slice(0,90),
    textoLargo: txt.length,
    muestra: txt.slice(0, 900)
  };
})()`;

(async () => {
  const destino = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?about:blank`, {method:'PUT'})).json();
  const ws = new WebSocket(destino.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let id = 0; const pend = new Map();
  const consola = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const [ok, fail] = pend.get(m.id); pend.delete(m.id); m.error ? fail(m.error) : ok(m.result); }
    if (m.method === 'Runtime.consoleAPICalled' && ['error','warning'].includes(m.params.type))
      consola.push({tipo:m.params.type, texto:(m.params.args||[]).map(a => a.value || a.description || '').join(' ').slice(0,300)});
    if (m.method === 'Runtime.exceptionThrown')
      consola.push({tipo:'excepcion', texto:String(m.params.exceptionDetails.text) + ' ' + String((m.params.exceptionDetails.exception||{}).description).slice(0,300)});
  };
  function cdp(method, params = {}) {
    return new Promise((ok, fail) => {
      const n = ++id;
      const t = setTimeout(() => { pend.delete(n); fail(Error('timeout CDP ' + method)); }, 30000);
      pend.set(n, [r => { clearTimeout(t); ok(r); }, e => { clearTimeout(t); fail(Error(JSON.stringify(e))); }]);
      ws.send(JSON.stringify({id:n, method, params}));
    });
  }
  async function evaluar(expression) {
    const r = await cdp('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true, replMode:true});
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result.value;
  }

  await cdp('Runtime.enable'); await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride', {width:ANCHO, height:ALTO, deviceScaleFactor:1, mobile:false});
  await cdp('Page.navigate', {url: ORIGEN + '/#/panel'});
  await pausa(1500);
  // Sin revisor, la aplicación abre «¿Quién está trabajando?» encima de todo y cada
  // captura sale tapada. TEMA=claro|oscuro fija el tema; sin TEMA queda el de fábrica.
  await evaluar(`localStorage.setItem('ufil.revisor', 'qa.barrido');
    ${process.env.TEMA ? `localStorage.setItem('ufil.tema', ${JSON.stringify(process.env.TEMA)});` : ''}
    true`);
  await cdp('Page.reload', {ignoreCache: true});
  await pausa(3000);

  fs.mkdirSync(SALIDA, {recursive:true});
  const informe = [];
  // EXTRA="ficha36=#/contratacion?id=36,otra=#/..." agrega rutas puntuales al recorrido.
  const extra = (process.env.EXTRA || '').split(',').filter(Boolean)
    .map(s => [s.slice(0, s.indexOf('=')), s.slice(s.indexOf('=') + 1)]);
  const todas = [...RUTAS, ...extra];
  const lista = SOLO.length ? todas.filter(([n]) => SOLO.includes(n)) : todas;

  for (const [nombre, hash] of lista) {
    consola.length = 0;
    try {
      await evaluar(`location.hash = ${JSON.stringify(hash)}`);
      await pausa(300);
      for (let i = 0; i < 80; i++) {
        if (await evaluar(`!document.querySelector('#vista .esqueleto')`)) break;
        await pausa(100);
      }
      await pausa(700);
      const diag = await evaluar(DIAG);
      const shot = await cdp('Page.captureScreenshot', {format:'png'});
      fs.writeFileSync(path.join(SALIDA, `${nombre}-${ANCHO}.png`), Buffer.from(shot.data, 'base64'));
      informe.push({ruta:nombre, hash, ...diag, consola:[...consola]});
      process.stdout.write(`${nombre} ok ${diag.alto}px${diag.desborde ? ' DESBORDE' : ''}${diag.vacio ? ' VACIO' : ''}${consola.length ? ' ' + consola.length + 'err' : ''}\n`);
    } catch (e) {
      informe.push({ruta:nombre, hash, error:String(e).slice(0, 300), consola:[...consola]});
      process.stdout.write(`${nombre} FALLO ${String(e).slice(0, 160)}\n`);
    }
  }
  fs.writeFileSync(path.join(SALIDA, `informe-${ANCHO}.json`), JSON.stringify(informe, null, 1));
  ws.close();
  process.exit(0);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
