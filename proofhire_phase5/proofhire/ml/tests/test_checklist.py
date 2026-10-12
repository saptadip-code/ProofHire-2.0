"""Checklist builder tests (Member 1, A-G4). Guidebook A8. Member 4 owns the real library file; these tests use
temporary library files so they never depend on, or modify, backend/app/data/checklist_library.json.
Run: PYTHONPATH=backend pytest ml/tests -q"""
import json
import os

import pytest

pytest.importorskip("pydantic")

from app.ml import checklist as C  # noqa: E402
from app.ml import evidence as E  # noqa: E402
from app.schemas.ml_schemas import ChecklistItem, EvidenceItem  # noqa: E402


def ev(code, n=1):
    model = code in E.MODEL_CODES
    sev, direction, label = (2, "increases_risk", code) if model else E.EVIDENCE_CATALOG[code]
    return EvidenceItem(id=f"E{n}", code=code, label=label, type="model" if model else "observed",
                        direction=direction, severity=sev, snippet=None, weight=0.5 if model else None)


def item(code, priority, triggers, text=None):
    return {"code": code, "text": f"Text for {code}" if text is None else text, "priority": priority, "triggers": triggers}


@pytest.fixture(autouse=True)
def fresh_cache():
    C.clear_cache()
    yield
    C.clear_cache()


@pytest.fixture()
def lib(tmp_path):
    def write(items):
        p = tmp_path / "checklist_library.json"
        p.write_text(json.dumps(items), encoding="utf-8")
        return p

    return write


GUIDEBOOK_EXAMPLE = [  # the three items shown in guidebook A8
    {"code": "CHK_NO_FEE", "text": "Never pay any fee before a signed offer; real employers do not charge applicants.",
     "priority": 1, "triggers": ["UPFRONT_FEE"]},
    {"code": "CHK_LEGAL_NAME", "text": "Ask for the registered legal name and look it up in the MCA company search.",
     "priority": 2, "triggers": ["NO_COMPANY_WEBSITE", "EMAIL_DOMAIN_MISMATCH", "FREE_EMAIL_CONTACT"]},
    {"code": "CHK_GENERAL_RECRUITER", "text": "Find the recruiter on the company's official page and message them there.",
     "priority": 3, "triggers": ["*"]},
]


# ------------------------------------------------------------------ matching
def test_guidebook_example_matching(lib):
    p = lib(GUIDEBOOK_EXAMPLE)
    out = C.build_checklist([ev("UPFRONT_FEE"), ev("NO_COMPANY_WEBSITE", 2)], library_path=p)
    assert [c.code for c in out] == ["CHK_NO_FEE", "CHK_LEGAL_NAME", "CHK_GENERAL_RECRUITER"]
    assert all(isinstance(c, ChecklistItem) and c.done is False for c in out)
    only_always = C.build_checklist([ev("DETAILED_REQUIREMENTS")], library_path=p)
    assert [c.code for c in only_always] == ["CHK_GENERAL_RECRUITER"]


def test_items_have_no_ids_and_keep_library_text_and_priority(lib):
    out = C.build_checklist([ev("UPFRONT_FEE")], library_path=lib(GUIDEBOOK_EXAMPLE))
    assert set(out[0].model_dump()) == {"code", "text", "priority", "done"}
    assert out[0].text == GUIDEBOOK_EXAMPLE[0]["text"] and out[0].priority == 1


def test_no_matching_trigger_and_no_always_on_gives_empty(lib):
    assert C.build_checklist([ev("NO_INTERVIEW")], library_path=lib([item("A", 1, ["UPFRONT_FEE"])])) == []
    assert C.build_checklist([], library_path=lib([item("A", 1, ["UPFRONT_FEE"])])) == []


def test_any_trigger_in_the_list_is_enough(lib):
    p = lib([item("A", 2, ["UPFRONT_FEE", "FREE_EMAIL_CONTACT", "NO_INTERVIEW"])])
    for code in ("UPFRONT_FEE", "FREE_EMAIL_CONTACT", "NO_INTERVIEW"):
        assert [c.code for c in C.build_checklist([ev(code)], library_path=p)] == ["A"]


def test_model_codes_and_protective_codes_can_trigger_items(lib):
    p = lib([item("M", 2, ["MODEL_TERM"]), item("P", 3, ["CORP_EMAIL_MATCHES_WEBSITE"])])
    got = C.build_checklist([ev("MODEL_TERM"), ev("CORP_EMAIL_MATCHES_WEBSITE", 2)], library_path=p)
    assert [c.code for c in got] == ["M", "P"]


def test_evidence_may_be_plain_codes(lib):
    assert [c.code for c in C.build_checklist(["UPFRONT_FEE"], library_path=lib(GUIDEBOOK_EXAMPLE))] == [
        "CHK_NO_FEE", "CHK_GENERAL_RECRUITER"]


# ------------------------------------------------------------------ always-on, dedupe, order, caps
def test_only_four_always_on_items_are_kept_lowest_priority_number_first(lib):
    items = [item(f"W{i}", p, ["*"]) for i, p in enumerate([3, 3, 2, 3, 1, 3, 2])]
    out = C.build_checklist([], library_path=lib(items))
    assert [c.code for c in out] == ["W4", "W2", "W6", "W0"]  # priorities 1, 2, 2, 3 -> library order breaks ties


def test_triggered_items_come_before_always_on_items_of_equal_priority(lib):
    p = lib([item("ALWAYS", 2, ["*"]), item("HIT", 2, ["UPFRONT_FEE"])])
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["HIT", "ALWAYS"]


def test_item_with_specific_and_always_on_triggers_is_not_duplicated(lib):
    p = lib([item("BOTH", 1, ["UPFRONT_FEE", "*"])])
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["BOTH"]
    assert [c.code for c in C.build_checklist([], library_path=p)] == ["BOTH"]


def test_duplicate_codes_in_library_are_deduplicated_first_entry_wins(lib):
    p = lib([item("DUP", 1, ["UPFRONT_FEE"], "first"), item("DUP", 3, ["UPFRONT_FEE"], "second")])
    out = C.build_checklist([ev("UPFRONT_FEE")], library_path=p)
    assert [(c.code, c.text) for c in out] == [("DUP", "first")]


def test_sorted_by_priority_then_library_order(lib):
    p = lib([item("C", 3, ["UPFRONT_FEE"]), item("A", 1, ["UPFRONT_FEE"]), item("B2", 2, ["UPFRONT_FEE"]),
             item("B1", 2, ["UPFRONT_FEE"])])
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["A", "B2", "B1", "C"]


def test_at_most_ten_items_keeping_the_highest_priority(lib):
    items = [item(f"T{i:02d}", 1 + i % 3, ["UPFRONT_FEE"]) for i in range(15)]
    out = C.build_checklist([ev("UPFRONT_FEE")], library_path=lib(items))
    assert len(out) == 10 and [c.priority for c in out] == sorted(c.priority for c in out)
    assert all(c.priority == 1 for c in out[:5])


# ------------------------------------------------------------------ missing / broken library (integration visibility)
def test_missing_library_returns_empty_and_reports_it_loudly(tmp_path, caplog):
    missing = tmp_path / "nope.json"
    with caplog.at_level("ERROR", logger="proofhire.ml"):
        assert C.build_checklist([ev("UPFRONT_FEE")], library_path=missing) == []
        assert C.build_checklist([ev("UPFRONT_FEE")], library_path=missing) == []
    errors = [r for r in caplog.records if "MISSING" in r.message]
    assert len(errors) == 1  # logged once per file state, not on every request
    st = C.library_status(missing)
    assert st["status"] == "missing" and st["items"] == 0 and "not found" in st["problems"][0]


def test_library_appearing_later_is_picked_up_without_restart(tmp_path):
    p = tmp_path / "lib.json"
    assert C.build_checklist([ev("UPFRONT_FEE")], library_path=p) == []
    p.write_text(json.dumps(GUIDEBOOK_EXAMPLE), encoding="utf-8")
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)][0] == "CHK_NO_FEE"


def test_edited_library_is_reread_when_modification_time_changes(lib):
    p = lib([item("OLD", 1, ["UPFRONT_FEE"])])
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["OLD"]
    p.write_text(json.dumps([item("NEW", 1, ["UPFRONT_FEE"])]), encoding="utf-8")
    os.utime(p, (p.stat().st_atime + 10, p.stat().st_mtime + 10))
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["NEW"]


def test_invalid_json_and_wrong_shapes_are_reported_not_raised(tmp_path, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with caplog.at_level("ERROR", logger="proofhire.ml"):
        assert C.build_checklist([ev("UPFRONT_FEE")], library_path=bad) == []
    assert C.library_status(bad)["status"] == "invalid"
    obj = tmp_path / "obj.json"
    obj.write_text(json.dumps({"code": "X"}), encoding="utf-8")
    assert C.build_checklist([ev("UPFRONT_FEE")], library_path=obj) == [] and C.library_status(obj)["status"] == "invalid"


def test_invalid_items_are_skipped_and_reported_valid_ones_still_work(lib):
    p = lib([item("OK", 1, ["UPFRONT_FEE"]), item("BADPRIO", 4, ["UPFRONT_FEE"]), item("NOTEXT", 1, ["UPFRONT_FEE"], text=""),
             item("LONG", 1, ["UPFRONT_FEE"], text="x" * 501), item("NOTRIG", 1, []), "oops",
             {"text": "no code", "priority": 1, "triggers": ["*"]}])
    st = C.library_status(p)
    assert st["status"] == "partial" and st["items"] == 1 and len(st["problems"]) == 6
    assert [c.code for c in C.build_checklist([ev("UPFRONT_FEE")], library_path=p)] == ["OK"]


def test_unknown_trigger_codes_are_flagged_but_the_item_is_kept(lib):
    p = lib([item("TYPO", 1, ["UPFRONT_FEES", "NO_INTERVIEW"])])
    st = C.library_status(p)
    assert st["status"] == "partial" and any("UPFRONT_FEES" in m for m in st["problems"])
    assert [c.code for c in C.build_checklist([ev("NO_INTERVIEW")], library_path=p)] == ["TYPO"]


def test_text_of_exactly_500_characters_is_accepted(lib):
    assert C.library_status(lib([item("A", 1, ["*"], text="x" * 500)]))["status"] == "ok"


# ------------------------------------------------------------------ the real library (Member 4), when present
def test_real_library_if_delivered_is_valid_and_triggers_are_a7_codes():
    if not C.LIBRARY_PATH.is_file():
        pytest.skip(f"Member 4's {C.LIBRARY_PATH.name} is not in this repository yet (integration dependency)")
    st = C.library_status()
    assert st["status"] == "ok", st["problems"]
    assert st["items"] >= 20  # guidebook D2
    triggers = {t for i in C.load_library().items for t in i.triggers}
    assert triggers <= set(E.ALL_EVIDENCE_CODES) | {"*"}


def test_module_never_writes_the_library(tmp_path):
    p = tmp_path / "lib.json"
    assert C.build_checklist([ev("UPFRONT_FEE")], library_path=p) == []
    assert not p.exists()  # reading a missing library must not create it
