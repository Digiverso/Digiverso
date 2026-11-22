from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.security import PasswordHasher, VerificationTokenManager
from app.domain.auth import (
    AccountNotVerifiedError,
    AccountStatus,
    ApiResponse,
    EmailAlreadyRegisteredError,
    EmailDeliveryError,
    InvalidCredentialsError,
    InvalidVerificationTokenError,
    LoginRequest,
    LoginResponseData,
    RateLimitExceededError,
    RegisterRequest,
    RegisterResponseData,
    Role,
    VerifyRequest,
    VerifyResponseData,
    WeakPasswordError,
    normalizar_correo,
)
from app.repository.auth_repository import AuthRepository
from app.repository.email_repository import EmailGateway


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        settings: Settings,
        email_gateway: EmailGateway,
        rate_limiter: RateLimiter,
        password_hasher: PasswordHasher | None = None,
        token_manager: VerificationTokenManager | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.email_gateway = email_gateway
        self.rate_limiter = rate_limiter
        self.password_hasher = password_hasher or PasswordHasher()
        self.token_manager = token_manager or VerificationTokenManager(settings.secret_key)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def registrar(self, datos: RegisterRequest, ip: str) -> ApiResponse[RegisterResponseData]:
        correo = normalizar_correo(str(datos.correo))
        ip_registro = ip or "desconocida"

        claves = (f"register:ip:{ip_registro}", f"register:correo:{correo}")
        if not self.rate_limiter.allows(*claves):
            raise RateLimitExceededError("Demasiados intentos de registro. Intenta nuevamente más tarde.")

        self._validar_contrasena(datos.password)

        if self.repo.obtener_cuenta_por_correo(correo) is not None:
            raise EmailAlreadyRegisteredError("El correo ya está registrado.")

        ahora = self.clock()
        cuenta = self.repo.crear_cuenta(
            nombre=datos.nombre,
            correo=correo,
            password_hash=self.password_hasher.hash(datos.password),
            estado=AccountStatus.PENDIENTE,
            rol=Role.CONSUMIDOR,
            creado_en=ahora,
        )

        token = self.token_manager.generate()
        token_hash = self.token_manager.hash_token(token)
        expira_en = ahora + timedelta(minutes=self.settings.verification_token_ttl_minutes)
        self.repo.crear_token_verificacion(cuenta.id, token_hash, ahora, expira_en)

        verification_url = f"{self.settings.verification_url_base.rstrip('/')}?token={token}"
        try:
            entrega = self.email_gateway.send_verification(
                correo=correo,
                nombre=cuenta.nombre,
                verification_url=verification_url,
                expires_at=expira_en,
            )
        except EmailDeliveryError:
            self.repo.registrar_auditoria(
                "correo_verificacion_fallido",
                cuenta.id,
                ip_registro,
                {"proveedor": self.settings.email_provider, "estado": "fallido"},
                ahora,
            )
            raise

        self.repo.registrar_auditoria(
            "registro_creado",
            cuenta.id,
            ip_registro,
            {"resultado": AccountStatus.PENDIENTE.value},
            ahora,
        )
        self.repo.registrar_auditoria(
            "correo_verificacion_enviado",
            cuenta.id,
            ip_registro,
            {
                "proveedor": entrega.provider,
                "mensajeId": entrega.message_id,
                "estado": entrega.estado,
            },
            ahora,
        )

        return ApiResponse[RegisterResponseData](
            message="Cuenta creada. Revisa tu correo para verificarla.",
            data=cuenta.to_register_data(),
        )

    def verificar(self, datos: VerifyRequest, ip: str) -> ApiResponse[VerifyResponseData]:
        ahora = self.clock()
        ip_verificacion = ip or "desconocida"
        token_hash = self.token_manager.hash_token(datos.token)
        token, cuenta = self.repo.consumir_token_verificacion(token_hash, ahora)

        if token is None or cuenta is None:
            motivo = "token_inexistente" if token is None else "token_expirado_o_usado"
            self.repo.registrar_auditoria(
                "verificacion_rechazada",
                token.cuenta_id if token is not None else None,
                ip_verificacion,
                {"motivo": motivo},
                ahora,
            )
            raise InvalidVerificationTokenError("El enlace de verificación es inválido, expiró o ya fue usado.")

        self.repo.registrar_auditoria(
            "cuenta_verificada",
            cuenta.id,
            ip_verificacion,
            {"resultado": AccountStatus.ACTIVA.value},
            ahora,
        )

        return ApiResponse[VerifyResponseData](
            message="Cuenta verificada correctamente.",
            data=VerifyResponseData(
                cuentaId=cuenta.id,
                estado=cuenta.estado,
                fechaVerificacion=cuenta.verificado_en or ahora,
            ),
        )

    def login(self, datos: LoginRequest, ip: str) -> ApiResponse[LoginResponseData]:
        correo = normalizar_correo(str(datos.correo))
        ip_login = ip or "desconocida"
        ahora = self.clock()
        cuenta = self.repo.obtener_cuenta_por_correo(correo)

        if cuenta is None or not self.password_hasher.verify(datos.password, cuenta.password_hash):
            self.repo.registrar_auditoria(
                "login_rechazado",
                cuenta.id if cuenta is not None else None,
                ip_login,
                {"motivo": "credenciales_invalidas"},
                ahora,
            )
            raise InvalidCredentialsError("Correo o contraseña inválidos.")

        if cuenta.estado is not AccountStatus.ACTIVA:
            self.repo.registrar_auditoria(
                "login_rechazado",
                cuenta.id,
                ip_login,
                {"motivo": "cuenta_no_verificada"},
                ahora,
            )
            raise AccountNotVerifiedError("Debes verificar tu correo antes de iniciar sesión.")

        return ApiResponse[LoginResponseData](
            message="Inicio de sesión permitido.",
            data=cuenta.to_login_data(),
        )

    def _validar_contrasena(self, password: str) -> None:
        errores: list[str] = []
        configuracion = self.settings

        if len(password) < configuracion.password_min_length:
            errores.append(f"Debe tener al menos {configuracion.password_min_length} caracteres.")
        if configuracion.password_require_uppercase and not any(caracter.isupper() for caracter in password):
            errores.append("Debe incluir al menos una letra mayúscula.")
        if configuracion.password_require_lowercase and not any(caracter.islower() for caracter in password):
            errores.append("Debe incluir al menos una letra minúscula.")
        if configuracion.password_require_digit and not any(caracter.isdigit() for caracter in password):
            errores.append("Debe incluir al menos un número.")
        if configuracion.password_require_special and not any(not caracter.isalnum() for caracter in password):
            errores.append("Debe incluir al menos un carácter especial.")

        if errores:
            raise WeakPasswordError(
                "La contraseña no cumple la política de seguridad.",
                {"codigo": "politica_contrasena", "detalle": errores},
            )
