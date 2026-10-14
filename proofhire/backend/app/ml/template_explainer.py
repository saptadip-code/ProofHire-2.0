"""Deterministic, network-free explanation (Member 1 / AI-ML). Guidebook A10 point 7: "the demo safety net".

build_template_explanation(risk_level, evidence, checklist_hints=None) -> Explanation(source="template", ...)

Same JSON shape as the LLM explanation: summary, key_concerns[{text, evidence_ids}], what_to_verify[str].

Inputs are ONLY what is supplied: the already-decided risk level, the evidence items (labels, snippets, ids) and the
checklist hint texts. Nothing about the employer is invented; the sentences around the labels are fixed wording.

Guarantees (tested):
  * pure function of its arguments: it receives only the already-decided level, so it cannot change the score or level;
  * every key_concerns[].evidence_ids entry is the id of an item in `evidence`;
  * a concern is built from observed, risk-increasing evidence (its label, plus the exact snippet when there is one),
    and at medium / high risk one pattern-level concern cites the model-derived, risk-increasing evidence;
  * what_to_verify is the supplied checklist hints; one fixed generic sentence is used only when no hint is supplied;
  * the language is cautious: it speaks of patterns and signals, never of a company being a scam or fraud.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from app.schemas.ml_schemas import EvidenceItem, Explanation, KeyConcern

MAX_CONCERNS = 5
MAX_MODEL_REFERENCES = 3
MAX_VERIFY_ITEMS = 5
MAX_SNIPPET_CHARS = 120
MAX_TEXT_CHARS = 300

SUMMARY = {
    "high": "This listing shows several patterns that are often linked to risky job offers. This is a risk estimate, "
            "not proof: verify the employer independently before sharing money or personal details.",
    "medium": "This listing mixes some warning signs with reassuring ones. This is a risk estimate, not a verdict: "
              "verify the employer before you share money or personal details.",
    "low": "This listing shows few of the patterns often linked to risky job offers. This is a risk estimate, not a "
           "verification of the employer: it is still sensible to check the company yourself.",
}
MODEL_CONCERN_PREFIX = "The model also found pattern signals in this listing: "
GENERIC_VERIFY = ("Check the employer through its official website and company registration records before you "
                  "share money or personal details.")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _tidy(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", _CONTROL.sub(" ", str(text))).strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _sentence(label: str) -> str:
    label = _tidy(label, 200).rstrip(" .")
    return label + "."


def observed_concern_text(item: EvidenceItem) -> str:
    """'<label>.' plus the exact listing snippet when the evidence has one."""
    text = _sentence(item.label)
    if item.snippet:
        text += ' The listing says: "' + _tidy(item.snippet, MAX_SNIPPET_CHARS) + '"'
    return _tidy(text, MAX_TEXT_CHARS)


def model_concern_text(items: list[EvidenceItem]) -> str:
    labels = "; ".join(_tidy(e.label, 90).rstrip(" .") for e in items)
    return _tidy(MODEL_CONCERN_PREFIX + labels + ".", MAX_TEXT_CHARS)


def build_template_explanation(
    risk_level, evidence: Iterable[EvidenceItem], checklist_hints: Optional[Iterable[str]] = None
) -> Explanation:
    """Template explanation for an already-decided `risk_level`, the assessment's `evidence` (ids E1..En) and the
    checklist hint texts (strings; pass [] / None when there are none)."""
    level = getattr(risk_level, "value", risk_level)
    items = list(evidence)

    concerns: list[KeyConcern] = []
    for e in items:
        if len(concerns) == MAX_CONCERNS:
            break
        if e.type.value == "observed" and e.direction.value == "increases_risk":
            concerns.append(KeyConcern(text=observed_concern_text(e), evidence_ids=[e.id]))
    if level in ("medium", "high"):
        model_items = [e for e in items if e.type.value == "model" and e.direction.value == "increases_risk"]
        if model_items and len(concerns) < MAX_CONCERNS:
            top = model_items[:MAX_MODEL_REFERENCES]
            concerns.append(KeyConcern(text=model_concern_text(top), evidence_ids=[e.id for e in top]))

    verify: list[str] = []
    for hint in checklist_hints or []:
        if isinstance(hint, str):
            h = _tidy(hint, MAX_TEXT_CHARS)
            if h and h not in verify:
                verify.append(h)
    if not verify:
        verify.append(GENERIC_VERIFY)
    return Explanation(source="template", summary=SUMMARY.get(level, SUMMARY["medium"]),
                       key_concerns=concerns, what_to_verify=verify[:MAX_VERIFY_ITEMS])


__all__ = ["build_template_explanation", "observed_concern_text", "model_concern_text", "SUMMARY", "GENERIC_VERIFY"]
