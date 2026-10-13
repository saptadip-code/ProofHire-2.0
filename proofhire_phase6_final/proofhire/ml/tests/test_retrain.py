"""Gated retraining (Member 1, A-G6): feedback eligibility, weighting, every promotion gate, fail-closed behaviour and
production-artifact protection. Uses a small slice of the synthetic CSV and temp dirs only (the committed artifacts
and reports are never touched). Run: PYTHONPATH=backend pytest ml/tests -q"""
import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

import evaluate as EV  # noqa: E402
import export_artifacts as EX  # noqa: E402
import modeling as M  # noqa: E402
import retrain as RT  # noqa: E402
import train as TR  # noqa: E402
from app.ml import model_store as S  # noqa: E402

_CACHE = {}
TODAY = dt.date(2026, 10, 12)


def _base():
    """Mini dataset + a valid 'production' artifact set built once (sklearn of this environment)."""
    if "base" not in _CACHE:
        root = Path(tempfile.mkdtemp(prefix="proofhire_retrain_"))
        df = M.load_dataset(M.DEFAULT_CSV)
        csv, hw = root / "mini.csv", root / "hw.csv"
        df.head(900).to_csv(csv, index=False)
        df.iloc[1000:1100].to_csv(hw, index=False)
        staging, evaluation = root / "b" / "staging.joblib", root / "b" / "evaluation.json"
        TR.run(csv, staging, verbose=False)
        EV.run(staging, csv, hw, root / "b_reports", evaluation, verbose=False)
        EX.export(staging, evaluation, root / "production", verbose=False)
        risky = df.iloc[1100:1500]
        risky = risky[risky["label"] == "1"].head(40).copy()
        risky["listing_id"] = [f"REAL-{i}" for i in range(len(risky))]
        risky.to_csv(root / "feedback.csv", index=False)
        _CACHE["base"] = (root, csv, hw)
    return _CACHE["base"]


def _env(tmp_path, with_hw=True):
    """A private copy of the production artifacts + paths for one test."""
    root, csv, hw = _base()
    art = tmp_path / "production"
    shutil.copytree(root / "production", art)
    return {
        "feedback_csv": root / "feedback.csv", "csv_path": csv, "handwritten_csv": hw if with_hw else tmp_path / "none.csv",
        "artifacts_dir": art, "reports_dir": tmp_path / "reports", "build_dir": tmp_path / "build",
        "changelog": tmp_path / "CHANGELOG.md", "tests_runner": lambda a, r: (True, "stub: tests ok"), "today": TODAY,
        "verbose": False,
    }


def _snapshot(d):
    return {p.name: p.read_bytes() for p in sorted(Path(d).iterdir())}


GOOD = {"synthetic_pr_auc": 0.97, "handwritten_recall": 0.90, "handwritten_n": 60,
        "pattern_holdout_recall": 0.85, "pattern_holdout_n": 30}


def _fake_gate_metrics(monkeypatch, baseline, candidate):
    calls = iter([baseline, candidate])
    monkeypatch.setattr(RT, "gate_metrics", lambda *a, **k: next(calls))


# ---------------------------------------------------------------- feedback eligibility
def _feedback_csv(tmp_path, rows):
    import pandas as pd

    cols = ["listing_id", "title", "company_name", "description", "label", "is_synthetic_demo", "report_count_approved"]
    pd.DataFrame(rows, columns=cols).to_csv(tmp_path / "fb.csv", index=False)
    return tmp_path / "fb.csv"


def _row(i, label="1", demo="0", approved="2", lid=None, title=None, company=None, desc=None):
    return [lid or f"REAL-{i}", title if title is not None else f"Intern {i}", company if company is not None else f"Co {i}",
            desc if desc is not None else f"Pay a registration fee of Rs 999 to confirm your seat number {i}.",
            label, demo, approved]


def test_only_approved_non_demo_complete_unique_rows_become_feedback(tmp_path):
    rows = [_row(1), _row(2),
            _row(3, label="0"),  # no approved report: NEVER used as 'legitimate'
            _row(4, approved="0"), _row(5, demo="1"), _row(6, lid="SYN-000006"),
            _row(7, desc=""), _row(8, title=" "), _row(9, company=""),
            _row(1)]  # exact duplicate of row 1
    X, y, stats = RT.load_feedback(_feedback_csv(tmp_path, rows))
    assert stats["rows_in"] == 10 and stats["eligible"] == 2 == len(y) == len(X)
    assert set(y.tolist()) == {1}  # label 0 rows are dropped, never turned into negatives
    assert stats["dropped_not_reported"] == 2 and stats["dropped_synthetic_demo"] == 2
    assert stats["dropped_incomplete"] == 3 and stats["dropped_duplicate"] == 1


def test_feedback_without_required_columns_is_refused(tmp_path):
    (tmp_path / "bad.csv").write_text("title,label\nx,1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="missing required columns"):
        RT.load_feedback(tmp_path / "bad.csv")


def test_no_eligible_feedback_changes_nothing(tmp_path):
    kw = _env(tmp_path)
    before = _snapshot(kw["artifacts_dir"])
    kw["feedback_csv"] = _feedback_csv(tmp_path, [_row(1, label="0"), _row(2, demo="1")])
    with pytest.raises(SystemExit, match="no eligible feedback"):
        RT.retrain(**kw)
    assert _snapshot(kw["artifacts_dir"]) == before and not kw["changelog"].exists()


def test_missing_feedback_file_and_bad_weight_are_refused(tmp_path):
    kw = _env(tmp_path)
    with pytest.raises(SystemExit, match="not found"):
        RT.retrain(**dict(kw, feedback_csv=tmp_path / "nope.csv"))
    with pytest.raises(SystemExit, match="weight"):
        RT.retrain(**dict(kw, weight=0))


# ---------------------------------------------------------------- weighting / staging
def test_sample_weight_reaches_the_classifier_and_changes_the_fit():
    df = M.load_dataset(M.DEFAULT_CSV).head(300)
    X, y = M.build_matrix(df)
    plain = M.fit_model(M.make_model("M3"), X, y)
    w = np.where(y == 1, 5.0, 1.0)
    weighted = M.fit_model(M.make_model("M3"), X, y, w)
    assert not np.allclose(plain.named_steps["clf"].coef_, weighted.named_steps["clf"].coef_)
    assert M.positive_scores(weighted, X).mean() > M.positive_scores(plain, X).mean()  # up-weighted risky class


def test_training_with_feedback_records_rows_weight_and_forces_m3(tmp_path):
    import joblib

    root, csv, _ = _base()
    X_fb, y_fb, _ = RT.load_feedback(root / "feedback.csv")
    st = TR.run(csv, tmp_path / "s.joblib", verbose=False, feedback=(X_fb, y_fb, 3.0))
    assert st["feedback_rows"] == len(y_fb) > 0 and st["feedback_weight"] == 3.0 and st["selected_model"] == "M3"
    assert joblib.load(tmp_path / "s.joblib")["feedback_rows"] == len(y_fb)
    lim = EV.limitations(60, 30, None, len(y_fb), 3.0)
    assert any("positive-only" in x for x in lim) and not any("feedback_rows = 0" in x for x in lim)


def test_limitations_state_synthetic_leakage_and_missing_handwritten_data():
    lim = EV.limitations(0, 30)
    text = " ".join(lim)
    assert "leakage" in text and "label noise" in text and "not real-world accuracy" in text
    assert any("null (n=0)" in x for x in lim)  # unavailable, not fabricated


# ---------------------------------------------------------------- gate logic (pure)
OK_TESTS = (True, "ok")


def _gates(baseline, candidate, size=1000, tests=OK_TESTS):
    return {g["gate"]: g["passed"] for g in RT.evaluate_gates(baseline, candidate, size, tests)}


def test_all_gates_pass_for_an_equal_or_better_candidate():
    better = dict(GOOD, synthetic_pr_auc=0.971, handwritten_recall=0.95, pattern_holdout_recall=0.9)
    assert all(_gates(GOOD, GOOD).values()) and all(_gates(GOOD, better).values())
    assert set(_gates(GOOD, GOOD)) == set(RT.GATE_NAMES)


def test_synthetic_pr_auc_may_drop_by_at_most_0_01():
    assert _gates(GOOD, dict(GOOD, synthetic_pr_auc=0.96))["synthetic_pr_auc"]  # exactly -0.01 allowed
    assert not _gates(GOOD, dict(GOOD, synthetic_pr_auc=0.9599))["synthetic_pr_auc"]


@pytest.mark.parametrize("key,gate", [("handwritten_recall", "handwritten_recall"),
                                      ("pattern_holdout_recall", "pattern_holdout_recall")])
def test_recall_gates_allow_no_drop(key, gate):
    assert _gates(GOOD, dict(GOOD, **{key: GOOD[key]}))[gate]
    assert not _gates(GOOD, dict(GOOD, **{key: GOOD[key] - 0.0001}))[gate]


def test_missing_comparison_data_fails_closed():
    for key, gate in (("handwritten_recall", "handwritten_recall"), ("pattern_holdout_recall", "pattern_holdout_recall"),
                      ("synthetic_pr_auc", "synthetic_pr_auc")):
        assert not _gates(dict(GOOD, **{key: None}), GOOD)[gate]  # production side unavailable
        assert not _gates(GOOD, dict(GOOD, **{key: None}))[gate]  # candidate side unavailable


def test_unloadable_production_model_fails_every_comparison():
    g = _gates(None, GOOD)
    assert not g["synthetic_pr_auc"] and not g["handwritten_recall"] and not g["pattern_holdout_recall"]
    assert g["artifact_size"] and g["ml_tests"]


def test_size_gate_and_test_gate():
    assert not _gates(GOOD, GOOD, size=S.MAX_ARTIFACT_BYTES)["artifact_size"]
    assert _gates(GOOD, GOOD, size=S.MAX_ARTIFACT_BYTES - 1)["artifact_size"]
    assert not _gates(GOOD, GOOD, tests=(False, "2 failed"))["ml_tests"]


# ---------------------------------------------------------------- ml-tests gate runner
class _Done:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_ml_tests_runner_reports_pass_fail_and_missing_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(RT.subprocess, "run", lambda *a, **k: _Done(0, "180 passed in 20s\n"))
    assert RT.run_ml_tests(tmp_path, tmp_path) == (True, "180 passed in 20s")
    monkeypatch.setattr(RT.subprocess, "run", lambda *a, **k: _Done(1, "2 failed, 178 passed\n"))
    ok, why = RT.run_ml_tests(tmp_path, tmp_path)
    assert not ok and "exit code 1" in why
    monkeypatch.setattr(RT.subprocess, "run", lambda *a, **k: _Done(1, "", "No module named pytest"))
    ok, why = RT.run_ml_tests(tmp_path, tmp_path)
    assert not ok and "not installed" in why
    def boom(*a, **k):
        raise OSError("no python")
    monkeypatch.setattr(RT.subprocess, "run", boom)
    assert RT.run_ml_tests(tmp_path, tmp_path)[0] is False


def test_ml_tests_runner_points_pytest_at_the_candidate(tmp_path, monkeypatch):
    seen = {}

    def fake(cmd, **kw):
        seen.update(kw["env"])
        return _Done(0, "ok\n")

    monkeypatch.setattr(RT.subprocess, "run", fake)
    RT.run_ml_tests(tmp_path / "cand", tmp_path / "rep")
    assert seen["PROOFHIRE_TEST_ARTIFACT_DIR"] == str(tmp_path / "cand")
    assert seen["PROOFHIRE_TEST_REPORTS_DIR"] == str(tmp_path / "rep")


# ---------------------------------------------------------------- full retrain: promotion and protection
def test_failed_gate_never_touches_production_artifacts(tmp_path, monkeypatch):
    kw = _env(tmp_path)
    before = _snapshot(kw["artifacts_dir"])
    _fake_gate_metrics(monkeypatch, GOOD, dict(GOOD, handwritten_recall=0.80))  # candidate recall dropped
    res = RT.retrain(**kw)
    assert res["promoted"] is False and not all(g["passed"] for g in res["gates"])
    assert _snapshot(kw["artifacts_dir"]) == before  # byte-identical
    assert not kw["changelog"].exists() and not kw["reports_dir"].exists()
    assert (kw["build_dir"] / "retrain_report.json").is_file()


def test_failing_ml_tests_block_promotion(tmp_path, monkeypatch):
    kw = _env(tmp_path)
    before = _snapshot(kw["artifacts_dir"])
    _fake_gate_metrics(monkeypatch, GOOD, GOOD)
    res = RT.retrain(**dict(kw, tests_runner=lambda a, r: (False, "1 failed")))
    assert res["promoted"] is False and [g["gate"] for g in res["gates"] if not g["passed"]] == ["ml_tests"]
    assert _snapshot(kw["artifacts_dir"]) == before


def test_missing_handwritten_file_fails_closed_with_real_models(tmp_path):
    kw = _env(tmp_path, with_hw=False)
    before = _snapshot(kw["artifacts_dir"])
    res = RT.retrain(**kw)  # real gate_metrics on real models
    gates = {g["gate"]: g for g in res["gates"]}
    assert not gates["handwritten_recall"]["passed"] and "unavailable" in gates["handwritten_recall"]["detail"]
    assert res["promoted"] is False and _snapshot(kw["artifacts_dir"]) == before


def test_unloadable_production_artifacts_fail_closed(tmp_path):
    kw = _env(tmp_path)
    (kw["artifacts_dir"] / S.MODEL_FILENAME).write_bytes(b"corrupt")  # SHA-256 no longer matches
    before = _snapshot(kw["artifacts_dir"])
    res = RT.retrain(**kw)
    assert res["promoted"] is False and res["baseline"] is None
    assert not {g["gate"]: g["passed"] for g in res["gates"]}["synthetic_pr_auc"]
    assert _snapshot(kw["artifacts_dir"]) == before


def test_real_gate_numbers_are_computed_for_both_models(tmp_path):
    kw = _env(tmp_path)
    res = RT.retrain(**dict(kw, dry_run=True))
    for side in ("baseline", "candidate"):
        m = res[side]
        assert 0.0 <= m["synthetic_pr_auc"] <= 1.0 and 0.0 <= m["handwritten_recall"] <= 1.0
        assert m["handwritten_n"] == 100 and m["pattern_holdout_n"] > 0
    assert res["promoted"] is False  # dry run never promotes, whatever the gates say


def test_successful_promotion_replaces_artifacts_bumps_version_and_logs(tmp_path, monkeypatch):
    kw = _env(tmp_path)
    old = json.loads((kw["artifacts_dir"] / S.META_FILENAME).read_text(encoding="utf-8"))
    _fake_gate_metrics(monkeypatch, GOOD, GOOD)
    res = RT.retrain(**kw)
    assert res["promoted"] is True and all(g["passed"] for g in res["gates"])
    new = json.loads((kw["artifacts_dir"] / S.META_FILENAME).read_text(encoding="utf-8"))
    assert old["model_version"] == "proofhire-lr-1.0.0" and new["model_version"] == "proofhire-lr-1.0.1"
    assert new["feedback_rows"] == res["feedback"]["eligible"] > 0 and new["sha256_model"] != old["sha256_model"]
    assert S.load_artifacts(kw["artifacts_dir"]).meta == new  # what the service would load
    assert sorted(p.name for p in kw["artifacts_dir"].iterdir()) == ["metrics.json", "model.joblib", "model_meta.json"]
    assert (kw["reports_dir"] / "metrics_full.json").is_file()
    line = kw["changelog"].read_text(encoding="utf-8").strip().splitlines()[-1]
    assert line.startswith("- 2026-10-12 | proofhire-lr-1.0.1 |") and f"feedback rows {new['feedback_rows']}" in line
    metrics = json.loads((kw["artifacts_dir"] / S.METRICS_FILENAME).read_text(encoding="utf-8"))
    assert any("positive-only" in x for x in metrics["limitations"])  # the limits of feedback are disclosed


def test_changelog_is_appended_not_overwritten(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    RT.append_changelog(path, "- first")
    RT.append_changelog(path, "- second")
    assert path.read_text(encoding="utf-8").splitlines()[-2:] == ["- first", "- second"]


def test_promote_refuses_a_tampered_candidate_and_keeps_production(tmp_path):
    kw = _env(tmp_path)
    cand = tmp_path / "cand"
    shutil.copytree(kw["artifacts_dir"], cand)
    with open(cand / S.MODEL_FILENAME, "ab") as fh:
        fh.write(b"tamper")
    before = _snapshot(kw["artifacts_dir"])
    with pytest.raises(S.ArtifactError):
        RT.promote(cand, kw["artifacts_dir"])
    assert _snapshot(kw["artifacts_dir"]) == before and not list(kw["artifacts_dir"].glob(".promote_*"))


# ---- release-validation fixes: export quirks must not corrupt features (data written by other members' tools)
def test_null_tokens_from_sql_exports_are_blank_not_real_values(tmp_path):
    import pandas as pd
    from app.ml import features as F

    cols = ["listing_id", "title", "company_name", "description", "requirements", "contact_email", "contact_phone",
            "company_website", "salary_max", "label"]
    rows = [["DB-1", "Data Entry Intern", "Co One", "Pay a registration fee of Rs 999 to confirm your seat.", tok, tok, tok, tok, tok, "1"]
            for tok in ("NULL", "None", "nan", "\\N", "N/A")]
    rows = [[r[0] + str(i), r[1], f"Co {i}", *r[3:]] for i, r in enumerate(rows)]
    pd.DataFrame(rows, columns=cols).to_csv(tmp_path / "fb.csv", index=False)
    X, y, stats = RT.load_feedback(tmp_path / "fb.csv")
    assert stats["eligible"] == 5
    for rec in X:
        feats = dict(zip(F.MODEL_INPUT_COLUMNS, rec))  # X rows are already the feature values
        assert feats["website_missing"] == 1 and feats["email_present"] == 0 and feats["phone_present"] == 0
        assert feats["req_words"] == 0 and feats["salary_max_month_log"] == 0


def test_real_values_are_not_blanked_by_the_null_token_rule(tmp_path):
    import pandas as pd
    from app.ml import features as F

    pd.DataFrame([["DB-1", "Intern", "Co", "Pay a registration fee of Rs 999 to confirm your seat.", "Python and SQL.", "hr@co.com", "https://co.com", "1"]],
                 columns=["listing_id", "title", "company_name", "description", "requirements", "contact_email", "company_website", "label"]
                 ).to_csv(tmp_path / "fb.csv", index=False)
    X, _, _ = RT.load_feedback(tmp_path / "fb.csv")
    feats = dict(zip(F.MODEL_INPUT_COLUMNS, X[0]))
    assert feats["email_present"] == 1 and feats["website_missing"] == 0 and feats["req_words"] == 3


def test_csv_files_saved_by_excel_load_with_every_encoding(tmp_path):
    import csv
    import io

    text_rows = [["listing_id", "title", "company_name", "description", "label"],
                 ["HW-1", "Intern \u2013 earn \u201cbig\u201d", "Co", "Pay a registration fee of Rs 999 today.", "1"]]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(text_rows)
    for name, enc in (("utf-8", "utf-8"), ("excel utf-8 with BOM", "utf-8-sig"), ("excel cp1252", "cp1252")):
        path = tmp_path / f"{name.replace(' ', '_')}.csv"
        path.write_bytes(buf.getvalue().encode(enc))
        df = M.load_dataset(path)
        assert list(df.columns) == ["listing_id", "title", "company_name", "description", "label"], name  # no BOM in the header
        assert df.loc[0, "title"] == "Intern \u2013 earn \u201cbig\u201d", name
