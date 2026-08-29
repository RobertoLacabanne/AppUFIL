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

-- ────────────────────────────────────────── CAPA 2: DOCUMENTO Y CARRIL DE DATOS ──
CREATE TABLE IF NOT EXISTS documento (
  id       INTEGER PRIMARY KEY,
  sha256   TEXT NOT NULL UNIQUE REFERENCES archivo(sha256),
  tipo     TEXT NOT NULL,               -- contrato_personal
  perfil   TEXT NOT NULL,               -- perfil de extracción aplicado
  camara   TEXT,
  estado   TEXT NOT NULL DEFAULT 'extraido'
);

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
  estado        TEXT NOT NULL DEFAULT 'automatico',  -- automatico|verificado|corregido
  revisado_por  TEXT,
  revisado_en   TEXT,
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
CREATE TABLE IF NOT EXISTS revision_humana (
  sha256 TEXT NOT NULL,
  campo  TEXT NOT NULL,
  accion TEXT NOT NULL,              -- verificar | corregir | ilegible | ausente | ambiguo
  valor  TEXT,
  quien  TEXT NOT NULL,
  cuando TEXT NOT NULL,
  PRIMARY KEY (sha256, campo)
);

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

-- ───────────────────────────────────────────────────────── VISTA DE TRABAJO ──
-- El contrato "consolidado". Un campo entra SOLO si tiene valor y no tiene
-- conflicto abierto. Todo lo demás sale NULL: ninguna consulta río abajo puede
-- tropezarse con un valor dudoso sin enterarse.
DROP VIEW IF EXISTS v_contrato;
CREATE VIEW v_contrato AS
SELECT
  d.id            AS documento_id,
  d.sha256        AS sha256,
  dp.persona_id   AS persona_id,
  d.camara        AS camara,
  a.nombre        AS archivo,
  MAX(CASE WHEN c.nombre='nombre'        THEN c.valor_literal END) AS nombre_literal,
  MAX(CASE WHEN c.nombre='nombre'        THEN n.valor_norm    END) AS nombre_norm,
  MAX(CASE WHEN c.nombre='documento'     THEN c.valor_literal END) AS documento_literal,
  MAX(CASE WHEN c.nombre='documento'     THEN n.valor_norm    END) AS documento_norm,
  MAX(CASE WHEN c.nombre='fecha_inicio'  THEN n.valor_norm    END) AS inicio,
  MAX(CASE WHEN c.nombre='fecha_fin'     THEN n.valor_norm    END) AS fin,
  CAST(MAX(CASE WHEN c.nombre='monto'    THEN n.valor_norm    END) AS INTEGER) AS monto_centavos,
  MAX(CASE WHEN c.nombre='cargo'         THEN c.valor_literal END) AS cargo,
  MIN(CASE WHEN c.nombre IN ('nombre','documento','fecha_inicio','fecha_fin','monto')
           THEN c.confianza END)                                   AS confianza_min
FROM documento d
JOIN archivo a ON a.sha256 = d.sha256
LEFT JOIN documento_persona dp ON dp.documento_id = d.id
LEFT JOIN campo c
       ON c.documento_id = d.id
      AND c.valor_literal IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM conflicto k
                      WHERE k.documento_id = c.documento_id
                        AND k.campo_nombre = c.nombre
                        AND k.estado = 'abierto')
LEFT JOIN normalizacion n ON n.campo_id = c.id
GROUP BY d.id;
