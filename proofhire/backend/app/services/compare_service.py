"""POST /assessments/compare (guidebook Section 5.4 and B4).

Loads both assessments and builds one row per signal:

    risk_score, risk_level, upfront_fee_amount, salary_monthly, email_type,
    website_present, interview_mode, application_channel, observed_risk_signals,
    approved_reports, connections_count

`better` is "a", "b" or "tie" and means "lower risk wins". Rows with no honest
ordering (salary_monthly) are always "tie". Nothing here computes a score: the
risk score and level are the ML result stored with each assessment.

The endpoint is public (like GET /assessments/{id}), so only non-sensitive facts
are returned: contact e-mail and phone are never part of the response, only the
e-mail TYPE ("company", "free" or "none").
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.db.models import Assessment
from app.schemas.assessment import AssessmentSummary, CompareResult, CompareRow
from app.services.assessment_service import _approved_report_count, _free_mail_domains, _load
from app.services.connection_service import compute_connections

_RISK_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}
_STRUCTURED_INTERVIEWS = {"video_call", "in_person", "phone_call"}  # evidence STRUCTURED_INTERVIEW (A7)
_MESSAGING_CHANNELS = {"whatsapp", "telegram"}  # evidence MESSAGING_APP_ONLY (A7)


def _salary_monthly(a: Assessment) -> int | None:
    """D8: salary is compared per month. Uses salary_max (or salary_min if that is all there is)."""
    row = a.listing
    value = row.salary_max if row.salary_max is not None else row.salary_min
    if value is None:
        return None
    if row.pay_period == "month":
        return int(value)
    if row.pay_period == "year":
        return round(value / 12)
    return None  # one_time pay has no monthly equivalent


def _email_type(a: Assessment) -> str:
    email = a.listing.contact_email
    if not email or "@" not in email:
        return "none"
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return "free" if domain in _free_mail_domains() else "company"


def _facts(db: Session, a: Assessment) -> dict:
    signals = [(s.signal_type, s.signal_value) for s in sorted(a.entity_signals, key=lambda s: s.id)]
    return {
        "risk_score": round(float(a.risk_score), 4),
        "risk_level": a.risk_level,
        "upfront_fee_amount": int(a.listing.upfront_fee_amount or 0),
        "salary_monthly": _salary_monthly(a),
        "email_type": _email_type(a),
        "website_present": bool(a.listing.company_website),
        "interview_mode": a.listing.interview_mode,
        "application_channel": a.listing.application_channel,
        "observed_risk_signals": sum(
            1 for e in a.evidence_items if e.evidence_type == "observed" and e.direction == "increases_risk"
        ),
        "approved_reports": _approved_report_count(db, a.id),
        "connections_count": len(compute_connections(db, a.id, signals)),
    }


# signal name -> function turning the value into a "risk rank" (lower = safer), or None = no ordering
_RANKS: list[tuple[str, Callable | None]] = [
    ("risk_score", lambda v: v),
    ("risk_level", lambda v: _RISK_LEVEL_RANK[v]),
    ("upfront_fee_amount", lambda v: v),
    ("salary_monthly", None),
    ("email_type", lambda v: 0 if v == "company" else 1),
    ("website_present", lambda v: 0 if v else 1),
    ("interview_mode", lambda v: 0 if v in _STRUCTURED_INTERVIEWS else 1),
    ("application_channel", lambda v: 1 if v in _MESSAGING_CHANNELS else 0),
    ("observed_risk_signals", lambda v: v),
    ("approved_reports", lambda v: v),
    ("connections_count", lambda v: v),
]


def _better(rank_fn: Callable | None, a_value, b_value) -> str:
    if rank_fn is None:
        return "tie"
    ra, rb = rank_fn(a_value), rank_fn(b_value)
    if ra < rb:
        return "a"
    if rb < ra:
        return "b"
    return "tie"


def _summary(db: Session, a: Assessment) -> AssessmentSummary:
    return AssessmentSummary(
        id=a.id,
        created_at=a.created_at,
        title=a.listing.title,
        company_name=a.listing.company_name,
        risk_score=round(float(a.risk_score), 4),
        risk_level=a.risk_level,
        evidence_count=len(a.evidence_items),
        report_count_approved=_approved_report_count(db, a.id),
    )


def compare_assessments(db: Session, id_a: int, id_b: int) -> CompareResult:
    if id_a == id_b:
        raise bad_request("assessment_id_a and assessment_id_b must be different")
    a = _load(db, id_a)  # 404 if missing
    b = _load(db, id_b)

    fa, fb = _facts(db, a), _facts(db, b)
    rows = [
        CompareRow(signal=name, a=fa[name], b=fb[name], better=_better(rank_fn, fa[name], fb[name]))
        for name, rank_fn in _RANKS
    ]
    return CompareResult(a=_summary(db, a), b=_summary(db, b), rows=rows)
