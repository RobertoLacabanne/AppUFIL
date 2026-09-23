"""Compara dos barridos: python herramientas/qa/comparar.py <carpeta-antes> <carpeta-despues> [ancho].
Por pantalla: alto, monoespaciados, mayúsculas, ausencias y botones, antes -> después."""
import json, sys
from pathlib import Path
base = Path('.')

def cargar(carpeta, ancho):
    p = base / carpeta / f'informe-{ancho}.json'
    if not p.exists():
        return {}
    return {r['ruta']: r for r in json.load(open(p, encoding='utf-8'))}

antes = cargar(sys.argv[1] if len(sys.argv) > 1 else '1920', sys.argv[3] if len(sys.argv) > 3 else '1920')
despues = cargar(sys.argv[2] if len(sys.argv) > 2 else 'gemini1920', sys.argv[3] if len(sys.argv) > 3 else '1920')

cab = f"{'ruta':<17}{'alto':>14}{'mono':>12}{'MAYUS':>12}{'ausenc':>12}{'botones':>12}  notas"
print(cab); print('-' * len(cab))
for k in antes:
    a, d = antes[k], despues.get(k)
    if not d:
        print(f'{k:<17}  (sin dato después)'); continue
    if a.get('error') or d.get('error'):
        print(f"{k:<17}  ERROR antes={bool(a.get('error'))} despues={bool(d.get('error'))}")
        if d.get('error'): print('      ', d['error'][:150])
        continue
    def par(campo, sub=None):
        va = a.get(campo, 0) if sub is None else a.get('conteos', {}).get(sub, 0)
        vd = d.get(campo, 0) if sub is None else d.get('conteos', {}).get(sub, 0)
        flecha = '=' if va == vd else ('v' if vd < va else '^')
        return f'{va}{flecha}{vd}'
    notas = []
    if d.get('desborde'): notas.append('DESBORDE')
    if d.get('vacio') and not a.get('vacio'): notas.append('QUEDO VACIO')
    if a.get('vacio') and not d.get('vacio'): notas.append('YA NO VACIO')
    if d.get('consola'): notas.append(f"{len(d['consola'])}err")
    print(f"{k:<17}{par('alto'):>14}{par('mono'):>12}{par('mayusculas'):>12}"
          f"{par('noConsta'):>12}{par('', 'button'):>12}  {' '.join(notas)}")
