from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_auth_service, get_client_ip
from app.domain.auth import (
    ApiResponse,
    LoginRequest,
    LoginResponseData,
    LogoutRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RefreshRequest,
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
    description="Valida credenciales, estado de la cuenta y emite tokens de acceso y refresco.",
    responses={
        401: {"description": "Credenciales inválidas"},
        403: {"description": "La cuenta aún no está verificada"},
        423: {"description": "Cuenta bloqueada temporalmente"},
        429: {"description": "Límite de intentos excedido"},
    },
)
def iniciar_sesion(
    datos: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[LoginResponseData]:
    return service.login(datos, ip)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
    description="Revoca el refresh token y la sesión asociada.",
    responses={
        401: {"description": "Refresh token inválido o revocado"},
    },
)
def cerrar_sesion(
    datos: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> None:
    service.logout(datos, ip)


@router.post(
    "/refresh",
    response_model=ApiResponse[LoginResponseData],
    status_code=status.HTTP_200_OK,
    summary="Rotar refresh token",
    description="Revoca la sesión actual y emite un nuevo par de tokens.",
    responses={
        401: {"description": "Refresh token inválido o ya rotado"},
    },
)
def renovar_sesion(
    datos: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[LoginResponseData]:
    return service.refresh(datos, ip)


@router.post(
    "/password/forgot",
    response_model=ApiResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Solicitar recuperación de contraseña",
    description="Responde de forma genérica y envía un enlace temporal si el correo existe.",
    responses={
        429: {"description": "Límite de solicitudes excedido"},
    },
)
def solicitar_recuperacion(
    datos: PasswordForgotRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[dict[str, str]]:
    return service.password_forgot(datos, ip)


@router.post(
    "/password/reset",
    response_model=ApiResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Restablecer contraseña",
    description="Valida el enlace temporal, aplica la política de contraseña y revoca las sesiones activas.",
    responses={
        400: {"description": "La contraseña no cumple la política"},
        410: {"description": "Token expirado, inválido o ya utilizado"},
    },
)
def restablecer_contrasena(
    datos: PasswordResetRequest,
    service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[dict[str, str]]:
    return service.password_reset(datos, ip)
