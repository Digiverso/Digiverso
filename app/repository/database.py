"""Conexión y esquema mínimo de SQLite para el módulo de catálogo."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id                 TEXT PRIMARY KEY,
    nombre             TEXT NOT NULL,
    nombre_normalizado TEXT NOT NULL,
    descripcion        TEXT,
    padre_id           TEXT REFERENCES categories(id) ON DELETE RESTRICT,
    estado             TEXT NOT NULL CHECK (estado IN ('activa', 'inactiva')),
    orden              INTEGER NOT NULL DEFAULT 0,
    ruta               TEXT NOT NULL,
    creado_en          TEXT NOT NULL,
    actualizado_en     TEXT NOT NULL,
    eliminado_en       TEXT
);

CREATE INDEX IF NOT EXISTS idx_categories_padre ON categories(padre_id);
CREATE INDEX IF NOT EXISTS idx_categories_ruta ON categories(ruta);

CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_nombre_padre
    ON categories(COALESCE(padre_id, ''), nombre_normalizado);

-- Productos (HU-08). ``categoria_id`` conserva el contrato usado por HU-07
-- para comprobar que una categoría con productos activos no puede desactivarse;
-- ``categorias`` guarda la lista completa declarada por el productor.
CREATE TABLE IF NOT EXISTS productos (
    id                 TEXT PRIMARY KEY,
    categoria_id       TEXT NOT NULL REFERENCES categories(id),
    estado             TEXT NOT NULL DEFAULT 'borrador'
        CHECK (estado IN ('borrador', 'en_revision', 'publicado', 'rechazado', 'archivado')),
    activo             INTEGER NOT NULL DEFAULT 0 CHECK (activo IN (0, 1)),
    nombre             TEXT NOT NULL DEFAULT '',
    descripcion        TEXT NOT NULL DEFAULT '',
    autor_nombre       TEXT NOT NULL DEFAULT '',
    calificacion       REAL NOT NULL DEFAULT 0,
    precio             INTEGER NOT NULL DEFAULT 0,
    moneda             TEXT NOT NULL DEFAULT 'COP',
    edad_minima        INTEGER NOT NULL DEFAULT 0,
    edad_maxima        INTEGER NOT NULL DEFAULT 99,
    categorias         TEXT NOT NULL DEFAULT '[]',
    medios             TEXT NOT NULL DEFAULT '[]',
    autor_id           TEXT NOT NULL DEFAULT '',
    creado_en          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado_desde       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archivado_en       TEXT,
    archivo_hash       TEXT,
    cambios_pendientes INTEGER NOT NULL DEFAULT 0 CHECK (cambios_pendientes IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_productos_precio ON productos(precio);
CREATE INDEX IF NOT EXISTS idx_productos_edades ON productos(edad_minima, edad_maxima);

-- Las licencias pertenecen a HU-15; HU-08 garantiza que archivar no las altera
-- y HU-10 añade ``actor_id`` para resolver la licencia del visitante autenticado.
CREATE TABLE IF NOT EXISTS licencias (
    id          TEXT PRIMARY KEY,
    producto_id TEXT NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    actor_id    TEXT NOT NULL DEFAULT '',
    tipo        TEXT NOT NULL,
    vigente     INTEGER NOT NULL DEFAULT 1 CHECK (vigente IN (0, 1)),
    creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_licencias_producto ON licencias(producto_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entidad     TEXT NOT NULL,
    entidad_id  TEXT NOT NULL,
    accion      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    actor_roles TEXT NOT NULL,
    fecha       TEXT NOT NULL,
    cambios     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entidad ON audit_log(entidad_id);

-- Reportes y sanciones (HU-12). La evidencia se guarda como JSON en una tabla
-- de acceso interno; las respuestas solo exponen metadatos al reportero y al
-- administrador. El índice parcial impide acumular reportes abiertos duplicados.
CREATE TABLE IF NOT EXISTS reportes (
    id              TEXT PRIMARY KEY,
    contenido_id    TEXT NOT NULL,
    tipo_contenido  TEXT NOT NULL DEFAULT 'producto',
    motivo          TEXT NOT NULL,
    evidencia       TEXT NOT NULL DEFAULT '[]',
    evidencia_hash  TEXT NOT NULL DEFAULT '',
    reportante_id   TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'abierto',
    fecha           TEXT NOT NULL,
    resolucion      TEXT,
    fecha_resolucion TEXT,
    metadatos       TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reportes_abiertos
    ON reportes(reportante_id, contenido_id)
    WHERE estado IN ('abierto', 'en_revision');

CREATE INDEX IF NOT EXISTS idx_reportes_estado ON reportes(estado, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_reportes_contenido ON reportes(contenido_id);

CREATE TABLE IF NOT EXISTS sanciones (
    id                TEXT PRIMARY KEY,
    reporte_id        TEXT,
    contenido_id      TEXT NOT NULL,
    tipo              TEXT NOT NULL,
    duracion_dias     INTEGER NOT NULL DEFAULT 0,
    usuario_afectado  TEXT NOT NULL,
    motivo            TEXT NOT NULL DEFAULT '',
    observacion       TEXT NOT NULL DEFAULT '',
    evidencia         TEXT NOT NULL DEFAULT '[]',
    evidencia_hash    TEXT NOT NULL DEFAULT '',
    accion_contenido  TEXT NOT NULL DEFAULT 'archivar',
    apelable          INTEGER NOT NULL DEFAULT 1,
    notificado        INTEGER NOT NULL DEFAULT 0,
    estado_contenido  TEXT,
    fecha             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sanciones_reporte ON sanciones(reporte_id);
CREATE INDEX IF NOT EXISTS idx_sanciones_usuario ON sanciones(usuario_afectado);

-- Parámetros de autenticación (HU-06). Cada versión es inmutable: las
-- actualizaciones insertan una fila nueva con los valores anteriores.
CREATE TABLE IF NOT EXISTS auth_parameter_versions (
    version        INTEGER PRIMARY KEY,
    vigente_desde  TEXT NOT NULL,
    modulo         TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    actor_roles    TEXT NOT NULL,
    motivo         TEXT NOT NULL DEFAULT '',
    anteriores     TEXT NOT NULL DEFAULT '{}',
    valores        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_parameter_versions_modulo
    ON auth_parameter_versions(modulo, version DESC);
"""


# Columnas añadidas en HU-08 a una tabla ``productos`` creada por HU-07.
# SQLite no permite ``ALTER TABLE ... IF NOT EXISTS``, por lo que se aplican de
# forma idempotente consultando ``PRAGMA table_info``.
_PRODUCT_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("nombre", "TEXT NOT NULL DEFAULT ''"),
    ("descripcion", "TEXT NOT NULL DEFAULT ''"),
    ("autor_nombre", "TEXT NOT NULL DEFAULT ''"),
    ("calificacion", "REAL NOT NULL DEFAULT 0"),
    ("precio", "INTEGER NOT NULL DEFAULT 0"),
    ("moneda", "TEXT NOT NULL DEFAULT 'COP'"),
    ("edad_minima", "INTEGER NOT NULL DEFAULT 0"),
    ("edad_maxima", "INTEGER NOT NULL DEFAULT 99"),
    ("categorias", "TEXT NOT NULL DEFAULT '[]'"),
    ("medios", "TEXT NOT NULL DEFAULT '[]'"),
    ("autor_id", "TEXT NOT NULL DEFAULT ''"),
    ("creado_en", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ("actualizado_en", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ("estado_desde", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ("archivado_en", "TEXT"),
    ("archivo_hash", "TEXT"),
    ("cambios_pendientes", "INTEGER NOT NULL DEFAULT 0"),
)


class Database:
    """Fábrica de conexiones SQLite con inicialización idempotente."""

    def __init__(self, path: Path) -> None:
        self.path = path
        # FTS5 no viene habilitado en todas las compilaciones de SQLite; si no
        # está disponible se usa un índice relacional simple con el mismo texto.
        self.fts5_available = True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(productos)")
            }
            for column, definition in _PRODUCT_MIGRATIONS:
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE productos ADD COLUMN {column} {definition}"
                    )
            licencias_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(licencias)")
            }
            if "actor_id" not in licencias_columns:
                connection.execute(
                    "ALTER TABLE licencias ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_licencias_actor "
                "ON licencias(producto_id, actor_id, vigente)"
            )
            # Estos índices dependen de columnas añadidas arriba, por lo que no
            # pueden formar parte del ``executescript`` inicial.
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_productos_estado ON productos(estado)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_productos_autor ON productos(autor_id)"
            )
            self._init_search_index(connection)

    def _init_search_index(self, connection: sqlite3.Connection) -> None:
        existente = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'productos_busqueda'"
        ).fetchone()
        if existente is not None:
            self.fts5_available = "virtual table" in existente["sql"].lower()
            return
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS productos_busqueda USING fts5("
                "id UNINDEXED, texto, tokenize='unicode61 remove_diacritics 2')"
            )
        except sqlite3.OperationalError:
            self.fts5_available = False
            connection.execute(
                "CREATE TABLE IF NOT EXISTS productos_busqueda ("
                "id TEXT PRIMARY KEY, texto TEXT NOT NULL)"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
