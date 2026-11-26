from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.security import PasswordHasher, SessionTokenManager, VerificationTokenManager
from app.domain.auth_parameters import (
    BLOQUEO_CUENTA,
    INTENTOS_FALLIDOS,
    LONGITUD_CONTRASENA,
    SETTING_FIELD_BY_CODE,
    TTL_ACCESO,
    TTL_RECUPERACION,
    TTL_REFRESCO,
    TTL_VERIFICACION,
    AuthParametersProvider,
)
from app.domain.auth import (
    Account,
    AccountLockedError,
    AccountNotVerifiedError,
    AccountStatus,
    ApiResponse,
    EmailAlreadyRegisteredError,
    EmailDeliveryError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidRefreshTokenError,
    InvalidVerificationTokenError,
    LoginRequest,
    LoginResponseData,
    LogoutRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RateLimitExceededError,
    RefreshRequest,
    RegisterRequest,
    RegisterResponseData,
    Role,
    SessionUser,
    VerifyRequest,
    VerifyResponseData,
    WeakPasswordError,
    normalizar_correo,
)
from app.domain.roles import permisos_para
from app.repository.auth_repository import AuthRepository
from app.repository.email_repository import EmailGateway
from app.services.notifications import NotificationPublisher


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        settings: Settings,
        email_gateway: EmailGateway,
        rate_limiter: RateLimiter,
        login_rate_limiter: RateLimiter | None = None,
        password_rate_limiter: RateLimiter | None = None,
        password_hasher: PasswordHasher | None = None,
        token_manager: VerificationTokenManager | None = None,
        session_token_manager: SessionTokenManager | None = None,
        clock: Callable[[], datetime] | None = None,
        parameters: AuthParametersProvider | None = None,
        notifier: NotificationPublisher | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.email_gateway = email_gateway
        self.rate_limiter = rate_limiter
        self.login_rate_limiter = login_rate_limiter or rate_limiter
        self.password_rate_limiter = password_rate_limiter or rate_limiter
        self.password_hasher = password_hasher or PasswordHasher()
        self.token_manager = token_manager or VerificationTokenManager(settings.secret_key)
        self.session_token_manager = session_token_manager or SessionTokenManager(settings)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.parameters = parameters
        self.notifier = notifier

    def _notificar_evento(
        self,
        cuenta: Account,
        tipo: str,
        *,
        clave_idempotencia: str,
        contexto: dict[str, str] | None = None,
    ) -> None:
        """Publica un evento de cuenta; un fallo de notificación no rompe la HU."""

        if self.notifier is None:
            return
        try:
            self.notifier.notificar_evento(
                cuenta_id=cuenta.id,
                tipo=tipo,
                contexto=contexto or {},
                clave_idempotencia=clave_idempotencia,
                nombre=cuenta.nombre,
                correo=cuenta.correo,
            )
        except Exception:
            pass

    def _parametro(self, codigo: str) -> int:
        """Lee el valor vigente (HU-06) o el estático de ``Settings``."""

        if self.parameters is not None:
            return self.parameters.value(codigo)
        return int(getattr(self.settings, SETTING_FIELD_BY_CODE[codigo]))

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
        expira_en = ahora + timedelta(minutes=self._parametro(TTL_VERIFICACION))
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
        self._notificar_evento(
            cuenta,
            "cuenta_verificada",
            clave_idempotencia=f"verificacion:{cuenta.id}",
            contexto={"nombre": cuenta.nombre},
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

        if not self.login_rate_limiter.allows(
            f"login:ip:{ip_login}",
            f"login:correo:{correo}",
        ):
            raise RateLimitExceededError(
                "Demasiados intentos de inicio de sesión. Intenta nuevamente más tarde."
            )

        cuenta = self.repo.obtener_cuenta_por_correo(correo)

        if cuenta is not None and cuenta.esta_bloqueada(ahora):
            segundos = (
                int((cuenta.bloqueado_hasta - ahora).total_seconds())
                if cuenta.bloqueado_hasta is not None
                else 0
            )
            self.repo.registrar_auditoria(
                "login_bloqueado",
                cuenta.id,
                ip_login,
                {"motivo": "cuenta_bloqueada"},
                ahora,
            )
            raise AccountLockedError(
                "La cuenta está bloqueada temporalmente.",
                {"codigo": "cuenta_bloqueada", "reintentosEnSegundos": max(segundos, 0)},
            )

        if cuenta is None or not self.password_hasher.verify(datos.password, cuenta.password_hash):
            bloqueada = False
            if cuenta is not None:
                bloqueada = cuenta.registrar_intento_fallido(
                    ahora,
                    self._parametro(INTENTOS_FALLIDOS),
                    self._parametro(BLOQUEO_CUENTA),
                )
            self.repo.registrar_auditoria(
                "login_rechazado",
                cuenta.id if cuenta is not None else None,
                ip_login,
                {"motivo": "credenciales_invalidas"},
                ahora,
            )
            if bloqueada:
                self.repo.registrar_auditoria(
                    "cuenta_bloqueada",
                    cuenta.id if cuenta is not None else None,
                    ip_login,
                    {"minutos": self._parametro(BLOQUEO_CUENTA)},
                    ahora,
                )
                raise AccountLockedError(
                    "La cuenta fue bloqueada temporalmente por intentos fallidos.",
                    {
                        "codigo": "cuenta_bloqueada",
                        "reintentosEnSegundos": self._parametro(BLOQUEO_CUENTA) * 60,
                    },
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

        cuenta.reiniciar_intentos()
        respuesta, sesion_id = self._emitir_sesion(cuenta, ahora)
        self.repo.registrar_auditoria(
            "login_exitoso",
            cuenta.id,
            ip_login,
            {"sesionId": sesion_id},
            ahora,
        )
        return ApiResponse[LoginResponseData](
            message="Inicio de sesión exitoso.",
            data=respuesta,
        )

    def logout(self, datos: LogoutRequest, ip: str) -> None:
        ahora = self.clock()
        ip_logout = ip or "desconocida"
        refresh_hash = self.session_token_manager.hash_refresh_token(datos.refreshToken)
        sesion = self.repo.sesion_por_hash(refresh_hash)

        if sesion is None or not sesion.esta_activa(ahora):
            self.repo.registrar_auditoria(
                "logout_rechazado",
                sesion.cuenta_id if sesion is not None else None,
                ip_logout,
                {"motivo": "refresh_token_invalido"},
                ahora,
            )
            raise InvalidRefreshTokenError("El refresh token es inválido o ya fue revocado.")

        self.repo.revocar_sesion_por_hash(refresh_hash, ahora)
        self.repo.registrar_auditoria(
            "logout",
            sesion.cuenta_id,
            ip_logout,
            {"sesionId": sesion.id},
            ahora,
        )

    def refresh(self, datos: RefreshRequest, ip: str) -> ApiResponse[LoginResponseData]:
        ahora = self.clock()
        ip_refresh = ip or "desconocida"
        refresh_hash = self.session_token_manager.hash_refresh_token(datos.refreshToken)
        sesion = self.repo.sesion_por_hash(refresh_hash)

        if sesion is None or not sesion.esta_activa(ahora):
            raise InvalidRefreshTokenError("El refresh token es inválido o ya fue rotado.")

        cuenta = self.repo.obtener_cuenta_por_id(sesion.cuenta_id)
        if cuenta is None or cuenta.estado is not AccountStatus.ACTIVA:
            raise InvalidRefreshTokenError("El refresh token ya no es válido.")

        self.repo.revocar_sesion_por_hash(refresh_hash, ahora)
        respuesta, nueva_sesion_id = self._emitir_sesion(cuenta, ahora)
        self.repo.registrar_auditoria(
            "refresh_rotado",
            cuenta.id,
            ip_refresh,
            {"sesionAnteriorId": sesion.id, "sesionNuevaId": nueva_sesion_id},
            ahora,
        )
        return ApiResponse[LoginResponseData](
            message="Sesión renovada correctamente.",
            data=respuesta,
        )

    def password_forgot(self, datos: PasswordForgotRequest, ip: str) -> ApiResponse[dict[str, str]]:
        correo = normalizar_correo(str(datos.correo))
        ip_recuperacion = ip or "desconocida"
        ahora = self.clock()

        if not self.password_rate_limiter.allows(
            f"password:ip:{ip_recuperacion}",
            f"password:correo:{correo}",
        ):
            raise RateLimitExceededError(
                "Demasiadas solicitudes de recuperación. Intenta nuevamente más tarde."
            )

        cuenta = self.repo.obtener_cuenta_por_correo(correo)
        mensaje = "Si el correo está registrado, enviamos un enlace para restablecer la contraseña."

        if cuenta is not None:
            token = self.token_manager.generate()
            token_hash = self.token_manager.hash_token(token)
            expira_en = ahora + timedelta(minutes=self._parametro(TTL_RECUPERACION))
            self.repo.crear_token_recuperacion(cuenta.id, token_hash, ahora, expira_en)
            reset_url = f"{self.settings.password_reset_url_base.rstrip('/')}?token={token}"
            try:
                entrega = self.email_gateway.send_password_reset(
                    correo=correo,
                    nombre=cuenta.nombre,
                    reset_url=reset_url,
                    expires_at=expira_en,
                )
            except EmailDeliveryError:
                self.repo.registrar_auditoria(
                    "correo_recuperacion_fallido",
                    cuenta.id,
                    ip_recuperacion,
                    {"proveedor": self.settings.email_provider, "estado": "fallido"},
                    ahora,
                )
            else:
                self.repo.registrar_auditoria(
                    "correo_recuperacion_enviado",
                    cuenta.id,
                    ip_recuperacion,
                    {
                        "proveedor": entrega.provider,
                        "mensajeId": entrega.message_id,
                        "estado": entrega.estado,
                    },
                    ahora,
                )

        self.repo.registrar_auditoria(
            "recuperacion_solicitada",
            cuenta.id if cuenta is not None else None,
            ip_recuperacion,
            {"resultado": "respuesta_generica"},
            ahora,
        )
        return ApiResponse[dict[str, str]](
            message=mensaje,
            data={"mensaje": "Revisa tu correo para continuar."},
        )

    def password_reset(self, datos: PasswordResetRequest, ip: str) -> ApiResponse[dict[str, str]]:
        ahora = self.clock()
        ip_reset = ip or "desconocida"
        token_hash = self.token_manager.hash_token(datos.token)
        token = self.repo.token_recuperacion_por_hash(token_hash)

        if token is None or not token.puede_usarse(ahora):
            self.repo.registrar_auditoria(
                "contrasena_restablecida_rechazada",
                token.cuenta_id if token is not None else None,
                ip_reset,
                {"motivo": "token_expirado_o_usado"},
                ahora,
            )
            raise InvalidPasswordResetTokenError(
                "El enlace de recuperación es inválido, expiró o ya fue usado."
            )

        self._validar_contrasena(datos.nuevaPassword)
        token_consumido, cuenta = self.repo.consumir_token_recuperacion(token_hash, ahora)

        if token_consumido is None or cuenta is None:
            self.repo.registrar_auditoria(
                "contrasena_restablecida_rechazada",
                token.cuenta_id,
                ip_reset,
                {"motivo": "token_no_disponible"},
                ahora,
            )
            raise InvalidPasswordResetTokenError(
                "El enlace de recuperación ya no es válido."
            )

        self.repo.actualizar_password(cuenta.id, self.password_hasher.hash(datos.nuevaPassword))
        cuenta.reiniciar_intentos()
        sesiones_revocadas = self.repo.revocar_sesiones_de_cuenta(cuenta.id, ahora)
        self.repo.registrar_auditoria(
            "contrasena_restablecida",
            cuenta.id,
            ip_reset,
            {"sesionesRevocadas": sesiones_revocadas},
            ahora,
        )
        self._notificar_evento(
            cuenta,
            "password_reset",
            clave_idempotencia=f"password_reset:{token.id}",
            contexto={"nombre": cuenta.nombre},
        )
        return ApiResponse[dict[str, str]](
            message="Contraseña actualizada correctamente.",
            data={"mensaje": "Ahora puedes iniciar sesión con tu nueva contraseña."},
        )

    def _emitir_sesion(self, cuenta: Account, ahora: datetime) -> tuple[LoginResponseData, str]:
        access_seconds = self._parametro(TTL_ACCESO) * 60
        expira_access = ahora + timedelta(seconds=access_seconds)
        expira_refresh = ahora + timedelta(days=self._parametro(TTL_REFRESCO))
        jti = secrets.token_urlsafe(12)
        access_token = self.session_token_manager.issue_access_token(
            cuenta_id=cuenta.id,
            rol=cuenta.rol.value,
            jti=jti,
            emitido_en=ahora,
            expira_en=expira_access,
            scopes=permisos_para(cuenta.rol),
        )
        refresh_token = self.session_token_manager.generate_refresh_token()
        refresh_hash = self.session_token_manager.hash_refresh_token(refresh_token)
        sesion = self.repo.crear_sesion(
            cuenta_id=cuenta.id,
            access_token_jti=jti,
            refresh_token_hash=refresh_hash,
            creado_en=ahora,
            expira_en=expira_refresh,
        )
        respuesta = LoginResponseData(
            accessToken=access_token,
            refreshToken=refresh_token,
            expiraEn=access_seconds,
            usuario=SessionUser(id=cuenta.id, rol=cuenta.rol),
        )
        return respuesta, sesion.id

    def _validar_contrasena(self, password: str) -> None:
        errores: list[str] = []
        configuracion = self.settings
        longitud_minima = self._parametro(LONGITUD_CONTRASENA)

        if len(password) < longitud_minima:
            errores.append(f"Debe tener al menos {longitud_minima} caracteres.")
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
