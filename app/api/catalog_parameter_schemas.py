"""Esquemas de la API de parametrización del catálogo (HU-13).

Se mantienen en un módulo propio para no modificar ``app/api/schemas.py``,
archivo compartido por HU-11 y HU-12.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.catalog_parameters import CATALOG_MODULO, CatalogParameterVersion


class CatalogParameterValidationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tipo: str
    minimo: int | None = None
    maximo: int | None = None
    requerido: bool = True
    permitidos: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, alias="maxItems")


class CatalogParameterDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    codigo: str
    nombre: str
    descripcion: str
    modulo: str
    campo: str | None = None
    valor: Any
    tipo: str
    validacion: CatalogParameterValidationSchema
    dependencias: list[str] = Field(default_factory=list)


class CatalogParametersData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int
    vigente_desde: datetime = Field(alias="vigenteDesde")
    modulo: str
    parametros: dict[str, Any]
    definiciones: list[CatalogParameterDetail]
    actualizado_por: str | None = Field(default=None, alias="actualizadoPor")
    motivo: str = ""

    @classmethod
    def from_version(
        cls,
        version: CatalogParameterVersion,
        definiciones: list[CatalogParameterDetail],
    ) -> CatalogParametersData:
        return cls(
            version=version.version,
            vigente_desde=version.vigente_desde,
            modulo=version.modulo,
            parametros=dict(version.valores),
            definiciones=definiciones,
            actualizado_por=version.actor_id or None,
            motivo=version.motivo,
        )


class CatalogParameterVersionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int
    vigente_desde: datetime = Field(alias="vigenteDesde")
    modulo: str
    parametros: dict[str, Any]
    anteriores: dict[str, Any]
    actor_id: str = Field(alias="actorId")
    actor_roles: list[str] = Field(alias="actorRoles")
    motivo: str = ""
    actual: bool = False

    @classmethod
    def from_version(
        cls, version: CatalogParameterVersion, *, actual: bool = False
    ) -> CatalogParameterVersionItem:
        return cls(
            version=version.version,
            vigente_desde=version.vigente_desde,
            modulo=version.modulo,
            parametros=dict(version.valores),
            anteriores=dict(version.anteriores),
            actor_id=version.actor_id,
            actor_roles=list(version.actor_roles),
            motivo=version.motivo,
            actual=actual,
        )


class CatalogParametersHistoryData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version_actual: int = Field(alias="versionActual")
    total: int
    versiones: list[CatalogParameterVersionItem]


class CatalogParametersUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    modulo: str = CATALOG_MODULO
    parametros: dict[str, Any]
    motivo: str | None = None
