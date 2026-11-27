"""Esquemas de la API de parametrización de comercio (HU-17).

Se mantienen en un módulo propio para no modificar ``app/api/schemas.py``,
archivo compartido por otras historias de usuario.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.commerce_parameters import COMMERCE_MODULO, CommerceParameterVersion


class CommerceParameterValidationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tipo: str
    minimo: int | None = None
    maximo: int | None = None
    requerido: bool = True
    permitidos: list[str] = Field(default_factory=list)


class CommerceParameterDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    codigo: str
    nombre: str
    descripcion: str
    modulo: str
    campo: str | None = None
    valor: Any
    tipo: str
    validacion: CommerceParameterValidationSchema
    dependencias: list[str] = Field(default_factory=list)


class CommerceParametersData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int
    vigente_desde: datetime = Field(alias="vigenteDesde")
    modulo: str
    parametros: dict[str, Any]
    definiciones: list[CommerceParameterDetail]
    actualizado_por: str | None = Field(default=None, alias="actualizadoPor")
    motivo: str = ""

    @classmethod
    def from_version(
        cls,
        version: CommerceParameterVersion,
        definiciones: list[CommerceParameterDetail],
    ) -> CommerceParametersData:
        return cls(
            version=version.version,
            vigente_desde=version.vigente_desde,
            modulo=version.modulo,
            parametros=dict(version.valores),
            definiciones=definiciones,
            actualizado_por=version.actor_id or None,
            motivo=version.motivo,
        )


class CommerceParameterVersionItem(BaseModel):
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
        cls, version: CommerceParameterVersion, *, actual: bool = False
    ) -> CommerceParameterVersionItem:
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


class CommerceParametersHistoryData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version_actual: int = Field(alias="versionActual")
    total: int
    versiones: list[CommerceParameterVersionItem]


class CommerceParametersUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    modulo: str = COMMERCE_MODULO
    parametros: dict[str, Any]
    motivo: str | None = None
