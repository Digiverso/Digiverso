from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.domain.auth import (
    Account,
    AccountStatus,
    AuditEvent,
    PasswordResetToken,
    Role,
    Session,
    VerificationToken,
    normalizar_correo,
)


class AuthRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reset()

    def _reset(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._accounts_by_email: dict[str, str] = {}
        self._tokens: dict[str, VerificationToken] = {}
        self._password_reset_tokens: dict[str, PasswordResetToken] = {}
        self._sessions: dict[str, Session] = {}
        self._audit_events: list[AuditEvent] = []
        self._next_account = 1
        self._next_token = 1
        self._next_password_reset_token = 1
        self._next_session = 1
        self._next_audit = 1

    def reset(self) -> None:
        with self._lock:
            self._reset()

    def crear_cuenta(
        self,
        nombre: str,
        correo: str,
        password_hash: str,
        estado: AccountStatus,
        rol: Role,
        creado_en: datetime,
    ) -> Account:
        with self._lock:
            cuenta_id = f"usr_{self._next_account:03d}"
            cuenta = Account(
                id=cuenta_id,
                nombre=nombre,
                correo=normalizar_correo(correo),
                password_hash=password_hash,
                estado=estado,
                rol=rol,
                creado_en=creado_en,
            )
            self._accounts[cuenta_id] = cuenta
            self._accounts_by_email[cuenta.correo] = cuenta_id
            self._next_account += 1
            return cuenta

    def obtener_cuenta_por_correo(self, correo: str) -> Account | None:
        with self._lock:
            cuenta_id = self._accounts_by_email.get(normalizar_correo(correo))
            return self._accounts.get(cuenta_id) if cuenta_id else None

    def obtener_cuenta_por_id(self, cuenta_id: str) -> Account | None:
        with self._lock:
            return self._accounts.get(cuenta_id)

    def actualizar_perfil(
        self,
        cuenta_id: str,
        *,
        nombre: str,
        biografia: str | None,
        foto: str | None,
    ) -> Account | None:
        with self._lock:
            cuenta = self._accounts.get(cuenta_id)
            if cuenta is None:
                return None
            cuenta.nombre = nombre
            cuenta.biografia = biografia
            cuenta.foto = foto
            return cuenta

    def actualizar_password(self, cuenta_id: str, password_hash: str) -> Account | None:
        with self._lock:
            cuenta = self._accounts.get(cuenta_id)
            if cuenta is None:
                return None
            cuenta.actualizar_password(password_hash)
            return cuenta

    def crear_token_verificacion(
        self,
        cuenta_id: str,
        token_hash: str,
        creado_en: datetime,
        expira_en: datetime,
    ) -> VerificationToken:
        with self._lock:
            token_id = f"vt_{self._next_token:03d}"
            token = VerificationToken(
                id=token_id,
                cuenta_id=cuenta_id,
                token_hash=token_hash,
                creado_en=creado_en,
                expira_en=expira_en,
            )
            self._tokens[token_hash] = token
            self._next_token += 1
            return token

    def token_por_hash(self, token_hash: str) -> VerificationToken | None:
        with self._lock:
            return self._tokens.get(token_hash)

    def consumir_token_verificacion(
        self,
        token_hash: str,
        ahora: datetime,
    ) -> tuple[VerificationToken | None, Account | None]:
        with self._lock:
            token = self._tokens.get(token_hash)
            if token is None:
                return None, None
            if not token.puede_usarse(ahora):
                return token, None
            cuenta = self._accounts.get(token.cuenta_id)
            if cuenta is None:
                return token, None
            token.consumir(ahora)
            cuenta.activar(ahora)
            return token, cuenta

    def crear_sesion(
        self,
        cuenta_id: str,
        access_token_jti: str,
        refresh_token_hash: str,
        creado_en: datetime,
        expira_en: datetime,
    ) -> Session:
        with self._lock:
            sesion_id = f"ses_{self._next_session:03d}"
            sesion = Session(
                id=sesion_id,
                cuenta_id=cuenta_id,
                access_token_jti=access_token_jti,
                refresh_token_hash=refresh_token_hash,
                creado_en=creado_en,
                expira_en=expira_en,
            )
            self._sessions[sesion_id] = sesion
            self._next_session += 1
            return sesion

    def sesion_por_hash(self, refresh_token_hash: str) -> Session | None:
        with self._lock:
            return next(
                (
                    sesion
                    for sesion in self._sessions.values()
                    if sesion.refresh_token_hash == refresh_token_hash
                ),
                None,
            )

    def sesion_por_jti(self, access_token_jti: str) -> Session | None:
        with self._lock:
            return next(
                (
                    sesion
                    for sesion in self._sessions.values()
                    if sesion.access_token_jti == access_token_jti
                ),
                None,
            )

    def revocar_sesion_por_hash(self, refresh_token_hash: str, ahora: datetime) -> Session | None:
        with self._lock:
            sesion = self.sesion_por_hash(refresh_token_hash)
            if sesion is None:
                return None
            sesion.revocar(ahora)
            return sesion

    def revocar_sesiones_de_cuenta(self, cuenta_id: str, ahora: datetime) -> int:
        with self._lock:
            revocadas = 0
            for sesion in self._sessions.values():
                if sesion.cuenta_id == cuenta_id and sesion.revocado_en is None:
                    sesion.revocar(ahora)
                    revocadas += 1
            return revocadas

    def sesiones_activas(self, cuenta_id: str | None = None, ahora: datetime | None = None) -> list[Session]:
        with self._lock:
            momento = ahora or datetime.now(timezone.utc)
            return [
                sesion
                for sesion in self._sessions.values()
                if (cuenta_id is None or sesion.cuenta_id == cuenta_id)
                and sesion.esta_activa(momento)
            ]

    def crear_token_recuperacion(
        self,
        cuenta_id: str,
        token_hash: str,
        creado_en: datetime,
        expira_en: datetime,
    ) -> PasswordResetToken:
        with self._lock:
            token_id = f"prt_{self._next_password_reset_token:03d}"
            token = PasswordResetToken(
                id=token_id,
                cuenta_id=cuenta_id,
                token_hash=token_hash,
                creado_en=creado_en,
                expira_en=expira_en,
            )
            self._password_reset_tokens[token_hash] = token
            self._next_password_reset_token += 1
            return token

    def token_recuperacion_por_hash(self, token_hash: str) -> PasswordResetToken | None:
        with self._lock:
            return self._password_reset_tokens.get(token_hash)

    def consumir_token_recuperacion(
        self,
        token_hash: str,
        ahora: datetime,
    ) -> tuple[PasswordResetToken | None, Account | None]:
        with self._lock:
            token = self._password_reset_tokens.get(token_hash)
            if token is None:
                return None, None
            if not token.puede_usarse(ahora):
                return token, None
            cuenta = self._accounts.get(token.cuenta_id)
            if cuenta is None:
                return token, None
            token.consumir(ahora)
            return token, cuenta

    def registrar_auditoria(
        self,
        tipo: str,
        cuenta_id: str | None,
        ip: str,
        metadata: dict[str, Any],
        registrado_en: datetime,
    ) -> AuditEvent:
        with self._lock:
            evento = AuditEvent(
                id=f"aud_{self._next_audit:03d}",
                tipo=tipo,
                cuenta_id=cuenta_id,
                ip=ip,
                metadata=dict(metadata),
                registrado_en=registrado_en,
            )
            self._audit_events.append(evento)
            self._next_audit += 1
            return evento

    def eventos_auditoria(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._audit_events)

    def total_cuentas(self) -> int:
        with self._lock:
            return len(self._accounts)


auth_repository = AuthRepository()
