"""Evidence engine (Member 1 / AI-ML). Guidebook A7.

build_evidence(listing, features, model) -> list[EvidenceItem]

Two kinds of evidence, always labelled by `type`:

  observed  deterministic rules over the submitted fields / text (17 codes, table below). `weight` is ALWAYS null.
            `snippet` is an exact contiguous span of the submitted title / description / requirements (or the exact
            submitted contact email for the email rules), at most 120 characters, taken from a regex match span.
            When the evidence comes from an absent / numeric / enum field there is no text to quote and the snippet
            is null - a snippet is never composed, paraphrased or invented.
  model     the top 5 positive and top 2 negative contributions `coef_i * x_i` of the production M3 pipeline
            (x_i = the value AFTER the fitted ColumnTransformer: TF-IDF weight, scaled number, 0/1 flag or one-hot).
            Codes MODEL_TERM (TF-IDF n-gram) / MODEL_FEATURE (structured feature), severity 2, weight = contribution
            rounded to 4 decimals (the intercept is not a contribution). Labels say 'wording' / 'signal': they
            describe how the model scored the TEXT, never a fact about the employer.

Order: observed by severity descending (stable, in A7 table order), then model by weight descending (positive
contributions first, then negative). Ids E1..En are assigned AFTER ordering, per assessment. Maximum 12 items.
If observed + model exceed 12 the tail (lowest-weight model items) is dropped; observed items are never dropped
in favour of model items.

`features` is the dict returned by features.build_row(listing) (the same one training used), so rules and model
agree on every derived value. `model` is the fitted sklearn Pipeline (ColumnTransformer 'prep' + LogisticRegression
last); with model=None only observed evidence is returned. numpy / scikit-learn are imported lazily, only for the
model part.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from app.ml import features as F
from app.ml.entities import FREE_MAIL_DOMAINS, email_domain_of, normalize_email, website_domain
from app.schemas.ml_schemas import EvidenceItem

log = logging.getLogger("proofhire.ml")

MAX_EVIDENCE_ITEMS = 12
MAX_SNIPPET_CHARS = 120
TOP_POSITIVE_CONTRIBUTIONS = 5
TOP_NEGATIVE_CONTRIBUTIONS = 2
MODEL_SEVERITY = 2

# (code, severity, direction, label) in the exact order of the guidebook A7 table.
_UP, _DOWN = "increases_risk", "decreases_risk"
OBSERVED_RULES: tuple[tuple[str, int, str, str], ...] = (
    ("UPFRONT_FEE", 3, _UP, "Asks the applicant to pay money"),
    ("PERSONAL_DATA_REQUEST", 3, _UP, "Asks for sensitive personal or financial details"),
    ("GUARANTEED_OFFER_CLAIM", 2, _UP, "Promises a guaranteed job or placement"),
    ("UNREALISTIC_PAY", 3, _UP, "Stated pay is far above the usual range for this kind of role"),
    ("FREE_EMAIL_CONTACT", 2, _UP, "Contact email is a free-mail address, not a company address"),
    ("EMAIL_DOMAIN_MISMATCH", 2, _UP, "Contact email domain differs from the company website domain"),
    ("NO_COMPANY_WEBSITE", 1, _UP, "No company website is given"),
    ("MESSAGING_APP_ONLY", 2, _UP, "Applications are handled only through a messaging app"),
    ("URGENCY_PRESSURE", 1, _UP, "Uses urgency or pressure wording"),
    ("NO_INTERVIEW", 2, _UP, "No real interview step (none or chat only)"),
    ("VAGUE_DESCRIPTION", 1, _UP, "The job description is very short"),
    ("VAGUE_REQUIREMENTS", 1, _UP, "Few or no requirements are stated"),
    ("EXCESSIVE_HYPE", 1, _UP, "Many exclamation marks or capital letters"),
    ("CORP_EMAIL_MATCHES_WEBSITE", 1, _DOWN, "Company email domain matches the company website domain"),
    ("DETAILED_REQUIREMENTS", 1, _DOWN, "Detailed requirements are listed"),
    ("STRUCTURED_INTERVIEW", 1, _DOWN, "A video, in-person or phone interview is offered"),
    ("PAY_IN_EXPECTED_RANGE", 1, _DOWN, "Stated pay is within the expected range for this kind of role"),
)
OBSERVED_CODES: tuple[str, ...] = tuple(r[0] for r in OBSERVED_RULES)
MODEL_CODES: tuple[str, ...] = ("MODEL_TERM", "MODEL_FEATURE")
# All codes a checklist trigger may use: the 17 observed codes + the model row of the A7 table (2 codes).
ALL_EVIDENCE_CODES: tuple[str, ...] = OBSERVED_CODES + MODEL_CODES
EVIDENCE_CATALOG: dict[str, tuple[int, str, str]] = {c: (s, d, label) for c, s, d, label in OBSERVED_RULES}

# Human wording for structured model features (label = "Model signal: <phrase>").
FEATURE_PHRASES = {
    "salary_max_month_log": "stated monthly pay level",
    "salary_ratio_vs_role": "pay compared with the role benchmark",
    "salary_spread": "gap between minimum and maximum pay",
    "desc_words": "length of the description",
    "req_words": "length of the requirements",
    "exclaim_count": "number of exclamation marks",
    "caps_ratio": "share of capital letters",
    "urgency_hits": "urgency wording",
    "fee_amount_log": "size of the upfront fee",
    "has_upfront_fee": "an upfront fee is mentioned or requested",
    "asks_personal_data": "sensitive personal data is requested",
    "guaranteed_claim": "a guaranteed job or placement is claimed",
    "no_experience_hype": "'no experience needed' together with high pay",
    "email_is_free": "contact email is a free-mail address",
    "email_present": "a contact email is given",
    "website_missing": "no company website",
    "domain_mismatch": "email domain differs from the website domain",
    "messaging_only": "applications only via a messaging app",
    "no_interview": "no real interview step",
    "vague_desc": "very short description",
    "vague_requirements": "few stated requirements",
    "phone_present": "a contact phone is given",
}
CATEGORY_PHRASES = {
    "work_mode": "work mode",
    "employment_type": "employment type",
    "application_channel": "application channel",
    "interview_mode": "interview mode",
}


class ModelEvidenceError(RuntimeError):
    """The fitted pipeline does not have the structure model evidence needs (not an M3-style pipeline)."""


# ------------------------------------------------------------------ text access / snippets
def _text_fields(listing: Any) -> list[str]:
    """Submitted free-text fields in the order the rules read them: title, description, requirements."""
    out = []
    for name in ("title", "description", "requirements"):
        value = listing.get(name) if (isinstance(listing, Mapping) or hasattr(listing, "keys")) else getattr(listing, name, None)
        out.append("" if value is None else str(getattr(value, "value", value)).strip())
    out[1] = out[1][: F.MAX_DESCRIPTION_CHARS]  # the same truncation features.py applies
    return out


def _clip(text: str) -> str:
    return text[:MAX_SNIPPET_CHARS]


_AMOUNT_AFTER = re.compile(r"\s*(?:of|:|-|–)?\s*(?:rs\.?|inr|₹)\s*[\d,]+(?:\.\d+)?", re.IGNORECASE)


def _lexicon_snippet(name: str, fields: list[str], extend_amount: bool = False) -> Optional[str]:
    """Exact span of the first un-negated lexicon match (title, then description, then requirements)."""
    for text in fields:
        if not text:
            continue
        m = F.search_lexicon(name, text)
        if m is None:
            continue
        end = m.end()
        if extend_amount and (tail := _AMOUNT_AFTER.match(text, end)):
            end = tail.end()  # 'registration fee of Rs 1,499' (still one contiguous span of the listing)
        return _clip(text[m.start():end])
    return None


def _urgency_snippet(fields: list[str]) -> Optional[str]:
    best: Optional[tuple[int, int, str]] = None  # (field index, start, span)
    for i, text in enumerate(fields):
        for phrase in F.URGENCY_PHRASES:
            m = re.search(re.escape(phrase), text, re.IGNORECASE)
            if m and (best is None or (i, m.start()) < (best[0], best[1])):
                best = (i, m.start(), text[m.start():m.end()])
        if best is not None and best[0] == i:
            break  # earliest field with a hit wins
    return _clip(best[2]) if best else None


_EXCLAIM_SPAN = re.compile(r"[^.!?\n]{0,80}!+")
_CAPS_RUN = re.compile(r"\b[A-Z]{2,}(?:[ \t]+[A-Z]{2,}\b)+")


def _hype_snippet(fields: list[str], exclaim_hit: bool) -> Optional[str]:
    if exclaim_hit:
        for text in fields:
            if (m := _EXCLAIM_SPAN.search(text)) is not None:
                return _clip(m.group().lstrip())
    for text in fields[:2]:  # caps_ratio is computed over title + description only (A4)
        if (m := _CAPS_RUN.search(text)) is not None:
            return _clip(m.group())
    return None


# ------------------------------------------------------------------ observed evidence
def _num(features: Mapping[str, Any], key: str) -> float:
    try:
        return float(features.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _observed_drafts(listing: Any, features: Mapping[str, Any]) -> list[dict]:
    """Rules in A7 table order -> drafts (no id yet). Decisions come from `features`, the training features."""
    fields = _text_fields(listing)
    get = (lambda n: listing.get(n)) if (isinstance(listing, Mapping) or hasattr(listing, "keys")) \
        else (lambda n: getattr(listing, n, None))
    email_raw = str(get("contact_email") or "").strip()  # exact submitted value: this is what a snippet may quote
    email = normalize_email(email_raw)  # lower-cased: used ONLY for domain decisions, never quoted
    e_dom = email_domain_of(email)
    email_quote = email_raw if email else None
    w_dom = website_domain(str(get("company_website") or ""))

    ratio = _num(features, "salary_ratio_vs_role")
    exclaim_hit = _num(features, "exclaim_count") >= 4
    interview = str(features.get("interview_mode") or "")

    hits: dict[str, tuple[bool, Optional[str]]] = {
        "UPFRONT_FEE": (bool(features.get("has_upfront_fee")), None),
        "PERSONAL_DATA_REQUEST": (bool(features.get("asks_personal_data")), None),
        "GUARANTEED_OFFER_CLAIM": (bool(features.get("guaranteed_claim")), None),
        "UNREALISTIC_PAY": (ratio >= 3, None),
        "FREE_EMAIL_CONTACT": (bool(features.get("email_is_free")), email_quote),
        "EMAIL_DOMAIN_MISMATCH": (bool(features.get("domain_mismatch")), email_quote),
        "NO_COMPANY_WEBSITE": (bool(features.get("website_missing")), None),
        "MESSAGING_APP_ONLY": (bool(features.get("messaging_only")), None),
        "URGENCY_PRESSURE": (_num(features, "urgency_hits") >= 2, None),
        "NO_INTERVIEW": (bool(features.get("no_interview")), None),
        "VAGUE_DESCRIPTION": (_num(features, "desc_words") < 40, None),
        "VAGUE_REQUIREMENTS": (_num(features, "req_words") < 8, None),
        "EXCESSIVE_HYPE": (exclaim_hit or _num(features, "caps_ratio") > 0.25, None),
        "CORP_EMAIL_MATCHES_WEBSITE": (bool(e_dom) and e_dom not in FREE_MAIL_DOMAINS and bool(w_dom) and e_dom == w_dom,
                                       email_quote),
        "DETAILED_REQUIREMENTS": (_num(features, "req_words") >= 25, None),
        "STRUCTURED_INTERVIEW": (interview in ("video_call", "in_person", "phone_call"), None),
        "PAY_IN_EXPECTED_RANGE": (0.5 <= ratio <= 1.8, None),
    }
    # Text-derived snippets (exact spans of the submitted text), only computed for rules that fired.
    text_snippets = {
        "UPFRONT_FEE": lambda: _lexicon_snippet("fee", fields, extend_amount=True),
        "PERSONAL_DATA_REQUEST": lambda: _lexicon_snippet("personal_data", fields),
        "GUARANTEED_OFFER_CLAIM": lambda: _lexicon_snippet("guaranteed_claim", fields),
        "URGENCY_PRESSURE": lambda: _urgency_snippet(fields),
        "EXCESSIVE_HYPE": lambda: _hype_snippet(fields, exclaim_hit),
    }

    drafts = []
    for code, severity, direction, label in OBSERVED_RULES:
        fired, snippet = hits[code]
        if not fired:
            continue
        if code in text_snippets:
            snippet = text_snippets[code]()
        drafts.append({"code": code, "label": label, "type": "observed", "direction": direction,
                       "severity": severity, "snippet": snippet, "weight": None})
    drafts.sort(key=lambda d: -d["severity"])  # stable: ties keep A7 table order
    return drafts


# ------------------------------------------------------------------ model evidence
class Contribution:
    """One model input column's contribution `coef * x` (logit scale). kind: 'term' | 'feature'."""

    __slots__ = ("kind", "name", "category", "value")

    def __init__(self, kind: str, name: str, category: Optional[str], value: float):
        self.kind, self.name, self.category, self.value = kind, name, category, value

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Contribution({self.kind}, {self.name!r}, {self.category!r}, {self.value:.4f})"


_INDEX_SLOT: Optional[tuple[Any, list[tuple[str, str, Optional[str]]]]] = None  # (model, column entries)


def _column_entries(model: Any) -> list[tuple[str, str, Optional[str]]]:
    """(kind, name, category) for every output column of the fitted ColumnTransformer, in output order."""
    global _INDEX_SLOT
    slot = _INDEX_SLOT
    if slot is not None and slot[0] is model:
        return slot[1]
    try:
        prep, clf = model.steps[0][1], model.steps[-1][1]
        transformers = prep.transformers_
        n_coef = clf.coef_.shape[1]
    except (AttributeError, IndexError, TypeError) as exc:
        raise ModelEvidenceError(f"model is not a ColumnTransformer + linear classifier pipeline: {exc}") from exc

    entries: list[tuple[str, str, Optional[str]]] = []
    for name, trans, cols in transformers:
        if name == "remainder" and trans == "drop":
            continue
        if name == "tfidf":
            entries += [("term", str(t), None) for t in trans.get_feature_names_out()]
        elif name in ("num", "bin"):
            entries += [("feature", F.MODEL_INPUT_COLUMNS[c], None) for c in cols]
        elif name == "cat":
            for c, categories in zip(cols, trans.categories_):
                entries += [("feature", F.MODEL_INPUT_COLUMNS[c], str(cat)) for cat in categories]
        else:
            raise ModelEvidenceError(f"unexpected ColumnTransformer step {name!r}")
    if len(entries) != n_coef:
        raise ModelEvidenceError(f"column map has {len(entries)} entries but the classifier has {n_coef} coefficients")
    _INDEX_SLOT = (model, entries)
    return entries


def model_contributions(listing: Any, features: Mapping[str, Any], model: Any) -> list[Contribution]:
    """All non-zero contributions coef_i * x_i for this listing (excluding the intercept).

    sum(contributions) + intercept_ is the model's logit, so sigmoid of it equals the reported risk_score.
    """
    import numpy as np

    entries = _column_entries(model)
    prep, clf = model.steps[0][1], model.steps[-1][1]
    row = [F.text_of(listing)] + [features[c] for c in F.FEATURE_ORDER]
    transformed = prep.transform(np.array([row], dtype=object))
    x = transformed.toarray()[0] if hasattr(transformed, "toarray") else np.asarray(transformed)[0]
    contrib = x * clf.coef_[0]
    out = []
    for i in np.flatnonzero(contrib):
        kind, name, category = entries[int(i)]
        out.append(Contribution(kind, name, category, float(contrib[i])))
    return out


def _model_label(c: Contribution, direction: str) -> str:
    if c.kind == "term":
        who = "risky" if direction == _UP else "legitimate"
        return f"Wording often seen in {who} listings: '{c.name}'"
    if c.category is not None:
        return f"Model signal: {CATEGORY_PHRASES.get(c.name, c.name)} is {c.category.replace('_', ' ')}"
    return f"Model signal: {FEATURE_PHRASES.get(c.name, c.name.replace('_', ' '))}"


def _model_drafts(listing: Any, features: Mapping[str, Any], model: Any) -> list[dict]:
    rounded = [(round(c.value, 4), c) for c in model_contributions(listing, features, model)]
    pos = sorted(((w, c) for w, c in rounded if w > 0), key=lambda t: -t[0])[:TOP_POSITIVE_CONTRIBUTIONS]
    neg = sorted(((w, c) for w, c in rounded if w < 0), key=lambda t: t[0])[:TOP_NEGATIVE_CONTRIBUTIONS]
    drafts = []
    for weight, c in pos + sorted(neg, key=lambda t: -t[0]):  # weight descending overall
        direction = _UP if weight > 0 else _DOWN
        drafts.append({"code": "MODEL_TERM" if c.kind == "term" else "MODEL_FEATURE",
                       "label": _model_label(c, direction), "type": "model", "direction": direction,
                       "severity": MODEL_SEVERITY, "snippet": None, "weight": weight})
    return drafts


# ------------------------------------------------------------------ public contract (A7)
def build_evidence(listing: Any, features: Optional[Mapping[str, Any]] = None, model: Any = None) -> list[EvidenceItem]:
    """Observed evidence (severity desc) then model evidence (weight desc); ids E1..En; at most 12 items.

    `features` defaults to features.build_row(listing). With model=None only observed evidence is produced.
    A model whose structure cannot be explained is logged at ERROR and skipped (observed evidence is still
    returned); nothing is invented in its place.
    """
    feats = features if features is not None else F.build_row(listing)
    drafts = _observed_drafts(listing, feats)
    if model is not None:
        try:
            drafts += _model_drafts(listing, feats, model)
        except Exception:  # noqa: BLE001 - never fail an assessment because evidence could not be explained
            log.exception("model-derived evidence skipped: could not compute coefficient contributions")
    return [EvidenceItem(id=f"E{i}", **d) for i, d in enumerate(drafts[:MAX_EVIDENCE_ITEMS], start=1)]


__all__ = [
    "build_evidence", "model_contributions", "Contribution", "ModelEvidenceError", "OBSERVED_RULES",
    "OBSERVED_CODES", "MODEL_CODES", "ALL_EVIDENCE_CODES", "EVIDENCE_CATALOG", "MAX_EVIDENCE_ITEMS",
]
