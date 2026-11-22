from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_auth_service, get_client_ip
from app.domain.auth import (
    ApiResponse,
    LoginRequest,
    LoginResponseData,
    RegisterRequest,
    RegisterResponseData,
    VerifyRequest,
    VerifyResponseData,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])


@router.post(
    "/register",
    response_model=ApiResponse[RegisterResponseData],
    status_code=status.HTTP_201_CREATED,
    summary="Registrar usuario",
    description="Crea una cuenta pendiente de verificación y envía el enlace de confirmación por correo.",
    responses={
        400: {"description": "Datos inválidos o contraseña que no cumple la política"},
        409: {"description": "El correo ya está registrado"},
        429: {"description": "Límite de intentos de registro excedido"},
        502: {"description": "No fue posible entregar el correo de verificación"},
    },
)
def registrar_usuario(
    datos: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[RegisterResponseData]:
    return service.registrar(datos, ip)


@router.post(
    "/email/verify",
    response_model=ApiResponse[VerifyResponseData],
    status_code=status.HTTP_200_OK,
    summary="Verificar cuenta",
    description="Valida el token de verificación, comprueba su vigencia y activa la cuenta una sola vez.",
    responses={
        410: {"description": "Token expirado, inválido o ya utilizado"},
    },
)
def verificar_cuenta(
    datos: VerifyRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[VerifyResponseData]:
    return service.verificar(datos, ip)


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponseData],
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión",
    description="Valida credenciales y bloquea el acceso mientras la cuenta esté pendiente de verificación.",
    responses={
        401: {"description": "Credenciales inválidas"},
        403: {"description": "La cuenta aún no está verificada"},
    },
)
def iniciar_sesion(
    datos: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[LoginResponseData]:
    return service.login(datos, ip)
