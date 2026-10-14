"""Repeat-pattern connections and masking (guidebook B6).

For an assessment A and each of its entity signals (type, value): count the
OTHER assessments B that carry the same (type, value). A connection is returned
only when at least one such assessment exists:

    times_seen       = count + 1                 (A itself plus the others)
    high_risk_count  = how many of the others have risk_level 'high'

Seeded demo rows (listings.is_synthetic_demo = 1) are not counted unless
include_demo is true. The query uses the composite index idx_signal.
"""

from __future__ import annotations

import re

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from app.db.models import Assessment, EntitySignal, Listing


def mask_email(value: str) -> str:
    """h***@gmail.com : first character, ***@, then the domain."""
    local, sep, domain = value.partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def mask_phone(value: str) -> str:
    """******1234 : digits only, everything but the last four hidden."""
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_signal_value(signal_type: str, value: str) -> str:
    """B6: emails and phones are masked; domains and company names are not."""
    if signal_type == "email":
        return mask_email(value)
    if signal_type == "phone":
        return mask_phone(value)
    return value


def compute_connections(
    db: Session,
    assessment_id: int,
    signals: list[tuple[str, str]],
    *,
    include_demo: bool = False,
) -> list[dict]:
    """Return [{signal_type, value_masked, times_seen, high_risk_count}] (B6)."""
    connections: list[dict] = []
    for signal_type, value in signals:
        stmt = (
            select(
                func.count(distinct(Assessment.id)),
                # CASE (not FILTER): MySQL 8.4 does not support aggregate FILTER (WHERE ...).
                func.count(distinct(case((Assessment.risk_level == "high", Assessment.id), else_=None))),
            )
            .select_from(EntitySignal)
            .join(Assessment, Assessment.id == EntitySignal.assessment_id)
            .join(Listing, Listing.id == Assessment.listing_id)
            .where(
                EntitySignal.signal_type == signal_type,
                EntitySignal.signal_value == value,
                EntitySignal.assessment_id != assessment_id,
            )
        )
        if not include_demo:
            stmt = stmt.where(Listing.is_synthetic_demo == False)  # noqa: E712 - SQL comparison
        others, high = db.execute(stmt).one()
        if others >= 1:
            connections.append(
                {
                    "signal_type": signal_type,
                    "value_masked": mask_signal_value(signal_type, value),
                    "times_seen": others + 1,
                    "high_risk_count": high,
                }
            )
    return connections
