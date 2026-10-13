"""Training contract tests (Member 1, A-G3): model definitions, selection rule, metrics, thresholds, feature contract.
Run: PYTHONPATH=backend pytest ml/tests -q"""
import numpy as np
import pytest

pytest.importorskip("sklearn")

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402


# ---------------------------------------------------------------- A5 model definitions
def test_model_hyperparameters_match_guidebook():
    m0, m1, m2, m3, m4 = (M.make_model(i) for i in ("M0", "M1", "M2", "M3", "M4"))
    assert (m0.strategy, m0.random_state) == ("stratified", 42)
    for m in (m1, m3):
        clf = m.named_steps["clf"]
        assert (clf.C, clf.solver, clf.max_iter) == (1.0, "liblinear", 500) and clf.class_weight is None
    assert m3.named_steps["clf"].random_state == 42
    rf = m2.named_steps["clf"]
    assert (rf.n_estimators, rf.max_depth, rf.min_samples_leaf, rf.n_jobs, rf.random_state) == (200, 12, 3, 1, 42)
    hgb = m4.named_steps["clf"]
    assert (hgb.max_iter, hgb.learning_rate, hgb.max_depth, hgb.random_state) == (200, 0.08, 6, 42)


def test_m3_preprocessing_is_exactly_the_prescribed_columntransformer():
    prep = M.make_model("M3").named_steps["prep"]
    names = [t[0] for t in prep.transformers]
    assert names == ["tfidf", "num", "bin", "cat"]
    tf = prep.transformers[0][1]
    assert (tf.ngram_range, tf.min_df, tf.max_features, tf.sublinear_tf, tf.strip_accents) == ((1, 2), 3, 3000, True, "unicode")
    assert type(prep.transformers[1][1]).__name__ == "StandardScaler"
    assert prep.transformers[2][1] == "passthrough"
    assert prep.transformers[3][1].handle_unknown == "ignore"


def test_column_selectors_follow_the_feature_contract():
    cols = F.MODEL_INPUT_COLUMNS
    assert cols == [F.TEXT_COL] + F.FEATURE_ORDER and cols[0] == "text" and len(cols) == 27
    assert cols[M.TEXT_IDX] == "text"
    assert [cols[i] for i in M.NUM_IDX] == F.NUM_COLS
    assert [cols[i] for i in M.BIN_IDX] == F.BIN_COLS
    assert [cols[i] for i in M.CAT_IDX] == F.CAT_COLS


def test_unknown_model_id_rejected():
    with pytest.raises(ValueError):
        M.make_model("M9")


# ---------------------------------------------------------------- feature compatibility (training == inference)
RISKY = {"title": "Data Entry Intern - Earn 40000 per month!!", "company_name": "Brightpath Careers",
         "description": "Work from home. No experience needed. Pay registration fee of Rs 1499 to confirm your seat. "
                        "Apply today, limited seats!", "salary_min": "40000", "salary_max": "40000",
         "contact_email": "brightpath.hr@gmail.com", "application_channel": "whatsapp",
         "upfront_fee_amount": "1499", "interview_mode": "chat_only"}


def test_train_and_inference_matrices_are_identical_and_fit_every_model():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame([RISKY, RISKY | {"title": "UI Designer Intern", "contact_email": "careers@nexora.com",
                                         "company_website": "https://nexora.com"}])
    df = df.fillna("")  # the real loader reads blanks as '' (keep_default_na=False)
    df["label"] = ["1", "0"]
    X, y = M.build_matrix(df)
    assert X.shape == (2, len(F.MODEL_INPUT_COLUMNS)) and X.dtype == object and y.tolist() == [1, 0]
    assert np.array_equal(X[0], np.array(F.model_input_values(RISKY), dtype=object))
    assert np.array_equal(S._model_matrix([RISKY])[0], X[0])  # exact runtime path


def test_pipelines_fit_on_object_matrix_without_pandas_input():
    pd = pytest.importorskip("pandas")
    base = M.load_dataset(M.DEFAULT_CSV).head(400)
    X, y = M.build_matrix(base)
    for mid in ("M0", "M1", "M2", "M3", "M4"):
        p = M.make_model(mid).fit(X, y)
        proba = p.predict_proba(X[:5])
        assert proba.shape == (5, 2) and np.all((proba >= 0) & (proba <= 1))
        assert getattr(p, "n_features_in_", len(F.MODEL_INPUT_COLUMNS)) == len(F.MODEL_INPUT_COLUMNS) or mid == "M0"


# ---------------------------------------------------------------- A5 step 6: selection rule
def test_selection_keeps_m3_when_m4_does_not_win_by_more_than_margin():
    assert M.select_model(0.95, 0.96)[0] == "M3"
    assert M.select_model(0.96, 0.90)[0] == "M3"


def test_selection_needs_both_margin_and_team_acceptance():
    sel, why = M.select_model(0.90, 0.9201, accept_challenger=False)
    assert sel == "M3" and "NOT accepted" in why
    assert M.select_model(0.90, 0.9201, accept_challenger=True)[0] == "M4"
    assert M.select_model(0.90, 0.9199, accept_challenger=True)[0] == "M3"


# ---------------------------------------------------------------- metrics
def test_compute_metrics_known_values():
    m = M.compute_metrics([0, 0, 1, 1], [0.1, 0.6, 0.4, 0.9])
    assert m["confusion"] == [[1, 1], [1, 1]]
    assert (m["accuracy"], m["precision"], m["recall"], m["f1"]) == (0.5, 0.5, 0.5, 0.5)
    assert m["roc_auc"] == 0.75 and m["pr_auc"] == 0.8333 and m["brier"] == 0.185


def test_compute_metrics_single_class_has_null_auc():
    m = M.compute_metrics([1, 1, 1], [0.9, 0.2, 0.7])
    assert m["roc_auc"] is None and m["pr_auc"] is None and m["recall"] == 0.6667


# ---------------------------------------------------------------- A6 thresholds
def _scores(neg_hi, pos_lo, seed=0):
    """300 negatives ~ U(0, neg_hi); 300 positives: 15 low (U(0, .2 or .1)) + 285 ~ U(pos_lo, 1)."""
    rng = np.random.default_rng(seed)
    y = np.array([0] * 300 + [1] * 300)
    stragglers = rng.uniform(0, min(pos_lo, 0.2), 15)
    s = np.concatenate([rng.uniform(0, neg_hi, 300), stragglers, rng.uniform(pos_lo, 1.0, 285)])
    return y, s


def test_thresholds_from_val_curve_when_rules_hold():
    y, s = _scores(neg_hi=0.7, pos_lo=0.2)
    th = M.select_thresholds(y, s)
    assert th["source"] == "val_pr_curve" and th["low"] < th["high"] and th["high"] - th["low"] >= 0.15
    assert (y[s >= th["high"]] == 1).mean() >= 0.90  # precision rule holds at `high`
    assert (s[y == 1] >= th["low"]).mean() >= 0.95  # recall rule holds at `low`
    for t in np.unique(s):  # high is the SMALLEST score meeting precision, low the LARGEST meeting recall
        if t < th["high"] - 1e-4:
            assert (y[s >= t] == 1).mean() < 0.90
        if t > th["low"] + 1e-4:
            assert (s[y == 1] >= t).mean() < 0.95


def test_thresholds_fall_back_when_gap_below_0_15():
    y, s = _scores(neg_hi=0.5, pos_lo=0.33)
    th = M.select_thresholds(y, s)
    assert 0 < th["raw_high"] - th["raw_low"] < 0.15  # fixture really is a narrow-gap case
    assert th["source"] == "fallback" and (th["low"], th["high"]) == (0.35, 0.70) and "gap" in th["reason"]


def test_thresholds_fall_back_when_inverted():
    # Perfectly separated scores: the literal A6 rules give high (~0.28) BELOW low (~0.63) -> inverted -> fallback.
    rng = np.random.default_rng(0)
    y = np.array([0] * 300 + [1] * 300)
    s = np.concatenate([rng.uniform(0.0, 0.30, 300), rng.uniform(0.60, 1.0, 300)])
    th = M.select_thresholds(y, s)
    assert th["raw_low"] >= th["raw_high"]
    assert th["source"] == "fallback" and (th["low"], th["high"]) == (0.35, 0.70) and "inverted" in th["reason"]


def test_thresholds_fall_back_when_precision_never_reaches_target():
    rng = np.random.default_rng(1)
    y = np.array([0, 1] * 100)
    th = M.select_thresholds(y, rng.uniform(0, 1, 200))
    assert th["source"] == "fallback" and th["raw_high"] is None and (th["low"], th["high"]) == (0.35, 0.70)


def test_risk_level_boundaries():
    th = {"low": 0.35, "high": 0.70}
    assert S.level_for(0.70, th) == "high" and S.level_for(0.6999, th) == "medium"
    assert S.level_for(0.35, th) == "medium" and S.level_for(0.3499, th) == "low"


# ---------------------------------------------------------------- dataset provenance
def test_dataset_provenance_is_read_from_readme():
    prov = M.read_dataset_provenance()
    assert prov["seed"] == 42 and len(prov["csv_sha256"]) == 64
    assert prov["generator_commit"] is None or isinstance(prov["generator_commit"], str)
