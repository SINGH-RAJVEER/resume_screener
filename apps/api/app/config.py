from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    database_url: str
    port: int
    web_url: str
    jwt_secret: str
    jwt_ttl: timedelta


def load_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if len(jwt_secret) < 32:
        raise ValueError("JWT_SECRET environment variable must be at least 32 characters")
    port_text = os.environ.get("PORT", "") or "8000"
    if port_text != "8000":
        raise ValueError("PORT must be 8000")
    ttl_text = os.environ.get("JWT_TTL", "") or "168h"
    jwt_ttl = parse_duration(ttl_text)
    if jwt_ttl <= timedelta(0):
        raise ValueError("JWT_TTL must be a positive duration")
    return Settings(
        database_url=database_url,
        port=8000,
        web_url=os.environ.get("WEB_URL", "") or "http://localhost:3000",
        jwt_secret=jwt_secret,
        jwt_ttl=jwt_ttl,
    )


def parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", value)
    if match is None:
        raise ValueError("JWT_TTL must be a positive duration")
    amount = float(match.group(1))
    unit = match.group(2)
    seconds = amount * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return timedelta(seconds=seconds)
