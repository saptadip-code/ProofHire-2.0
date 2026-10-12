"""Path setup so `pytest ml/tests -q` works with or without PYTHONPATH=backend (Member 1)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "backend", ROOT / "ml" / "data", ROOT / "ml"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


import os  # noqa: E402

import pytest  # noqa: E402

_LLM_VARS = ("LLM_ENABLED", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_API_KEY",
             "LLM_FALLBACK_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_MAX_TOKENS", "LLM_TEMPERATURE", "LLM_RPM_LIMIT",
             "LLM_CACHE_SIZE", "LLM_CACHE_TTL_SECONDS")


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """Every test starts with the LLM switched off and no keys, whatever is in the developer's shell or .env, so no
    test can ever reach a real provider. Tests that need the LLM set the variables and replace llm_client._post_json."""
    for name in _LLM_VARS:
        monkeypatch.delenv(name, raising=False)
    try:
        from app.ml import llm_client
    except ImportError:  # pydantic / sklearn missing: the modules that need it skip themselves
        yield
        return
    llm_client.reset_state()
    yield
    llm_client.reset_state()
