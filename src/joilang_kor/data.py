"""JOICommands-280 로더와 정합성 검사.

원본: pipeline_common.py 의
load_dataset_rows / select_rows / parse_connected_devices 를 그대로 옮겼다.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .evaluation import gt_code, parse_json_object

EXPECTED_CATEGORY_COUNTS = {"1": 30, "2": 30, "3": 30, "4": 30, "5": 30, "6": 30, "7": 50, "8": 50}
REQUIRED_COLUMNS = ("index", "category", "command_kor", "command_eng", "connected_devices", "gt")


def load_dataset_rows(dataset_path: str | Path) -> list[dict[str, str]]:
    with Path(dataset_path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_categories(values: list[str] | tuple[str, ...] | None) -> set[str]:
    normalized: set[str] = set()
    for raw in values or []:
        for item in str(raw).split(","):
            token = item.strip()
            if token:
                normalized.add(token)
    return normalized


def select_rows(
    rows: list[dict[str, str]],
    *,
    start_row: int = 1,
    end_row: int | None = None,
    limit: int | None = None,
    categories: list[str] | tuple[str, ...] | None = None,
) -> list[tuple[int, dict[str, str]]]:
    """(1부터 세는 행 번호, 행) 목록. 행 번호는 CSV의 물리적 순서다."""
    selected: list[tuple[int, dict[str, str]]] = []
    if start_row < 1:
        start_row = 1
    last = end_row if end_row is not None else len(rows)
    category_filter = normalize_categories(categories)
    for idx, row in enumerate(rows, start=1):
        if idx < start_row or idx > last:
            continue
        category = str(row.get("category", "")).strip()
        if category_filter and category not in category_filter:
            continue
        selected.append((idx, row))
        if limit is not None and len(selected) >= limit:
            break
    return selected


def parse_connected_devices(value: Any) -> dict[str, Any]:
    """CSV의 connected_devices 셀(JSON 또는 Python 리터럴 형식)을 dict로 읽는다. 비어 있으면 {}."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):   # 원본과 같이 어느 파서도 못 읽으면 {}
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def parse_reference(gt_text: Any) -> dict[str, Any]:
    """기준 출력(gt 열)을 JSON 객체로 읽는다(평가기와 같은 파서). 키는 name, cron, period, script 다.
    기준 코드 문자열은 evaluation.gt_code(reference) 로 얻는다."""
    return parse_json_object(gt_text, label="gt")


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_dataset(dataset_path: str | Path) -> dict[str, Any]:
    """행 수·범주 구성·필수 열·기준 JSON·(category,index) 유일성을 검사한다.

    index 열은 범주 안에서만 유일하다(각 범주 1..N). 전역 식별자는 (category, index)
    또는 CSV 행 번호다. 검사는 파일을 수정하지 않는다.
    """
    rows = load_dataset_rows(dataset_path)
    problems: list[str] = []
    columns = list(rows[0].keys()) if rows else []
    for column in REQUIRED_COLUMNS:
        if column not in columns:
            problems.append(f"missing column: {column}")
    category_counts = Counter(str(r.get("category", "")).strip() for r in rows)
    if dict(category_counts) != EXPECTED_CATEGORY_COUNTS:
        problems.append(f"category counts {dict(sorted(category_counts.items()))} != {EXPECTED_CATEGORY_COUNTS}")
    if len(rows) != 280:
        problems.append(f"row count {len(rows)} != 280")

    keys = Counter((str(r.get("category", "")).strip(), str(r.get("index", "")).strip()) for r in rows)
    duplicates = sorted(k for k, n in keys.items() if n > 1)
    if duplicates:
        problems.append(f"duplicate (category,index): {duplicates[:5]}")

    reference_errors: list[str] = []
    empty_reference_code = 0
    empty_command = 0
    connected_rows = 0
    for row_no, row in enumerate(rows, start=1):
        try:
            ref = parse_reference(row.get("gt", ""))
            if not gt_code(ref).strip():
                empty_reference_code += 1
        except ValueError as exc:
            reference_errors.append(f"row {row_no}: {exc}")
        if not str(row.get("command_eng", "")).strip():
            empty_command += 1
        if parse_connected_devices(row.get("connected_devices")):
            connected_rows += 1
    if reference_errors:
        problems.append(f"unparseable gt: {reference_errors[:3]}")
    if empty_reference_code:
        problems.append(f"empty reference code rows: {empty_reference_code}")
    if empty_command:
        problems.append(f"empty command_eng rows: {empty_command}")

    return {
        "dataset": str(Path(dataset_path)),
        "sha256": sha256_file(dataset_path),
        "rows": len(rows),
        "columns": columns,
        "category_counts": dict(sorted(category_counts.items())),
        "unique_category_index_pairs": len(keys),
        "rows_with_connected_devices": connected_rows,
        "problems": problems,
        "ok": not problems,
    }
