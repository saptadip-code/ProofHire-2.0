"""TEST-ONLY stand-ins for Member 1's ML package.

Nothing here ships in the app. The real files are not delivered yet, so the
tests install fake `app.ml.pipeline` and `app.schemas.ml_schemas` modules into
sys.modules (undone automatically by monkeypatch) and exercise the real gateway,
service, router and database code around them.

The fake result follows guidebook A2's description of the first-hour stub: score
0.91 when upfront_fee_amount > 0 else 0.12, two evidence items, a template
explanation, two checklist items, entities from the email. It is a mock for
automated tests only and is never used outside tests/.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

FREE_MAIL = {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "proton.me", "rediffmail.com"}


def stub_result(listing: dict) -> dict:
    risky = (listing.get("upfront_fee_amount") or 0) > 0
    entities = []
    email = listing.get("contact_email")
    if email:
        entities.append({"type": "email", "value": email.strip().lower()})
        domain = email.split("@")[-1].lower()
        if domain not in FREE_MAIL:
            entities.append({"type": "email_domain", "value": domain})
    return {
        "risk_score": 0.91 if risky else 0.12,
        "risk_level": "high" if risky else "low",
        "thresholds": {"low": 0.35, "high": 0.70},
        "model_version": "proofhire-lr-stub-test",
        "evidence": [
            {
                "id": "E1",
                "code": "UPFRONT_FEE",
                "label": "Asks the applicant to pay money",
                "type": "observed",
                "direction": "increases_risk",
                "severity": 3,
                "snippet": "registration fee of Rs 1,499",
                "weight": None,
            },
            {
                "id": "E2",
                "code": "MODEL_TERM",
                "label": "Wording often seen in risky listings: 'guaranteed placement'",
                "type": "model",
                "direction": "increases_risk",
                "severity": 2,
                "snippet": None,
                "weight": 1.84,
            },
        ],
        "explanation": {
            "source": "template",
            "summary": "Test summary: this listing shows patterns linked to fee-based scams.",
            "key_concerns": [{"text": "An upfront fee is requested.", "evidence_ids": ["E1"]}],
            "what_to_verify": ["Ask for the company's registered legal name."],
        },
        "checklist": [
            {"code": "CHK_NO_FEE", "text": "Never pay any fee before a signed, verified offer.", "priority": 1},
            {"code": "CHK_GENERAL_RECRUITER", "text": "Find the recruiter on the official page.", "priority": 3},
        ],
        "entities": entities,
        "llm_meta": {"provider": "template", "model": "template", "latency_ms": 0, "success": True, "error_code": None},
    }


class FakeMlListingInput(BaseModel):
    """Stands in for ml_schemas.ListingInput: accepts whatever the gateway sends."""

    model_config = ConfigDict(extra="allow")


class Wrapped(BaseModel):
    """A pydantic object result (like Member 1's MlResult would be) instead of a plain dict."""

    model_config = ConfigDict(extra="allow")


def install_fake_ml(monkeypatch, *, loaded: bool = True, result_fn=stub_result, raises: Exception | None = None):
    """Install fake ML modules. Returns a namespace whose .calls lists every assess_listing call."""
    state = SimpleNamespace(calls=[], status_calls=0)

    def assess_listing(listing, with_llm: bool = True):
        state.calls.append(listing.model_dump())
        if raises is not None:
            raise raises
        return result_fn(listing.model_dump())

    def model_status():
        state.status_calls += 1
        return {"loaded": loaded, "model_version": "proofhire-lr-stub-test" if loaded else None, "llm_enabled": False}

    pipeline = types.ModuleType("app.ml.pipeline")
    pipeline.assess_listing = assess_listing
    pipeline.model_status = model_status
    schemas = types.ModuleType("app.schemas.ml_schemas")
    schemas.ListingInput = FakeMlListingInput

    monkeypatch.setitem(sys.modules, "app.ml.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "app.schemas.ml_schemas", schemas)
    return state


def remove_ml(monkeypatch):
    """Make the ML package look absent, even if the real files are added to the project later."""
    monkeypatch.setitem(sys.modules, "app.ml.pipeline", None)  # None => ImportError on import
    monkeypatch.setitem(sys.modules, "app.schemas.ml_schemas", None)
