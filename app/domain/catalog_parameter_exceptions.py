"""Errores de la parametrización del catálogo (HU-13).

Se definen en un módulo propio para no tocar ``app/domain/exceptions.py``,
donde convergen otras historias de usuario. Todas las clases derivan de las
bases existentes, por lo que el manejador global ya las traduce al sobre
``{ message, data, success }``.
"""

from __future__ import annotations

from app.domain.exceptions import CatalogError, ForbiddenError


class InvalidCatalogParameterError(CatalogError):
    """Parámetro CAT inválido (tipo, rango o dependencia)."""

    status_code = 400
    code = "CATALOG_PARAMETER_INVALID"


CatalogParameterError = InvalidCatalogParameterError


class CatalogParameterModuleError(InvalidCatalogParameterError):
    code = "CATALOG_PARAMETER_MODULE"


class CatalogParameterNotFoundError(InvalidCatalogParameterError):
    code = "CATALOG_PARAMETER_NOT_FOUND"


class CatalogParametersForbiddenError(ForbiddenError):
    code = "CATALOG_PARAMETERS_FORBIDDEN"


class CatalogParameterVersionNotFoundError(CatalogError):
    status_code = 404
    code = "CATALOG_PARAMETER_VERSION_NOT_FOUND"
