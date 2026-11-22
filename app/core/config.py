from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_env_file() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        values[key.strip()] = cleaned
    return values


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_debug: bool
    app_port: int
    secret_key: str
    password_min_length: int
    password_require_uppercase: bool
    password_require_lowercase: bool
    password_require_digit: bool
    password_require_special: bool
    verification_token_ttl_minutes: int
    verification_url_base: str
    register_rate_limit: int
    rate_limit_window_seconds: int
    email_provider: str
    email_from: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool


def load_settings() -> Settings:
    file_values = _read_env_file()

    def value(name: str, default: str) -> str:
        return os.getenv(name, file_values.get(name, default))

    return Settings(
        app_name=value("APP_NAME", "Digiverso API"),
        app_env=value("APP_ENV", "development"),
        app_debug=_as_bool(value("APP_DEBUG", "true")),
        app_port=int(value("APP_PORT", "8000")),
        secret_key=value("SECRET_KEY", "cambia-este-valor-en-produccion"),
        password_min_length=int(value("AUTH_PASSWORD_MIN_LENGTH", "8")),
        password_require_uppercase=_as_bool(value("AUTH_PASSWORD_REQUIRE_UPPERCASE", "true")),
        password_require_lowercase=_as_bool(value("AUTH_PASSWORD_REQUIRE_LOWERCASE", "true")),
        password_require_digit=_as_bool(value("AUTH_PASSWORD_REQUIRE_DIGIT", "true")),
        password_require_special=_as_bool(value("AUTH_PASSWORD_REQUIRE_SPECIAL", "true")),
        verification_token_ttl_minutes=int(value("AUTH_VERIFICATION_TOKEN_TTL_MINUTES", "15")),
        verification_url_base=value("AUTH_VERIFICATION_URL_BASE", "http://127.0.0.1:8000/verificar-correo"),
        register_rate_limit=int(value("AUTH_REGISTER_RATE_LIMIT", "10")),
        rate_limit_window_seconds=int(value("AUTH_RATE_LIMIT_WINDOW_SECONDS", "600")),
        email_provider=value("EMAIL_PROVIDER", "console").strip().lower(),
        email_from=value("EMAIL_FROM", "no-responder@digiverso.local"),
        smtp_host=value("SMTP_HOST", ""),
        smtp_port=int(value("SMTP_PORT", "587")),
        smtp_username=value("SMTP_USERNAME", ""),
        smtp_password=value("SMTP_PASSWORD", ""),
        smtp_use_tls=_as_bool(value("SMTP_USE_TLS", "true")),
    )


settings = load_settings()
