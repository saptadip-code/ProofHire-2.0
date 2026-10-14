"""Feature extraction shared by training and inference (Member 1 / AI-ML). Guidebook A4.

Single source of truth: ml/train.py (rows from the synthetic CSV) and the runtime pipeline (one
ListingInput) both call build_row() and text_of(). Nothing else may compute these features.

Runtime constraints (guidebook D5, A14): stdlib only here - NO pandas, numpy, scikit-learn or pydantic
imports. `listing` may be a pydantic ListingInput, any attribute object, or a plain mapping (a CSV row
with string values / empty strings is fine). Missing, None and "" are all treated as "not given".

Blank handling (no cleaning step, guidebook A3): salary 0 / empty means "not stated" -> salary features 0.

Runtime data files (both in backend/app/data, owned by Member 1, regenerated from ml/data/lexicons.py):
  role_benchmarks.json   SYNTHETIC development medians (INR per month). Not verified real salary data.
  lexicons_runtime.json  urgency phrases + fee / personal-data / guaranteed-claim / no-experience regexes.
"""
from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from app.ml.entities import FREE_MAIL_DOMAINS

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# ------------------------------------------------------------------ feature contract (A4)
NUM_COLS = [
    "salary_max_month_log", "salary_ratio_vs_role", "salary_spread", "desc_words", "req_words",
    "exclaim_count", "caps_ratio", "urgency_hits", "fee_amount_log",
]
BIN_COLS = [
    "has_upfront_fee", "asks_personal_data", "guaranteed_claim", "no_experience_hype", "email_is_free",
    "email_present", "website_missing", "domain_mismatch", "messaging_only", "no_interview",
    "vague_desc", "vague_requirements", "phone_present",
]
CAT_COLS = ["work_mode", "employment_type", "application_channel", "interview_mode"]
TEXT_COL = "text"  # TF-IDF input column; produced by text_of(), not by build_row()
# Order of the structured columns returned by build_row() (num, bin, cat as listed in the A4 table).
# The text column is separate (TEXT_COL). One-hot expansion of CAT_COLS is done by the sklearn pipeline.
FEATURE_ORDER = NUM_COLS + BIN_COLS + CAT_COLS

# Literal values from guidebook Section 5.1 (also the defaults used for missing/invalid input).
CAT_VALUES = {
    "work_mode": ["onsite", "remote", "hybrid"],
    "employment_type": ["internship", "full_time", "part_time", "contract"],
    "application_channel": ["email", "website_form", "whatsapp", "telegram", "phone", "linkedin_dm", "unknown"],
    "interview_mode": ["video_call", "in_person", "phone_call", "chat_only", "none"],
}
_PAY_PERIODS = ("month", "year", "one_time")
_DEFAULTS = {"work_mode": "onsite", "employment_type": "internship", "application_channel": "unknown",
             "interview_mode": "none", "pay_period": "month"}

# Caps / thresholds from A4.
RATIO_CAP, SPREAD_CAP, EXCLAIM_CAP = 20.0, 10.0, 15
MAX_DESCRIPTION_CHARS = 8000  # A14: truncate description to 8000 chars


# ------------------------------------------------------------------ runtime data
def _load_json(name: str) -> dict:
    path = _DATA_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # fail loudly: silently scoring without lexicons would be wrong
        raise FileNotFoundError(f"ML runtime data file missing: {path}") from exc


_LEX = _load_json("lexicons_runtime.json")
_BENCH = _load_json("role_benchmarks.json")

URGENCY_PHRASES = tuple(p.lower() for p in _LEX["urgency_phrases"])
_PATTERNS = {
    "fee": [re.compile(p, re.IGNORECASE) for p in _LEX["fee_patterns"]],
    "personal_data": [re.compile(p, re.IGNORECASE) for p in _LEX["personal_data_patterns"]],
    "guaranteed_claim": [re.compile(p, re.IGNORECASE) for p in _LEX["guaranteed_claim_patterns"]],
    "no_experience": [re.compile(p, re.IGNORECASE) for p in _LEX["no_experience_patterns"]],
}
_NEGATION = re.compile(_LEX["negation_pattern"], re.IGNORECASE)

_BENCH_DEFAULT = _BENCH["default"]
# Longest keyword first so specific keywords ("software developer") beat short ones ("sales", "seo").
_ROLE_KEYWORDS = sorted(
    ((kw.lower(), r["role"]) for r in _BENCH["roles"] for kw in r["keywords"]), key=lambda t: (-len(t[0]), t[0])
)
_ROLE_MEDIANS = {r["role"]: r["monthly_median_inr"] for r in _BENCH["roles"]}


# ------------------------------------------------------------------ tolerant input access
def _get(listing: Any, name: str) -> Any:
    if isinstance(listing, dict) or hasattr(listing, "keys"):
        try:
            return listing.get(name)
        except Exception:
            return None
    return getattr(listing, name, None)


def _str(v: Any) -> str:
    if v is None:
        return ""
    v = getattr(v, "value", v)  # Enum -> literal string
    return str(v).strip()


def _int(v: Any) -> int:
    """Tolerant non-negative int: None / "" / junk -> 0; '1,499' -> 1499; 1499.0 -> 1499."""
    s = _str(v).replace(",", "")
    if not s:
        return 0
    try:
        return max(int(float(s)), 0)
    except (ValueError, OverflowError):
        return 0


def _enum(v: Any, allowed, default: str) -> str:
    s = _str(v).lower()
    return s if s in allowed else default


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ text helpers
def _title(listing) -> str:
    return _str(_get(listing, "title"))


def _description(listing) -> str:
    return _str(_get(listing, "description"))[:MAX_DESCRIPTION_CHARS]


def _requirements(listing) -> str:
    return _str(_get(listing, "requirements"))


def raw_text_of(listing: Any) -> str:
    """title + description + requirements, whitespace-collapsed, ORIGINAL case.

    Regex rules (and evidence snippets in A-G4) run over this so snippets are exact spans from the listing.
    """
    return _collapse(" ".join([_title(listing), _description(listing), _requirements(listing)]))


def text_of(listing: Any) -> str:
    """TF-IDF input: title, company, description, requirements; lower-cased, whitespace collapsed (A4)."""
    parts = [_title(listing), _str(_get(listing, "company_name")), _description(listing), _requirements(listing)]
    return _collapse(" ".join(parts)).lower()


# ------------------------------------------------------------------ lexicon matching
def search_lexicon(name: str, text: str) -> Optional["re.Match[str]"]:
    """First (earliest) un-negated regex match for lexicon `name` in text, or None.

    name in {"fee", "personal_data", "guaranteed_claim", "no_experience"}. Matches directly preceded by a
    negation ("no registration fee", "never ... deposit") are ignored. The returned re.Match carries the
    exact span, used by evidence.py for snippets.
    """
    best = None
    for pat in _PATTERNS[name]:
        for m in pat.finditer(text):
            window = text[max(0, m.start() - 30): m.start()]
            if _NEGATION.search(window):
                continue
            if best is None or m.start() < best.start():
                best = m
            break  # earliest un-negated match for this pattern is enough
    return best


def urgency_matches(text: str) -> list[str]:
    """Distinct urgency-lexicon phrases present in text (case-insensitive), in lexicon order."""
    low = text.lower()
    return [p for p in URGENCY_PHRASES if p in low]


# ------------------------------------------------------------------ salary / role
def to_monthly(amount: int, pay_period: str) -> float:
    """Normalise a stated salary to monthly (decision D8). year -> /12. month and one_time are used as stated
    (a one_time payment has no period; it is compared to the monthly benchmark as-is)."""
    return amount / 12.0 if pay_period == "year" else float(amount)


def detect_role(title: str) -> str:
    """Role key from the title via role_benchmarks.json keywords; 'default' when nothing matches."""
    low = title.lower()
    for kw, role in _ROLE_KEYWORDS:
        if kw in low:
            return role
    return "default"


def benchmark(role: str, employment_type: str) -> float:
    """Monthly benchmark median (INR) for (role, employment_type). SYNTHETIC development numbers."""
    table = _ROLE_MEDIANS.get(role, _BENCH_DEFAULT)
    return float(table.get(employment_type) or _BENCH_DEFAULT.get(employment_type) or _BENCH_DEFAULT["internship"])


# ------------------------------------------------------------------ domains
def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[1].strip().lower() if "@" in email else ""


def _site_domain(url: str) -> str:
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url.strip(), flags=re.IGNORECASE)
    host = re.split(r"[/?#]", host, maxsplit=1)[0].rsplit("@", 1)[-1].split(":", 1)[0].lower()
    return host[4:] if host.startswith("www.") else host


# ------------------------------------------------------------------ the feature row
def build_row(listing: Any) -> "OrderedDict[str, Any]":
    """Structured features in FEATURE_ORDER (A4): 9 numeric floats, 13 binary ints (0/1), 4 categorical strings."""
    title, desc, req = _title(listing), _description(listing), _requirements(listing)
    raw = raw_text_of(listing)

    emp = _enum(_get(listing, "employment_type"), CAT_VALUES["employment_type"], _DEFAULTS["employment_type"])
    work_mode = _enum(_get(listing, "work_mode"), CAT_VALUES["work_mode"], _DEFAULTS["work_mode"])
    channel = _enum(_get(listing, "application_channel"), CAT_VALUES["application_channel"], _DEFAULTS["application_channel"])
    interview = _enum(_get(listing, "interview_mode"), CAT_VALUES["interview_mode"], _DEFAULTS["interview_mode"])
    period = _enum(_get(listing, "pay_period"), _PAY_PERIODS, _DEFAULTS["pay_period"])

    salary_max, salary_min = _int(_get(listing, "salary_max")), _int(_get(listing, "salary_min"))
    fee_amount = _int(_get(listing, "upfront_fee_amount"))
    monthly_max = to_monthly(salary_max, period) if salary_max > 0 else 0.0
    bench = benchmark(detect_role(title), emp)
    ratio = min(monthly_max / bench, RATIO_CAP) if monthly_max > 0 and bench > 0 else 0.0
    spread = min(salary_max / max(salary_min, 1), SPREAD_CAP) if salary_max > 0 else 0.0

    desc_words, req_words = len(desc.split()), len(req.split())
    exclaim = min(title.count("!") + desc.count("!") + req.count("!"), EXCLAIM_CAP)
    letters = [c for c in f"{title} {desc}" if c.isalpha()]
    caps_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0

    email = _str(_get(listing, "contact_email"))
    website = _str(_get(listing, "company_website"))
    phone = _str(_get(listing, "contact_phone"))
    e_dom, w_dom = _email_domain(email), _site_domain(website)
    email_free = int(bool(e_dom) and e_dom in FREE_MAIL_DOMAINS)

    row: "OrderedDict[str, Any]" = OrderedDict()
    row["salary_max_month_log"] = math.log1p(monthly_max)
    row["salary_ratio_vs_role"] = ratio
    row["salary_spread"] = spread
    row["desc_words"] = float(desc_words)
    row["req_words"] = float(req_words)
    row["exclaim_count"] = float(exclaim)
    row["caps_ratio"] = caps_ratio
    row["urgency_hits"] = float(len(urgency_matches(raw)))
    row["fee_amount_log"] = math.log1p(fee_amount)

    row["has_upfront_fee"] = int(fee_amount > 0 or search_lexicon("fee", raw) is not None)
    row["asks_personal_data"] = int(search_lexicon("personal_data", raw) is not None)
    row["guaranteed_claim"] = int(search_lexicon("guaranteed_claim", raw) is not None)
    row["no_experience_hype"] = int(search_lexicon("no_experience", raw) is not None and ratio > 2)
    row["email_is_free"] = email_free
    row["email_present"] = int(bool(email))
    row["website_missing"] = int(not website)
    row["domain_mismatch"] = int(bool(e_dom) and not email_free and bool(w_dom) and e_dom != w_dom)
    row["messaging_only"] = int(channel in ("whatsapp", "telegram"))
    row["no_interview"] = int(interview in ("none", "chat_only"))
    row["vague_desc"] = int(desc_words < 40)
    row["vague_requirements"] = int(req_words < 8)
    row["phone_present"] = int(bool(phone))

    row["work_mode"] = work_mode
    row["employment_type"] = emp
    row["application_channel"] = channel
    row["interview_mode"] = interview
    return row


def build_model_row(listing: Any) -> "OrderedDict[str, Any]":
    """build_row() plus the TEXT_COL ('text') column: one complete input row for the sklearn Pipeline."""
    row = build_row(listing)
    row[TEXT_COL] = text_of(listing)
    return row


# ------------------------------------------------------------------ model input contract (A-G3)
# Column order of ONE model input row = [TEXT_COL] + FEATURE_ORDER. The sklearn ColumnTransformer selects
# columns by POSITION in this list (not by name) so the same pipeline can be fed a plain numpy object array
# at inference without importing pandas (guidebook D5 / A14). Training and inference both use this list.
MODEL_INPUT_COLUMNS = [TEXT_COL] + FEATURE_ORDER


def model_input_values(listing: Any) -> list:
    """One model input row as a plain list, aligned with MODEL_INPUT_COLUMNS (text first, then FEATURE_ORDER)."""
    row = build_model_row(listing)
    return [row[c] for c in MODEL_INPUT_COLUMNS]


__all__ = [
    "NUM_COLS", "BIN_COLS", "CAT_COLS", "TEXT_COL", "FEATURE_ORDER", "CAT_VALUES",
    "MODEL_INPUT_COLUMNS", "model_input_values",
    "build_row", "build_model_row", "text_of", "raw_text_of", "search_lexicon", "urgency_matches",
    "to_monthly", "detect_role", "benchmark",
]
