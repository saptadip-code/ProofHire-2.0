"""Business logic for /assessments (guidebook B4, B6). Routers stay thin.

create_assessment   POST   score through the ML gateway, then store everything in ONE transaction
get_assessment      GET    rebuild the AssessmentResult from the database (connections recomputed live)
list_assessments    GET    the caller's saved assessments, paginated
delete_assessment   DELETE owner only
update_checklist_item PATCH owner (JWT user or X-Owner-Token) ticks / unticks one item

The backend never computes a score, level, evidence, explanation or checklist:
all of that comes from the ML pipeline (through app.services.ml_gateway) and is
stored exactly as returned.
"""

from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import AppError, forbidden, not_found
from app.core.security import generate_owner_token, hash_owner_token, owner_token_matches
from app.db.models import (
    Assessment,
    AssessmentChecklistItem,
    EntitySignal,
    EvidenceItem,
    Listing,
    LlmCall,
    Report,
    User,
)
from app.db.session import describe_db_error
from app.schemas.assessment import (
    AssessmentCreated,
    AssessmentPage,
    AssessmentResult,
    AssessmentSummary,
    ChecklistItemOut,
    ChecklistPatchResult,
    ConnectionOut,
    EntityOut,
    EvidenceOut,
    ExplanationOut,
    KeyConcern,
    ListingEcho,
    ListingInput,
    Thresholds,
)
from app.services import ml_gateway
from app.services.connection_service import compute_connections, mask_email, mask_phone, mask_signal_value

logger = logging.getLogger("proofhire.assessments")

MAX_ID = 2**63 - 1  # ids are BIGINT; anything outside is simply "not found"

# Section 6: these free-mail domains are never stored as domain signals (they would
# link unrelated listings). B5 says the list is shared with ML (app.ml.entities.FREE_MAIL_DOMAINS);
# until that module exists, the six domains named in Section 6 are used.
_FREE_MAIL_FALLBACK = frozenset({"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "proton.me", "rediffmail.com"})


def _free_mail_domains() -> frozenset[str]:
    try:
        domains = getattr(importlib.import_module("app.ml.entities"), "FREE_MAIL_DOMAINS", None)
        if domains:
            return frozenset(str(d).lower() for d in domains)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read FREE_MAIL_DOMAINS from app.ml.entities: %s", type(exc).__name__)
    return _FREE_MAIL_FALLBACK


def _dec(value: float) -> Decimal:
    """Float to the 4-decimal DECIMAL the schema stores."""
    return Decimal(str(round(float(value), 4)))


# ==================================================================================
# create
# ==================================================================================
def _add_children(db: Session, assessment_id: int, ml: ml_gateway.MlOutput) -> None:
    """Insert evidence, checklist, entity signals and the LLM log row (B4 step 4)."""
    for order, ev in enumerate(ml.evidence):
        db.add(
            EvidenceItem(
                assessment_id=assessment_id,
                public_id=ev.id,
                code=ev.code,
                label=ev.label[:255],
                evidence_type=ev.type,
                direction=ev.direction,
                severity=ev.severity,
                snippet=ev.snippet[:500] if ev.snippet else None,
                weight=_dec(ev.weight) if ev.weight is not None else None,  # NULL for observed
                sort_order=order,  # order returned by ML
            )
        )

    seen_codes: set[str] = set()
    for item in ml.checklist:
        if item.code in seen_codes:  # UNIQUE(assessment_id, code)
            logger.warning("Duplicate checklist code from ML ignored: %s", item.code)
            continue
        seen_codes.add(item.code)
        db.add(
            AssessmentChecklistItem(
                assessment_id=assessment_id,
                code=item.code,
                text=item.text[:500],
                priority=item.priority,
                is_done=False,
            )
        )

    free_mail = _free_mail_domains()
    seen_signals: set[tuple[str, str]] = set()
    for ent in ml.entities:
        value = ent.value.strip()
        if not value or len(value) > 255:
            continue
        if ent.type in ("email_domain", "website_domain") and value.lower() in free_mail:
            continue
        if (ent.type, value) in seen_signals:
            continue
        seen_signals.add((ent.type, value))
        db.add(EntitySignal(assessment_id=assessment_id, signal_type=ent.type, signal_value=value))

    if ml.llm_meta is not None:
        meta = ml.llm_meta
        db.add(
            LlmCall(
                assessment_id=assessment_id,
                provider=meta.provider[:32],
                model=meta.model[:100],
                latency_ms=meta.latency_ms,
                success=meta.success,
                error_code=meta.error_code[:64] if meta.error_code else None,
            )
        )


def create_assessment(db: Session, listing: ListingInput, user: User | None) -> AssessmentResult:
    """POST /assessments. Returns AssessmentCreated (with owner_token) for anonymous callers."""
    # 1) Score first. A 503/500 here happens before any database write.
    ml = ml_gateway.run_assessment(listing)

    # 2) Anonymous callers get a random owner token; only its SHA-256 hash is stored.
    owner_token = None if user is not None else generate_owner_token()

    # 3) One transaction: everything is saved or nothing is.
    try:
        listing_row = Listing(**listing.model_dump(), is_synthetic_demo=False)
        db.add(listing_row)
        db.flush()

        assessment = Assessment(
            user_id=user.id if user is not None else None,
            listing_id=listing_row.id,
            owner_token_hash=hash_owner_token(owner_token) if owner_token else None,
            risk_score=_dec(ml.risk_score),
            risk_level=ml.risk_level,
            threshold_low=_dec(ml.thresholds.low),  # copied at scoring time
            threshold_high=_dec(ml.thresholds.high),
            model_version=ml.model_version,
            explanation_source=ml.explanation.source,
            summary=ml.explanation.summary,
            key_concerns=[c.model_dump() for c in ml.explanation.key_concerns],
            what_to_verify=list(ml.explanation.what_to_verify),
        )
        db.add(assessment)
        db.flush()
        assessment_id = assessment.id

        _add_children(db, assessment_id, ml)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Saving an assessment failed: %s", describe_db_error(exc))
        raise AppError("internal_error", "Could not save the assessment", 500) from None
    except Exception:
        db.rollback()
        raise

    # 4) Rebuild the response from what was actually stored.
    db.expire_all()
    stored = _load(db, assessment_id)
    return _build_result(db, stored, is_owner=True, owner_token=owner_token)


# ==================================================================================
# read
# ==================================================================================
def _load(db: Session, assessment_id: int) -> Assessment:
    if not 1 <= assessment_id <= MAX_ID:
        raise not_found("Assessment not found")
    stmt = (
        select(Assessment)
        .options(
            joinedload(Assessment.listing),
            selectinload(Assessment.evidence_items),
            selectinload(Assessment.checklist_items),
            selectinload(Assessment.entity_signals),
        )
        .where(Assessment.id == assessment_id)
    )
    assessment = db.scalar(stmt)
    if assessment is None:
        raise not_found("Assessment not found")
    return assessment


def is_owner(assessment: Assessment, user: User | None, owner_token: str | None) -> bool:
    """B4: the caller's user id equals user_id, or X-Owner-Token hashes to owner_token_hash."""
    if user is not None and assessment.user_id is not None and assessment.user_id == user.id:
        return True
    return owner_token_matches(owner_token, assessment.owner_token_hash)


def _approved_report_count(db: Session, assessment_id: int) -> int:
    return db.scalar(
        select(func.count(Report.id)).where(Report.assessment_id == assessment_id, Report.status == "approved")
    ) or 0


def _build_result(db: Session, a: Assessment, *, is_owner: bool, owner_token: str | None = None) -> AssessmentResult:
    row = a.listing

    # B4: contact fields are returned only to the owner; others see them masked.
    email = row.contact_email if is_owner or not row.contact_email else mask_email(row.contact_email)
    phone = row.contact_phone if is_owner or not row.contact_phone else mask_phone(row.contact_phone)
    listing = ListingEcho(
        title=row.title,
        company_name=row.company_name,
        description=row.description,
        requirements=row.requirements,
        location=row.location,
        work_mode=row.work_mode,
        employment_type=row.employment_type,
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        pay_period=row.pay_period,
        currency=row.currency,
        contact_email=email,
        contact_phone=phone,
        application_channel=row.application_channel,
        company_website=row.company_website,
        upfront_fee_amount=row.upfront_fee_amount,
        interview_mode=row.interview_mode,
    )

    signals = [(s.signal_type, s.signal_value) for s in sorted(a.entity_signals, key=lambda s: s.id)]
    # The same masking applies to the entity list, otherwise it would leak the raw email/phone.
    entities = [EntityOut(type=t, value=v if is_owner else mask_signal_value(t, v)) for t, v in signals]
    connections = [ConnectionOut(**c) for c in compute_connections(db, a.id, signals)]

    fields = dict(
        assessment_id=a.id,
        created_at=a.created_at,
        listing=listing,
        risk_score=round(float(a.risk_score), 4),
        risk_level=a.risk_level,
        thresholds=Thresholds(low=float(a.threshold_low), high=float(a.threshold_high)),
        model_version=a.model_version,
        evidence=[
            EvidenceOut(
                id=e.public_id,
                code=e.code,
                label=e.label,
                type=e.evidence_type,
                direction=e.direction,
                severity=e.severity,
                snippet=e.snippet,
                weight=float(e.weight) if e.weight is not None else None,
            )
            for e in sorted(a.evidence_items, key=lambda e: e.sort_order)
        ],
        explanation=ExplanationOut(
            source=a.explanation_source,
            summary=a.summary,
            key_concerns=[KeyConcern(**c) for c in (a.key_concerns or [])],
            what_to_verify=list(a.what_to_verify or []),
        ),
        checklist=[
            ChecklistItemOut(id=c.id, code=c.code, text=c.text, priority=c.priority, done=c.is_done)
            for c in sorted(a.checklist_items, key=lambda c: (c.priority, c.id))
        ],
        entities=entities,
        connections=connections,
        report_count_approved=_approved_report_count(db, a.id),
    )
    if owner_token is not None:
        return AssessmentCreated(**fields, owner_token=owner_token)
    return AssessmentResult(**fields)


def get_assessment(db: Session, assessment_id: int, user: User | None, owner_token: str | None) -> AssessmentResult:
    """GET /assessments/{id}: open to anyone who knows the id; contact details only for the owner."""
    assessment = _load(db, assessment_id)
    return _build_result(db, assessment, is_owner=is_owner(assessment, user, owner_token))


# ==================================================================================
# list
# ==================================================================================
def list_assessments(db: Session, user: User, page: int, limit: int, risk_level: str | None) -> AssessmentPage:
    """GET /assessments: the caller's own assessments, newest first."""
    conditions = [Assessment.user_id == user.id]
    if risk_level is not None:
        conditions.append(Assessment.risk_level == risk_level)

    evidence_count = (
        select(func.count(EvidenceItem.id))
        .where(EvidenceItem.assessment_id == Assessment.id)
        .correlate(Assessment)
        .scalar_subquery()
    )
    approved_reports = (
        select(func.count(Report.id))
        .where(Report.assessment_id == Assessment.id, Report.status == "approved")
        .correlate(Assessment)
        .scalar_subquery()
    )

    total = db.scalar(select(func.count(Assessment.id)).where(*conditions)) or 0
    rows = db.execute(
        select(
            Assessment.id,
            Assessment.created_at,
            Listing.title,
            Listing.company_name,
            Assessment.risk_score,
            Assessment.risk_level,
            evidence_count.label("evidence_count"),
            approved_reports.label("report_count_approved"),
        )
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(*conditions)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    items = [
        AssessmentSummary(
            id=r.id,
            created_at=r.created_at,
            title=r.title,
            company_name=r.company_name,
            risk_score=round(float(r.risk_score), 4),
            risk_level=r.risk_level,
            evidence_count=r.evidence_count or 0,
            report_count_approved=r.report_count_approved or 0,
        )
        for r in rows
    ]
    return AssessmentPage(items=items, total=total, page=page, limit=limit)


# ==================================================================================
# delete
# ==================================================================================
def delete_assessment(db: Session, assessment_id: int, user: User | None, owner_token: str | None) -> None:
    """DELETE /assessments/{id}: owner only (404 unknown, 403 not the owner).

    Removes the assessment, its listing, evidence, checklist, signals and reports.
    The llm_calls log rows are kept with assessment_id set to NULL (Section 6).
    The children are deleted explicitly, in dependency order, so the result is the
    same whether or not the database enforces ON DELETE rules (MySQL does; the
    SQLite test database does not by default).
    """
    assessment = _load(db, assessment_id)
    if not is_owner(assessment, user, owner_token):
        raise forbidden("You do not own this assessment")

    aid, listing_id = assessment.id, assessment.listing_id
    try:
        db.execute(update(LlmCall).where(LlmCall.assessment_id == aid).values(assessment_id=None))
        for child in (EvidenceItem, AssessmentChecklistItem, EntitySignal, Report):
            db.execute(delete(child).where(child.assessment_id == aid))
        db.execute(delete(Assessment).where(Assessment.id == aid))
        db.execute(delete(Listing).where(Listing.id == listing_id))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Deleting an assessment failed: %s", describe_db_error(exc))
        raise AppError("internal_error", "Could not delete the assessment", 500) from None
    db.expunge_all()


# ==================================================================================
# checklist PATCH
# ==================================================================================
def update_checklist_item(
    db: Session,
    assessment_id: int,
    item_id: int,
    done: bool,
    user: User | None,
    owner_token: str | None,
) -> ChecklistPatchResult:
    """PATCH /assessments/{id}/checklist/{item_id} (B4).

    Order of checks (so nothing is revealed to a stranger):
      1. unknown assessment id                       -> 404
      2. caller is not the owner (JWT user or token) -> 403
      3. item does not exist OR belongs to another
         assessment                                  -> 404
    Sets is_done and done_at (UTC now, or NULL when un-ticked). Repeating the same
    value is allowed and changes nothing (done_at keeps the first tick time).
    """
    if not 1 <= assessment_id <= MAX_ID:
        raise not_found("Assessment not found")
    assessment = db.scalar(select(Assessment).where(Assessment.id == assessment_id))
    if assessment is None:
        raise not_found("Assessment not found")
    if not is_owner(assessment, user, owner_token):
        raise forbidden("You do not own this assessment")

    item = None
    if 1 <= item_id <= MAX_ID:
        item = db.scalar(
            select(AssessmentChecklistItem).where(
                AssessmentChecklistItem.id == item_id,
                AssessmentChecklistItem.assessment_id == assessment_id,  # item must belong to THIS assessment
            )
        )
    if item is None:
        raise not_found("Checklist item not found")

    if item.is_done != done:
        try:
            item.is_done = done
            item.done_at = datetime.now(UTC).replace(tzinfo=None) if done else None  # naive UTC, like the other columns
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Updating a checklist item failed: %s", describe_db_error(exc))
            raise AppError("internal_error", "Could not update the checklist item", 500) from None

    return ChecklistPatchResult(id=item.id, done=bool(item.is_done))
