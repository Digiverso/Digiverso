"""Esquemas Pydantic de seguimiento, feed y recomendaciones (HU-19)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FollowData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seguidor_id: str = Field(alias="seguidorId")
    seguido_id: str = Field(alias="seguidoId")
    fecha: str
    total_siguiendo: int = Field(alias="totalSiguiendo")
    total_seguidores: int = Field(alias="totalSeguidores")


class UnfollowData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seguidor_id: str = Field(alias="seguidorId")
    seguido_id: str = Field(alias="seguidoId")
    eliminado: bool
    total_siguiendo: int = Field(alias="totalSiguiendo")
    total_seguidores: int = Field(alias="totalSeguidores")


class FeedItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(alias="productId")
    nombre: str
    autor: str
    precio: int
    moneda: str
    fecha: str
    categoria: str
    miniatura: str | None = None


class FeedData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[FeedItem]
    total: int
    pagina: int
    tamanio_pagina: int = Field(alias="tamanioPagina")


class InterestsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    categorias: list[str]


class InterestsData(BaseModel):
    categorias: list[str]
    total: int
    maximo: int


class RecommendationItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(alias="productId")
    nombre: str
    autor: str
    precio: int
    moneda: str
    categoria: str
    fecha: str
    motivo: str
    puntuacion: float


class RecommendationsData(BaseModel):
    items: list[RecommendationItem]
    total: int
    limite: int
    orden: str
