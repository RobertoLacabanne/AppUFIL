// CDP sin dependencias: navegador real, frontend sin modificar y backend sintético.
const cfg = JSON.parse(process.argv[2]);
const evidencia = {};
const pausa = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const destino = await (await fetch(`http://127.0.0.1:${cfg.cdp}/json/new?about:blank`,{method:'PUT'})).json();
  const ws = new WebSocket(destino.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { ws.onopen=resolve; ws.onerror=reject; });
  let id=0; const pendientes=new Map();
  ws.onmessage=e=>{const m=JSON.parse(e.data); if(m.id&&pendientes.has(m.id)){
    const [ok,fail]=pendientes.get(m.id); pendientes.delete(m.id); m.error?fail(m.error):ok(m.result);
  }};
  ws.onclose=()=>{for(const [,fail] of pendientes.values()) fail(Error('El navegador cerró CDP durante una observación'));};
  function cdp(method,params={}) { return new Promise((ok,fail)=>{
    const n=++id;
    const timer=setTimeout(()=>{pendientes.delete(n);fail(Error('CDP sin respuesta: '+method+' '+(params.expression||'').slice(0,180)));},12000);
    pendientes.set(n,[r=>{clearTimeout(timer);ok(r)},e=>{clearTimeout(timer);fail(Error(String(e)+'; '+method+' '+(params.expression||'').slice(0,240)))}]);
    ws.send(JSON.stringify({id:n,method,params}));
  }); }
  async function evaluar(expression){const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,replMode:true});
    if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value;}
  async function hasta(expression){for(let i=0;i<120;i++){if(await evaluar(expression))return;await pausa(50);}throw Error('Timeout: '+expression);}
  await cdp('Network.enable'); await cdp('Runtime.enable'); await cdp('Page.enable');
  await cdp('Network.setCookie',{name:'ufil_legajo',value:cfg.slug,url:cfg.origen});
  await cdp('Page.navigate',{url:cfg.origen+'/#/ingesta'});
  await hasta(`typeof pedirQuitarArchivo === 'function' && document.querySelector('[data-lista="archivos"]') !== null`);
  await evaluar(`window.__errores=[]; window.__promesas=[]; window.__peticiones=[];
    addEventListener('error',e=>__errores.push(e.message));
    addEventListener('unhandledrejection',e=>{__promesas.push(String(e.reason));e.preventDefault()});
    window.__fetch=fetch; window.__api=api; window.__vPapelera=vPapelera;
    window.__vIngesta=vIngesta;
    window.fetch=async (...args)=>{const r=await __fetch(...args);__peticiones.push({ruta:String(args[0]),body:args[1]?.body,status:r.status});return r;};
    window.__cerrar=()=>document.querySelectorAll('dialog').forEach(d=>{d.close();d.remove();});  // close() encola el evento que la app usa para sacar el diálogo; sin quitarlo acá, el siguiente paso podía encontrar el #b-quitar de un diálogo ya cerrado.`);
  const selector = sha => `Array.from(document.querySelectorAll('button')).find(b=>b.dataset.sha===${JSON.stringify(sha)} || (b.getAttribute('onclick')||'').includes(${JSON.stringify(sha)}))`;
  evidencia.contrato = await evaluar(`(async()=>{const a=await api('/api/archivos');return a.archivos.map(f=>({nombre:f.nombre,confirmacion:f.confirmacion_quitar,procesando:f.procesando,revisiones:f.revisiones}));})()`);

  await evaluar(`${selector(cfg.casos.apostrofe)}.click()`);
  evidencia.apostrofe = await evaluar(`({errores:__errores.slice(),dialogos:document.querySelectorAll('dialog').length})`);
  await evaluar(`__cerrar()`);
  await evaluar(`${selector(cfg.casos.xss)}.click()`);
  evidencia.xss = await evaluar(`({codigoEjecutado:globalThis.__revisionXss===1,handler:${selector(cfg.casos.xss)}.getAttribute('onclick')})`);
  await evaluar(`__cerrar()`);

  await evaluar(`${selector(cfg.casos.normal)}.click(); document.querySelector('#b-quitar').click(); document.querySelector('#b-quitar').click()`);
  await hasta(`__peticiones.some(p=>p.ruta==='/api/archivo/quitar') && document.querySelectorAll('dialog').length===0`);
  evidencia.quitar = await evaluar(`__peticiones.filter(p=>p.ruta==='/api/archivo/quitar')`);
  await evaluar(`location.hash='#/papelera'`);
  await hasta(`document.querySelector('#vista h2')?.textContent === 'Papelera de archivos' && document.querySelector('button.peligro')`);
  evidencia.navegacion = await evaluar(`({seccion:seccionDe('#/papelera').id,enlaceVisible:!!document.querySelector('#nav-secciones a[href="#/papelera"]'),titulo:document.title})`);

  await evaluar(`pedirRestaurarArchivo(${JSON.stringify(cfg.casos.normal)}); pedirRestaurarArchivo(${JSON.stringify(cfg.casos.normal)})`);
  await hasta(`__peticiones.filter(p=>p.ruta==='/api/archivo/restaurar').length>=1`);
  await pausa(300);
  evidencia.dobleRestauracion = await evaluar(`({peticiones:__peticiones.filter(p=>p.ruta==='/api/archivo/restaurar'),texto:document.querySelector('dialog')?.textContent})`);
  await evaluar(`__cerrar(); await api('/api/archivo/quitar',{method:'POST',body:JSON.stringify({sha256:${JSON.stringify(cfg.casos.normal)},confirmacion:${JSON.stringify('QUITAR '+cfg.casos.normal)}})}); await vPapelera()`);
  await evaluar(`pedirDestruirArchivo(${JSON.stringify(cfg.casos.normal)},'sintetico.pdf',${JSON.stringify('DESTRUIR '+cfg.casos.normal)});
    document.querySelector('#conf-destruir').value='DESTRUIR';document.querySelector('#conf-destruir').dispatchEvent(new Event('input'));document.querySelector('#b-destruir').click()`);
  await hasta(`__peticiones.some(p=>p.ruta==='/api/archivo/destruir')`);
  evidencia.destruir=await evaluar(`__peticiones.filter(p=>p.ruta==='/api/archivo/destruir')`);

  await evaluar(`__cerrar(); await pedirQuitarArchivo('invalido','sintetico','QUITAR invalido',false,0);document.querySelector('#b-quitar').click()`);
  await hasta(`document.querySelector('dialog')?.textContent.includes('64 caracteres')`);
  evidencia.shaInvalido=await evaluar(`({respuesta:__peticiones.filter(p=>p.ruta==='/api/archivo/quitar').at(-1),mensaje:document.querySelector('dialog').textContent.trim()})`);
  await evaluar(`__cerrar(); await pedirQuitarArchivo('a'.repeat(64),'sintetico','QUITAR '+ 'a'.repeat(64),true,0)`);
  evidencia.procesando=await evaluar(`document.querySelector('dialog').textContent.trim()`);
  await evaluar(`__cerrar()`);

  // A partir de aquí: respuestas controladas para fallos y condiciones de carrera.
  await evaluar(`api=async ruta=>ruta==='/api/cuentas'?{legajo:{slug:'test'},documentos:0}:{archivos:[],total:0,limite:100,desde:0}; await vPapelera()`);
  evidencia.vacia=await evaluar(`vista.textContent.includes('La papelera está vacía')`);
  await evaluar(`api=async ruta=>ruta==='/api/cuentas'?{legajo:{slug:'test'},documentos:0}:{}; await vPapelera()`);
  evidencia.respuestaIncompleta=await evaluar(`vista.textContent.includes('La papelera está vacía')`);
  await evaluar(`api=async ruta=>ruta==='/api/cuentas'?{legajo:null,documentos:0}:{archivos:[{sha256:'a'.repeat(64),nombre:'en papelera.pdf'}]}; await vPapelera()`);
  evidencia.baseSuelta=await evaluar(`({muestraArchivo:vista.textContent.includes('en papelera.pdf'),texto:vista.textContent.trim().slice(0,240)})`);

  await evaluar(`__cerrar();api=async()=>{throw new Error('Fallo de red simulado')}; await pedirRestaurarArchivo('a'.repeat(64))`);
  evidencia.errorRed=await evaluar(`document.querySelector('dialog').textContent.includes('Fallo de red simulado')`);
  await evaluar(`__cerrar();window.__contador=0;api=async ruta=>{if(ruta==='/api/archivo/restaurar')return {ok:true};throw new Error('GET posterior falló')}; await pedirRestaurarArchivo('a'.repeat(64))`);
  await pausa(100);
  evidencia.refrescoSinCatch=await evaluar(`({promesas:__promesas.slice(),dialogos:document.querySelectorAll('dialog').length})`);

  await evaluar(`__cerrar();window.__soltar=null;api=async ruta=>{if(ruta==='/api/archivo/restaurar')return await new Promise(r=>__soltar=r);return ruta==='/api/cuentas'?{legajo:{slug:'test'},documentos:0}:{archivos:[],total:0,limite:100,desde:0}};
    pedirRestaurarArchivo('a'.repeat(64));__cerrar();location.hash='#/informes';`);
  await pausa(100);
  await evaluar(`vista.innerHTML='<h2>Informes elegidos por la persona</h2>';__soltar({ok:true})`);
  await pausa(100);
  evidencia.perdidaContexto=await evaluar(`({hash:location.hash,vista:vista.textContent.trim().slice(0,160)})`);

  await evaluar(`__cerrar();window.__destrucciones=0;api=async()=>{__destrucciones++;return new Promise(()=>{})};
    await pedirDestruirArchivo('a'.repeat(64),'sintetico','DESTRUIR '+'a'.repeat(64));
    window.__i=document.querySelector('#conf-destruir');window.__b=document.querySelector('#b-destruir');
    __i.value='DESTRUIR';__i.dispatchEvent(new Event('input'));__b.click();
    __i.value='DESTRUI';__i.dispatchEvent(new Event('input'));__i.value='DESTRUIR';__i.dispatchEvent(new Event('input'));__b.click()`);
  evidencia.dobleDestruccion=await evaluar(`({peticiones:__destrucciones,botonHabilitado:!__b.disabled})`);
  await evaluar(`__cerrar()`);

  await evaluar(`api=async ruta=>ruta==='/api/cuentas'?{legajo:{slug:'test'},documentos:0}:(()=>{const u=new URL(ruta,location.origin),limite=Number(u.searchParams.get('limite')||1500),desde=Number(u.searchParams.get('desde')||0);return {archivos:Array.from({length:Math.min(limite,1500-desde)},(_,i)=>({sha256:(i+desde).toString(16).padStart(64,'0'),nombre:'SINTETICO '+(i+desde),documentos:1,bytes:100})),total:1500,limite,desde}})();
    window.__inicio=performance.now();await vPapelera();window.__duracion=performance.now()-__inicio;`);
  evidencia.listaGrande=await evaluar(`({filas:vista.querySelectorAll('tbody tr').length,botones:vista.querySelectorAll('button').length,ms:Math.round(__duracion),paginador:!!vista.querySelector('.paginador,.paginacion-link'),buscador:!!vista.querySelector('input')})`);

  // Geometría real, con imagen SVG sintética de dimensiones conocidas.
  await evaluar(`api=__api;const img=document.querySelector('#visor-img');img.src='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800"><rect x="120" y="160" width="60" height="40" fill="blue"/></svg>');
    await img.decode();document.querySelector('#visor').hidden=false;
    const m=document.querySelector('#visor-marco');m.hidden=false;m.style.left='20%';m.style.top='20%';m.style.width='10%';m.style.height='5%';
    visorZoom=1;aplicarZoomVisor();`);
  const geometria=`(()=>{const i=document.querySelector('#visor-img').getBoundingClientRect(),m=document.querySelector('#visor-marco').getBoundingClientRect();return {imagenAncho:i.width,marcoX:m.left-i.left,marcoY:m.top-i.top,esperadoX:i.width*.2,esperadoY:i.height*.2}})()`;
  evidencia.zoomAntes=await evaluar(geometria);
  await evaluar(`visorZoom=2;aplicarZoomVisor()`);
  evidencia.zoomDespues=await evaluar(geometria);
  evidencia.erroresObservados=await evaluar(`({errores:__errores,promesas:__promesas})`);
  evidencia.clasesVisor=await evaluar(`document.querySelector('.visor-controles').className`);
  console.log(JSON.stringify(evidencia,null,2));
  ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
