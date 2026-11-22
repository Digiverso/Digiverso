from __future__ import annotations

from fastapi import Request

from app.core.config import settings
from app.core.rate_limit import RateLimiter
from app.repository.auth_repository import auth_repository
from app.repository.email_repository import build_email_gateway
from app.services.auth_service import AuthService

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


def get_auth_service() -> AuthService:
    return AuthService(
        repo=auth_repository,
        settings=settings,
        email_gateway=build_email_gateway(settings),
        rate_limiter=register_rate_limiter,
        login_rate_limiter=login_rate_limiter,
        password_rate_limiter=password_recovery_rate_limiter,
    )


def get_client_ip(request: Request) -> str:
    if request.client is None:
        return "desconocida"
    return request.client.host
