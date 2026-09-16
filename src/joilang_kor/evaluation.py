"""DET 평가기(8항 비교, 기준 가중치, 통과 임계값 0.90).

원본: 8항 평가기(det_evaluator.py, strict_det_evaluate_row). 비교값 계산 함수(similarity, extract_*,
coverage_score, precision_score, dataflow_heuristic_score)와 계산 순서를 그대로 옮겼다. 공개 평가 경로
`evaluate_item` 은 여덟 비교값의 가중합 e(0–1)와 τ=0.90 을 적용한다. `original_det_evaluate_row` 는 원본 함수의
결과 형식(0–100 점수, 임계값 70)을 같은 비교값 위에서 재현하며 대조 테스트에만 쓴다.

비교값의 순서와 이름(원고 표의 k=1..8):
 1 code_similarity          공백 제거 후 SequenceMatcher(기본 설정) ratio
 2 schedule_match           정규화한 cron, period 일치 여부 평균
 3 required_service_recall  기준 서비스 목록의 포함률(중복 반영)
 4 service_precision        생성 서비스 목록의 정밀도
 5 receiver_coverage        기준 수신 대상 문자열 포함률
 6 numeric_grounding        기준 수치 문자열 포함률
 7 string_enum_grounding    따옴표 내부 문자열 포함률
 8 declaration_count        var/let/const 선언 수 비율(최대 1)
정적 참조 비교이며 실행 의미의 동등성을 검증하지 않는다.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from typing import Any

SERVICE_CALL_RE = re.compile(r"\([^)]*\)\.([A-Za-z_][A-Za-z0-9_]*)")
RECEIVER_RE = re.compile(r"\(([^)]*)\)\.")
NUMERIC_RE = re.compile(r"(?<![A-Za-z_])-?\d+(?:\.\d+)?")
STRING_ARG_RE = re.compile(r"['\"]([^'\"]+)['\"]")

COMPONENT_KEYS = (
    "code_similarity",
    "schedule_match",
    "required_service_recall",
    "service_precision",
    "receiver_coverage",
    "numeric_grounding",
    "string_enum_grounding",
    "declaration_count",
)
BASE_WEIGHTS = (0.30, 0.15, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05)
DEFAULT_THRESHOLD = 0.90
HARD_GATE_REASONS = ("invalid_json", "missing_official_gt", "missing_generated_code")


def parse_json_object(value: Any, *, label: str) -> dict[str, Any]:
    if isinstance(value, list):
        if not value:
            raise ValueError(f"{label} is an empty list")
        value = value[0]
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if isinstance(parsed, list):
        if not parsed:
            raise ValueError(f"{label} is an empty JSON list")
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def normalize_candidate(candidate: Any) -> dict[str, Any]:
    parsed = parse_json_object(candidate, label="generated candidate")
    return {
        "name": str(parsed.get("name", "")),
        "cron": str(parsed.get("cron", "")),
        "period": parsed.get("period", 0),
        "code": str(parsed.get("code") or parsed.get("script") or ""),
    }


def gt_code(gt_json: dict[str, Any]) -> str:
    return str(gt_json.get("code") or gt_json.get("script") or "")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def extract_services(code: str) -> list[str]:
    return SERVICE_CALL_RE.findall(str(code or ""))


def extract_receivers(code: str) -> list[str]:
    return [normalize_text(item) for item in RECEIVER_RE.findall(str(code or ""))]


def extract_numeric_literals(code: str) -> list[str]:
    return NUMERIC_RE.findall(str(code or ""))


def extract_string_args(code: str) -> list[str]:
    return [normalize_text(item).lower() for item in STRING_ARG_RE.findall(str(code or ""))]


def coverage_score(reference_items: list[str], generated_items: list[str]) -> float:
    if not reference_items:
        return 1.0
    ref_counter = Counter(reference_items)
    gen_counter = Counter(generated_items)
    covered = sum(min(count, gen_counter.get(item, 0)) for item, count in ref_counter.items())
    return covered / sum(ref_counter.values())


def precision_score(reference_items: list[str], generated_items: list[str]) -> float:
    if not generated_items:
        return 1.0 if not reference_items else 0.0
    ref_counter = Counter(reference_items)
    gen_counter = Counter(generated_items)
    matched = sum(min(count, ref_counter.get(item, 0)) for item, count in gen_counter.items())
    return matched / sum(gen_counter.values())


def dataflow_heuristic_score(reference_code: str, generated_code: str) -> float:
    ref_assignments = len(re.findall(r"\b(?:var|let|const)\s+[A-Za-z_][A-Za-z0-9_]*\s*=", reference_code or ""))
    gen_assignments = len(re.findall(r"\b(?:var|let|const)\s+[A-Za-z_][A-Za-z0-9_]*\s*=", generated_code or ""))
    if ref_assignments == 0:
        return 1.0
    if gen_assignments >= ref_assignments:
        return 1.0
    return gen_assignments / ref_assignments


def compare_bool(left: Any, right: Any) -> bool:
    return normalize_text(left) == normalize_text(right)


def compute_components(gt_json: dict[str, Any], generated_json: dict[str, Any]) -> tuple[list[float], list[str]]:
    """여덟 비교값(반올림 없음)과 실패 유형. 원본 strict_det_evaluate_row 의 계산부와 같다."""
    failure_reasons: list[str] = []
    reference_code = gt_code(gt_json)
    generated_code = str(generated_json.get("code") or "")
    if not reference_code:
        failure_reasons.append("missing_gt_code")
    if not generated_code:
        failure_reasons.append("missing_generated_code")

    cron_match = compare_bool(gt_json.get("cron", ""), generated_json.get("cron", ""))
    period_match = compare_bool(gt_json.get("period", ""), generated_json.get("period", ""))
    if not cron_match:
        failure_reasons.append("cron_mismatch")
    if not period_match:
        failure_reasons.append("period_mismatch")

    code_sim = similarity(reference_code, generated_code) if reference_code and generated_code else 0.0
    if not code_sim >= 0.995:
        failure_reasons.append("gt_mismatch")

    ref_service_list = extract_services(reference_code)
    gen_service_list = extract_services(generated_code)
    service_coverage = coverage_score(ref_service_list, gen_service_list)
    service_precision = precision_score(ref_service_list, gen_service_list)
    if ref_service_list and service_coverage < 0.999:
        failure_reasons.append("gt_service_coverage")
    if gen_service_list and service_precision < 0.999:
        failure_reasons.append("unknown_service")

    receiver_coverage = coverage_score(extract_receivers(reference_code), extract_receivers(generated_code))
    if not receiver_coverage >= 0.999:
        failure_reasons.append("gt_receiver_coverage")

    numeric_grounding = coverage_score(extract_numeric_literals(reference_code), extract_numeric_literals(generated_code))
    if numeric_grounding < 0.999:
        failure_reasons.append("numeric_grounding")
    enum_grounding = coverage_score(extract_string_args(reference_code), extract_string_args(generated_code))
    if enum_grounding < 0.999:
        failure_reasons.append("enum_grounding")
    dataflow_score = dataflow_heuristic_score(reference_code, generated_code)
    if dataflow_score < 0.999:
        failure_reasons.append("dataflow")

    schedule_score = 1.0 if cron_match and period_match else (0.5 if cron_match or period_match else 0.0)
    components = [
        code_sim,
        schedule_score,
        service_coverage,
        service_precision,
        receiver_coverage,
        numeric_grounding,
        enum_grounding,
        dataflow_score,
    ]
    return components, failure_reasons


def weighted_score(components: list[float], weights: tuple[float, ...] = BASE_WEIGHTS) -> float:
    if len(weights) != len(COMPONENT_KEYS) or abs(sum(weights) - 1.0) > 1e-9 or any(w < 0 for w in weights):
        raise ValueError("weights must be eight non-negative values summing to 1")
    return sum(w * s for w, s in zip(weights, components))


def _parse_pair(reference: Any, candidate: Any) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """기준·후보를 읽어 (gt_json, generated_json, 하드 게이트 사유)를 돌려준다."""
    reasons: list[str] = []
    try:
        gt_json = parse_json_object(reference, label="gt")
    except ValueError as exc:
        reasons.append("missing_official_gt")
        gt_json = {"_error": str(exc)}
    try:
        generated_json = normalize_candidate(candidate)
    except ValueError as exc:
        reasons.append("invalid_json")
        generated_json = {"_error": str(exc), "name": "", "cron": "", "period": "", "code": ""}
    return gt_json, generated_json, reasons


def _dedupe(reasons: list[str]) -> list[str]:
    unique: list[str] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return unique


def evaluate_item(
    reference: Any,
    candidate: Any,
    *,
    weights: tuple[float, ...] = BASE_WEIGHTS,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """평가 항목 하나의 DET 결과.

    reference: gt 열 문자열 또는 JSON 객체(script 또는 code 키). candidate: 생성 출력 문자열/객체.
    파싱 실패면 e=0, v=0. 파싱 후 code 가 비면 v=0(비교값은 남는다). 통과 = v=1 이고 e >= τ.
    """
    gt_json, generated_json, failure_reasons = _parse_pair(reference, candidate)
    components, reasons = compute_components(gt_json, generated_json)
    failure_reasons.extend(reasons)
    e = weighted_score(components, weights)
    if "invalid_json" in failure_reasons or "missing_official_gt" in failure_reasons:
        e = 0.0
    v = 1 if not any(r in failure_reasons for r in HARD_GATE_REASONS) else 0
    det_pass = bool(v == 1 and e >= float(threshold))
    unique_reasons = _dedupe(failure_reasons)
    return {
        "components": dict(zip(COMPONENT_KEYS, components)),
        "e": e,
        "v": v,
        "det_pass": det_pass,
        "threshold": float(threshold),
        "weights": list(weights),
        "failure_reasons": unique_reasons,
        "reference_code": gt_code(gt_json),
        "generated_code": str(generated_json.get("code") or ""),
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    passed = sum(1 for r in results if r["det_pass"])
    return {
        "n": n,
        "passed": passed,
        "detpass": passed / n if n else 0.0,
        "sdet": sum(float(r["e"]) for r in results) / n if n else 0.0,
    }


def original_det_evaluate_row(*, row: dict[str, Any], candidate: Any, row_no: int | str,
                              det_threshold: float = 70.0) -> dict[str, Any]:
    """원본 8항 평가기 함수(0–100 점수, 임계값 70)의 결과 형식을 compute_components 위에서 재현한다.

    공개 경로는 evaluate_item 이다. 이 함수는 원본 결과와의 대조 테스트(tests/fixtures/parity_cases.json)에 쓴다.
    """
    gt_json, generated_json, failure_reasons = _parse_pair(row.get("gt"), candidate)
    components, reasons = compute_components(gt_json, generated_json)
    failure_reasons.extend(reasons)
    code_sim, schedule, service_coverage, service_precision, receiver_coverage, numeric, enum, dataflow = components
    det_score = 100.0 * weighted_score(components, BASE_WEIGHTS)
    if "invalid_json" in failure_reasons or "missing_official_gt" in failure_reasons:
        det_score = 0.0
    det_pass = det_score >= float(det_threshold) and not any(r in failure_reasons for r in HARD_GATE_REASONS)
    cron_match = "cron_mismatch" not in failure_reasons
    period_match = "period_mismatch" not in failure_reasons
    code_match = code_sim >= 0.995
    unique_reasons = _dedupe(failure_reasons)
    return {
        "row_no": row_no,
        "det_score": round(det_score, 4),
        "det_pass": bool(det_pass),
        "gt_exact": bool(cron_match and period_match and code_match),
        "gt_similarity": round(code_sim, 6),
        "schedule_match": bool(cron_match and period_match),
        "cron_match": bool(cron_match),
        "period_match": bool(period_match),
        "code_match": bool(code_match),
        "gt_service_coverage": round(service_coverage, 6),
        "gt_service_precision": round(service_precision, 6),
        "gt_receiver_coverage": round(receiver_coverage, 6),
        "dataflow_score": round(dataflow, 6),
        "numeric_grounding": round(numeric, 6),
        "enum_grounding": round(enum, 6),
        "failure_reasons": unique_reasons,
        "gt_code": gt_code(gt_json),
        "generated_code": str(generated_json.get("code") or ""),
    }
