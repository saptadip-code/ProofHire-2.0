"""Entity normalisation tests (Member 1, A-G4). Guidebook A9. Run: PYTHONPATH=backend pytest ml/tests -q"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ml import entities as N
from app.ml.entities import FREE_MAIL_DOMAINS

pytest.importorskip("pydantic")
from app.schemas.ml_schemas import Entity, ListingInput  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2] / "backend"
BASE = dict(title="Data Intern", company_name="Nexora Labs", description="A reasonably long description of the role.")


def ents(**kw):
    return [(e.type.value, e.value) for e in N.extract_entities(ListingInput(**{**BASE, **kw}))]


# ------------------------------------------------------------------ email / email_domain
def test_email_is_lower_cased_and_trimmed():
    assert ("email", "careers@nexora.com") in ents(contact_email="Careers@Nexora.COM")
    padded = N.extract_entities({"company_name": "Zen", "contact_email": "  Careers@Nexora.COM \n"})  # raw mapping input
    assert [(e.type.value, e.value) for e in padded][:2] == [("email", "careers@nexora.com"), ("email_domain", "nexora.com")]


def test_corporate_email_also_yields_email_domain():
    got = ents(contact_email="Careers@Nexora.com")
    assert ("email", "careers@nexora.com") in got and ("email_domain", "nexora.com") in got


@pytest.mark.parametrize("domain", sorted(FREE_MAIL_DOMAINS))
def test_free_mail_domains_never_create_an_email_domain_entity(domain):
    got = ents(contact_email=f"Someone@{domain.upper()}")
    assert ("email", f"someone@{domain}") in got  # the address itself is still a signal
    assert not [t for t, _ in got if t == "email_domain"]


def test_guidebook_free_mail_list_is_exact():
    assert FREE_MAIL_DOMAINS == {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "proton.me", "rediffmail.com"}


def test_subdomain_of_a_free_mail_provider_is_not_treated_as_free_mail():
    assert ("email_domain", "mail.gmail.com") in ents(contact_email="a@mail.gmail.com")


# ------------------------------------------------------------------ phone
@pytest.mark.parametrize("raw", [
    "9876543210", "98765 43210", "+91 98765 43210", "+919876543210", "(+91) 98765-43210", "09876543210",
    "0 98765 43210", " +91-98765-43210 ", "+91 098765 43210"])
def test_indian_phone_numbers_normalise_to_ten_digits(raw):
    assert N.normalize_phone(raw) == "9876543210"
    assert ("phone", "9876543210") in ents(contact_phone=raw)


@pytest.mark.parametrize("raw", ["12345", "98765432", "+91 12345 678", "98765432101", "919876543210", "0123456789", "---", "()"])
def test_invalid_phone_numbers_are_skipped_not_guessed(raw):
    assert N.normalize_phone(raw) == ""
    assert not [t for t, _ in ents(contact_phone=raw) if t == "phone"]


# ------------------------------------------------------------------ website_domain
@pytest.mark.parametrize("raw,expected", [
    ("https://www.Nexora.com", "nexora.com"), ("http://nexora.com/careers?id=3#top", "nexora.com"),
    ("https://WWW.nexora.co.in:8080/", "nexora.co.in"), ("https://jobs.nexora.com", "jobs.nexora.com"),
    ("https://user:pw@nexora.com/x", "nexora.com")])
def test_website_domain_has_no_scheme_www_port_or_path(raw, expected):
    assert N.website_domain(raw) == expected
    assert ("website_domain", expected) in ents(company_website=raw)


def test_free_mail_website_never_creates_a_website_domain_entity():
    assert not [t for t, _ in ents(company_website="https://www.gmail.com/jobs") if t == "website_domain"]


# ------------------------------------------------------------------ company_name
@pytest.mark.parametrize("raw,expected", [
    ("Nexora Technologies Pvt. Ltd.", "nexora"), ("ACME, Inc.", "acme"), ("Zen Solutions LLP", "zen"),
    ("Brightpath Private Limited", "brightpath"), ("Nexora Labs", "nexora labs"),
    ("Nex-Ora  Labs!", "nex ora labs"), ("Bob's Café Pvt Ltd", "bobs café"),
    ("Technologies Solutions Ltd", "technologies solutions ltd"), ("  Solutions  ", "solutions"),
    ("Inc Works Inc", "inc works")])
def test_company_name_normalisation(raw, expected):
    assert N.normalize_company_name(raw) == expected


def test_suffix_words_inside_the_name_are_kept():
    assert N.normalize_company_name("Pvt Ltd Trading Co") == "pvt ltd trading co"  # only TRAILING suffixes go


def test_suffix_list_is_the_guidebook_list():
    assert N.COMPANY_SUFFIXES == {"inc", "ltd", "pvt", "llp", "private", "limited", "technologies", "solutions"}


# ------------------------------------------------------------------ empties, order, types
def test_empty_values_are_skipped():
    got = ents()
    assert got == [("company_name", "nexora labs")]


def test_blank_strings_behave_like_missing():
    row = {"company_name": "Zen", "contact_email": "", "contact_phone": "  ", "company_website": ""}  # CSV-style row
    assert [(e.type.value, e.value) for e in N.extract_entities(row)] == [("company_name", "zen")]
    assert ents(contact_email=None, contact_phone=None, company_website=None) == [("company_name", "nexora labs")]


def test_output_order_and_types_are_stable():
    got = ents(contact_email="hr@nexora.com", contact_phone="+91 98765 43210", company_website="https://nexora.com")
    assert [t for t, _ in got] == ["email", "email_domain", "phone", "website_domain", "company_name"]
    assert all(isinstance(e, Entity) for e in N.extract_entities(ListingInput(**BASE)))


def test_no_duplicate_entities():
    got = ents(contact_email="hr@nexora.com", company_website="https://nexora.com")
    assert len(got) == len(set(got))


def test_accepts_plain_mappings_and_attribute_objects():
    row = {"company_name": "Zen Solutions LLP", "contact_email": "A@Zen.in", "contact_phone": "", "company_website": None}
    assert [(e.type.value, e.value) for e in N.extract_entities(row)] == [
        ("email", "a@zen.in"), ("email_domain", "zen.in"), ("company_name", "zen")]
    obj = SimpleNamespace(company_name="Zen", contact_email=None, contact_phone="09876543210", company_website=None)
    assert [(e.type.value, e.value) for e in N.extract_entities(obj)] == [("phone", "9876543210"), ("company_name", "zen")]


def test_malformed_email_is_not_a_signal():
    assert N.normalize_email("not-an-email") == "" and N.normalize_email(None) == "" and N.normalize_email("a@b") == ""
    assert N.extract_entities({"company_name": "Zen", "contact_email": "not-an-email"})[0].type.value == "company_name"


def test_module_import_stays_stdlib_only():
    code = ("import sys; import app.ml.entities; "
            "bad=[m for m in ('pandas','numpy','sklearn','scipy','pydantic') if m in sys.modules]; "
            "sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(BACKEND)!r}); {code}"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
