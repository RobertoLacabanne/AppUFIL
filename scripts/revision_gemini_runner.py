"""Revisión reproducible: frontend detached intacto + backend actual + datos sintéticos.

Ejecutar: python -m unittest scripts.revision_gemini_runner -v
Requiere Node >=22 y Edge instalado. REVISION_WEB selecciona la interfaz;
por omisión usa .revision-gemini/ufil/web. REVISION_EVIDENCIA selecciona la salida.
No forma parte del discovery de pruebas del producto.
"""
import json
import hashlib
import os
import subprocess
import socket
import time
import unittest
from urllib.request import urlopen
from pathlib import Path
from unittest.mock import patch

from pruebas import test_nucleo_web as soporte
from pruebas.test_papelera_archivos import sembrar
from ufil import config, db

RAIZ = Path(__file__).resolve().parents[1]


class RevisionGemini(unittest.TestCase):
    setUp = soporte.NucleoPorHTTP.setUp
    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir

    def test_revision_con_navegador_real(self):
        web = Path(os.environ.get('REVISION_WEB', str(RAIZ/'.revision-gemini'/'ufil'/'web'))).resolve()
        self.assertTrue(web.is_dir())
        con = db.abrir(self.base)
        casos = {}
        try:
            for clave,nombre in [('normal','sintetico.pdf'),('apostrofe',"O'Brien.pdf"),
                                 ('xss',"x',globalThis.__revisionXss=1,'z.pdf")]:
                sha=sembrar(con,self.base.parent,texto='SINTETICO '+clave,completo=True)
                con.execute('UPDATE archivo SET nombre=? WHERE sha256=?',(nombre,sha))
                casos[clave]=sha
            con.commit()
        finally:
            con.close()
        perfil=self.temporal/'edge-profile'
        perfil.mkdir()
        edge=Path(os.environ.get('REVISION_EDGE',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'))
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            cdp = s.getsockname()[1]
        with patch.object(config,'WEB',web):
            p=subprocess.Popen([str(edge),'--headless=new','--no-first-run','--no-default-browser-check',
                '--disable-gpu',f'--remote-debugging-port={cdp}',f'--user-data-dir={perfil}','about:blank'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                limite=time.monotonic()+20
                while True:
                    try:
                        with urlopen(f'http://127.0.0.1:{cdp}/json/version', timeout=1) as r:
                            json.load(r)
                        break
                    except OSError:
                        if time.monotonic() >= limite or p.poll() is not None:
                            self.fail(f'El navegador no publicó CDP (salida: {p.poll()})')
                        time.sleep(.1)
                datos={'cdp':cdp,
                       'origen':f'http://127.0.0.1:{self.srv.server_address[1]}',
                       'slug':self.legajo.slug,'casos':casos}
                r=subprocess.run(['node',str(RAIZ/'scripts'/'revision_gemini_browser.cjs'),json.dumps(datos)],
                    capture_output=True,text=True,encoding='utf-8',timeout=90,cwd=RAIZ)
                self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
                evidencia=json.loads(r.stdout)
                evidencia['ejecucion'] = {
                    'web': str(web), 'app_js_sha256': hashlib.sha256((web/'app.js').read_bytes()).hexdigest(),
                    'fecha': db.ahora(), 'esquema_backend': db.ESQUEMA_VERSION,
                    'navegador': str(edge),
                    'metodo': 'Navegador headless por CDP, backend real y casos sintéticos; fallos de red y carreras simulados',
                }
                salida = Path(os.environ.get('REVISION_EVIDENCIA', str(RAIZ/'docs'/'revision-gemini-evidencia.json')))
                salida.write_text(
                    json.dumps(evidencia,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(json.dumps(evidencia,ensure_ascii=True,indent=2))
            finally:
                p.terminate()
                p.wait(timeout=10)


if __name__=='__main__':
    unittest.main()
