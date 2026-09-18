-- Esquema del sistema de análisis documental — UFIL Paraná
--
-- La separación de los dos carriles (sección 5 del pliego) es ESTRUCTURAL, no una
-- convención de nombres: el dato leído vive en `campo`, la conjetura vive en
-- `interpretacion` y no puede existir sin al menos una fila en
-- `interpretacion_fuente`. No hay forma de mezclarlos por accidente.

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────── CAPA 0: INGESTA ──
CREATE TABLE IF NOT EXISTS archivo (
  sha256        TEXT PRIMARY KEY,
  ruta_original TEXT NOT NULL,          -- solo lectura. Nunca se escribe ahí.
  nombre        TEXT NOT NULL,
  bytes         INTEGER NOT NULL,
  mtime         REAL,
  mime          TEXT,
  paginas       INTEGER,
  ingerido_en   TEXT NOT NULL
);

-- Copias exactas del mismo contenido en otras rutas. No se borra ninguna:
-- el original es inmutable, así que se registra el hecho y se sigue.
CREATE TABLE IF NOT EXISTS duplicado (
  sha256        TEXT NOT NULL REFERENCES archivo(sha256),
  ruta_original TEXT NOT NULL,
  visto_en      TEXT NOT NULL,
  PRIMARY KEY (sha256, ruta_original)
);

-- Ajustes del sistema. Hoy tiene una sola clave que importa: `demostracion`, que
-- enciende un aviso fijo en toda la interfaz. Si esto se muestra en una reunión, nadie
-- puede confundir un contrato inventado para probar el software con uno de la
-- Legislatura, y no puede depender de que alguien se acuerde de aclararlo.
CREATE TABLE IF NOT EXISTS ajuste (
  clave TEXT PRIMARY KEY,
  valor TEXT
);

-- Control de integridad de los originales. La restricción 2 no puede depender de un
-- muestreo al azar: sobre miles de archivos, mirar doce por corrida es no mirar.
-- Acá se registra cuándo se rehashó cada archivo, y `ufil verificar` empieza siempre
-- por los que hace más tiempo que no se miran. Así la cobertura avanza sola y se puede
-- decir con números cuánto del acervo está verificado y desde cuándo.
CREATE TABLE IF NOT EXISTS integridad (
  sha256        TEXT PRIMARY KEY REFERENCES archivo(sha256),
  verificado_en TEXT NOT NULL,
  ok            INTEGER NOT NULL,
  detalle       TEXT
);

CREATE TABLE IF NOT EXISTS procedencia (
  sha256          TEXT PRIMARY KEY REFERENCES archivo(sha256),
  legajo          TEXT,
  acta            TEXT,
  domicilio       TEXT,
  dispositivo     TEXT,
  fecha_secuestro TEXT,
  operador        TEXT,
  lote            TEXT
);

CREATE TABLE IF NOT EXISTS pagina (
  id            INTEGER PRIMARY KEY,
  sha256        TEXT NOT NULL REFERENCES archivo(sha256),
  nro           INTEGER NOT NULL,       -- 1-based, como la foliatura
  ancho_pt      REAL, alto_pt REAL,
  tiene_texto   INTEGER,                -- 1 = trae capa de texto nativa
  render        TEXT,                   -- derivado: PNG de la página
  render_escala REAL,                   -- px por punto, para mapear el recuadro
  rotacion      INTEGER DEFAULT 0,      -- grados que hubo que girar para dejarla derecha
  clasificacion TEXT,                   -- qué es esta foja: contrato_obra, factura, ...
  -- El dibujo de la foja, no los bytes del PDF que la envuelve. Es lo que permite
  -- reconocer el mismo papel cuando llega adentro de otro archivo. Ver ufil/huella.py.
  huella        TEXT,
  UNIQUE (sha256, nro)
);

-- ─────────────────────────────────────────────── CAPA 1: LECTURA DE LA PÁGINA ──
-- Una fila por (página × ruta de lectura). Nunca se pisan: conviven para poder
-- compararlas. De la comparación sale el conflicto.
CREATE TABLE IF NOT EXISTS lectura (
  id          INTEGER PRIMARY KEY,
  pagina_id   INTEGER NOT NULL REFERENCES pagina(id),
  ruta        TEXT NOT NULL,            -- nativo | ocr_a | ocr_b | vlm
  motor       TEXT NOT NULL,
  version     TEXT,
  confianza   REAL,
  ms          INTEGER,
  creado_en   TEXT NOT NULL,
  UNIQUE (pagina_id, ruta)
);

CREATE TABLE IF NOT EXISTS palabra (
  id         INTEGER PRIMARY KEY,
  lectura_id INTEGER NOT NULL REFERENCES lectura(id),
  orden      INTEGER NOT NULL,
  texto      TEXT NOT NULL,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL,   -- en puntos PDF, origen arriba-izquierda
  conf       REAL
);
CREATE INDEX IF NOT EXISTS ix_palabra_lectura ON palabra(lectura_id, orden);
-- Buscar una foja por su dibujo: es lo que se pregunta en cada carga, contra todas
-- las fojas que ya hay en el legajo.
CREATE INDEX IF NOT EXISTS ix_pagina_huella ON pagina(huella);

-- Índice de texto completo sobre lo leído de cada página. `remove_diacritics 2` hace
-- que buscar "locacion" encuentre "locación": el que busca no tiene por qué acordarse
-- de dónde iba la tilde, y el OCR tampoco es confiable con ellas.
CREATE VIRTUAL TABLE IF NOT EXISTS pagina_texto USING fts5(
  texto,
  sha256 UNINDEXED,
  nro    UNINDEXED,
  tokenize = "unicode61 remove_diacritics 2"
);

-- ────────────────────────────────────────── CAPA 2: DOCUMENTO Y CARRIL DE DATOS ──
-- Un archivo PDF puede contener VARIOS contratos: así es como sale de un escáner de
-- oficina cuando se pasa una pila de expedientes de corrido. Por eso el documento NO
-- es el archivo: es un TRAMO DE PÁGINAS dentro de un archivo.
--
-- Antes esto era `sha256 UNIQUE`, o sea un contrato por archivo, y un PDF con cinco
-- contratos producía un solo registro mezclando campos de contratos distintos. Un
-- registro inventado, y sin marca. Es la razón por la que existe `orden`.
-- `clave` es la IDENTIDAD de la pieza, y no es lo mismo que `id` ni que `orden`.
--
-- `orden` es una posición en una fila que se rearma en cada resegmentación: sirve para
-- ordenar y no para identificar. `id` lo asigna SQLite y se pierde apenas la pieza se
-- borra y se vuelve a crear, que es justamente lo que pasa al resegmentar.
--
-- `clave` es el archivo y la foja donde la pieza EMPIEZA. Las fojas de un PDF no se
-- mueven, así que una pieza que sigue empezando en la misma foja es la misma pieza
-- aunque haya cambiado de tipo, de largo o de posición. Eso es lo que permite que una
-- resegmentación conserve la pieza —y con ella las revisiones que cuelgan— en vez de
-- destruirla y tener que reasociar todo a mano.
--
-- `estado` distingue lo que el sistema sabe de lo que todavía no:
--   segmentado  — la pieza existe; los campos no se extrajeron todavía
--   extraido    — se le pasó un perfil y se le sacaron los campos
--   sin_perfil  — ningún extractor la reconoce. NO es un error y no se descarta:
--                 es un documento que el sistema todavía no sabe leer, y tiene que
--                 poder verse, buscarse, clasificarse a mano y recibir un extractor
--                 más adelante sin volver a subir nada.
CREATE TABLE IF NOT EXISTS documento (
  id            INTEGER PRIMARY KEY,
  sha256        TEXT NOT NULL REFERENCES archivo(sha256),
  orden         INTEGER NOT NULL DEFAULT 1,   -- 1º, 2º… contrato dentro del archivo
  clave         TEXT,                         -- identidad estable: <sha256>:<foja inicial>
  pagina_desde  INTEGER,
  pagina_hasta  INTEGER,
  tipo          TEXT NOT NULL,
  perfil        TEXT NOT NULL,
  camara        TEXT,
  estado        TEXT NOT NULL DEFAULT 'extraido',
  clasificado_por TEXT,                       -- si una persona dijo qué es esta pieza
  clasificado_en  TEXT,
  UNIQUE (sha256, orden)
);
CREATE INDEX IF NOT EXISTS ix_documento_clave ON documento(clave);

-- EL CARRIL DE DATOS.
-- Regla dura: o hay valor_literal, o hay nulo_motivo. Nunca los dos, nunca ninguno.
-- Regla dura: si hay valor_literal, hay anclaje (página + recuadro). Sin excepción.
CREATE TABLE IF NOT EXISTS campo (
  id            INTEGER PRIMARY KEY,
  documento_id  INTEGER NOT NULL REFERENCES documento(id),
  nombre        TEXT NOT NULL,
  valor_literal TEXT,                   -- tal como está en el papel, sin tocar
  nulo_motivo   TEXT,                   -- ilegible | ausente | ambiguo | conflicto
  pagina_nro    INTEGER,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL,
  ruta          TEXT,
  confianza     REAL,
  lectura_id    INTEGER REFERENCES lectura(id),
  -- Ver ufil/confianza.py: los ocho estados y cuáles son FIRMES. La regla que
  -- sostiene todo el sistema es que sólo un estado firme alimenta personas
  -- consolidadas, acumulados, superposiciones, interpretaciones y totales.
  estado        TEXT NOT NULL DEFAULT 'no_revisado',
  revisado_por  TEXT,
  revisado_en   TEXT,
  -- Lo que había leído la máquina antes de que una persona lo tocara. Se guarda para
  -- poder DESHACER: en una herramienta de trabajo la gente se equivoca revisando, y no
  -- tener vuelta atrás obliga a reprocesar el lote entero para arreglar un clic.
  valor_auto    TEXT,
  motivo_auto   TEXT,
  conf_auto     REAL,
  ruta_auto     TEXT,
  UNIQUE (documento_id, nombre),
  CHECK ((valor_literal IS NULL) <> (nulo_motivo IS NULL)),
  CHECK (valor_literal IS NULL OR (pagina_nro IS NOT NULL AND x0 IS NOT NULL))
);

-- Discrepancia entre rutas sobre un mismo campo. El sistema NO elige.
CREATE TABLE IF NOT EXISTS conflicto (
  id           INTEGER PRIMARY KEY,
  documento_id INTEGER NOT NULL REFERENCES documento(id),
  campo_nombre TEXT NOT NULL,
  estado       TEXT NOT NULL DEFAULT 'abierto',   -- abierto|resuelto
  resuelto_por TEXT, resuelto_en TEXT,
  UNIQUE (documento_id, campo_nombre)
);

CREATE TABLE IF NOT EXISTS conflicto_variante (
  id           INTEGER PRIMARY KEY,
  conflicto_id INTEGER NOT NULL REFERENCES conflicto(id),
  ruta         TEXT NOT NULL,
  valor        TEXT,
  confianza    REAL,
  pagina_nro   INTEGER, x0 REAL, y0 REAL, x1 REAL, y1 REAL
);

-- Lo que un modelo de visión PROPONE para un campo escrito a mano.
--
-- Vive en su propia tabla y NUNCA en `campo`. Es la línea que sostiene el carril de
-- datos: un valor sólo entra ahí cuando una persona lo confirmó mirando el recorte. La
-- propuesta existe para ahorrarle tipeo a esa persona, no para reemplazar su decisión.
--
-- Y es el registro de qué se le mandó a un servicio externo y cuándo, que en un legajo
-- penal hace falta poder responder.
CREATE TABLE IF NOT EXISTS propuesta (
  campo_id  INTEGER PRIMARY KEY REFERENCES campo(id) ON DELETE CASCADE,
  valor     TEXT,                  -- lo transcripto, tal cual; NULL si ilegible
  ilegible  INTEGER NOT NULL DEFAULT 0,
  nota      TEXT,
  modelo    TEXT NOT NULL,
  creado_en TEXT NOT NULL
);

-- Historial de decisiones humanas. NO se pisa nunca: una fila por decisión.
--
-- `revision_humana` guarda la ÚLTIMA decisión de cada campo, porque su clave primaria
-- es (sha256, orden, campo) y sirve para reaplicar revisiones tras un reproceso. Esto
-- es otra cosa: el rastro completo, para que un auditor pueda reconstruir quién cambió
-- qué, cuándo, desde qué valor y por qué. Sin esto, corregir dos veces borra la
-- primera corrección y con ella la explicación de por qué se hizo.
CREATE TABLE IF NOT EXISTS auditoria (
  id              INTEGER PRIMARY KEY,
  campo_id        INTEGER REFERENCES campo(id) ON DELETE SET NULL,
  -- Se guardan también los identificadores estables del documento: si el campo se
  -- borra en un reproceso, el rastro tiene que sobrevivir igual.
  sha256          TEXT NOT NULL,
  orden           INTEGER NOT NULL DEFAULT 1,
  campo_nombre    TEXT NOT NULL,
  accion          TEXT NOT NULL,          -- verificar | corregir | ilegible | ausente | ...
  valor_anterior  TEXT,
  valor_nuevo     TEXT,
  motivo_anterior TEXT,
  motivo_nuevo    TEXT,
  estado_anterior TEXT,
  estado_nuevo    TEXT,
  observacion     TEXT,                   -- lo que la persona quiso dejar dicho
  quien           TEXT NOT NULL,
  cuando          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auditoria_campo ON auditoria(campo_id);
CREATE INDEX IF NOT EXISTS ix_auditoria_doc   ON auditoria(sha256, orden, campo_nombre);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON auditoria(cuando);

CREATE TABLE IF NOT EXISTS excepcion (
  id           INTEGER PRIMARY KEY,
  documento_id INTEGER REFERENCES documento(id),
  sha256       TEXT,
  clase        TEXT NOT NULL,
  detalle      TEXT,
  estado       TEXT NOT NULL DEFAULT 'abierta',
  creado_en    TEXT NOT NULL
);

-- Registro DURADERO de la revisión humana de campos. Igual que `fusion_decidida`,
-- sobrevive a que se vuelva a correr el pipeline: se indexa por el hash del archivo y
-- el nombre del campo, no por ids que se regeneran. Si mejoramos el perfil de
-- extracción y reprocesamos el lote, el equipo NO pierde la revisión que ya hizo.
-- EL ANCLAJE, y por qué `orden` no alcanza.
--
-- `orden` es la posición de la pieza adentro del archivo: 1ª, 2ª, 3ª. Se recalcula en
-- cada reproceso contando los tramos que salieron de la clasificación. Eso significa
-- que NO identifica a la pieza: identifica a un lugar en una fila que se rearma.
--
-- El día que el sistema aprende un tipo documental nuevo, una foja que antes era
-- `continuacion` pasa a ser una pieza propia, todas las de atrás se corren un lugar, y
-- la corrección que una persona hizo sobre la 2ª pieza se reaplica sobre otra. Con
-- estado `corregido` y confianza 1,0, o sea entrando como firme en los totales. Está
-- reproducido en pruebas/test_actualizacion.py.
--
-- Por eso se guarda además DÓNDE estaba lo que la persona miró: la foja y el recuadro
-- del campo, y el tramo de la pieza en ese momento. La foja es el ancla fuerte —las
-- páginas de un PDF no se mueven— y el recuadro desempata cuando hay varias piezas en
-- la misma foja. Cuando el anclaje no alcanza para decidir, la revisión NO se aplica:
-- queda marcada `requiere_reasociacion` y la mira una persona. Perder trabajo humano es
-- malo; aplicarlo al documento equivocado en silencio es peor.
CREATE TABLE IF NOT EXISTS revision_humana (
  sha256 TEXT NOT NULL,
  orden  INTEGER NOT NULL DEFAULT 1,
  campo  TEXT NOT NULL,
  accion TEXT NOT NULL,              -- verificar | corregir | ilegible | ausente | ambiguo
  valor  TEXT,
  quien  TEXT NOT NULL,
  cuando TEXT NOT NULL,
  -- Anclaje estable. Nulo en las filas anteriores a que esto existiera: ver
  -- `_anclar_revisiones_viejas` en ufil/db.py, que las completa con lo que haya.
  ancla_pagina INTEGER,              -- foja donde estaba el campo que se revisó
  ancla_x0 REAL, ancla_y0 REAL, ancla_x1 REAL, ancla_y1 REAL,
  ancla_desde  INTEGER,              -- tramo de la pieza en el momento de revisar
  ancla_hasta  INTEGER,
  ancla_tipo   TEXT,                 -- qué era la pieza cuando se la revisó
  estado TEXT NOT NULL DEFAULT 'vigente',   -- vigente | requiere_reasociacion
  motivo TEXT,                       -- por qué necesita que alguien la mire
  PRIMARY KEY (sha256, orden, campo)
);
CREATE INDEX IF NOT EXISTS ix_revision_ancla ON revision_humana(sha256, ancla_pagina);

-- ───────────────────────────────────────────────── EL CONJUNTO DOCUMENTAL ──
-- Un escaneo o una entrega no es un archivo: es un CONJUNTO de archivos con un orden.
-- La oficina que responde un oficio manda nueve PDF, y el noveno sigue donde terminó
-- el octavo. Ese orden es información del expediente, no del sistema de archivos: se
-- pierde apenas alguien renombra un archivo, y con él se pierde la única pista de que
-- una pieza sigue en la parte siguiente.
--
-- Se guarda aparte del archivo a propósito: el mismo PDF puede llegar dos veces, en
-- dos entregas distintas, y eso es un hecho del expediente que hay que poder ver.
CREATE TABLE IF NOT EXISTS conjunto (
  id         INTEGER PRIMARY KEY,
  nombre     TEXT NOT NULL,
  organismo  TEXT,
  expediente TEXT,                    -- número del expediente o actuación de origen
  anio       INTEGER,
  nota       TEXT,
  creado_en  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conjunto_archivo (
  conjunto_id INTEGER NOT NULL REFERENCES conjunto(id),
  sha256      TEXT NOT NULL REFERENCES archivo(sha256),
  orden       INTEGER NOT NULL,       -- la parte 1, la parte 2… como llegaron
  PRIMARY KEY (conjunto_id, sha256)
);
CREATE INDEX IF NOT EXISTS ix_conjunto_orden ON conjunto_archivo(conjunto_id, orden);

-- ─────────────────────────── UNA PIEZA QUE SIGUE EN OTRO ARCHIVO ──
-- El límite de un PDF no es el límite de un documento. Un remito de cuatro fojas puede
-- quedar partido entre dos archivos porque así salió del escáner, y son UNA pieza.
--
-- El tramo principal sigue estando en `documento` (sha256, pagina_desde, pagina_hasta):
-- no se movió nada, para no romper lo que ya anda. Acá se agregan los tramos QUE SIGUEN,
-- en otro archivo o en fojas no contiguas del mismo.
CREATE TABLE IF NOT EXISTS pieza_tramo (
  id           INTEGER PRIMARY KEY,
  documento_id INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  sha256       TEXT NOT NULL REFERENCES archivo(sha256),
  pagina_desde INTEGER NOT NULL,
  pagina_hasta INTEGER NOT NULL,
  orden        INTEGER NOT NULL DEFAULT 1,   -- en qué orden se leen los tramos
  quien        TEXT,                          -- quién dijo que continúa; NULL = lo dedujo el sistema
  cuando       TEXT,
  UNIQUE (documento_id, sha256, pagina_desde)
);
CREATE INDEX IF NOT EXISTS ix_pieza_tramo ON pieza_tramo(documento_id, orden);

-- ────────────────────────────── QUÉ ETAPA PRODUJO ESTO, Y SI SIGUE VIGENTE ──
-- El acervo se carga durante años y el sistema aprende cosas nuevas en el medio. Cuando
-- eso pasa, lo ya cargado tiene que poder aprovecharlas SIN volver a subirlo y sin
-- volver a leerlo entero.
--
-- Para eso hay que poder contestar una pregunta que antes no se podía: «esto que está
-- guardado, ¿lo produjo el algoritmo que tengo ahora?». Hasta acá la respuesta salía de
-- mirar si existía una fila, y eso contesta otra cosa: que ALGUNA vez se procesó. Con
-- ese criterio, mejorar el OCR no vuelve a leer nada y agregar un extractor no alcanza
-- a lo viejo, porque la fila ya está.
--
-- Acá queda el SELLO de cada resultado: qué etapa, con qué versión de algoritmo y con
-- qué configuración. Un resultado cuyo sello no es el vigente está viejo, y se sabe sin
-- adivinarlo. Ver ufil/versiones.py.
--
-- `alcance_id` es texto a propósito: según la etapa es un SHA-256, el id de una página o
-- el de un documento, y una sola tabla para todas es lo que permite preguntar «qué
-- quedó viejo» de una vez en lugar de recorrer diez tablas distintas.
CREATE TABLE IF NOT EXISTS resultado_etapa (
  etapa      TEXT NOT NULL,
  alcance    TEXT NOT NULL,          -- archivo | pagina | documento | legajo
  alcance_id TEXT NOT NULL,          -- sha256 | pagina.id | documento.id | '' (legajo)
  version    INTEGER NOT NULL,       -- versión del algoritmo que lo produjo
  firma      TEXT NOT NULL,          -- huella de la configuración que lo produjo
  estado     TEXT NOT NULL,          -- pendiente|corriendo|parcial|terminado|
                                     -- desactualizado|fallido|detenido
  cuando     TEXT NOT NULL,
  -- `heredado` cuando el resultado ya estaba en la base antes de que existiera el
  -- sellado y se lo adoptó en vez de recalcularlo. Es distinto de haber comprobado que
  -- coincide, y la interfaz tiene que poder decir cuál de las dos cosas es.
  origen     TEXT,
  detalle    TEXT,
  PRIMARY KEY (etapa, alcance, alcance_id)
);
CREATE INDEX IF NOT EXISTS ix_resultado_etapa ON resultado_etapa(etapa, estado);

-- ───────────────────────────────── CAPA 3: NORMALIZACIÓN E IDENTIDAD (APARTE) ──
-- No pisa el literal. Es una tabla satélite, auditable y reversible sin volver
-- a leer los documentos.
CREATE TABLE IF NOT EXISTS normalizacion (
  campo_id   INTEGER PRIMARY KEY REFERENCES campo(id),
  tipo       TEXT NOT NULL,             -- fecha | monto | documento | nombre
  valor_norm TEXT,                      -- fecha ISO, monto en centavos, etc.
  nota       TEXT
);

CREATE TABLE IF NOT EXISTS persona (
  id           INTEGER PRIMARY KEY,
  clave_fuerte TEXT UNIQUE,             -- CUIL/CUIT/DNI normalizado. NULL si no hay.
  doc_tipo     TEXT,
  doc_numero   TEXT,
  creado_en    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persona_alias (
  id            INTEGER PRIMARY KEY,
  persona_id    INTEGER NOT NULL REFERENCES persona(id),
  nombre_literal TEXT NOT NULL,
  nombre_norm   TEXT NOT NULL,
  campo_id      INTEGER REFERENCES campo(id)
);

-- Qué persona corresponde a cada documento. Lo escribe la Capa 3 y lo reescribe
-- una fusión confirmada por una persona. Es el único lugar donde se decide que dos
-- contratos son "del mismo".
CREATE TABLE IF NOT EXISTS documento_persona (
  documento_id INTEGER PRIMARY KEY REFERENCES documento(id),
  persona_id   INTEGER NOT NULL REFERENCES persona(id),
  via          TEXT NOT NULL              -- clave_fuerte | sin_clave | fusion_confirmada
);

-- Registro DURADERO de las decisiones humanas sobre identidad. Sobrevive a que se
-- vuelva a correr todo el pipeline: se lo indexa por los nombres normalizados, no por
-- ids que se regeneran. Volver a procesar el lote no debe hacerle perder al equipo el
-- trabajo de revisión que ya hizo.
-- La clave NO puede ser el nombre normalizado: justamente en los casos que importan
-- (dos personas que se llaman parecido) el nombre es ambiguo y la decisión se pierde
-- al reprocesar. Se indexa por un identificador estable: la clave fuerte cuando hay
-- documento, y el SHA-256 de un documento representativo cuando no lo hay.
CREATE TABLE IF NOT EXISTS fusion_decidida (
  ident_a   TEXT NOT NULL,
  ident_b   TEXT NOT NULL,
  nombre_a  TEXT,
  nombre_b  TEXT,
  decision  TEXT NOT NULL,               -- aceptada | rechazada
  quien     TEXT NOT NULL,
  cuando    TEXT NOT NULL,
  PRIMARY KEY (ident_a, ident_b)
);

-- Las fusiones se PROPONEN. Aplicarlas es una decisión humana registrada.
CREATE TABLE IF NOT EXISTS fusion_propuesta (
  id          INTEGER PRIMARY KEY,
  persona_a   INTEGER NOT NULL REFERENCES persona(id),
  persona_b   INTEGER NOT NULL REFERENCES persona(id),
  nombre_a    TEXT,
  nombre_b    TEXT,
  ident_a     TEXT,
  ident_b     TEXT,
  score       REAL NOT NULL,
  motivo      TEXT NOT NULL,
  estado      TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente|aceptada|rechazada
  decidido_por TEXT, decidido_en TEXT,
  UNIQUE (persona_a, persona_b)
);

-- ────────────────────────────────────── CAPA 5: EL CARRIL DE INTERPRETACIÓN ──
-- Vive en su propia tabla. Toda interpretación exige al menos una fuente:
-- lo garantiza la aplicación al insertar y lo verifica `ufil verificar`.
CREATE TABLE IF NOT EXISTS interpretacion (
  id        INTEGER PRIMARY KEY,
  alcance   TEXT NOT NULL,              -- documento | persona | lote
  alcance_id TEXT,
  clase     TEXT NOT NULL,              -- resumen | patron | anomalia | relevancia
  texto     TEXT NOT NULL,
  origen    TEXT NOT NULL,              -- regla:<nombre> | modelo:<id>
  creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interpretacion_fuente (
  interpretacion_id INTEGER NOT NULL REFERENCES interpretacion(id),
  documento_id      INTEGER REFERENCES documento(id),
  campo_id          INTEGER REFERENCES campo(id),
  pagina_nro        INTEGER,
  nota              TEXT
);
CREATE INDEX IF NOT EXISTS ix_interp_fuente ON interpretacion_fuente(interpretacion_id);

-- ──────────────────────────── EL NÚMERO QUE EL PAPEL ESCRIBE DOS VECES ──
-- Un acto administrativo escribe cada cantidad en letras y en dígitos, y eso no es
-- una redundancia burocrática: es una salvaguarda para que un cero de más no pase
-- desapercibido. Para este sistema son DOS LECTURAS del propio documento, sin pagar
-- un segundo motor de OCR.
--
-- Se guardan TODOS los cotejos, no sólo los que fallan. Los que coinciden son la
-- prueba de que el importe se leyó bien; guardar sólo las diferencias dejaría un
-- hallazgo sin nada contra qué medirlo, y sin manera de saber si el sistema miró.
--
-- `coinciden` es NULL cuando alguna de las dos no se pudo leer. Eso NO es un
-- desacuerdo del papel: es una lectura que falló, y decir «no coinciden» sería
-- acusar al documento de algo que hizo el OCR.
CREATE TABLE IF NOT EXISTS cotejo_numero (
  id             INTEGER PRIMARY KEY,
  sha256         TEXT NOT NULL REFERENCES archivo(sha256),
  pagina_nro     INTEGER NOT NULL,
  clase          TEXT NOT NULL,          -- monto | cantidad
  letras         TEXT NOT NULL,          -- tal como está en el papel
  digitos        TEXT NOT NULL,          -- tal como está en el papel
  valor_letras   INTEGER,                -- centavos; NULL si no se pudo leer
  valor_digitos  INTEGER,
  coinciden      INTEGER,                -- 1 | 0 | NULL (no se pudo leer una)
  -- Dónde arranca en el texto de la foja. No se muestra: está para que dos veces
  -- la MISMA diferencia en la misma foja sean dos hallazgos y no uno. En la memoria
  -- descriptiva de este expediente «21 (VEINTIOCHO)» aparece en dos frases
  -- distintas, y son dos errores, no uno repetido.
  desde          INTEGER NOT NULL DEFAULT 0,
  UNIQUE (sha256, pagina_nro, letras, digitos, desde)
);
CREATE INDEX IF NOT EXISTS ix_cotejo_pagina ON cotejo_numero(sha256, pagina_nro);

-- ───────────────────────────────────────────────────────── VISTA DE TRABAJO ──
-- El contrato "consolidado". Un campo entra SOLO si tiene valor y no tiene
-- conflicto abierto. Todo lo demás sale NULL: ninguna consulta río abajo puede
-- tropezarse con un valor dudoso sin enterarse.
-- ═══════════════════════════════════════════════════════════════════════════
-- Las dos vistas de contrato, y por qué son dos
--
-- `v_contrato` trae SOLAMENTE campos en estado firme (ver ufil/confianza.py). Es la
-- que alimenta personas consolidadas, acumulados, superposiciones, interpretaciones y
-- totales. Se llama así —el nombre corto, el obvio— a propósito: un SELECT futuro que
-- se olvide de filtrar tiene que salir seguro, no peligroso.
--
-- `v_contrato_todo` trae todo lo que se leyó, firme o no, con el estado de cada campo
-- al lado. Es para las pantallas donde hay que MOSTRAR lo provisional como provisional:
-- la ficha del documento, la cola, los listados con su badge.
--
-- Antes de esta separación pasaba lo que este sistema existe para que no pase: nombres
-- de OCR con confianza 0,31 entraban como personas consolidadas, y el acumulado sumaba
-- $761.900 de montos que en ese momento estaban en la cola esperando revisión.
-- ═══════════════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS v_contrato;
CREATE VIEW v_contrato AS
SELECT
  d.id            AS documento_id,
  d.sha256        AS sha256,
  dp.persona_id   AS persona_id,
  d.camara        AS camara,
  d.tipo          AS tipo,
  a.nombre        AS archivo,
  MAX(CASE WHEN c.nombre='nombre'        THEN c.valor_literal END) AS nombre_literal,
  MAX(CASE WHEN c.nombre='nombre'        THEN n.valor_norm    END) AS nombre_norm,
  MAX(CASE WHEN c.nombre='documento'     THEN c.valor_literal END) AS documento_literal,
  MAX(CASE WHEN c.nombre='documento'     THEN n.valor_norm    END) AS documento_norm,
  MAX(CASE WHEN c.nombre='fecha_inicio'  THEN n.valor_norm    END) AS inicio,
  MAX(CASE WHEN c.nombre='fecha_fin'     THEN n.valor_norm    END) AS fin,
  CAST(MAX(CASE WHEN c.nombre='monto'    THEN n.valor_norm    END) AS INTEGER) AS monto_centavos,
  CAST(MAX(CASE WHEN c.nombre='monto_total' THEN n.valor_norm  END) AS INTEGER) AS monto_total_centavos,
  CAST(MAX(CASE WHEN c.nombre='monto_total_letras' THEN n.valor_norm END) AS INTEGER)
                                                                       AS monto_total_letras_centavos,
  MAX(CASE WHEN c.nombre='cargo'         THEN c.valor_literal END) AS cargo,
  d.orden         AS orden,
  d.pagina_desde  AS pagina_desde,
  d.pagina_hasta  AS pagina_hasta,
  MIN(CASE WHEN c.nombre IN ('nombre','documento','fecha_inicio','fecha_fin','monto')
           THEN c.confianza END)                                   AS confianza_min,
  SUM(CASE WHEN c.estado IN ('verificado','corregido') THEN 1 ELSE 0 END) AS campos_humanos
FROM documento d
JOIN archivo a ON a.sha256 = d.sha256
LEFT JOIN documento_persona dp ON dp.documento_id = d.id
LEFT JOIN campo c
       ON c.documento_id = d.id
      AND c.valor_literal IS NOT NULL
      -- LA LÍNEA: sólo estados firmes. Sin esto, un valor que está en la cola
      -- esperando que alguien lo mire termina sumado en un total que se presenta
      -- como leído con seguridad.
      AND c.estado IN ('automatico_alta','verificado','corregido')
      -- Y ADEMÁS, ningún conflicto abierto. Es a propósito que sean dos condiciones y
      -- no una: el estado y la tabla de conflictos los escriben caminos distintos, y
      -- si alguno quedara mal esta es la última barrera antes de que un valor que
      -- nadie resolvió termine adentro de un total que se presenta como firme. En la
      -- regla que sostiene todo el sistema, la redundancia se paga sola.
      AND NOT EXISTS (SELECT 1 FROM conflicto k
                       WHERE k.documento_id = c.documento_id
                         AND k.campo_nombre = c.nombre
                         AND k.estado = 'abierto')
LEFT JOIN normalizacion n ON n.campo_id = c.id
-- Y SOLAMENTE CONTRATOS. Sin esta línea, una factura de $2.500 entraba a la vista con
-- su nombre y su monto, se sumaba al acumulado de lo contratado y el panel decía «2
-- contratos» donde había un contrato y una factura. Peor todavía cuando la factura es
-- el cobro de ese mismo contrato: la misma plata contada dos veces.
--
-- La lista sale de ufil/clasificacion.py y la sustituye db.py al aplicar el esquema.
-- Es a propósito que no esté escrita acá: una lista repetida en dos archivos se separa
-- el día que alguien agrega un tipo, y lo que se rompe es un total.
WHERE d.tipo IN ({{TIPOS_CONTRATO}})
  -- Una pieza que ningún extractor reconoce se ve y se cuenta (ver `v_documento_todo`)
  -- pero NO entra acá: esta vista alimenta acumulados y totales, y un documento sin
  -- campos leídos no puede sumar ni figurar como contrato firme.
  AND d.estado <> 'sin_perfil'
GROUP BY d.id;

-- Todos los documentos, de cualquier familia, con el estado de cada campo al lado y
-- SIN filtrar por firmeza. Es para las pantallas que tienen que MOSTRAR lo provisional
-- como provisional: la ficha del documento, la cola, los listados con su sello.
--
-- Se llama `v_documento_todo` y no `v_contrato_todo` porque acá adentro hay facturas,
-- recibos y decretos además de contratos. El nombre viejo invitaba justo al error que
-- este bloque existe para evitar: tomar por contrato cualquier fila que salga de acá.
DROP VIEW IF EXISTS v_contrato_todo;
DROP VIEW IF EXISTS v_documento_todo;
CREATE VIEW v_documento_todo AS
SELECT
  d.id            AS documento_id,
  d.sha256        AS sha256,
  dp.persona_id   AS persona_id,
  d.camara        AS camara,
  d.tipo          AS tipo,
  -- A qué carril va: lo pactado, lo cobrado, o un acto administrativo. `null` cuando
  -- el tipo no está en ninguna familia conocida, que es como tiene que salir: un
  -- documento sin clasificar se ve y se cuenta, no se acomoda en la familia más
  -- probable. Ver `familia()` en ufil/clasificacion.py.
  CASE WHEN d.estado = 'sin_perfil'           THEN NULL
       WHEN d.tipo IN ({{TIPOS_CONTRATO}})    THEN 'contrato'
       WHEN d.tipo IN ({{TIPOS_COMPROBANTE}}) THEN 'comprobante'
       WHEN d.tipo IN ({{TIPOS_ACTO}})        THEN 'acto'
  END             AS familia,
  -- Qué tanto sabe el sistema de esta pieza. `sin_perfil` es un documento que existe y
  -- que todavía no sabemos leer: se ve, se cuenta y se puede clasificar a mano.
  d.estado        AS estado,
  d.clave         AS clave,
  a.nombre        AS archivo,
  MAX(CASE WHEN c.nombre='nombre'        THEN c.valor_literal END) AS nombre_literal,
  MAX(CASE WHEN c.nombre='nombre'        THEN c.estado        END) AS nombre_estado,
  MAX(CASE WHEN c.nombre='documento'     THEN c.valor_literal END) AS documento_literal,
  MAX(CASE WHEN c.nombre='documento'     THEN c.estado        END) AS documento_estado,
  MAX(CASE WHEN c.nombre='fecha_inicio'  THEN n.valor_norm    END) AS inicio,
  MAX(CASE WHEN c.nombre='fecha_inicio'  THEN c.estado        END) AS inicio_estado,
  MAX(CASE WHEN c.nombre='fecha_fin'     THEN n.valor_norm    END) AS fin,
  MAX(CASE WHEN c.nombre='fecha_fin'     THEN c.estado        END) AS fin_estado,
  CAST(MAX(CASE WHEN c.nombre='monto'    THEN n.valor_norm    END) AS INTEGER) AS monto_centavos,
  MAX(CASE WHEN c.nombre='monto'         THEN c.estado        END) AS monto_estado,
  CAST(MAX(CASE WHEN c.nombre='monto_total' THEN n.valor_norm  END) AS INTEGER) AS monto_total_centavos,
  MAX(CASE WHEN c.nombre='cargo'         THEN c.valor_literal END) AS cargo,
  d.orden         AS orden,
  d.pagina_desde  AS pagina_desde,
  d.pagina_hasta  AS pagina_hasta,
  -- Cuántos de los campos críticos están firmes, provisionales o esperando a alguien.
  -- Con esto una fila puede decir de sí misma qué tan confiable es, sin que la
  -- pantalla tenga que ir a buscarlo campo por campo.
  SUM(CASE WHEN c.nombre IN ('nombre','documento','fecha_inicio','fecha_fin','monto')
            AND c.estado IN ('automatico_alta','verificado','corregido')
           THEN 1 ELSE 0 END)                                      AS criticos_firmes,
  SUM(CASE WHEN c.nombre IN ('nombre','documento','fecha_inicio','fecha_fin','monto')
            AND c.estado IN ('pendiente_baja','conflicto','no_revisado')
           THEN 1 ELSE 0 END)                                      AS criticos_pendientes,
  MIN(CASE WHEN c.nombre IN ('nombre','documento','fecha_inicio','fecha_fin','monto')
           THEN c.confianza END)                                   AS confianza_min
FROM documento d
JOIN archivo a ON a.sha256 = d.sha256
LEFT JOIN documento_persona dp ON dp.documento_id = d.id
LEFT JOIN campo c ON c.documento_id = d.id
LEFT JOIN normalizacion n ON n.campo_id = c.id
GROUP BY d.id;


-- ═══════════════════════════════════════════════════════════════════════════
-- LO COBRADO. El otro carril.
-- ═══════════════════════════════════════════════════════════════════════════
-- Facturas, recibos y remitos. Misma regla de firmeza que `v_contrato` —sólo campos
-- que se pueden afirmar— y separada de los contratos porque dicen cosas distintas: el
-- contrato es lo que se pactó pagar, el comprobante es lo que se cobró. Un total que
-- los sume no es más completo: no corresponde a nada.
--
-- Las facturas de talonario traen el importe escrito a mano y NO se leen (ver
-- ufil/manuscrito.py). Salen acá con `monto_centavos` en null, que es la verdad: hay
-- un comprobante y no sabemos por cuánto. Contarlo como cero sería peor.
DROP VIEW IF EXISTS v_comprobante;
CREATE VIEW v_comprobante AS
SELECT
  d.id            AS documento_id,
  d.sha256        AS sha256,
  dp.persona_id   AS persona_id,
  d.tipo          AS tipo,
  a.nombre        AS archivo,
  MAX(CASE WHEN c.nombre='nombre'      THEN c.valor_literal END) AS nombre_literal,
  MAX(CASE WHEN c.nombre='nombre'      THEN n.valor_norm    END) AS nombre_norm,
  MAX(CASE WHEN c.nombre='documento'   THEN c.valor_literal END) AS documento_literal,
  MAX(CASE WHEN c.nombre='documento'   THEN n.valor_norm    END) AS documento_norm,
  MAX(CASE WHEN c.nombre='comprobante' THEN c.valor_literal END) AS comprobante,
  MAX(CASE WHEN c.nombre='fecha_inicio' THEN n.valor_norm   END) AS emitida,
  CAST(MAX(CASE WHEN c.nombre='monto'  THEN n.valor_norm    END) AS INTEGER) AS monto_centavos,
  d.orden         AS orden,
  d.pagina_desde  AS pagina_desde,
  d.pagina_hasta  AS pagina_hasta,
  MIN(CASE WHEN c.nombre IN ('nombre','documento','monto') THEN c.confianza END)
                                                                 AS confianza_min,
  SUM(CASE WHEN c.estado IN ('verificado','corregido') THEN 1 ELSE 0 END) AS campos_humanos
FROM documento d
JOIN archivo a ON a.sha256 = d.sha256
LEFT JOIN documento_persona dp ON dp.documento_id = d.id
LEFT JOIN campo c
       ON c.documento_id = d.id
      AND c.valor_literal IS NOT NULL
      AND c.estado IN ('automatico_alta','verificado','corregido')
      AND NOT EXISTS (SELECT 1 FROM conflicto k
                       WHERE k.documento_id = c.documento_id
                         AND k.campo_nombre = c.nombre
                         AND k.estado = 'abierto')
LEFT JOIN normalizacion n ON n.campo_id = c.id
WHERE d.tipo IN ({{TIPOS_COMPROBANTE}})
  AND d.estado <> 'sin_perfil'      -- misma razón que en `v_contrato`
GROUP BY d.id;
