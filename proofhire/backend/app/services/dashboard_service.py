"""Dashboard queries and the model-metrics reader (guidebook B4, D9, A12).

    get_summary(db, include_demo)   GET /dashboard/summary   (cached 30 s per include_demo)
    get_trends(db, days, include_demo)  GET /dashboard/trends  (cached 60 s per days+include_demo)
    load_model_metrics()            GET /dashboard/model-metrics

DEMO DATA (decision D9). Rows seeded by scripts/seed_demo.py have listings.is_synthetic_demo = 1.
With include_demo=false (the default) every number below leaves out assessments whose listing is a
demo row, and everything that hangs off them (their evidence, signals and reports). include_demo=true
adds them back and the summary says so in `data_scope`. Nothing is ever computed from demo rows
and shown as "real".

MODEL METRICS are never computed here. load_model_metrics() only reads the file Member 1 exports
(backend/app/ml/artifacts/metrics.json), checks that it has the documented structure (A11/A12) and
returns it unchanged plus model_version. A missing or invalid file is a 503, never a substitute.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Assessment, EntitySignal, EvidenceItem, Listing, LlmCall, Report
from app.schemas.dashboard import (
    DashboardSummary,
    LevelCounts,
    LlmStats,
    ReportCounts,
    TopEvidence,
    TrendPoint,
)

logger = logging.getLogger("proofhire.dashboard")

SUMMARY_TTL_SECONDS = 30  # B4
TRENDS_TTL_SECONDS = 60  # B4
TOP_EVIDENCE_LIMIT = 8  # B4: top 8

# --------------------------------------------------------------------------------------
# Where Member 1 exports the artifacts (guidebook A12, B4). Tests point these at a temp folder.
# --------------------------------------------------------------------------------------
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "ml" / "artifacts"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
MODEL_META_PATH = ARTIFACTS_DIR / "model_meta.json"
MAX_ARTIFACT_BYTES = 1_000_000  # real files are a few KB; anything bigger is not metrics.json


# ======================================================================================
# Tiny in-memory TTL cache (B4: "In-memory TTL cache 30 s, key includes include_demo")
# ======================================================================================
_cache: dict[tuple, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _clock() -> float:
    return time.monotonic()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cached(key: tuple, ttl: int, build):
    now = _clock()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
    value = build()  # computed outside the lock: a slow query must not block other requests
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def _today() -> date:
    """Today in UTC (all stored times are UTC). A function so tests can fix the date."""
    return datetime.now(UTC).date()


def _scope(include_demo: bool) -> list:
    """WHERE conditions on the joined `listings` row. `IS NOT 1` is also true for a NULL
    listing (an llm_calls row whose assessment was deleted), which is what we want."""
    return [] if include_demo else [Listing.is_synthetic_demo.is_not(True)]


# ======================================================================================
# GET /dashboard/summary
# ======================================================================================
def get_summary(db: Session, include_demo: bool) -> DashboardSummary:
    return _cached(("summary", include_demo), SUMMARY_TTL_SECONDS, lambda: _build_summary(db, include_demo))


def _build_summary(db: Session, include_demo: bool) -> DashboardSummary:
    scope = _scope(include_demo)

    # 1) total, by level, sum of scores, template explanations: one pass over assessments.
    level_rows = db.execute(
        select(
            Assessment.risk_level,
            func.count(Assessment.id),
            func.coalesce(func.sum(Assessment.risk_score), 0),
            func.coalesce(func.sum(case((Assessment.explanation_source == "template", 1), else_=0)), 0),
        )
        .select_from(Assessment)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(*scope)
        .group_by(Assessment.risk_level)
    ).all()
    by_level = {"low": 0, "medium": 0, "high": 0}
    total = 0
    score_sum = 0.0
    template_fallbacks = 0
    for level, n, s, t in level_rows:
        by_level[level] = int(n)
        total += int(n)
        score_sum += float(s)
        template_fallbacks += int(t)
    avg_score = round(score_sum / total, 4) if total else None

    # 2) top evidence: how often each (code, label) was shown, most frequent first.
    ev_rows = db.execute(
        select(EvidenceItem.code, EvidenceItem.label, func.count(EvidenceItem.id).label("n"))
        .select_from(EvidenceItem)
        .join(Assessment, Assessment.id == EvidenceItem.assessment_id)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(*scope)
        .group_by(EvidenceItem.code, EvidenceItem.label)
        .order_by(func.count(EvidenceItem.id).desc(), EvidenceItem.code, EvidenceItem.label)
        .limit(TOP_EVIDENCE_LIMIT)
    ).all()
    top_evidence = [TopEvidence(code=c, label=l, count=int(n)) for c, l, n in ev_rows]

    # 3) reports on in-scope assessments, by status.
    rep_rows = db.execute(
        select(Report.status, func.count(Report.id))
        .select_from(Report)
        .join(Assessment, Assessment.id == Report.assessment_id)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(*scope)
        .group_by(Report.status)
    ).all()
    rep = {"pending": 0, "approved": 0, "rejected": 0}
    for status, n in rep_rows:
        rep[status] = int(n)
    reports = ReportCounts(total=sum(rep.values()), **rep)

    # 4) connections_found: distinct (signal_type, signal_value) pairs that appear in 2+ different
    #    in-scope assessments (the repeat patterns the report page shows as "seen N times").
    repeated = (
        select(EntitySignal.signal_type, EntitySignal.signal_value)
        .select_from(EntitySignal)
        .join(Assessment, Assessment.id == EntitySignal.assessment_id)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(*scope)
        .group_by(EntitySignal.signal_type, EntitySignal.signal_value)
        .having(func.count(func.distinct(EntitySignal.assessment_id)) > 1)
        .subquery()
    )
    connections_found = int(db.scalar(select(func.count()).select_from(repeated)) or 0)

    # 5) LLM usage from llm_calls. Rows with provider 'template' are the built-in fallback, not an LLM
    #    call, so they are not counted as calls (they would make the success rate look perfect).
    #    Rows whose assessment was deleted (assessment_id NULL) are kept: the log outlives the assessment.
    calls, ok, latency_sum = db.execute(
        select(
            func.count(LlmCall.id),
            func.coalesce(func.sum(case((LlmCall.success.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(LlmCall.latency_ms), 0),
        )
        .select_from(LlmCall)
        .outerjoin(Assessment, Assessment.id == LlmCall.assessment_id)
        .outerjoin(Listing, Listing.id == Assessment.listing_id)
        .where(LlmCall.provider != "template", *scope)
    ).one()
    calls = int(calls)
    llm = LlmStats(
        calls=calls,
        success_rate=round(int(ok) / calls, 4) if calls else None,
        avg_latency_ms=round(float(latency_sum) / calls, 1) if calls else None,
        template_fallbacks=template_fallbacks,
    )

    return DashboardSummary(
        total_assessments=total,
        by_level=LevelCounts(**by_level),
        avg_risk_score=avg_score,
        top_evidence=top_evidence,
        reports=reports,
        connections_found=connections_found,
        llm=llm,
        data_scope="including_demo" if include_demo else "real_only",
    )


# ======================================================================================
# GET /dashboard/trends
# ======================================================================================
def get_trends(db: Session, days: int, include_demo: bool) -> list[TrendPoint]:
    return _cached(("trends", days, include_demo), TRENDS_TTL_SECONDS, lambda: _build_trends(db, days, include_demo))


def _build_trends(db: Session, days: int, include_demo: bool) -> list[TrendPoint]:
    """One point per day for the last `days` days, today included, oldest first, zero-filled."""
    today = _today()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, datetime.min.time())  # naive UTC, like created_at
    end = datetime.combine(today + timedelta(days=1), datetime.min.time())

    day = func.date(Assessment.created_at)
    rows = db.execute(
        select(day, Assessment.risk_level, func.count(Assessment.id))
        .select_from(Assessment)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(Assessment.created_at >= start, Assessment.created_at < end, *_scope(include_demo))
        .group_by(day, Assessment.risk_level)
    ).all()

    # MySQL returns a date object, SQLite a string: str() gives YYYY-MM-DD for both.
    buckets = {(first_day + timedelta(days=i)).isoformat(): {"low": 0, "medium": 0, "high": 0} for i in range(days)}
    for d, level, n in rows:
        bucket = buckets.get(str(d))
        if bucket is not None:
            bucket[level] = int(n)
    return [
        TrendPoint(date=d, count=b["low"] + b["medium"] + b["high"], high=b["high"], medium=b["medium"], low=b["low"])
        for d, b in buckets.items()
    ]


# ======================================================================================
# GET /dashboard/model-metrics
# ======================================================================================
_NUMBER_KEYS = ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier")  # synthetic_test (A11)
_OBJECT_KEYS = ("synthetic_test", "baselines", "pattern_holdout", "handwritten", "cv")  # A11


def _unavailable(reason: str) -> AppError:
    # 503 model_unavailable: the artifact the dashboard depends on is not usable. The message names
    # the file and the problem, never the path on the server or any content of the file.
    return AppError("model_unavailable", f"Model metrics are not available: {reason}", 503)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class _TooLarge(ValueError):
    """The file is bigger than any real metrics.json."""


def _reject_constant(name: str):
    raise ValueError(f"non-finite number {name}")


def _check_structure(data: object) -> str | None:
    """Return a short problem description, or None if `data` has the documented metrics.json shape."""
    if not isinstance(data, dict):
        return "the top level must be a JSON object"
    missing = [k for k in (*_OBJECT_KEYS, "limitations") if k not in data]
    if missing:
        return "missing key(s): " + ", ".join(missing)
    wrong = [k for k in _OBJECT_KEYS if not isinstance(data[k], dict)]
    if wrong:
        return "these must be JSON objects: " + ", ".join(wrong)
    if not isinstance(data["limitations"], list) or not all(isinstance(x, str) for x in data["limitations"]):
        return "limitations must be a list of strings"
    test = data["synthetic_test"]
    missing = [k for k in (*_NUMBER_KEYS, "confusion") if k not in test]
    if missing:
        return "synthetic_test is missing: " + ", ".join(missing)
    bad = [k for k in _NUMBER_KEYS if not _is_number(test[k])]
    if bad:
        return "synthetic_test values must be finite numbers: " + ", ".join(bad)
    conf = test["confusion"]
    if not (
        isinstance(conf, list)
        and len(conf) == 2
        and all(isinstance(r, list) and len(r) == 2 and all(_is_number(x) for x in r) for r in conf)
    ):
        return "synthetic_test.confusion must be [[tn, fp], [fn, tp]]"
    return None


def _read_json(path: Path) -> object:
    """Read a small JSON file. Raises FileNotFoundError, or ValueError for anything unusable."""
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise _TooLarge("file too large")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _model_version() -> str | None:
    """model_version from model_meta.json (A12). None if that file is absent or unusable: it is logged,
    and the metrics are still returned, because the numbers themselves are real."""
    try:
        meta = _read_json(MODEL_META_PATH)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        logger.warning("model_meta.json could not be read (%s): model_version will be null", type(exc).__name__)
        return None
    version = meta.get("model_version") if isinstance(meta, dict) else None
    return version if isinstance(version, str) and version else None


def load_model_metrics() -> dict:
    """Contents of metrics.json plus model_version. Never recomputes or invents a number."""
    try:
        data = _read_json(METRICS_PATH)
    except FileNotFoundError:
        logger.warning("metrics.json not found (the AI/ML artifacts are not installed yet)")
        raise _unavailable("metrics.json was not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("metrics.json could not be read: %s", type(exc).__name__)
        raise _unavailable("metrics.json could not be read") from None
    except _TooLarge:
        logger.error("metrics.json is larger than %s bytes", MAX_ARTIFACT_BYTES)
        raise _unavailable("metrics.json is too large to be a metrics file") from None
    except ValueError as exc:  # includes json.JSONDecodeError
        logger.error("metrics.json is not valid JSON: %s", type(exc).__name__)
        raise _unavailable("metrics.json is not valid JSON") from None

    problem = _check_structure(data)
    if problem is not None:
        logger.error("metrics.json does not match the documented structure: %s", problem)
        raise _unavailable(f"metrics.json does not have the expected structure ({problem})")

    version = _model_version()
    if version is None and isinstance(data.get("model_version"), str):
        version = data["model_version"]
    return {**data, "model_version": version}
