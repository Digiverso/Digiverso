from __future__ import annotations

import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.domain.auth import EmailDeliveryError


@dataclass(frozen=True)
class EmailDelivery:
    provider: str
    message_id: str
    estado: str
    intento_en: datetime


class EmailGateway(Protocol):
    def send_verification(
        self,
        correo: str,
        nombre: str,
        verification_url: str,
        expires_at: datetime,
    ) -> EmailDelivery: ...

    def send_password_reset(
        self,
        correo: str,
        nombre: str,
        reset_url: str,
        expires_at: datetime,
    ) -> EmailDelivery: ...


def render_verification_template(nombre: str, verification_url: str, minutos: int) -> str:
    template_path = Path(__file__).resolve().parents[1] / "templates" / "email" / "verificacion_correo.html"
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("{{nombre}}", escape(nombre))
        .replace("{{url}}", escape(verification_url))
        .replace("{{minutos}}", str(minutos))
    )


def render_password_reset_template(nombre: str, reset_url: str, minutos: int) -> str:
    template_path = Path(__file__).resolve().parents[1] / "templates" / "email" / "recuperacion_contrasena.html"
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("{{nombre}}", escape(nombre))
        .replace("{{url}}", escape(reset_url))
        .replace("{{minutos}}", str(minutos))
    )


class ConsoleEmailGateway:
    def __init__(self, ttl_minutes: int, password_reset_ttl_minutes: int | None = None) -> None:
        self.ttl_minutes = ttl_minutes
        self.password_reset_ttl_minutes = password_reset_ttl_minutes or ttl_minutes

    def send_verification(
        self,
        correo: str,
        nombre: str,
        verification_url: str,
        expires_at: datetime,
    ) -> EmailDelivery:
        render_verification_template(nombre, verification_url, self.ttl_minutes)
        return EmailDelivery(
            provider="console",
            message_id=f"console_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now(),
        )

    def send_password_reset(
        self,
        correo: str,
        nombre: str,
        reset_url: str,
        expires_at: datetime,
    ) -> EmailDelivery:
        render_password_reset_template(nombre, reset_url, self.password_reset_ttl_minutes)
        return EmailDelivery(
            provider="console",
            message_id=f"console_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now(),
        )


class SmtpEmailGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_verification(
        self,
        correo: str,
        nombre: str,
        verification_url: str,
        expires_at: datetime,
    ) -> EmailDelivery:
        html = render_verification_template(
            nombre,
            verification_url,
            self.settings.verification_token_ttl_minutes,
        )
        message = EmailMessage()
        message["Subject"] = "Verifica tu cuenta de Digiverso"
        message["From"] = self.settings.email_from
        message["To"] = correo
        message.set_content(html, subtype="html")

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_username:
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError("No fue posible enviar el correo de verificación.") from exc

        return EmailDelivery(
            provider="smtp",
            message_id=f"smtp_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now(),
        )

    def send_password_reset(
        self,
        correo: str,
        nombre: str,
        reset_url: str,
        expires_at: datetime,
    ) -> EmailDelivery:
        html = render_password_reset_template(
            nombre,
            reset_url,
            self.settings.password_reset_ttl_minutes,
        )
        message = EmailMessage()
        message["Subject"] = "Restablece tu contraseña de Digiverso"
        message["From"] = self.settings.email_from
        message["To"] = correo
        message.set_content(html, subtype="html")

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_username:
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError("No fue posible enviar el correo de recuperación.") from exc

        return EmailDelivery(
            provider="smtp",
            message_id=f"smtp_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now(),
        )


def build_email_gateway(settings: Settings) -> EmailGateway:
    if settings.email_provider == "smtp":
        return SmtpEmailGateway(settings)
    return ConsoleEmailGateway(
        settings.verification_token_ttl_minutes,
        settings.password_reset_ttl_minutes,
    )


# --------------------------------------------------------------- HU-05
class NotificationSender(Protocol):
    """Envío genérico usado por la cola de notificaciones (FUN-12)."""

    def send(
        self, correo: str, nombre: str, asunto: str, mensaje: str
    ) -> EmailDelivery: ...


class ConsoleNotificationSender:
    def send(
        self, correo: str, nombre: str, asunto: str, mensaje: str
    ) -> EmailDelivery:
        return EmailDelivery(
            provider="console",
            message_id=f"console_ntf_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(timezone.utc),
        )


class SmtpNotificationSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(
        self, correo: str, nombre: str, asunto: str, mensaje: str
    ) -> EmailDelivery:
        message = EmailMessage()
        message["Subject"] = asunto
        message["From"] = self.settings.email_from
        message["To"] = correo
        message.set_content(mensaje)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_username:
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError("No fue posible enviar la notificación.") from exc
        return EmailDelivery(
            provider="smtp",
            message_id=f"smtp_ntf_{uuid.uuid4().hex[:12]}",
            estado="enviado",
            intento_en=datetime.now(timezone.utc),
        )


def build_notification_sender(settings: Settings) -> NotificationSender:
    if settings.email_provider == "smtp":
        return SmtpNotificationSender(settings)
    return ConsoleNotificationSender()
