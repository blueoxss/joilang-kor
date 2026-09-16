from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def parity() -> dict:
    return json.loads((ROOT / "tests/fixtures/parity_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def schema():
    from joilang_kor.schema import load_service_schema

    return load_service_schema(ROOT / "schemas/service_list_ver2.0.1.json")


@pytest.fixture(scope="session")
def rows():
    from joilang_kor.data import load_dataset_rows

    return load_dataset_rows(ROOT / "datasets/JOICommands-280.csv")


@pytest.fixture(scope="session")
def pipeline():
    from joilang_kor.pipeline import Pipeline

    return Pipeline(
        schema_path=ROOT / "schemas/service_list_ver2.0.1.json",
        blocks_dir=ROOT / "prompts/initial_blocks",
        source_prompt_dir=ROOT / "prompts/source_prompt",
        feedback_rules_path=ROOT / "prompts/feedback_rules.json",
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """테스트 중 어떤 HTTP 요청도 나가지 않아야 한다."""
    import urllib.request

    def _blocked(*args, **kwargs):
        raise AssertionError("network access attempted during tests")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
