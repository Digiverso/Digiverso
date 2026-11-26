"""Servicio de roles y permisos (HU-04, FUN-09/10/11)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import Settings
from app.domain.actor import Actor
from app.domain.auth import (
    Account,
    AccountNotFoundError,
    InvalidRoleError,
    LastAdministratorError,
    PermissionDeniedError,
    Role,
)
from app.domain.roles import (
    ROLE_WRITE_PERMISSION,
    PermissionValidator,
    RoleAssignment,
    UserPermissions,
    normalizar_rol,
    permisos_para,
    recursos_para,
)
from app.repository.auth_repository import AuthRepository

Principal = Actor | Account


class RolesPermissionsService:
    def __init__(
        self,
        repo: AuthRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.validator = PermissionValidator()

    # ------------------------------------------------------------ PRC-09
    def asignar_rol(
        self,
        *,
        cuenta_id: str,
        rol: str | Role,
        actor: Principal,
        ip: str = "",
    ) -> RoleAssignment:
        ahora = self.clock()
        ip_registro = ip or "desconocida"
        actor_id = self._actor_id(actor)

        if not self._es_admin(actor):
            self._auditar_rechazo(
                cuenta_id=cuenta_id,
                actor_id=actor_id,
                motivo="permiso_denegado",
                ip=ip_registro,
                ahora=ahora,
            )
            raise PermissionDeniedError(
                "Solo un administrador puede asignar roles.",
                {"codigo": "permiso_denegado", "permiso": ROLE_WRITE_PERMISSION},
            )

        cuenta = self.repo.obtener_cuenta_por_id(cuenta_id)
        if cuenta is None:
            raise AccountNotFoundError(
                "No existe la cuenta indicada.",
                {"codigo": "usuario_no_encontrado", "usuarioId": cuenta_id},
            )

        try:
            rol_nuevo = normalizar_rol(rol)
        except InvalidRoleError:
            self._auditar_rechazo(
                cuenta_id=cuenta_id,
                actor_id=actor_id,
                motivo="rol_no_permitido",
                ip=ip_registro,
                ahora=ahora,
                rol=str(rol),
            )
            raise

        rol_anterior = cuenta.rol
        if (
            rol_anterior is Role.ADMINISTRADOR
            and rol_nuevo is not Role.ADMINISTRADOR
            and self.repo.contar_por_rol(Role.ADMINISTRADOR) <= 1
        ):
            self._auditar_rechazo(
                cuenta_id=cuenta_id,
                actor_id=actor_id,
                motivo="ultimo_administrador",
                ip=ip_registro,
                ahora=ahora,
                rol=str(rol_nuevo.value),
            )
            raise LastAdministratorError(
                "No se puede quitar el rol al último administrador.",
                {"codigo": "ultimo_administrador", "usuarioId": cuenta_id},
            )

        # Idempotencia: repetir la misma asignación no genera un nuevo cambio.
        if rol_anterior is rol_nuevo:
            return RoleAssignment(
                usuario_id=cuenta_id,
                rol_anterior=rol_anterior,
                rol_nuevo=rol_nuevo,
            )

        actualizada = self.repo.actualizar_rol(cuenta_id, rol_nuevo)
        if actualizada is None:
            raise AccountNotFoundError(
                "No existe la cuenta indicada.",
                {"codigo": "usuario_no_encontrado", "usuarioId": cuenta_id},
            )

        self.repo.registrar_auditoria(
            "rol_asignado",
            cuenta_id,
            ip_registro,
            {
                "usuario": cuenta_id,
                "actorId": actor_id,
                "rolAnterior": rol_anterior.value,
                "rolNuevo": rol_nuevo.value,
                "fecha": ahora.isoformat(),
            },
            ahora,
        )
        return RoleAssignment(
            usuario_id=cuenta_id,
            rol_anterior=rol_anterior,
            rol_nuevo=rol_nuevo,
        )

    # ------------------------------------------------------------ PRC-10
    def permisos_de(self, cuenta: Account) -> UserPermissions:
        return UserPermissions(
            usuario_id=cuenta.id,
            rol=cuenta.rol,
            permisos=permisos_para(cuenta.rol),
            recursos=recursos_para(cuenta.rol),
        )

    # ------------------------------------------------------------ PRC-11
    def ensure_permiso(
        self,
        *,
        permiso: str,
        actor: Principal | None = None,
        cuenta: Account | None = None,
        recurso: str | None = None,
        accion: str | None = None,
        ip: str = "",
    ) -> None:
        """Valida permiso, recurso y acción; audita cualquier denegación."""

        roles_extra = self._roles_de(actor)
        if Role.ADMINISTRADOR.value in roles_extra or ROLE_WRITE_PERMISSION in roles_extra:
            rol = Role.ADMINISTRADOR
        else:
            rol = cuenta.rol if cuenta is not None else Role.CONSUMIDOR
        try:
            self.validator.ensure(
                rol=rol,
                permiso=permiso,
                roles_extra=roles_extra,
                recurso=recurso,
                accion=accion,
            )
        except PermissionDeniedError as exc:
            self.repo.registrar_auditoria(
                "permiso_denegado",
                cuenta.id if cuenta is not None else self._actor_id(actor),
                ip or "desconocida",
                {
                    "permiso": permiso,
                    "recurso": recurso,
                    "accion": accion,
                    "rol": rol.value,
                    "fecha": self.clock().isoformat(),
                },
                self.clock(),
            )
            raise

    # ------------------------------------------------------------ internos
    @staticmethod
    def _roles_de(principal: Principal | None) -> tuple[str, ...]:
        if isinstance(principal, Account):
            return (principal.rol.value,)
        if isinstance(principal, Actor):
            return principal.roles
        return ()

    @classmethod
    def _es_admin(cls, principal: Principal) -> bool:
        roles = cls._roles_de(principal)
        return (
            Role.ADMINISTRADOR.value in roles
            or ROLE_WRITE_PERMISSION in roles
        )

    @staticmethod
    def _actor_id(principal: Principal | None) -> str:
        return principal.id if principal is not None else "desconocido"

    def _auditar_rechazo(
        self,
        *,
        cuenta_id: str,
        actor_id: str,
        motivo: str,
        ip: str,
        ahora: datetime,
        rol: str | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "usuario": cuenta_id,
            "actorId": actor_id,
            "motivo": motivo,
            "fecha": ahora.isoformat(),
        }
        if rol is not None:
            metadata["rol"] = rol
        self.repo.registrar_auditoria(
            "rol_asignacion_rechazada", cuenta_id, ip, metadata, ahora
        )
