"""Entity normalisation (Member 1 / AI-ML). Guidebook A9.

extract_entities(listing) -> list[Entity] normalises the contact / identity signals the backend stores in
entity_signals and uses to compute connections between assessments:

  email           lower-case, trimmed                                    (free-mail addresses ARE returned)
  email_domain    domain of the email; SKIPPED for FREE_MAIL_DOMAINS
  phone           digits only, leading +91 or 0 dropped, must be 10 digits
  website_domain  host without "www."; SKIPPED for FREE_MAIL_DOMAINS
  company_name    lower-case, punctuation removed, trailing suffixes inc/ltd/pvt/llp/private/limited/
                  technologies/solutions stripped

Only non-empty, valid values are returned (no empty strings, no invalid phones / emails). Output order is fixed:
email, email_domain, phone, website_domain, company_name. No model, DB, network or file I/O.

Import rule: features.py imports FREE_MAIL_DOMAINS from here and promises a stdlib-only inference path, so this
module imports NOTHING outside the standard library at module level. The pydantic `Entity` model is imported
lazily inside extract_entities(). The small normalisers (normalize_email, email_domain_of, website_domain, ...)
are shared with evidence.py so the evidence rules and the stored signals agree on what a "domain" is.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Guidebook Section 6 free-mail list. The backend imports it as `from app.ml.entities import FREE_MAIL_DOMAINS`.
FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "yahoo.com",
        "hotmail.com",
        "proton.me",
        "rediffmail.com",
    }
)

# A9 suffix list (words stripped from the END of the normalised company name).
COMPANY_SUFFIXES = frozenset(
    {"inc", "ltd", "pvt", "llp", "private", "limited", "technologies", "solutions"}
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # same pattern as ListingInput.contact_email
_APOSTROPHES = re.compile(r"['‘’`]")
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def _field(listing: Any, name: str) -> str:
    """Tolerant string access for a pydantic model, attribute object or mapping; None -> ''."""
    if isinstance(listing, dict) or hasattr(listing, "keys"):
        try:
            value = listing.get(name)
        except Exception:
            value = None
    else:
        value = getattr(listing, name, None)
    value = getattr(value, "value", value)  # Enum -> literal
    return "" if value is None else str(value).strip()


# ------------------------------------------------------------------ individual normalisers
def normalize_email(raw: Optional[str]) -> str:
    """Lower-cased, trimmed email; '' when empty or not shaped like an email."""
    email = (raw or "").strip().lower()
    return email if _EMAIL_RE.match(email) else ""


def email_domain_of(email: str) -> str:
    """Domain part of a normalised email ('' if none). Free-mail domains are NOT filtered here."""
    return email.rsplit("@", 1)[1].strip().lower() if "@" in email else ""


def website_domain(raw: Optional[str]) -> str:
    """Host of a website URL: lower-case, no scheme / credentials / port / path, no leading 'www.'."""
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (raw or "").strip(), flags=re.IGNORECASE)
    host = re.split(r"[/?#]", host, maxsplit=1)[0].rsplit("@", 1)[-1].split(":", 1)[0].strip().lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def normalize_phone(raw: Optional[str]) -> str:
    """Indian mobile number as exactly 10 digits, or '' when it cannot be normalised.

    Spaces, hyphens and parentheses are ignored; a leading '+91' is removed; remaining non-digits are dropped and ONE
    leading '0' is removed. The result must be exactly 10 digits, otherwise '' (never guessed or padded).
    """
    compact = re.sub(r"[\s\-()]", "", (raw or "").strip())
    if compact.startswith("+91"):
        compact = compact[3:]
    digits = re.sub(r"\D", "", compact)
    if digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def normalize_company_name(raw: Optional[str]) -> str:
    """Lower-case, punctuation removed, trailing legal/generic suffixes stripped ('' if the name is empty).

    'Nexora Technologies Pvt. Ltd.' -> 'nexora'. If stripping would leave nothing (the name consists only of suffix
    words, e.g. 'Solutions Ltd'), the punctuation-free name is kept ('solutions ltd') instead of being dropped.
    """
    text = _NON_WORD.sub(" ", _APOSTROPHES.sub("", (raw or "").lower()))
    tokens = text.split()
    kept = list(tokens)
    while kept and kept[-1] in COMPANY_SUFFIXES:
        kept.pop()
    return " ".join(kept) if kept else " ".join(tokens)


# ------------------------------------------------------------------ public contract (A9)
def extract_entities(listing: Any) -> list:
    """Normalised entity signals for one listing -> list[app.schemas.ml_schemas.Entity]. Pure function."""
    from app.schemas.ml_schemas import Entity  # lazy: keeps this module's import path stdlib-only

    out = []

    email = normalize_email(_field(listing, "contact_email"))
    if email:
        out.append(Entity(type="email", value=email))
        domain = email_domain_of(email)
        if domain and domain not in FREE_MAIL_DOMAINS:
            out.append(Entity(type="email_domain", value=domain))

    phone = normalize_phone(_field(listing, "contact_phone"))
    if phone:
        out.append(Entity(type="phone", value=phone))

    site = website_domain(_field(listing, "company_website"))
    if site and site not in FREE_MAIL_DOMAINS:
        out.append(Entity(type="website_domain", value=site))

    company = normalize_company_name(_field(listing, "company_name"))
    if company:
        out.append(Entity(type="company_name", value=company))

    return out


__all__ = [
    "FREE_MAIL_DOMAINS", "COMPANY_SUFFIXES", "extract_entities", "normalize_email", "email_domain_of",
    "website_domain", "normalize_phone", "normalize_company_name",
]
