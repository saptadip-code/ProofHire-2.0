"""End-to-end train -> evaluate -> export on a small slice of the synthetic CSV, plus version-bump rules and
failure safety (Member 1, A-G3). Writes only to tmp dirs. Run: PYTHONPATH=backend pytest ml/tests -q"""
import json

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

import evaluate as EV  # noqa: E402
import export_artifacts as EX  # noqa: E402
import modeling as M  # noqa: E402
import train as TR  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402

_CACHE = {}


def _mini(tmp_path):
    """Run train + evaluate once on 900 rows (cached); returns (csv, staging, evaluation, hw_csv)."""
    if "paths" not in _CACHE:
        import tempfile
        from pathlib import Path

        base = Path(tempfile.mkdtemp(prefix="proofhire_mini_"))
        df = M.load_dataset(M.DEFAULT_CSV)
        csv, hw = base / "mini.csv", base / "hw.csv"
        df.head(900).to_csv(csv, index=False)
        df.iloc[1000:1060].to_csv(hw, index=False)
        staging = base / "build" / "staging.joblib"
        TR.run(csv, staging, verbose=False)
        evaluation = base / "build" / "evaluation.json"
        EV.run(staging, csv, hw, base / "reports", evaluation, verbose=False)
        _CACHE["paths"] = (csv, staging, evaluation, hw, base)
    return _CACHE["paths"]


def test_staging_respects_split_and_selection_rule(tmp_path):
    import joblib

    _, staging, _, _, _ = _mini(tmp_path)
    st = joblib.load(staging)
    assert st["selected_model"] == "M3" and set(st["models_train"]) == {"M0", "M1", "M2", "M3", "M4"}
    assert st["feature_order"] == F.FEATURE_ORDER and st["splits"]["holdout"] > 0
    assert st["production_train_rows"] == st["splits"]["train"] + st["splits"]["val"]  # train+val refit, no test
    assert st["holdout_excluded_rows"] == 0  # fake_offer_letter is never in train


def test_evaluation_writes_only_measured_numbers(tmp_path):
    csv, _, evaluation, hw, base = _mini(tmp_path)
    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    m = ev["metrics"]
    assert m["handwritten"]["n"] == 60 and 0.0 <= m["handwritten"]["recall"] <= 1.0
    (tn, fp), (fn, tp) = m["synthetic_test"]["confusion"]
    assert tn + fp + fn + tp == int((M.load_dataset(csv)["split"] == "test").sum())
    assert (base / "reports" / "metrics_full.json").is_file()
    assert set(ev["thresholds"]) == {"low", "high"}


def test_missing_handwritten_file_gives_null_metrics_not_made_up_ones(tmp_path):
    csv, staging, _, _, _ = _mini(tmp_path)
    out = tmp_path / "evaluation.json"
    EV.run(staging, csv, tmp_path / "does_not_exist.csv", tmp_path / "reports", out, verbose=False)
    hw = json.loads(out.read_text(encoding="utf-8"))["metrics"]["handwritten"]
    assert hw == {"precision": None, "recall": None, "n": 0}


def test_export_writes_exact_artifacts_that_pass_the_runtime_loader(tmp_path):
    _, staging, evaluation, _, _ = _mini(tmp_path)
    art = tmp_path / "artifacts"
    meta = EX.export(staging, evaluation, art, verbose=False)
    assert sorted(p.name for p in art.iterdir()) == ["metrics.json", "model.joblib", "model_meta.json"]
    assert meta["model_version"] == "proofhire-lr-1.0.0"
    on_disk = json.loads((art / S.META_FILENAME).read_text(encoding="utf-8"))
    assert on_disk == meta and set(meta) == set(S.REQUIRED_META_KEYS)
    assert meta["sha256_model"] == S.sha256_file(art / S.MODEL_FILENAME)
    assert json.loads((art / S.METRICS_FILENAME).read_text(encoding="utf-8")) == \
        json.loads(evaluation.read_text(encoding="utf-8"))["metrics"]
    loaded = S.load_artifacts(art)  # the exact startup checks of the service
    assert loaded.meta == meta


def test_second_export_bumps_patch_and_feature_change_bumps_minor(tmp_path):
    _, staging, evaluation, _, _ = _mini(tmp_path)
    art = tmp_path / "artifacts"
    assert EX.export(staging, evaluation, art, verbose=False)["model_version"] == "proofhire-lr-1.0.0"
    assert EX.export(staging, evaluation, art, verbose=False)["model_version"] == "proofhire-lr-1.0.1"
    meta = json.loads((art / S.META_FILENAME).read_text(encoding="utf-8"))
    meta["feature_order"] = meta["feature_order"][:-1]  # previous model had a different feature set
    (art / S.META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")
    assert EX.export(staging, evaluation, art, verbose=False)["model_version"] == "proofhire-lr-1.1.0"
    assert EX.export(staging, evaluation, art, bump="major", verbose=False)["model_version"] == "proofhire-lr-2.0.0"


def test_next_version_rules():
    fo = list(F.FEATURE_ORDER)
    prev = {"model_version": "proofhire-lr-1.2.3", "feature_order": fo}
    assert EX.next_version(None, fo) == "proofhire-lr-1.0.0"
    assert EX.next_version(prev, fo) == "proofhire-lr-1.2.4"
    assert EX.next_version(prev, fo[:-1]) == "proofhire-lr-1.3.0"
    assert EX.next_version(prev, fo, "minor") == "proofhire-lr-1.3.0"
    assert EX.next_version(prev, fo, "major") == "proofhire-lr-2.0.0"
    with pytest.raises(ValueError):
        EX.next_version(prev, fo, "huge")


def test_failed_export_leaves_existing_artifacts_untouched(tmp_path, monkeypatch):
    _, staging, evaluation, _, _ = _mini(tmp_path)
    art = tmp_path / "artifacts"
    EX.export(staging, evaluation, art, verbose=False)
    before = {p.name: p.read_bytes() for p in art.iterdir()}
    monkeypatch.setattr(S, "MAX_ARTIFACT_BYTES", 10)  # force the 10 MB gate to fail
    with pytest.raises(SystemExit):
        EX.export(staging, evaluation, art, verbose=False)
    assert {p.name: p.read_bytes() for p in art.iterdir()} == before  # nothing replaced, no temp dirs left


def test_mismatched_evaluation_is_refused(tmp_path):
    _, staging, evaluation, _, _ = _mini(tmp_path)
    bad = tmp_path / "evaluation.json"
    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    ev["run_id"] = "someone-elses-run"
    bad.write_text(json.dumps(ev), encoding="utf-8")
    with pytest.raises(SystemExit):
        EX.export(staging, bad, tmp_path / "artifacts", verbose=False)


def test_rebuild_script_refuses_unpinned_scikit_learn():
    import rebuild_artifacts as RB

    with pytest.raises(SystemExit, match="Refusing to build"):
        RB.check_pinned("1.8.0")
    RB.check_pinned(S.REQUIRED_SKLEARN_VERSION)  # pinned: no error
    RB.check_pinned("1.8.0", allow_unpinned=True)  # dev escape hatch
