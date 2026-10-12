"""Verification checklist builder (Member 1 / AI-ML). Guidebook A8.

build_checklist(evidence) -> list[ChecklistItem]

The checklist CONTENT lives in backend/app/data/checklist_library.json, owned by Member 4. This module only READS it
(never creates, edits or ships a copy). Each library item: {code, text (<= 500 chars), priority 1-3, triggers[]},
where triggers are evidence codes from the A7 table (observed codes + MODEL_TERM / MODEL_FEATURE) or "*".

Selection (A8):
  * an item matches when any of its triggers is the code of an evidence item in this assessment;
  * "*" items are always-on; at most 4 always-on items are kept (lowest priority number first, then library order);
  * duplicates by `code` are removed (first library entry wins);
  * triggers that are not A7 evidence codes are reported by library_status() (item kept, status 'partial');
  * sorted by priority (1 first); at equal priority items triggered by evidence come before always-on items, then
    library order; at most 10 items are returned.
Items are returned WITHOUT ids (ChecklistItem{code, text, priority, done=false}); the backend stores them.

Missing / broken library (local development): NOTHING is invented. The builder logs ONE error per file state and
returns an empty list; library_status() reports {"status": "missing" | "invalid" | "partial" | "ok", ...} so the
integration problem stays visible instead of being papered over with substitute content. Library files are re-read
automatically when their modification time changes (so Member 4's edits show up without a restart).
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from app.ml.evidence import ALL_EVIDENCE_CODES
from app.schemas.ml_schemas import ChecklistItem

log = logging.getLogger("proofhire.ml")

LIBRARY_PATH = Path(__file__).resolve().parents[1] / "data" / "checklist_library.json"
MAX_CHECKLIST_ITEMS = 10
MAX_ALWAYS_ON_ITEMS = 4
MAX_TEXT_CHARS = 500
ALWAYS_ON = "*"


@dataclass(frozen=True)
class LibraryItem:
    code: str
    text: str
    priority: int
    triggers: tuple[str, ...]
    order: int  # position in the library file (tie-breaker)


@dataclass(frozen=True)
class Library:
    path: str
    status: str  # ok | partial | invalid | missing
    items: tuple[LibraryItem, ...] = ()
    problems: tuple[str, ...] = field(default_factory=tuple)


_LOCK = threading.Lock()
_CACHE: dict[str, tuple[Optional[float], Library]] = {}  # path -> (mtime or None when missing, library)


def _parse(raw: Any, path: str) -> Library:
    if not isinstance(raw, list):
        return Library(path, "invalid", (), ("top-level JSON value must be a list of items",))
    items: list[LibraryItem] = []
    problems: list[str] = []
    seen: set[str] = set()
    for idx, entry in enumerate(raw):
        where = f"item #{idx}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        code, text, priority, triggers = (entry.get(k) for k in ("code", "text", "priority", "triggers"))
        if not (isinstance(code, str) and code.strip()):
            problems.append(f"{where}: missing code")
            continue
        where = f"item {code!r}"
        if not (isinstance(text, str) and text.strip()) or len(text) > MAX_TEXT_CHARS:
            problems.append(f"{where}: text must be 1-{MAX_TEXT_CHARS} characters")
            continue
        if isinstance(priority, bool) or priority not in (1, 2, 3):
            problems.append(f"{where}: priority must be 1, 2 or 3")
            continue
        if not (isinstance(triggers, list) and triggers and all(isinstance(t, str) and t for t in triggers)):
            problems.append(f"{where}: triggers must be a non-empty list of strings")
            continue
        if code in seen:
            problems.append(f"{where}: duplicate code ignored (first entry wins)")
            continue
        unknown = [t for t in triggers if t != ALWAYS_ON and t not in ALL_EVIDENCE_CODES]
        if unknown:  # kept (it can still be always-on / partly triggerable) but reported: a typo never fires
            problems.append(f"{where}: unknown trigger code(s) {unknown} (not in guidebook A7); item kept")
        seen.add(code)
        items.append(LibraryItem(code, text, int(priority), tuple(triggers), idx))
    status = "ok" if not problems else ("partial" if items else "invalid")
    return Library(path, status, tuple(items), tuple(problems))


def load_library(path: Optional[Path] = None) -> Library:
    """Read (and cache by modification time) the checklist library. Never raises."""
    p = Path(path) if path is not None else LIBRARY_PATH
    key = str(p)
    try:
        mtime: Optional[float] = p.stat().st_mtime
    except OSError:
        mtime = None
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]

    if mtime is None:
        lib = Library(key, "missing", (), (f"file not found: {p}",))
        log.error("checklist library MISSING (%s): checklists will be empty until Member 4 delivers it", p)
    else:
        try:
            lib = _parse(json.loads(p.read_text(encoding="utf-8")), key)
        except (OSError, ValueError) as exc:
            lib = Library(key, "invalid", (), (f"unreadable JSON ({exc.__class__.__name__}): {exc}",))
        if lib.status != "ok":
            log.error("checklist library %s (%s): %s", lib.status.upper(), p, "; ".join(lib.problems))
    with _LOCK:
        _CACHE[key] = (mtime, lib)
    return lib


def library_status(path: Optional[Path] = None) -> dict:
    """{'status', 'path', 'items', 'problems'} for diagnostics / health checks (not part of the HTTP contract)."""
    lib = load_library(path)
    return {"status": lib.status, "path": lib.path, "items": len(lib.items), "problems": list(lib.problems)}


def clear_cache() -> None:
    """Forget cached libraries (used by reload_model() and tests)."""
    with _LOCK:
        _CACHE.clear()


def _codes(evidence: Iterable[Any]) -> set[str]:
    codes = set()
    for e in evidence or ():
        code = e if isinstance(e, str) else getattr(e, "code", None)
        if isinstance(code, str) and code:
            codes.add(code)
    return codes


def build_checklist(evidence: Iterable[Any], library_path: Optional[Path] = None) -> list[ChecklistItem]:
    """Select checklist items for the evidence codes of one assessment (see module docstring for the rules)."""
    lib = load_library(library_path)
    if not lib.items:
        return []
    codes = _codes(evidence)

    triggered = [i for i in lib.items if any(t != ALWAYS_ON and t in codes for t in i.triggers)]
    always_pool = sorted((i for i in lib.items if ALWAYS_ON in i.triggers), key=lambda i: (i.priority, i.order))
    always = always_pool[:MAX_ALWAYS_ON_ITEMS]

    chosen: dict[str, tuple[int, int, int, LibraryItem]] = {}
    for item in triggered:
        chosen[item.code] = (item.priority, 0, item.order, item)  # 0: evidence-triggered sorts before always-on
    for item in always:
        chosen.setdefault(item.code, (item.priority, 1, item.order, item))

    ordered = [t[3] for t in sorted(chosen.values(), key=lambda t: t[:3])][:MAX_CHECKLIST_ITEMS]
    return [ChecklistItem(code=i.code, text=i.text, priority=i.priority, done=False) for i in ordered]


__all__ = ["build_checklist", "load_library", "library_status", "clear_cache", "LIBRARY_PATH", "Library", "LibraryItem"]
