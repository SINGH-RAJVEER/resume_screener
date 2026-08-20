from __future__ import annotations

import pytest

from app.config import load_settings


def set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/template")
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-is-at-least-32-characters")


def test_backend_port_is_8000_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.delenv("PORT", raising=False)

    assert load_settings().port == 8000


def test_backend_rejects_other_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("PORT", "8001")

    with pytest.raises(ValueError, match="PORT must be 8000"):
        load_settings()
