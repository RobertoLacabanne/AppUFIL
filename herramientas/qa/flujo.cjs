// El recorrido de una persona que abre un legajo y lo investiga, en un Chrome real.
//
//   abrir el legajo → entender el estado → encontrar una contratación → ver qué se
//   compró → abrir un precio → compararlo → abrir la fuente → revisar un hallazgo →
//   resolverlo → buscar un proveedor → llegar a los informes
//
// Todo con clics sobre lo que la pantalla muestra: ningún paso escribe un id en la
// barra de direcciones. Si un paso no encuentra dónde hacer clic, el recorrido falla
// ahí, que es exactamente donde se perdería una persona.
//
// Uso (lo llama barrer.py con --flujo, o a mano con un Chrome abierto por CDP):
//   ORIGEN=http://127.0.0.1:8812 SALIDA=<carpeta> ANCHO=1366 ALTO=768 node flujo.cjs
const fs = require('fs');
const path = require('path');

const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const ORIGEN = process.env.ORIGEN || 'http://127.0.0.1:8812';
const SALIDA = process.env.SALIDA || './flujo';
const ANCHO = Number(process.env.ANCHO || 1366);
const ALTO = Number(process.env.ALTO || 768);
const pausa = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const destino = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?about:blank`, {method: 'PUT'})).json();
  const ws = new WebSocket(destino.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let id = 0; const pend = new Map(); const consola = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const [ok, fail] = pend.get(m.id); pend.delete(m.id); m.error ? fail(m.error) : ok(m.result); }
    if (m.method === 'Runtime.exceptionThrown')
      consola.push(String((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text).slice(0, 300));
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error')
      consola.push((m.params.args || []).map(a => a.value || a.description || '').join(' ').slice(0, 300));
  };
  const cdp = (method, params = {}) => new Promise((ok, fail) => {
    const n = ++id;
    const t = setTimeout(() => { pend.delete(n); fail(Error('timeout CDP ' + method)); }, 30000);
    pend.set(n, [r => { clearTimeout(t); ok(r); }, e => { clearTimeout(t); fail(Error(JSON.stringify(e))); }]);
    ws.send(JSON.stringify({id: n, method, params}));
  });
  const evaluar = async expr => {
    const r = await cdp('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true, replMode: true});
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result.value;
  };
  // Quieta es cuando no queda un esqueleto de carga y la vista ya tiene algo escrito.
  const quieto = async () => {
    for (let i = 0; i < 150; i++) {
      if (await evaluar(`!document.querySelector('#vista .esqueleto, #vista .cargando, #vista .cargando-tabla') &&
          (document.querySelector('#vista')?.innerText || '').trim().length > 40`)) break;
      await pausa(100);
    }
    await pausa(500);
  };
  // Hace clic en el primer elemento que cumple el selector y cuyo texto coincide.
  const clic = async (selector, texto) => {
    const hecho = await evaluar(`(() => {
      const t = ${JSON.stringify(texto || '')}.toLowerCase();
      const el = [...document.querySelectorAll(${JSON.stringify(selector)})]
        .find(e => e.offsetParent !== null && (!t || e.textContent.toLowerCase().includes(t)));
      if (!el) return false;
      el.scrollIntoView({block: 'center'}); el.click(); return true;
    })()`);
    if (!hecho) throw Error(`no encontré dónde hacer clic: ${selector}${texto ? ' «' + texto + '»' : ''}`);
    await quieto();
  };
  const hay = async (selector, texto) => evaluar(`(() => {
    const t = ${JSON.stringify(texto || '')}.toLowerCase();
    return [...document.querySelectorAll(${JSON.stringify(selector)})]
      .some(e => !t || e.textContent.toLowerCase().includes(t));
  })()`);

  fs.mkdirSync(SALIDA, {recursive: true});
  const pasos = [];
  let n = 0;
  const paso = async (nombre, fn) => {
    consola.length = 0;
    const t0 = Date.now();
    try {
      const nota = await fn();
      const shot = await cdp('Page.captureScreenshot', {format: 'png'});
      const archivo = `${String(++n).padStart(2, '0')}-${nombre}-${ANCHO}.png`;
      fs.writeFileSync(path.join(SALIDA, archivo), Buffer.from(shot.data, 'base64'));
      const hash = await evaluar('location.hash');
      pasos.push({paso: nombre, ok: consola.length === 0, hash, ms: Date.now() - t0, nota: nota || '', errores: [...consola]});
      process.stdout.write(`${consola.length ? 'ERR' : 'ok '} ${nombre}  ${hash}  ${nota || ''}${consola.length ? '  ' + consola[0] : ''}\n`);
    } catch (e) {
      // Qué había en pantalla cuando falló: sin esto, «no encontré dónde hacer clic»
      // no dice si la pantalla estaba vacía, en error o en otra ruta.
      let habia = '';
      try { habia = await evaluar(`location.hash + ' | ' + (document.querySelector('#vista')?.innerText || '').split(String.fromCharCode(10)).join(' ').slice(0, 300)`); } catch (_) {}
      try {
        const shot = await cdp('Page.captureScreenshot', {format: 'png'});
        fs.writeFileSync(path.join(SALIDA, `FALLO-${nombre}-${ANCHO}.png`), Buffer.from(shot.data, 'base64'));
      } catch (_) {}
      process.stdout.write(`      en pantalla: ${habia}
`);
      pasos.push({paso: nombre, ok: false, error: String(e).slice(0, 300), habia, errores: [...consola]});
      process.stdout.write(`FALLO ${nombre}: ${String(e).slice(0, 200)}\n`);
      throw e;
    }
  };

  await cdp('Runtime.enable'); await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride', {width: ANCHO, height: ALTO, deviceScaleFactor: 1, mobile: false});
  await cdp('Page.navigate', {url: ORIGEN + '/#/panel'});
  await pausa(1500);
  await evaluar(`localStorage.setItem('ufil.revisor', 'qa.flujo'); true`);
  await cdp('Page.reload', {ignoreCache: true});
  await pausa(2500);

  let fallo = null;
  try {
    await paso('resumen', async () => {
      await quieto();
      if (!await hay('#vista h1, #vista h2')) throw Error('el resumen no tiene título');
      if (!await hay('#vista .cifra', 'contrataciones')) throw Error('el resumen no dice cuántas contrataciones hay');
      return await evaluar(`[...document.querySelectorAll('#vista .tarea b')].map(b => b.textContent).join(' · ')`);
    });
    await paso('contrataciones', () => clic('.nav-lateral a, nav a', 'Contrataciones'));
    await paso('una-contratacion', async () => {
      // La que tenga hallazgos: es por donde empezaría una persona.
      const conHallazgos = await hay('#vista .chip-hallazgos');
      if (conHallazgos) {
        await evaluar(`(() => { const f = document.querySelector('#vista .chip-hallazgos').closest('tr');
          f.querySelector('a[href^="#/contratacion"]').click(); return true; })()`);
        await quieto();
      } else await clic('#vista a[href^="#/contratacion"]');
      if (!await hay('#vista h2', 'qué se compró')) throw Error('la ficha no dice qué se compró');
      return await evaluar(`document.querySelector('#vista h1').textContent`);
    });
    await paso('fuente-de-un-precio', async () => {
      await clic('#vista .enlace-fuente');
      const abierto = await evaluar(`!!document.querySelector('dialog[open], .visor:not([hidden]), #visor:not([hidden]), .panel-fuente, .dos-fojas')`);
      if (!abierto) throw Error('la fuente no abrió ningún visor');
      await evaluar(`document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true`);
      await pausa(400);
      return 'visor abierto';
    });
    await paso('items-y-precios', () => clic('.nav-lateral a, nav a', 'Ítems y precios'));
    await paso('comparar-un-precio', async () => {
      if (await hay('#vista a.enlace-comparar')) await clic('#vista a.enlace-comparar');
      else await clic('#vista a[href^="#/renglon"]');
      if (!await hay('#vista h1')) throw Error('la comparación no tiene título');
      return await evaluar(`(document.querySelector('#vista .cifras') || document.querySelector('#vista .aviso') || {}).textContent?.replace(/\\s+/g, ' ').slice(0, 160) || ''`);
    });
    await paso('hallazgos', () => clic('.nav-lateral a, nav a', 'Hallazgos'));
    await paso('abrir-un-hallazgo', async () => {
      await clic('#vista details.hz > summary');
      if (!await hay('#vista details.hz[open] [data-guardar-hallazgo]')) throw Error('el hallazgo abierto no ofrece dónde resolverlo');
      return await evaluar(`document.querySelector('#vista details.hz[open] .hz-tipo').textContent`);
    });
    await paso('resolver-el-hallazgo', async () => {
      await evaluar(`(() => { const d = document.querySelector('#vista details.hz[open]');
        d.querySelector('select').value = 'relevante';
        d.querySelector('textarea').value = 'Verificado contra la foja en el recorrido de QA.';
        d.querySelector('[data-guardar-hallazgo]').click(); return true; })()`);
      await pausa(1200); await quieto();
      const quedo = await hay('#vista .hz-estado', 'relevante');
      if (!quedo) throw Error('después de guardar, ningún hallazgo figura como relevante');
      return 'guardado como relevante';
    });
    await paso('proveedores', () => clic('.nav-lateral a, nav a', 'Proveedores'));
    await paso('buscar-un-proveedor', async () => {
      const campo = await evaluar(`(() => { const i = document.querySelector('#vista input[type="search"], #vista input[type="text"]');
        if (!i) return false; i.value = '30-'; i.dispatchEvent(new Event('input', {bubbles: true})); return true; })()`);
      await pausa(800);
      if (!campo) return 'la pantalla no tiene buscador';
      await clic('#vista a[href^="#/entidad"], #vista tr[data-href], #vista tbody tr');
      return await evaluar(`(document.querySelector('#vista h1') || {}).textContent || ''`);
    });
    await paso('informes', async () => {
      await clic('.nav-lateral a, nav a', 'Informes');
      const accion = await hay('#vista a, #vista button', 'descargar')
        || await hay('#vista a, #vista button', 'generar')
        || await hay('#vista a, #vista button', 'sacar en');
      if (!accion)
        throw Error('Informes no ofrece cómo generar o descargar un informe');
      return 'con acción de descarga';
    });
  } catch (e) { fallo = e; }

  fs.writeFileSync(path.join(SALIDA, `flujo-${ANCHO}.json`), JSON.stringify(pasos, null, 1));
  ws.close();
  process.exit(fallo || pasos.some(p => !p.ok) ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
