"""Errores de la parametrización de comunidad (HU-21).

Módulo propio para no tocar ``app/domain/exceptions.py``, compartido por otras
historias. Todas las clases derivan de las bases existentes, de modo que el
manejador global traduce los errores al sobre ``{ message, data, success }``.
"""

from __future__ import annotations

from app.domain.exceptions import CatalogError, ForbiddenError


class InvalidCommunityParameterError(CatalogError):
    """Parámetro COMU inválido (tipo, rango o dependencia)."""

    status_code = 400
    code = "COMMUNITY_PARAMETER_INVALID"


CommunityParameterError = InvalidCommunityParameterError


class CommunityParameterModuleError(InvalidCommunityParameterError):
    code = "COMMUNITY_PARAMETER_MODULE"


class CommunityParameterNotFoundError(InvalidCommunityParameterError):
    code = "COMMUNITY_PARAMETER_NOT_FOUND"


class CommunityParametersForbiddenError(ForbiddenError):
    code = "COMMUNITY_PARAMETERS_FORBIDDEN"


class CommunityParameterVersionNotFoundError(CatalogError):
    status_code = 404
    code = "COMMUNITY_PARAMETER_VERSION_NOT_FOUND"
