"""Checklist library validity (guidebook D2): every trigger is a valid A7 evidence code or '*'."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
A7_CODES = {
    "UPFRONT_FEE", "PERSONAL_DATA_REQUEST", "GUARANTEED_OFFER_CLAIM", "UNREALISTIC_PAY", "FREE_EMAIL_CONTACT",
    "EMAIL_DOMAIN_MISMATCH", "NO_COMPANY_WEBSITE", "MESSAGING_APP_ONLY", "URGENCY_PRESSURE", "NO_INTERVIEW",
    "VAGUE_DESCRIPTION", "VAGUE_REQUIREMENTS", "EXCESSIVE_HYPE", "CORP_EMAIL_MATCHES_WEBSITE",
    "DETAILED_REQUIREMENTS", "STRUCTURED_INTERVIEW", "PAY_IN_EXPECTED_RANGE", "MODEL_TERM", "MODEL_FEATURE",
}
REPORT_TYPES = {"advance_fee", "impersonation", "personal_data_request", "fake_company", "harassment", "other"}


def _library():
    return json.loads((DATA / "checklist_library.json").read_text(encoding="utf-8"))


def test_at_least_20_items_with_unique_codes():
    items = _library()
    assert len(items) >= 20
    codes = [i["code"] for i in items]
    assert len(codes) == len(set(codes))


def test_item_fields_are_valid():
    for item in _library():
        assert item["code"] and 0 < len(item["text"]) <= 500
        assert item["priority"] in (1, 2, 3)
        assert item["triggers"], item["code"]


def test_every_trigger_is_a_valid_evidence_code_or_star():
    for item in _library():
        for trigger in item["triggers"]:
            assert trigger == "*" or trigger in A7_CODES, (item["code"], trigger)


def test_at_least_four_always_on_items():
    assert sum(1 for i in _library() if "*" in i["triggers"]) >= 4


def test_every_observed_risk_code_has_an_item():
    covered = {t for i in _library() for t in i["triggers"]}
    assert {"UPFRONT_FEE", "PERSONAL_DATA_REQUEST", "UNREALISTIC_PAY", "NO_INTERVIEW"} <= covered


def test_moderation_policy_covers_every_report_type():
    policy = json.loads((DATA / "moderation_policy.json").read_text(encoding="utf-8"))
    assert set(policy["report_types"]) == REPORT_TYPES
    for rule in policy["report_types"].values():
        assert rule["acceptance_rule"] and len(rule["rejection_reasons"]) == 3
