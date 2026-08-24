import pytest

from app.persistence.join_policy import (
    PUBLIC_EMAIL_DOMAINS,
    InvalidDomainError,
    email_domain,
    normalize_domain,
)


def test_normalize_domain_strips_at_and_casefolds() -> None:
    assert normalize_domain("@Company.COM") == "company.com"


def test_normalize_domain_accepts_multi_level_domains() -> None:
    assert normalize_domain("mail.corp.example.co.uk") == "mail.corp.example.co.uk"


@pytest.mark.parametrize("domain", ["", "@", "company", "company..com", "-bad.com", "bad-.com"])
def test_normalize_domain_rejects_malformed_values(domain: str) -> None:
    with pytest.raises(InvalidDomainError):
        normalize_domain(domain)


@pytest.mark.parametrize("domain", sorted(PUBLIC_EMAIL_DOMAINS))
def test_normalize_domain_rejects_public_providers(domain: str) -> None:
    with pytest.raises(InvalidDomainError):
        normalize_domain(domain)


def test_email_domain_is_casefolded_suffix_after_the_last_at() -> None:
    assert email_domain("Ada@Company.com") == "company.com"
    assert email_domain("ada@corp@example.com") == "example.com"
