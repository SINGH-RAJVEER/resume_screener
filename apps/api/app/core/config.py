
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import URL

from ..billing.settings import BillingSettings, load_billing_settings


@dataclass(frozen=True)
class Settings:
    database_url: str
    web_url: str
    jwt_secret: str
    jwt_ttl: timedelta
    storage_root: str = ".local-storage"
    billing: BillingSettings = field(default_factory=BillingSettings)


def load_settings() -> Settings:
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if len(jwt_secret) < 32:
        raise ValueError("JWT_SECRET environment variable must be at least 32 characters")
    ttl_text = os.environ.get("JWT_TTL", "") or "168h"
    jwt_ttl = parse_duration(ttl_text)
    if jwt_ttl <= timedelta(0):
        raise ValueError("JWT_TTL must be a positive duration")
    return Settings(
        database_url=load_database_url(),
        web_url=os.environ.get("WEB_URL", "") or "http://localhost:3000",
        jwt_secret=jwt_secret,
        jwt_ttl=jwt_ttl,
        storage_root=os.environ.get("STORAGE_ROOT", "") or ".local-storage",
        billing=load_billing_settings(),
    )


def load_database_url() -> str:
    if database_url := os.environ.get("DATABASE_URL"):
        return database_url

    names = ["DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD"]
    values = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"Missing database environment variables: {', '.join(missing)}")

    port_text = os.environ.get("DATABASE_PORT", "5432")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("DATABASE_PORT must be an integer") from error

    return URL.create(
        "postgresql+asyncpg",
        username=values["DATABASE_USER"],
        password=values["DATABASE_PASSWORD"],
        host=values["DATABASE_HOST"],
        port=port,
        database=values["DATABASE_NAME"],
    ).render_as_string(hide_password=False)


def parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", value)
    if match is None:
        raise ValueError("JWT_TTL must be a positive duration")
    amount = float(match.group(1))
    unit = match.group(2)
    seconds = amount * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return timedelta(seconds=seconds)
