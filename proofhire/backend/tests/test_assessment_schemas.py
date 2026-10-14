"""ListingInput validation, exactly as guidebook Section 5.2 (pure Pydantic, no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.assessment import UINT32_MAX, ListingInput

BASE = {
    "title": "Data Entry Intern",
    "company_name": "Nexora Labs",
    "description": "Enter data into our internal tools for twenty hours per week.",
}


def make(**overrides) -> ListingInput:
    return ListingInput(**{**BASE, **overrides})


def errors_for(**overrides) -> dict[str, str]:
    with pytest.raises(ValidationError) as info:
        make(**overrides)
    return {".".join(str(p) for p in e["loc"]): e["msg"] for e in info.value.errors()}


def test_minimal_listing_gets_the_documented_defaults():
    x = make()
    assert x.work_mode == "onsite"
    assert x.employment_type == "internship"
    assert x.pay_period == "month"
    assert x.currency == "INR"
    assert x.application_channel == "unknown"
    assert x.upfront_fee_amount == 0
    assert x.interview_mode == "none"
    for optional in ("requirements", "location", "salary_min", "salary_max", "contact_email", "contact_phone", "company_website"):
        assert getattr(x, optional) is None


@pytest.mark.parametrize("field,value", [("title", "ab"), ("title", "x" * 201), ("company_name", "a"), ("company_name", "x" * 201)])
def test_required_text_length_limits(field, value):
    assert field in errors_for(**{field: value})


def test_boundary_lengths_are_accepted():
    make(title="abc", company_name="ab", description="d" * 20)
    make(title="t" * 200, company_name="c" * 200, description="d" * 8000)


@pytest.mark.parametrize("length", [19, 8001])
def test_description_must_be_20_to_8000_characters(length):
    assert "description" in errors_for(description="d" * length)


def test_required_fields_are_required():
    with pytest.raises(ValidationError) as info:
        ListingInput()
    missing = {e["loc"][0] for e in info.value.errors()}
    assert missing == {"title", "company_name", "description"}


def test_optional_text_limits():
    assert "requirements" in errors_for(requirements="r" * 4001)
    assert "location" in errors_for(location="l" * 201)
    make(requirements="r" * 4000, location="l" * 200)


def test_salary_max_must_not_be_below_salary_min():
    errs = errors_for(salary_min=50000, salary_max=40000)
    assert "salary_max" in errs
    assert "salary_min" in errs["salary_max"]


def test_salary_equal_or_single_value_is_fine():
    make(salary_min=1000, salary_max=1000)
    make(salary_min=1000)
    make(salary_max=1000)


@pytest.mark.parametrize("field", ["salary_min", "salary_max", "upfront_fee_amount"])
def test_money_fields_reject_negative_and_oversized_numbers(field):
    assert field in errors_for(**{field: -1})
    assert field in errors_for(**{field: UINT32_MAX + 1})  # would overflow INT UNSIGNED in MySQL
    make(**{field: UINT32_MAX})


@pytest.mark.parametrize(
    "field,value",
    [
        ("work_mode", "office"),
        ("employment_type", "freelance"),
        ("pay_period", "week"),
        ("application_channel", "sms"),
        ("interview_mode", "video"),
    ],
)
def test_enums_accept_only_the_documented_literals(field, value):
    assert field in errors_for(**{field: value})


@pytest.mark.parametrize("value", ["onsite", "remote", "hybrid"])
def test_work_mode_literals(value):
    assert make(work_mode=value).work_mode == value


@pytest.mark.parametrize("bad", ["no-at-sign", "a@b", "a b@c.com", "@c.com"])
def test_contact_email_pattern(bad):
    assert "contact_email" in errors_for(contact_email=bad)


def test_contact_email_max_255_and_valid_example():
    assert make(contact_email="hr@example.com").contact_email == "hr@example.com"
    assert "contact_email" in errors_for(contact_email="a" * 250 + "@x.com")


@pytest.mark.parametrize("bad", ["98765abc", "98765#43210", "9" * 33])
def test_contact_phone_pattern_and_length(bad):
    assert "contact_phone" in errors_for(contact_phone=bad)


def test_contact_phone_allows_digits_space_plus_dash_parentheses():
    assert make(contact_phone="+91 (98765) 43-210").contact_phone == "+91 (98765) 43-210"


@pytest.mark.parametrize("bad", ["example.com", "ftp://example.com", "www.example.com"])
def test_company_website_must_start_with_http_or_https(bad):
    assert "company_website" in errors_for(company_website=bad)


def test_company_website_ok_and_max_500():
    assert make(company_website="https://example.com").company_website == "https://example.com"
    assert "company_website" in errors_for(company_website="https://" + "a" * 500)


@pytest.mark.parametrize("bad", ["IN", "INRR", "12A", ""])
def test_currency_must_be_three_letters(bad):
    assert "currency" in errors_for(currency=bad)


def test_currency_is_upper_cased():
    assert make(currency="usd").currency == "USD"


def test_blank_optional_text_fields_become_none():
    x = make(requirements="  ", location="", contact_email=" ", contact_phone="", company_website="  ")
    assert x.requirements is None and x.location is None
    assert x.contact_email is None and x.contact_phone is None and x.company_website is None


def test_required_text_is_trimmed_before_length_check():
    assert "title" in errors_for(title="  ab  ")
    assert make(title="  Data Intern  ").title == "Data Intern"


def test_unknown_fields_are_ignored():
    x = ListingInput(**BASE, is_synthetic_demo=True, user_id=5)
    assert not hasattr(x, "is_synthetic_demo")
    assert "user_id" not in x.model_dump()
