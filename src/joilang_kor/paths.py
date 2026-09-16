"""저장소 자료(데이터·스키마·프롬프트)의 기본 경로 해석.

editable 설치(pip install -e .) 또는 저장소 checkout 안에서 실행하면 자료를 자동으로 찾는다.
일반 설치(site-packages)에서는 저장소 루트를 찾지 못하므로 CLI 옵션으로 경로를 명시해야 한다.
"""
from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

DATASET_FILE = "datasets/JOICommands-280.csv"
SCHEMA_FILE = "schemas/service_list_ver2.0.1.json"
RETRIEVAL_CORPUS_FILE = "schemas/service_retrieval_corpus.json"
SOURCE_PROMPT_DIR = "prompts/source_prompt"
BLOCKS_DIR = "prompts/initial_blocks"
FEEDBACK_RULES_FILE = "prompts/feedback_rules.json"


def find_repo_root() -> Path | None:
    """`datasets/JOICommands-280.csv` 와 `prompts/` 를 함께 가진 상위 디렉터리를 찾는다."""
    for base in (PACKAGE_DIR, Path.cwd()):
        for directory in [base, *base.parents]:
            if (directory / DATASET_FILE).is_file() and (directory / SOURCE_PROMPT_DIR).is_dir():
                return directory
    return None


def default_path(relative: str, explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = find_repo_root()
    if root is None:
        raise FileNotFoundError(
            f"저장소 자료 '{relative}' 를 찾을 수 없습니다. 저장소 checkout 안에서 실행하거나 경로를 명시하세요."
        )
    return root / relative
