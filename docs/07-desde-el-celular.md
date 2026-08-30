# Entrar desde un celular

Un fiscal que quiere mirar una superposición parado en un pasillo no va a volver al
escritorio a prender la computadora. Esto es para eso.

---

## Cómo se hace

En la computadora donde está el sistema:

```bash
python3 -m ufil.cli servir --red
```

Aparece un cartel con la dirección y una clave:

```
  ┌─ MODO RED ──────────────────────────────────────────────┐
  │ El sistema quedó visible para los demás equipos de      │
  │ esta red. Para entrar desde un celular, en el navegador:│
  │                                                         │
  │     http://192.168.1.40:8713                            │
  │                                                         │
  │     clave de acceso:   9AN8SD                           │
  └─────────────────────────────────────────────────────────┘
```

En el teléfono, conectado al **mismo wifi**: abrir el navegador, escribir esa dirección,
escribir la clave. Listo.

La clave **cambia cada vez que se levanta el sistema**. Es a propósito: una clave que
queda escrita en algún lado es una clave que dentro de seis meses tiene medio edificio.

---

## Por qué hay clave, y qué protege

Sin `--red`, el sistema escucha en `127.0.0.1` y lo ve **sólo quien está sentado en esa
computadora**. Es el modo por omisión y es el más seguro.

Con `--red`, lo ve **cualquiera que esté en la misma red**. Eso, sobre un legajo penal,
no se puede dejar abierto: alcanzaría con que alguien escribiera la dirección IP. Por
eso el modo red pide clave, y por eso la clave no es opcional ni configurable: se activa
sola con la dirección de escucha, para que no exista la forma de abrirlo a la red y
quedarse sin clave por olvido.

**Lo que la clave resuelve:** que un compañero curioso, alguien de otra oficina, o
cualquier equipo conectado al wifi abra el legajo escribiendo una dirección.

**Lo que la clave NO resuelve, y conviene tenerlo claro:** el tráfico va en HTTP plano.
Quien pueda mirar los paquetes de esa red —el administrador de la red, un equipo
intervenido— puede leer lo que se transmite, la clave incluida. Para taparlo haría falta
HTTPS con certificado propio, y un certificado propio en máquinas sin internet significa
instalarlo a mano en cada teléfono.

**La decisión tomada fue:** modo red para la red de la fiscalía, que está bajo control;
`127.0.0.1` —el modo por omisión— para todo lo demás. Si el sistema alguna vez tuviera
que salir de esa red, esto hay que revisarlo antes.

Tras cinco intentos fallidos desde una misma dirección, cada intento nuevo empieza a
hacerse esperar. No es una barrera infranqueable: es que probar combinaciones a lo bruto
deje de ser gratis.

---

## Qué se puede hacer desde el teléfono

Todo. No es una versión recortada: son las mismas pantallas, reordenadas para una
pantalla angosta y para el dedo en vez del mouse.

| | En el celular |
|---|---|
| Panel, superposiciones, fichas | Igual, en una columna |
| Buscar | Igual |
| **Cola de revisión** | La lupa con el recorte de la foja queda **clavada arriba** y la lista corre por debajo. Se decide con botones grandes, sin atajos de teclado |
| Ver un contrato | Los datos arriba, la foja abajo |
| Cargar escaneos | Anda, pero conviene hacerlo desde la computadora: son archivos grandes |

Tres cosas cambian a propósito en la pantalla chica:

1. **El encabezado y el menú no quedan clavados arriba.** En una pantalla de teléfono se
   comían la cuarta parte del alto y el trabajo empezaba a la mitad. Se van con el scroll.
2. **Los botones son de dedo, no de mouse:** 44 píxeles de alto, que es la medida abajo
   de la cual se falla el toque.
3. **Los atajos de teclado se ocultan.** En un teléfono no hay teclado, y decir «apretá
   J» donde no hay J es peor que no decir nada.

---

## Lo que conviene NO hacer desde el teléfono

**Sacarle una foto a un contrato y subirla.** El sistema la va a aceptar, pero una foto
de celular es el peor material posible: sombra despareja, papel curvado, foco irregular.
Está medido en `docs/08-hasta-donde-aguanta-el-escaneo.md` qué pasa cuando la calidad
baja, y no es lindo. Los contratos entran por el escáner.
