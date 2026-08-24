
import pytest

from app.core.config import load_database_url


def test_database_url_can_be_provided_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql://postgres:password@localhost:5432/skillsignal"
    monkeypatch.setenv("DATABASE_URL", url)

    assert load_database_url() == url


def test_database_url_escapes_discrete_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_HOST", "postgres")
    monkeypatch.setenv("DATABASE_NAME", "skillsignal")
    monkeypatch.setenv("DATABASE_USER", "app")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss/word")

    assert load_database_url() == (
        "postgresql+asyncpg://app:p%40ss%2Fword@postgres:5432/skillsignal"
    )
