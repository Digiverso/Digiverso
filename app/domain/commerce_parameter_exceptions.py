"""Errores de la parametrización de comercio (HU-17).

Se definen en un módulo propio para no tocar ``app/domain/exceptions.py``,
archivo compartido por otras historias. Todas las clases derivan de las bases
existentes, por lo que el manejador global ya las traduce al sobre
``{ message, data, success }``.
"""

from __future__ import annotations

from app.domain.exceptions import CatalogError, ForbiddenError


class InvalidCommerceParameterError(CatalogError):
    """Parámetro COM inválido (tipo, rango o regla de negocio)."""

    status_code = 400
    code = "COMMERCE_PARAMETER_INVALID"


CommerceParameterError = InvalidCommerceParameterError


class CommerceParameterModuleError(InvalidCommerceParameterError):
    code = "COMMERCE_PARAMETER_MODULE"


class CommerceParameterNotFoundError(InvalidCommerceParameterError):
    code = "COMMERCE_PARAMETER_NOT_FOUND"


class CommerceParametersForbiddenError(ForbiddenError):
    code = "COMMERCE_PARAMETERS_FORBIDDEN"


class CommerceParameterVersionNotFoundError(CatalogError):
    status_code = 404
    code = "COMMERCE_PARAMETER_VERSION_NOT_FOUND"
