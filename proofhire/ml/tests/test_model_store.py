"""Startup artifact validation tests (Member 1, A-G3): serialization/loading, hash validation, version check,
feature compatibility, warm-up. Uses a throw-away model trained on a small slice of the synthetic CSV, so these tests
do not depend on the committed artifacts. Run: PYTHONPATH=backend pytest ml/tests -q"""
import json
import shutil

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")
import joblib  # noqa: E402

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402

_CACHE = {}


def _good_dir(tmp_path):
    """A valid artifact set (tiny M3) written to tmp_path; trained once per test session."""
    if "model" not in _CACHE:
        X, y = M.build_matrix(M.load_dataset(M.DEFAULT_CSV).head(500))
        _CACHE["model"] = M.make_model("M3").fit(X, y)
    d = tmp_path / "artifacts"
    d.mkdir()
    joblib.dump(_CACHE["model"], d / S.MODEL_FILENAME, compress=3)
    meta = {
        "model_version": "proofhire-lr-1.0.0", "trained_at": "2026-10-10T00:00:00Z",
        "sklearn_version": S.running_sklearn_version(), "python_version": "3.x", "selected_model": "M3",
        "thresholds": {"low": 0.35, "high": 0.70}, "feature_order": list(F.FEATURE_ORDER),
        "dataset": {"type": "synthetic", "rows": 500, "seed": 42, "generator_commit": None},
        "sha256_model": S.sha256_file(d / S.MODEL_FILENAME), "feedback_rows": 0,
    }
    (d / S.META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")
    (d / S.METRICS_FILENAME).write_text(json.dumps({"synthetic_test": {}}), encoding="utf-8")
    return d


def _edit_meta(d, **changes):
    meta = json.loads((d / S.META_FILENAME).read_text(encoding="utf-8"))
    meta.update(changes)
    (d / S.META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")


def test_valid_artifacts_round_trip_and_score(tmp_path):
    d = _good_dir(tmp_path)
    loaded = S.load_artifacts(d)
    assert loaded.sha256 == loaded.meta["sha256_model"] == S.sha256_file(d / S.MODEL_FILENAME)
    assert loaded.metrics == {"synthetic_test": {}}
    risky = {"title": "Data Entry Intern", "company_name": "Brightpath Careers",
             "description": "Work from home. Pay registration fee of Rs 1499 to confirm your seat. Apply today!",
             "upfront_fee_amount": 1499, "contact_email": "x.hr@gmail.com", "application_channel": "whatsapp"}
    score = S.predict_score(loaded, risky)
    assert 0.0 <= score <= 1.0 and score == round(score, 4)


def test_sha256_mismatch_is_rejected_before_unpickling(tmp_path):
    d = _good_dir(tmp_path)
    with open(d / S.MODEL_FILENAME, "ab") as fh:
        fh.write(b"tamper")
    with pytest.raises(S.ArtifactError, match="SHA-256"):
        S.load_artifacts(d)


def test_sha256_in_meta_altered_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    _edit_meta(d, sha256_model="0" * 64)
    with pytest.raises(S.ArtifactError, match="SHA-256"):
        S.load_artifacts(d)


def test_sklearn_version_mismatch_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    _edit_meta(d, sklearn_version="0.0.1")
    with pytest.raises(S.ArtifactError, match="scikit-learn mismatch"):
        S.load_artifacts(d)


def test_feature_order_mismatch_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    _edit_meta(d, feature_order=list(reversed(F.FEATURE_ORDER)))
    with pytest.raises(S.ArtifactError, match="feature_order"):
        S.load_artifacts(d)


@pytest.mark.parametrize("name", [S.MODEL_FILENAME, S.META_FILENAME])
def test_missing_files_are_rejected(tmp_path, name):
    d = _good_dir(tmp_path)
    (d / name).unlink()
    with pytest.raises(S.ArtifactError, match="not found"):
        S.load_artifacts(d)


def test_missing_metrics_does_not_block_scoring(tmp_path):
    d = _good_dir(tmp_path)
    (d / S.METRICS_FILENAME).unlink()
    assert S.load_artifacts(d).metrics is None


@pytest.mark.parametrize("change", [
    {"model_version": "lr-1.0.0"}, {"model_version": "proofhire-lr-1.0"},
    {"thresholds": {"low": 0.8, "high": 0.7}}, {"thresholds": {"low": 0.1}}, {"thresholds": {"low": -0.1, "high": 0.5}},
    {"sha256_model": "xyz"}, {"dataset": {"type": "synthetic"}},
])
def test_invalid_meta_values_are_rejected(tmp_path, change):
    d = _good_dir(tmp_path)
    _edit_meta(d, **change)
    with pytest.raises(S.ArtifactError):
        S.load_artifacts(d)


def test_meta_missing_required_key_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    meta = json.loads((d / S.META_FILENAME).read_text(encoding="utf-8"))
    del meta["feedback_rows"]
    (d / S.META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(S.ArtifactError, match="missing keys"):
        S.load_artifacts(d)


def test_corrupt_model_file_with_matching_hash_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    (d / S.MODEL_FILENAME).write_bytes(b"not a joblib file")
    _edit_meta(d, sha256_model=S.sha256_file(d / S.MODEL_FILENAME))
    with pytest.raises(S.ArtifactError, match="joblib.load failed"):
        S.load_artifacts(d)


class BrokenModel:  # module level so it pickles; returns a "probability" outside [0, 1]
    def predict_proba(self, X):
        import numpy as np
        return np.array([[0.0, 7.0]] * len(X))


def test_failed_warmup_prediction_is_rejected(tmp_path):
    d = _good_dir(tmp_path)
    joblib.dump(BrokenModel(), d / S.MODEL_FILENAME)
    _edit_meta(d, sha256_model=S.sha256_file(d / S.MODEL_FILENAME))
    with pytest.raises(S.ArtifactError, match="not a probability"):
        S.load_artifacts(d)


def test_model_expecting_other_feature_count_fails_warmup(tmp_path):
    d = _good_dir(tmp_path)
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    narrow = LogisticRegression().fit(np.array([[0.0], [1.0], [0.2], [0.9]]), [0, 1, 0, 1])
    joblib.dump(narrow, d / S.MODEL_FILENAME)
    _edit_meta(d, sha256_model=S.sha256_file(d / S.MODEL_FILENAME))
    with pytest.raises(S.ArtifactError, match="warm-up prediction failed"):
        S.load_artifacts(d)


def test_version_parse_and_format_round_trip():
    assert S.parse_version("proofhire-lr-2.10.3") == (2, 10, 3)
    assert S.format_version(2, 10, 3) == "proofhire-lr-2.10.3"
    for bad in ("", "proofhire-lr-1.0", "proofhire-rf-1.0.0", "proofhire-lr-1.0.0-beta"):
        with pytest.raises(S.ArtifactError):
            S.parse_version(bad)
