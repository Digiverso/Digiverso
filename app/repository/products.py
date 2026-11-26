"""Repositorio SQLite de productos y sus licencias (HU-08)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from app.domain.catalog_search import (
    ProductQuery,
    indexable_text,
    normalize_text,
    relevance_score,
    text_matches,
)
from app.domain.product import ESTADO_PUBLICADO, MEDIO_ACTIVO, Medio, Product
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _medios_from_json(raw: str | None) -> list[Medio]:
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [
        Medio(
            id=str(item.get("id")) if item.get("id") else None,
            tipo=str(item.get("tipo", "imagen")),
            url=str(item.get("url", "")),
            orden=int(item.get("orden", 0) or 0),
            estado=str(item.get("estado", MEDIO_ACTIVO) or MEDIO_ACTIVO),
        )
        for item in items
        if isinstance(item, dict)
    ]


class SQLiteProductRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_index()

    # --------------------------------------------------------- índice HU-10
    def _index_text(self, product: Product) -> str:
        return indexable_text(
            nombre=product.nombre,
            descripcion=product.descripcion,
            autor=product.autor_nombre,
            categorias=product.categorias,
            category_names=[product.categoria_id] if product.categoria_id else [],
        )

    @staticmethod
    def _index_write(connection: sqlite3.Connection, product: Product, texto: str) -> None:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='productos_busqueda'"
        ).fetchone() is None:
            return
        if connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='productos_busqueda'"
        ).fetchone()[0].lower().find("virtual table") >= 0:
            connection.execute("DELETE FROM productos_busqueda WHERE id = ?", (product.id,))
            connection.execute(
                "INSERT INTO productos_busqueda (id, texto) VALUES (?, ?)",
                (product.id, texto),
            )
        else:
            connection.execute(
                "INSERT OR REPLACE INTO productos_busqueda (id, texto) VALUES (?, ?)",
                (product.id, texto),
            )

    @staticmethod
    def _index_fts_query(terms: ProductQuery) -> str | None:
        groups: list[str] = []
        for group in terms.terms.groups:
            expressions = []
            for term in group:
                safe = "".join(character for character in normalize_text(term) if character.isalnum())
                if safe:
                    expressions.append(f'"{safe}"*')
            if expressions:
                groups.append("(" + " OR ".join(expressions) + ")")
        return " AND ".join(groups) if groups else None

    def _ensure_index(self) -> None:
        """Reconstruye el índice si hay productos que aún no están en él."""

        with self.database.connection() as connection:
            total = connection.execute("SELECT COUNT(*) AS total FROM productos").fetchone()["total"]
            indexed = connection.execute(
                "SELECT COUNT(*) AS total FROM productos_busqueda"
            ).fetchone()["total"]
            if total == indexed:
                return
            connection.execute("DELETE FROM productos_busqueda")
            for row in connection.execute("SELECT * FROM productos").fetchall():
                product = self._rows_to_products([row])[0]
                self._index_write(connection, product, self._index_text(product))

    def _candidate_ids(self, query: ProductQuery) -> set[str] | None:
        """IDs que el índice considera relevantes; ``None`` si no hay q."""

        if query.terms.is_empty:
            return None
        with self.database.connection() as connection:
            if self.database.fts5_available:
                match = self._index_fts_query(query)
                if not match:
                    return set()
                return {
                    row["id"]
                    for row in connection.execute(
                        "SELECT id FROM productos_busqueda WHERE productos_busqueda MATCH ?",
                        (match,),
                    ).fetchall()
                }
            return {
                row["id"]
                for row in connection.execute(
                    "SELECT id, texto FROM productos_busqueda"
                ).fetchall()
                if text_matches(query.terms, row["texto"] or "")
            }

    # ---------------------------------------------------------------- lectura
    def _rows_to_products(self, rows: Iterable[sqlite3.Row]) -> list[Product]:
        products: list[Product] = []
        for row in rows:
            creado_en = _datetime(row["creado_en"]) or datetime.now(timezone.utc)
            actualizado_en = _datetime(row["actualizado_en"]) or creado_en
            estado_desde = _datetime(row["estado_desde"]) or creado_en
            try:
                categorias = json.loads(row["categorias"] or "[]")
            except (TypeError, ValueError):
                categorias = []
            products.append(
                Product(
                    id=row["id"],
                    nombre=row["nombre"] or "",
                    descripcion=row["descripcion"] or "",
                    autor_nombre=row["autor_nombre"] or "",
                    calificacion=float(row["calificacion"] or 0),
                    precio=int(row["precio"] or 0),
                    autor_id=row["autor_id"] or "",
                    categoria_id=row["categoria_id"],
                    moneda=row["moneda"] or "COP",
                    edad_minima=int(row["edad_minima"] or 0),
                    edad_maxima=int(row["edad_maxima"] or 99),
                    categorias=[str(item) for item in categorias],
                    medios=_medios_from_json(row["medios"]),
                    estado=row["estado"],
                    activo=bool(row["activo"]),
                    creado_en=creado_en,
                    actualizado_en=actualizado_en,
                    estado_desde=estado_desde,
                    archivado_en=_datetime(row["archivado_en"]),
                    archivo_hash=row["archivo_hash"],
                    cambios_pendientes=bool(row["cambios_pendientes"]),
                )
            )
        return products

    def get(self, product_id: str) -> Product | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM productos WHERE id = ?", (product_id,)
            ).fetchone()
        return self._rows_to_products([row])[0] if row else None

    def list_by_estado(self, estado: str) -> list[Product]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM productos WHERE estado = ? ORDER BY creado_en DESC, id DESC",
                (estado,),
            ).fetchall()
        return self._rows_to_products(rows)

    def list_showcase(self) -> list[Product]:
        """Vitrina: únicamente productos publicados y activos."""

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM productos
                WHERE estado = ? AND activo = 1
                ORDER BY creado_en DESC, id DESC
                """,
                (ESTADO_PUBLICADO,),
            ).fetchall()
        return self._rows_to_products(rows)

    def search_products(self, query: ProductQuery) -> tuple[list[Product], int]:
        """Busca publicados con filtros AND, orden estable y paginación."""

        conditions = ["estado = ?", "activo = 1"]
        parameters: list[Any] = [ESTADO_PUBLICADO]
        if query.categoria:
            # ``categorias`` se guarda como JSON; este patrón evita depender de
            # la extensión JSON1 y respeta productos con varias categorías.
            conditions.append("categorias LIKE ?")
            parameters.append(f'%"{query.categoria}"%')
        if query.edad is not None:
            conditions.append("edad_minima <= ? AND edad_maxima >= ?")
            parameters.extend([query.edad, query.edad])
        if query.precio_min is not None:
            conditions.append("precio >= ?")
            parameters.append(query.precio_min)
        if query.precio_max is not None:
            conditions.append("precio <= ?")
            parameters.append(query.precio_max)

        indexed_ids = self._candidate_ids(query)
        with self.database.connection() as connection:
            index_text = {
                row["id"]: row["texto"] or ""
                for row in connection.execute("SELECT id, texto FROM productos_busqueda")
            }
            rows = connection.execute(
                "SELECT * FROM productos WHERE " + " AND ".join(conditions) +
                " ORDER BY creado_en DESC, id DESC",
                parameters,
            ).fetchall()
        products = self._rows_to_products(rows)

        if indexed_ids is not None:
            # Unión del índice FTS con la tolerancia a errores: así un typo como
            # "ilustrasion" sigue encontrando "ilustraciones".
            tolerantes = {
                product.id
                for product in products
                if text_matches(query.terms, index_text.get(product.id, self._index_text(product)))
            }
            permitidos = indexed_ids | tolerantes
            products = [
                product
                for product in products
                if product.id in permitidos
                and relevance_score(
                    query.terms,
                    product.nombre,
                    index_text.get(product.id, self._index_text(product)),
                )
                > 0
            ]

        productos_ordenados = self._sort(products, query.orden, query.terms, index_text)
        total = len(productos_ordenados)
        return productos_ordenados[query.offset : query.offset + query.tamanio_pagina], total

    def _sort(
        self,
        products: list[Product],
        orden: str,
        terms: ProductQuery,
        index_text: dict[str, str],
    ) -> list[Product]:
        def fecha(product: Product) -> float:
            return product.creado_en.timestamp()

        if orden == "precio_asc":
            return sorted(products, key=lambda item: (item.precio, item.id))
        if orden == "precio_desc":
            return sorted(products, key=lambda item: (-item.precio, item.id))
        if orden == "fecha_asc":
            return sorted(products, key=lambda item: (fecha(item), item.id))
        if orden == "fecha_desc":
            return sorted(products, key=lambda item: (-fecha(item), item.id))
        # Relevancia: puntaje, fecha y id como desempates deterministas.
        return sorted(
            products,
            key=lambda item: (
                -relevance_score(
                    terms, item.nombre, index_text.get(item.id, self._index_text(item))
                ),
                -fecha(item),
                item.id,
            ),
        )

    def next_id(self) -> str:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(CAST(substr(id, 6) AS INTEGER)), 0) + 1 AS next_number
                FROM productos
                WHERE id GLOB 'prod_[0-9]*'
                """
            ).fetchone()
        return f"prod_{int(row['next_number']):03d}"

    def next_media_id(self) -> str:
        """Siguiente ``med_XXX`` libre considerando también medios eliminados."""

        with self.database.connection() as connection:
            rows = connection.execute("SELECT medios FROM productos").fetchall()
        mayor = 0
        for row in rows:
            try:
                medios = json.loads(row["medios"] or "[]")
            except (TypeError, ValueError):
                continue
            for medio in medios if isinstance(medios, list) else []:
                if not isinstance(medio, dict):
                    continue
                identificador = str(medio.get("id") or "")
                if identificador.startswith("med_") and identificador[4:].isdigit():
                    mayor = max(mayor, int(identificador[4:]))
        return f"med_{mayor + 1:03d}"

    # ---------------------------------------------------------------- escritura
    def _values(self, product: Product) -> tuple[Any, ...]:
        """Valores en el orden de la sentencia UPDATE (sin el ``id``)."""

        return (
            product.categoria_id or (product.categorias[0] if product.categorias else ""),
            product.estado,
            int(product.activo),
            product.nombre,
            product.descripcion,
            product.autor_nombre,
            product.calificacion,
            product.precio,
            product.moneda,
            product.edad_minima,
            product.edad_maxima,
            json.dumps(product.categorias, ensure_ascii=False),
            json.dumps([asdict(medio) for medio in product.medios], ensure_ascii=False),
            product.autor_id,
            _iso(product.creado_en),
            _iso(product.actualizado_en),
            _iso(product.estado_desde),
            _iso(product.archivado_en) if product.archivado_en else None,
            product.archivo_hash,
            int(product.cambios_pendientes),
        )

    def save(self, product: Product) -> Product:
        columns = (
            "id, categoria_id, estado, activo, nombre, descripcion, autor_nombre, "
            "calificacion, precio, moneda, edad_minima, edad_maxima, categorias, medios, "
            "autor_id, creado_en, actualizado_en, estado_desde, archivado_en, "
            "archivo_hash, cambios_pendientes"
        )
        placeholders = ", ".join("?" for _ in columns.split(", "))
        with self.database.connection() as connection:
            connection.execute(
                f"INSERT INTO productos ({columns}) VALUES ({placeholders})",
                (product.id, *self._values(product)),
            )
            self._index_write(connection, product, self._index_text(product))
        return product

    def update(self, product: Product) -> Product:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE productos SET
                    categoria_id = ?, estado = ?, activo = ?, nombre = ?, descripcion = ?,
                    autor_nombre = ?, calificacion = ?, precio = ?, moneda = ?,
                    edad_minima = ?, edad_maxima = ?, categorias = ?, medios = ?,
                    autor_id = ?, creado_en = ?, actualizado_en = ?, estado_desde = ?,
                    archivado_en = ?, archivo_hash = ?, cambios_pendientes = ?
                WHERE id = ?
                """,
                (*self._values(product), product.id),
            )
            self._index_write(connection, product, self._index_text(product))
        return product

    # --------------------------------------------------------------- licencias
    def add_license(
        self,
        product_id: str,
        *,
        tipo: str = "estandar",
        license_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Registro mínimo de licencia (HU-08) con titular para HU-10."""

        owner = actor_id or ""
        with self.database.connection() as connection:
            if license_id is None:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS next_number
                    FROM licencias WHERE id GLOB 'lic_[0-9]*'
                    """
                ).fetchone()
                license_id = f"lic_{int(row['next_number']):03d}"
            connection.execute(
                """
                INSERT INTO licencias (id, producto_id, actor_id, tipo, vigente, creado_en)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    license_id,
                    product_id,
                    owner,
                    tipo,
                    _iso(datetime.now(timezone.utc)),
                ),
            )
        return {
            "id": license_id,
            "productoId": product_id,
            "actorId": owner,
            "tipo": tipo,
            "vigente": True,
        }

    def active_license_for(
        self, product_id: str, actor_id: str | None
    ) -> dict[str, Any] | None:
        """Licencia vigente del actor sobre el producto, si existe."""

        if not actor_id:
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, producto_id, actor_id, tipo, vigente, creado_en
                FROM licencias
                WHERE producto_id = ? AND actor_id = ? AND vigente = 1
                ORDER BY id LIMIT 1
                """,
                (product_id, actor_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "productoId": row["producto_id"],
            "actorId": row["actor_id"],
            "tipo": row["tipo"],
            "vigente": bool(row["vigente"]),
            "creadoEn": row["creado_en"],
        }

    def list_licenses(self, product_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, producto_id, tipo, vigente, creado_en FROM licencias "
                "WHERE producto_id = ? ORDER BY id",
                (product_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "productoId": row["producto_id"],
                "tipo": row["tipo"],
                "vigente": bool(row["vigente"]),
                "creadoEn": row["creado_en"],
            }
            for row in rows
        ]

    def count_active_licenses(self, product_id: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM licencias WHERE producto_id = ? AND vigente = 1",
                (product_id,),
            ).fetchone()
        return int(row["total"])
