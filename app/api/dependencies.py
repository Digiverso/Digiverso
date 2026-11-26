from __future__ import annotations

from datetime import datetime

import jwt
from fastapi import Header, Request

from app.core.config import Settings, settings
from app.core.rate_limit import RateLimiter
from app.domain.auth import Account, AccountStatus, InvalidCredentialsError
from app.repository.auth_repository import auth_repository
from app.repository.email_repository import build_email_gateway
from app.repository.photo_storage import PhotoStorage, build_photo_storage
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService

register_rate_limiter = RateLimiter(
    limit=settings.register_rate_limit,
    window_seconds=settings.rate_limit_window_seconds,
)
login_rate_limiter = RateLimiter(
    limit=settings.login_rate_limit,
    window_seconds=settings.rate_limit_window_seconds,
)
password_recovery_rate_limiter = RateLimiter(
    limit=settings.password_recovery_rate_limit,
    window_seconds=settings.rate_limit_window_seconds,
)


def build_auth_service(settings: Settings) -> AuthService:
    return AuthService(
        repo=auth_repository,
        settings=settings,
        email_gateway=build_email_gateway(settings),
        rate_limiter=RateLimiter(
            limit=settings.register_rate_limit,
            window_seconds=settings.rate_limit_window_seconds,
        ),
        login_rate_limiter=RateLimiter(
            limit=settings.login_rate_limit,
            window_seconds=settings.rate_limit_window_seconds,
        ),
        password_rate_limiter=RateLimiter(
            limit=settings.password_recovery_rate_limit,
            window_seconds=settings.rate_limit_window_seconds,
        ),
    )


def _auth_service_para(request: Request) -> AuthService:
    override = request.app.dependency_overrides.get(get_auth_service)
    if override is not None:
        return override()

    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthService):
        return service

    service = build_auth_service(request.app.state.settings)
    request.app.state.auth_service = service
    return service


def get_auth_service(request: Request) -> AuthService:
    return _auth_service_para(request)


def get_current_account(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Account:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise InvalidCredentialsError("Se requiere un token de acceso.")

    token = authorization.split(None, 1)[1]
    service = _auth_service_para(request)
    try:
        claims = service.session_token_manager.decode_access_token(token, verify_exp=False)
        expira = int(claims["exp"])
        cuenta_id = str(claims["sub"])
        jti = str(claims["jti"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidCredentialsError("El token de acceso es inválido.") from exc

    ahora: datetime = service.clock()
    if expira <= int(ahora.timestamp()):
        raise InvalidCredentialsError("El token de acceso expiró.")

    sesion = service.repo.sesion_por_jti(jti)
    if sesion is None or not sesion.esta_activa(ahora) or sesion.cuenta_id != cuenta_id:
        raise InvalidCredentialsError("La sesión asociada al token no está activa.")

    cuenta = service.repo.obtener_cuenta_por_id(cuenta_id)
    if cuenta is None or cuenta.estado is not AccountStatus.ACTIVA:
        raise InvalidCredentialsError("La cuenta no está disponible.")
    return cuenta


def get_profile_service(request: Request) -> ProfileService:
    service = getattr(request.app.state, "profile_service", None)
    if isinstance(service, ProfileService):
        return service

    auth_service = _auth_service_para(request)
    storage: PhotoStorage = getattr(request.app.state, "photo_storage", None)
    if storage is None:
        storage = build_photo_storage(request.app.state.settings)
        request.app.state.photo_storage = storage

    service = ProfileService(
        repo=auth_service.repo,
        settings=request.app.state.settings,
        photo_storage=storage,
        clock=auth_service.clock,
    )
    request.app.state.profile_service = service
    return service


def get_client_ip(request: Request) -> str:
    if request.client is None:
        return "desconocida"
    return request.client.host
