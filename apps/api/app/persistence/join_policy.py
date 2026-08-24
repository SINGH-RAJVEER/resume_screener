import re

# Domains anyone can register mailboxes on cannot be claimed by one
# organization, or its policy would capture every future signup from them.
PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "zoho.com",
        "yandex.com",
    }
)

_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)


class InvalidDomainError(ValueError):
    pass


def normalize_domain(domain: str) -> str:
    normalized = domain.strip().casefold().removeprefix("@")
    if (
        not normalized
        or normalized in PUBLIC_EMAIL_DOMAINS
        or not _DOMAIN_PATTERN.fullmatch(normalized)
    ):
        raise InvalidDomainError(
            "Enter a valid company email domain; public email providers are not claimable"
        )
    return normalized


def email_domain(email: str) -> str:
    _, _, domain = email.rpartition("@")
    return domain.casefold()
