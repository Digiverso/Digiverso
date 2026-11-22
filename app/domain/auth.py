from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class AccountStatus(StrEnum):
    PENDIENTE = "pendiente_verificacion"
    ACTIVA = "activa"


class Role(StrEnum):
    CONSUMIDOR = "consumidor"


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nombre": "Ana Pérez",
                "correo": "ana@example.com",
                "password": "Abcdef1!",
                "aceptar_politicas": True,
            }
        }
    )

    nombre: str = Field(..., min_length=2, max_length=100, description="Nombre del visitante")
    correo: EmailStr = Field(..., description="Correo electrónico del visitante")
    password: str = Field(..., min_length=1, description="Contraseña de la cuenta")
    aceptar_politicas: bool = Field(..., description="Aceptación de políticas de privacidad y términos")

    @field_validator("nombre")
    @classmethod
    def normalizar_nombre(cls, value: str) -> str:
        return value.strip()

    @field_validator("aceptar_politicas")
    @classmethod
    def politicas_aceptadas(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Debes aceptar las políticas de privacidad y términos de uso")
        return value


class RegisterResponseData(BaseModel):
    userId: str
    correo: str
    estado: AccountStatus
    rol: Role


class VerifyRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "token": "token_temporal_recibido_por_correo"
            }
        }
    )

    token: str = Field(..., min_length=10, description="Token de verificación recibido por correo")


class VerifyResponseData(BaseModel):
    cuentaId: str
    estado: AccountStatus
    fechaVerificacion: datetime


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "correo": "ana@example.com",
                "password": "Abcdef1!",
            }
        }
    )

    correo: EmailStr
    password: str


class LoginResponseData(BaseModel):
    userId: str
    correo: str
    estado: AccountStatus
    rol: Role


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    message: str
    data: T
    success: bool = True


def normalizar_correo(correo: str) -> str:
    return correo.strip().lower()


@dataclass
class Account:
    id: str
    nombre: str
    correo: str
    password_hash: str
    estado: AccountStatus = AccountStatus.PENDIENTE
    rol: Role = Role.CONSUMIDOR
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verificado_en: datetime | None = None

    def esta_pendiente(self) -> bool:
        return self.estado is AccountStatus.PENDIENTE

    def activar(self, ahora: datetime) -> None:
        self.estado = AccountStatus.ACTIVA
        self.verificado_en = ahora

    def to_register_data(self) -> RegisterResponseData:
        return RegisterResponseData(
            userId=self.id,
            correo=self.correo,
            estado=self.estado,
            rol=self.rol,
        )

    def to_login_data(self) -> LoginResponseData:
        return LoginResponseData(
            userId=self.id,
            correo=self.correo,
            estado=self.estado,
            rol=self.rol,
        )


@dataclass
class VerificationToken:
    id: str
    cuenta_id: str
    token_hash: str
    creado_en: datetime
    expira_en: datetime
    usado_en: datetime | None = None

    def puede_usarse(self, ahora: datetime) -> bool:
        return self.usado_en is None and self.expira_en > ahora

    def consumir(self, ahora: datetime) -> bool:
        if not self.puede_usarse(ahora):
            return False
        self.usado_en = ahora
        return True


@dataclass(frozen=True)
class AuditEvent:
    id: str
    tipo: str
    cuenta_id: str | None
    ip: str
    metadata: dict[str, Any]
    registrado_en: datetime


class DomainError(Exception):
    status_code: int = 400
    codigo: str = "error_dominio"

    def __init__(self, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data if data is not None else {"codigo": self.codigo}


class WeakPasswordError(DomainError):
    status_code = 400
    codigo = "politica_contrasena"


class EmailAlreadyRegisteredError(DomainError):
    status_code = 409
    codigo = "correo_duplicado"


class InvalidVerificationTokenError(DomainError):
    status_code = 410
    codigo = "token_invalido"


class AccountNotVerifiedError(DomainError):
    status_code = 403
    codigo = "cuenta_no_verificada"


class InvalidCredentialsError(DomainError):
    status_code = 401
    codigo = "credenciales_invalidas"


class RateLimitExceededError(DomainError):
    status_code = 429
    codigo = "limite_excedido"


class EmailDeliveryError(DomainError):
    status_code = 502
    codigo = "envio_correo_fallido"
