"""Esquemas Pydantic del catálogo (categorías y productos)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.category import Category
from app.domain.product import Product


class CategoryNode(BaseModel):
    """Nodo del árbol; ``hijos`` contiene las subcategorías activas."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    nombre: str
    descripcion: str | None = None
    padre_id: str | None = Field(default=None, alias="padreId")
    estado: str
    orden: int
    hijos: list[CategoryNode] = Field(default_factory=list)

    @classmethod
    def from_category(cls, category: Category) -> CategoryNode:
        return cls(
            id=category.id,
            nombre=category.nombre,
            descripcion=category.descripcion,
            padre_id=category.padre_id,
            estado=category.estado,
            orden=category.orden,
            hijos=[],
        )


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    nombre: str
    descripcion: str | None = None
    padre_id: str | None = Field(default=None, alias="padreId")
    orden: int = 0


class CategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    nombre: str | None = None
    descripcion: str | None = None
    padre_id: str | None = Field(default=None, alias="padreId")
    orden: int | None = None


CategoryNode.model_rebuild()


# ------------------------------------------------------------ HU-08 (SUB-09)
class MedioItem(BaseModel):
    """Medio tal como lo declara el productor; se normaliza en el dominio."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str | None = None
    tipo: str = "imagen"
    url: str
    orden: int = 0


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    nombre: str
    descripcion: str
    precio: int
    moneda: str = "COP"
    edad_minima: int = Field(default=0, alias="edadMinima")
    edad_maxima: int = Field(default=99, alias="edadMaxima")
    categorias: list[str] = Field(default_factory=list)
    medios: list[MedioItem | str] = Field(default_factory=list)
    # Se acepta pero se ignora: el autor siempre se toma del token (HU-08).
    autor_id: str | None = Field(
        default=None,
        alias="autorId",
        description="Ignorado: el autor se obtiene del token de autenticación.",
    )


class ProductUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    nombre: str | None = None
    descripcion: str | None = None
    precio: int | None = None
    moneda: str | None = None
    edad_minima: int | None = Field(default=None, alias="edadMinima")
    edad_maxima: int | None = Field(default=None, alias="edadMaxima")
    categorias: list[str] | None = None
    medios: list[MedioItem | str] | None = None
    autor_id: str | None = Field(
        default=None,
        alias="autorId",
        description="Ignorado: no se puede cambiar la autoría del producto.",
    )


class MedioResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    tipo: str
    url: str
    orden: int = 0


class LicenciaUsuarioResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    producto_id: str = Field(alias="productoId")
    actor_id: str = Field(default="", alias="actorId")
    tipo: str
    vigente: bool
    creado_en: str = Field(alias="creadoEn")


class ProductResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    nombre: str
    descripcion: str
    precio: int
    moneda: str
    edad_minima: int = Field(alias="edadMinima")
    edad_maxima: int = Field(alias="edadMaxima")
    autor: str = ""
    calificacion: float = 0.0
    miniatura: str | None = None
    categoria: str | None = None
    categorias: list[str]
    estado: str
    # HU-10: el identificador del productor y el total de licencias solo se
    # exponen al propio autor o a un administrador.
    autor_id: str | None = Field(default=None, alias="autorId")
    medios: list[MedioResponse]
    creado_en: datetime = Field(alias="creadoEn")
    actualizado_en: datetime = Field(alias="actualizadoEn")
    licencias_activas: int = Field(default=0, alias="licenciasActivas")
    licencia: LicenciaUsuarioResponse | None = None

    @classmethod
    def from_product(
        cls,
        product: Product,
        *,
        licencias_activas: int = 0,
        incluir_privados: bool = True,
        categoria: str | None = None,
        licencia: dict[str, Any] | None = None,
    ) -> ProductResponse:
        return cls(
            id=product.id,
            nombre=product.nombre,
            descripcion=product.descripcion,
            precio=product.precio,
            moneda=product.moneda,
            edad_minima=product.edad_minima,
            edad_maxima=product.edad_maxima,
            autor=product.autor_nombre or "Autor Digiverso",
            calificacion=product.calificacion,
            miniatura=product.miniatura,
            categoria=categoria,
            categorias=product.categorias,
            estado=product.estado,
            autor_id=product.autor_id if incluir_privados else None,
            medios=[
                MedioResponse(
                    id=medio.id, tipo=medio.tipo, url=medio.url, orden=medio.orden
                )
                for medio in sorted(product.medios, key=lambda item: item.orden)
            ],
            creado_en=product.creado_en,
            actualizado_en=product.actualizado_en,
            licencias_activas=licencias_activas if incluir_privados else 0,
            licencia=LicenciaUsuarioResponse(**licencia) if licencia else None,
        )


class ProductTransition(ProductResponse):
    """Respuesta de una transición: estado resultante y fecha efectiva."""

    estado_anterior: str = Field(alias="estadoAnterior")
    transicion: str
    fecha: datetime

    @classmethod
    def from_product(
        cls,
        product: Product,
        *,
        estado_anterior: str,
        transicion: str,
        licencias_activas: int = 0,
    ) -> ProductTransition:
        return cls(
            **ProductResponse.from_product(
                product, licencias_activas=licencias_activas
            ).model_dump(by_alias=False),
            estado_anterior=estado_anterior,
            transicion=transicion,
            fecha=product.estado_desde,
        )


ProductResponse.model_rebuild()
ProductTransition.model_rebuild()


# ------------------------------------------------------------ HU-10 (SUB-11/12)
class ProductSearchItem(BaseModel):
    """Ítem público de búsqueda/vitrina: sin identificadores privados."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    nombre: str
    precio: int
    moneda: str
    autor: str
    categoria: str | None = None
    categoria_id: str | None = Field(default=None, alias="categoriaId")
    calificacion: float = 0.0
    miniatura: str | None = None
    edad_minima: int = Field(alias="edadMinima")
    edad_maxima: int = Field(alias="edadMaxima")

    @classmethod
    def from_product(
        cls, product: Product, *, categoria: str | None = None
    ) -> ProductSearchItem:
        return cls(
            id=product.id,
            nombre=product.nombre,
            precio=product.precio,
            moneda=product.moneda,
            autor=product.autor_nombre or "Autor Digiverso",
            categoria=categoria or product.categoria_id,
            categoria_id=product.categoria_id,
            calificacion=product.calificacion,
            miniatura=product.miniatura,
            edad_minima=product.edad_minima,
            edad_maxima=product.edad_maxima,
        )


class ProductSearchPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ProductSearchItem]
    total: int
    pagina: int
    tamanio_pagina: int = Field(alias="tamanioPagina")


class ShowcaseCategory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    nombre: str
    total: int
    productos: list[ProductSearchItem]


class ShowcaseData(BaseModel):
    categorias: list[ShowcaseCategory]
    total: int
