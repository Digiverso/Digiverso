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

-- Contrato mínimo con HU-08: permite comprobar que una categoría con
-- productos activos no puede desactivarse. No sustituye al módulo de productos.
CREATE TABLE IF NOT EXISTS productos (
    id           TEXT PRIMARY KEY,
    categoria_id TEXT NOT NULL REFERENCES categories(id),
    estado       TEXT NOT NULL DEFAULT 'publicado',
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);

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
"""


class Database:
    """Fábrica de conexiones SQLite con inicialización idempotente."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)

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
