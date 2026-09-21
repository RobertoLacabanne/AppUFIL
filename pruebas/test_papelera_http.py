"""Contrato de Gemini ejercitado por HTTP real, sin tocar la interfaz."""
import unittest
from unittest.mock import patch

from pruebas import test_nucleo_web as soporte
from pruebas.test_papelera_archivos import sembrar
from ufil import db


class PapeleraHTTP(unittest.TestCase):
    setUp = soporte.NucleoPorHTTP.setUp
    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir

    def archivo(self):
        cx = db.abrir(self.base)
        try:
            return sembrar(cx, self.base.parent, completo=True)
        finally:
            cx.close()

    def test_contrato_quitar_listar_restaurar_destruir(self):
        sha = self.archivo()
        estado, datos = self.pedir('/api/archivos')
        self.assertEqual(estado, 200)
        a = datos['archivos'][0]
        self.assertTrue(a['tiene_revisiones_humanas'])
        self.assertEqual(a['documentos'], 1)
        self.assertFalse(a['procesando'])
        estado, _ = self.pedir('/api/archivo/quitar', {'sha256':sha,'confirmacion':a['confirmacion_quitar']}, 'POST')
        self.assertEqual(estado, 200)
        self.assertEqual(self.pedir('/api/archivos')[1]['archivos'], [])
        estado, datos = self.pedir('/api/papelera/archivos')
        self.assertEqual(estado, 200)
        self.assertEqual(datos['archivos'][0]['sha256'], sha)
        self.assertEqual(self.pedir('/api/archivo/restaurar', {'sha256':sha}, 'POST')[0], 200)
        self.assertEqual(self.pedir('/api/archivo/restaurar', {'sha256':sha}, 'POST')[0], 409)
        self.assertEqual(self.pedir('/api/archivo/destruir', {'sha256':sha,'confirmacion':'DESTRUIR '+sha}, 'POST')[0], 409)
        self.pedir('/api/archivo/quitar', {'sha256':sha,'confirmacion':'QUITAR '+sha}, 'POST')
        self.assertEqual(self.pedir('/api/archivo/destruir', {'sha256':sha,'confirmacion':'DESTRUIR '+sha}, 'POST')[0], 200)
        self.assertEqual(self.pedir('/api/papelera/archivos')[1]['archivos'], [])

    def test_validacion_y_procesamiento(self):
        sha = self.archivo()
        for cuerpo in ([], {}, {'sha256':23}, {'sha256':sha,'confirmacion':'si'}):
            self.assertEqual(self.pedir('/api/archivo/quitar',cuerpo,'POST')[0],400)
        with patch.object(self.servidor.Procesador,'ocupado',return_value=True):
            self.assertTrue(self.pedir('/api/archivos')[1]['archivos'][0]['procesando'])
            self.assertEqual(self.pedir('/api/archivo/quitar',{'sha256':sha,'confirmacion':'QUITAR '+sha},'POST')[0],409)


if __name__ == '__main__':
    unittest.main()
