"""Committed-artifact tests (Member 1, guidebook A15 test_artifacts.py + A-G3): sha256, versions, schema of
model_meta.json / metrics.json, and consistency between model.joblib, metrics.json and the dataset.
Run: PYTHONPATH=backend pytest ml/tests -q"""
import json

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402

ART = S.ARTIFACT_DIR
if not (ART / S.META_FILENAME).is_file():
    pytest.skip("no committed artifacts yet (run train.py, evaluate.py, export_artifacts.py)", allow_module_level=True)

META = json.loads((ART / S.META_FILENAME).read_text(encoding="utf-8"))
METRICS = json.loads((ART / S.METRICS_FILENAME).read_text(encoding="utf-8"))
LOADABLE_HERE = META["sklearn_version"] == S.running_sklearn_version()


def test_three_artifacts_exist_with_exact_filenames_and_size_limit():
    for name in ("model.joblib", "model_meta.json", "metrics.json"):
        assert (ART / name).is_file(), name
    assert (ART / S.MODEL_FILENAME).stat().st_size < 10 * 1024 * 1024


def test_sha256_matches():
    assert S.sha256_file(ART / S.MODEL_FILENAME) == META["sha256_model"]


def test_sklearn_version_equals_pinned_1_7_2():
    """Guidebook A15. Only meaningful where scikit-learn 1.7.2 is installed; elsewhere it is skipped, not faked."""
    if S.running_sklearn_version() != S.REQUIRED_SKLEARN_VERSION:
        pytest.skip(f"running scikit-learn {S.running_sklearn_version()} != pinned {S.REQUIRED_SKLEARN_VERSION}; "
                    "run this test in the pinned environment")
    assert META["sklearn_version"] == S.REQUIRED_SKLEARN_VERSION, (
        f"artifact was trained with scikit-learn {META['sklearn_version']}; retrain and re-export with "
        f"{S.REQUIRED_SKLEARN_VERSION}: PYTHONPATH=backend python ml/train.py && python ml/evaluate.py && "
        "python ml/export_artifacts.py")


def test_meta_has_exactly_the_guidebook_keys():
    assert set(META) == set(S.REQUIRED_META_KEYS)
    S.validate_meta(META)
    assert META["selected_model"] in ("M3", "M4")
    assert set(META["dataset"]) == {"type", "rows", "seed", "generator_commit"} and META["dataset"]["type"] == "synthetic"
    assert META["trained_at"].endswith("Z")
    assert isinstance(META["feedback_rows"], int) and META["feedback_rows"] >= 0  # > 0 after a promoted retrain
    assert set(META["thresholds"]) == {"low", "high"}


def test_meta_matches_feature_and_dataset_contracts():
    assert META["feature_order"] == F.FEATURE_ORDER
    prov = M.read_dataset_provenance()
    assert META["dataset"]["seed"] == prov["seed"] and META["dataset"]["generator_commit"] == prov["generator_commit"]
    assert META["dataset"]["rows"] == len(M.load_dataset(M.DEFAULT_CSV))


def test_metrics_json_has_exactly_the_guidebook_shape():
    assert set(METRICS) == {"synthetic_test", "baselines", "pattern_holdout", "handwritten", "cv", "limitations"}
    assert set(METRICS["synthetic_test"]) == {"precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion"}
    (tn, fp), (fn, tp) = METRICS["synthetic_test"]["confusion"]
    assert min(tn, fp, fn, tp) >= 0
    assert set(METRICS["baselines"]) == {"M0", "M1", "M2", "M3", "M4"}
    assert set(METRICS["pattern_holdout"]) == {"recall", "n"}
    assert set(METRICS["handwritten"]) == {"precision", "recall", "n"}
    assert set(METRICS["cv"]) == {"pr_auc_mean", "pr_auc_std"}
    assert METRICS["limitations"] and all(isinstance(x, str) and x for x in METRICS["limitations"])
    for key in ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier"):
        assert 0.0 <= METRICS["synthetic_test"][key] <= 1.0


def test_handwritten_is_null_exactly_when_no_rows_were_scored():
    hw = METRICS["handwritten"]
    if hw["n"] == 0:
        assert hw["precision"] is None and hw["recall"] is None  # never a made-up number
    else:
        assert 0.0 <= hw["precision"] <= 1.0 and 0.0 <= hw["recall"] <= 1.0


def test_metrics_counts_agree_with_the_dataset():
    df = M.load_dataset(M.DEFAULT_CSV)
    (tn, fp), (fn, tp) = METRICS["synthetic_test"]["confusion"]
    assert tn + fp + fn + tp == int((df["split"] == "test").sum())
    assert tp + fn == int(((df["split"] == "test") & (df["label"] == "1")).sum())
    hold = df[(df["split"] == "holdout") & (df["label"] == "1")]
    assert METRICS["pattern_holdout"]["n"] == len(hold)


def test_metrics_reproduce_from_the_artifact_on_the_test_split():
    if not LOADABLE_HERE:
        pytest.skip(f"artifact trained with scikit-learn {META['sklearn_version']}, running {S.running_sklearn_version()}")
    loaded = S.load_artifacts(ART)
    X, y = M.build_matrix(M.load_dataset(M.DEFAULT_CSV).query("split == 'test'"))
    again = M.compute_metrics(y, M.positive_scores(loaded.pipeline, X))
    for key in ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion"):
        assert again[key] == METRICS["synthetic_test"][key], key


def test_thresholds_in_meta_follow_the_a6_rules():
    low, high = META["thresholds"]["low"], META["thresholds"]["high"]
    assert 0.0 <= low < high <= 1.0
    if (low, high) != (0.35, 0.70):  # derived from the val PR curve -> the gap rule must hold
        assert high - low >= 0.15


def test_full_report_agrees_with_shipped_artifacts():
    path = M.REPORTS_DIR / "metrics_full.json"
    if not path.is_file():
        pytest.skip("ml/reports/metrics_full.json not present")
    full = json.loads(path.read_text(encoding="utf-8"))
    assert full["metrics_json"] == METRICS
    assert full["thresholds"] == META["thresholds"]
    assert full["selected_model"] == META["selected_model"] and full["trained_at"] == META["trained_at"]
    assert full["sklearn_version"] == META["sklearn_version"]


def test_committed_artifact_loads_in_this_environment():
    if not LOADABLE_HERE:
        pytest.skip(f"artifact trained with scikit-learn {META['sklearn_version']}, running {S.running_sklearn_version()}")
    loaded = S.load_artifacts(ART)
    assert loaded.meta["model_version"] == META["model_version"] and loaded.metrics == METRICS
