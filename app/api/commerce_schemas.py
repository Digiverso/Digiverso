"""Esquemas de respuesta de Comercio (HU-15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LicenseData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    producto_id: str = Field(alias="productoId")
    comprador_id: str = Field(alias="compradorId")
    estado: str
    condiciones: str
    fecha_emision: str = Field(alias="fechaEmision")


class DownloadData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    expira_en: datetime = Field(alias="expiraEn")
    nombre_archivo: str = Field(alias="nombreArchivo")

    @classmethod
    def from_result(cls, result: Any) -> DownloadData:
        return cls(
            url=result.url,
            expira_en=result.expira_en,
            nombre_archivo=result.nombre_archivo,
        )


class PurchaseItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    producto_id: str = Field(alias="productoId")
    estado: str
    fecha_compra: str = Field(alias="fechaCompra")
    precio: int
    moneda: str
    licencia_id: str | None = Field(default=None, alias="licenciaId")
    estado_licencia: str | None = Field(default=None, alias="estadoLicencia")


class LicenseItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    producto_id: str = Field(alias="productoId")
    comprador_id: str = Field(alias="compradorId")
    estado: str
    condiciones: str
    fecha_emision: str = Field(alias="fechaEmision")
    compra_id: str = Field(alias="compraId")


class HistoryData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    compras: list[PurchaseItem]
    licencias: list[LicenseItem]
    pagina: int
    tamanio_pagina: int = Field(alias="tamanioPagina")
    total: int
    total_paginas: int = Field(alias="totalPaginas")


class SaleItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    venta_id: str = Field(alias="ventaId")
    orden_id: str = Field(alias="ordenId")
    product_id: str = Field(alias="productId")
    producto: str
    monto: int
    comision: int
    neto: int
    moneda: str
    fecha: str


class SalesData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[SaleItem]
    total_neto: int = Field(alias="totalNeto")
    pagina: int
    tamanio_pagina: int = Field(alias="tamanioPagina")
    total: int
    total_paginas: int = Field(alias="totalPaginas")


class PayoutItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payout_id: str = Field(alias="payoutId")
    productor_id: str = Field(alias="productorId")
    periodo: str
    total: int
    moneda: str
    estado: str
    fecha_generacion: str = Field(alias="fechaGeneracion")


class PayoutsData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[PayoutItem]
    pagina: int
    tamanio_pagina: int = Field(alias="tamanioPagina")
    total: int
    total_paginas: int = Field(alias="totalPaginas")
