"""Runtime inference must stay light (guidebook D5 / A14): no pandas, no training code, no test framework.
Static check of every runtime module's imports + a subprocess check of what actually gets imported.
Run: PYTHONPATH=backend pytest ml/tests -q"""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNTIME_FILES = sorted((BACKEND / "app" / "ml").glob("*.py")) + [
    BACKEND / "app" / "routers" / "ml.py", BACKEND / "app" / "schemas" / "ml_schemas.py"]
FORBIDDEN = {"pandas", "matplotlib", "pytest", "xgboost", "seaborn", "modeling", "train", "evaluate", "retrain",
             "export_artifacts", "rebuild_artifacts", "generate_synthetic", "lexicons"}
ALLOWED_THIRD_PARTY = {"numpy", "scipy", "sklearn", "joblib", "httpx", "pydantic", "fastapi", "starlette"}


def _imported_roots(path: Path) -> set:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_runtime_modules_import_nothing_forbidden():
    assert RUNTIME_FILES
    for path in RUNTIME_FILES:
        bad = _imported_roots(path) & FORBIDDEN
        assert not bad, f"{path.relative_to(ROOT)} imports training/test-only modules: {sorted(bad)}"


def test_runtime_third_party_imports_are_the_guidebook_set():
    stdlib = set(sys.stdlib_module_names)
    for path in RUNTIME_FILES:
        extra = {r for r in _imported_roots(path) if r not in stdlib and r not in ALLOWED_THIRD_PARTY and r != "app"}
        assert not extra, f"{path.relative_to(ROOT)} imports unexpected packages: {sorted(extra)}"


def _run_blocked(code: str, art_dir: Path):
    """Run `code` in a fresh interpreter where importing pandas / matplotlib / pytest RAISES ModuleNotFoundError (as on Render,
    where they are not installed), with ARTIFACT_DIR pointing at `art_dir`. Returns the parsed JSON on the last stdout line."""
    import os

    prelude = ("import sys, json\n"
               "class _Block:\n"
               "    def find_spec(self, name, path=None, target=None):\n"
               "        if name.split('.')[0] in ('pandas', 'matplotlib', 'pytest'):\n"
               "            raise ModuleNotFoundError(f'{name} is not installed (simulated Render runtime)')\n"
               "sys.meta_path.insert(0, _Block())\n"
               "import app.ml.model_store as S\nfrom pathlib import Path\nS.ARTIFACT_DIR = Path(sys.argv[1])\n")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TEMP", "TMP")}
    env["PYTHONPATH"] = str(BACKEND)
    r = subprocess.run([sys.executable, "-c", prelude + code, str(art_dir)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def _tiny_artifacts(tmp_path):
    pytest.importorskip("pandas")  # only to TRAIN the throw-away model here; the subprocess runs without it
    from test_model_store import _good_dir

    return _good_dir(tmp_path)


def test_model_loads_and_scores_with_pandas_unavailable(tmp_path):
    pytest.importorskip("sklearn")
    art = _tiny_artifacts(tmp_path)
    out = _run_blocked(
        "L = S.load_artifacts(S.ARTIFACT_DIR)\n"
        "score = S.predict_score(L, {'title': 'Data Entry Intern', 'company_name': 'Brightpath', 'description': "
        "'Pay a registration fee of Rs 1499 to confirm your seat today.', 'upfront_fee_amount': 1499})\n"
        "print(json.dumps({'score': score, 'project': sorted(m for m in sys.modules if m.split('.')[0] in "
        "('modeling', 'train', 'retrain', 'evaluate', 'export_artifacts'))}))", art)
    assert 0.0 <= out["score"] <= 1.0 and out["project"] == []


def test_whole_service_runs_with_pandas_unavailable_and_without_llm_keys(tmp_path):
    pytest.importorskip("pydantic")
    pytest.importorskip("fastapi")
    pytest.importorskip("sklearn")
    art = _tiny_artifacts(tmp_path)
    out = _run_blocked(
        "import app.routers.ml, app.ml.llm_client\nfrom app.ml import pipeline as P\n"
        "from app.schemas.ml_schemas import ListingInput\nP.load_model()\nassert P.model_status()['loaded'], P.get_load_error()\n"
        "r = P.assess_listing(ListingInput(title='Data Entry Intern', company_name='Brightpath Careers', "
        "description='Pay a registration fee of Rs 1499 to confirm your seat today.', upfront_fee_amount=1499))\n"
        "print(json.dumps({'score': r.risk_score, 'source': r.explanation.source.value, 'project': sorted(m for m in "
        "sys.modules if m.split('.')[0] in ('modeling', 'train', 'retrain', 'evaluate', 'export_artifacts'))}))", art)
    assert 0.0 <= out["score"] <= 1.0 and out["source"] == "template" and out["project"] == []
