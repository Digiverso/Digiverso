"""Política de roles y permisos de la HU-04 (SUB-05).

AUT-09 se mantiene fuera del catálogo entero de HU-06: define qué roles se
pueden asignar y qué permisos efectivos deriva cada uno. La decisión final se
toma siempre en el servicio, no en el token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.domain.auth import InvalidRoleError, PermissionDeniedError, Role

AUT_09 = "AUT-09"
ROLES_PERMITIDOS: tuple[Role, ...] = (
    Role.CONSUMIDOR,
    Role.PRODUCTOR,
    Role.ADMINISTRADOR,
)

ROLE_PERMISSIONS: dict[Role, tuple[str, ...]] = {
    Role.CONSUMIDOR: (
        "users.profile.read",
        "users.profile.write",
    ),
    Role.PRODUCTOR: (
        "users.profile.read",
        "users.profile.write",
        "catalog.product.create",
        "catalog.product.edit",
        "commerce.sales.read",
    ),
    Role.ADMINISTRADOR: (
        "users.profile.read",
        "users.profile.write",
        "users.permissions.read",
        "catalog.category.write",
        "catalog.product.create",
        "catalog.product.edit",
        "catalog.product.write",
        "commerce.sales.read",
        "admin.users.roles.write",
        "admin.auth.parameters.write",
    ),
}


def _recursos_desde(permisos: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(".".join(p.split(".")[:-1]) for p in permisos))


ROLE_RESOURCES: dict[Role, tuple[str, ...]] = {
    rol: _recursos_desde(permisos) for rol, permisos in ROLE_PERMISSIONS.items()
}

ROLE_WRITE_PERMISSION = "admin.users.roles.write"


def normalizar_rol(valor: str | Role) -> Role:
    """Convierte un valor externo en un rol permitido por AUT-09."""

    candidato = str(valor).strip().lower() if not isinstance(valor, Role) else valor
    try:
        rol = Role(candidato)
    except ValueError as exc:
        raise InvalidRoleError(
            f"El rol '{valor}' no está permitido por {AUT_09}.",
            {"codigo": "rol_no_permitido", "rolesPermitidos": [r.value for r in ROLES_PERMITIDOS]},
        ) from exc
    if rol not in ROLES_PERMITIDOS:
        raise InvalidRoleError(
            f"El rol '{valor}' no está permitido por {AUT_09}.",
            {"codigo": "rol_no_permitido", "rolesPermitidos": [r.value for r in ROLES_PERMITIDOS]},
        )
    return rol


def permisos_para(rol: str | Role) -> tuple[str, ...]:
    return ROLE_PERMISSIONS.get(normalizar_rol(rol), ())


def recursos_para(rol: str | Role) -> tuple[str, ...]:
    return ROLE_RESOURCES.get(normalizar_rol(rol), ())


class PermissionValidator:
    """Validador interno (PRC-11): rol, recurso y acción antes de ejecutar."""

    def __init__(
        self,
        permisos_por_rol: Mapping[Role, tuple[str, ...]] | None = None,
    ) -> None:
        self._permisos_por_rol = permisos_por_rol or ROLE_PERMISSIONS

    def permisos_para(self, rol: str | Role) -> tuple[str, ...]:
        return self._permisos_por_rol.get(normalizar_rol(rol), ())

    def recursos_para(self, rol: str | Role) -> tuple[str, ...]:
        return _recursos_desde(self.permisos_para(rol))

    def ensure(
        self,
        *,
        rol: str | Role,
        permiso: str,
        roles_extra: tuple[str, ...] = (),
        recurso: str | None = None,
        accion: str | None = None,
    ) -> None:
        permitidos = set(self.permisos_para(rol)) | {
            extra for extra in roles_extra if "." in extra
        }
        if permiso not in permitidos:
            raise PermissionDeniedError(
                f"Se requiere el permiso {permiso} para esta operación.",
                {"codigo": "permiso_denegado", "permiso": permiso, "rol": str(rol)},
            )

        if recurso and not any(p.startswith(f"{recurso}.") for p in permitidos):
            raise PermissionDeniedError(
                f"El rol no tiene acceso al recurso {recurso}.",
                {"codigo": "permiso_denegado", "permiso": permiso, "recurso": recurso},
            )

        if accion and not any(p.endswith(f".{accion}") for p in permitidos):
            raise PermissionDeniedError(
                f"El rol no puede ejecutar la acción {accion}.",
                {"codigo": "permiso_denegado", "permiso": permiso, "accion": accion},
            )


@dataclass(frozen=True)
class RoleAssignment:
    """Resultado de PRC-09 con los tres campos exigidos por la HU-04."""

    usuario_id: str
    rol_anterior: Role
    rol_nuevo: Role


@dataclass(frozen=True)
class UserPermissions:
    """Permisos efectivos (PRC-10): rol, permisos y recursos."""

    usuario_id: str
    rol: Role
    permisos: tuple[str, ...]
    recursos: tuple[str, ...]
