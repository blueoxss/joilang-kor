"""생성 출력의 규칙 검사(JSON 형식, 필수 키, 서비스 등록 여부, 인자 자료형·허용값).

원본: 12항 strict 평가기(det_evaluator.py, 구현 스냅샷)의 스키마 검사 부분
(_coerce_candidate_object, _extract_uses, _resolve_service, _score_args 등)을 옮겼다.
원본 12항 평가기의 점수 계산(의미 유사도·정밀도·69.9 상한 등)은 옮기지 않았다.
검사 결과의 failure_reasons 는 feedback 모듈의 블록 보강 규칙과 연결된다.

검출 범위(문서 docs/pipeline.md 와 일치해야 한다):
- invalid_json: JSON 으로 읽을 수 없음
- schema_missing_keys: JSON 객체가 아니거나 name/cron/period/code 중 누락
- unknown_service:<member>: 스키마(및 connected_devices 로 추정한 장치)에서 서비스를 찾지 못함
- service_match: 서비스 해석 실패가 하나라도 있음(멤버 접근이 전혀 없는 코드·빈 코드 포함, 원본과 동일)
- arg_type: 함수 호출 인자의 수·자료형·허용값 점수 < 1(멤버 접근이 전혀 없는 코드·빈 코드 포함, 원본과 동일)
- no_parseable_member_access: 코드가 비어 있지 않은데 수신자.멤버 형태가 하나도 없음
실패 유형 목록은 원본 strict 평가기의 스키마 검사부와 같다. 멤버 토큰의 대문자 여부는 실패 유형이 아니라
usages[*].service_case 표시로만 남긴다(후처리 lowercase_service_members 가 정정한다).
검출하지 않는 것: JOILang 문법(if/wait until 구문), 실행 의미, 태그가 실제 장치와 연결되는지.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .schema import canonical_service_name, lowercase_output_member_name

MEMBER_ACCESS_RE = re.compile(
    r"(?P<receiver>all\([^\n\r()]+\)|\([^\n\r()]+\))\.(?P<member>[A-Za-z_][A-Za-z0-9_]*)[ \t]*(?:\((?P<args>[^()]*)\))?"
)
TAG_RE = re.compile(r"#([A-Za-z_][A-Za-z0-9_]*)")
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
INTEGER_RE = re.compile(r"^-?\d+$")
QUOTED_RE = re.compile(r'^"(?:[^"\\]|\\.)*"$')
REQUIRED_KEYS = ("name", "cron", "period", "code")


def extract_json_block(text: str) -> str:
    """응답 문자열에서 JSON 객체 부분을 잘라 낸다(원본 pipeline_common._extract_json_block)."""
    stripped = (text or "").strip()
    if not stripped:
        return stripped
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def parse_candidate_text(text: str) -> tuple[bool, dict[str, Any] | None, str]:
    """(파싱 성공 여부, 객체, 잘라 낸 원문). 리스트면 첫 객체를 쓴다(원본 _coerce_candidate_object)."""
    candidate = extract_json_block(text or "")
    if not candidate:
        return False, None, candidate
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return False, None, candidate
    if isinstance(parsed, dict):
        return True, parsed, candidate
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        return True, parsed[0], candidate
    return True, None, candidate


def _extract_enums(meta: dict[str, Any]) -> set[str]:
    enums = set()
    for raw in meta.get("enums_descriptor", []) or []:
        enums.add(str(raw).split(" - ", 1)[0].strip())
    return {item for item in enums if item}


def _split_args(arg_string: str | None) -> list[str]:
    if arg_string is None:
        return []
    text = arg_string.strip()
    if not text:
        return []
    args: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    depth = 0
    for ch in text:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if ch == '"':
            current.append(ch)
            in_string = not in_string
            continue
        if not in_string:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
        current.append(ch)
    if current:
        args.append("".join(current).strip())
    return args


def extract_uses(code: str) -> list[dict[str, Any]]:
    uses: list[dict[str, Any]] = []
    for match in MEMBER_ACCESS_RE.finditer(code or ""):
        receiver = match.group("receiver")
        member = match.group("member")
        args = _split_args(match.group("args"))
        uses.append(
            {
                "receiver": receiver,
                "tags": TAG_RE.findall(receiver),
                "member": member,
                "args": args,
                "is_call": match.group("args") is not None,
            }
        )
    return uses


def _connected_context_devices(connected_devices: dict[str, Any], tags: list[str], schema: dict[str, dict[str, Any]]) -> set[str]:
    if not connected_devices or not tags:
        return set()
    matched_devices: set[str] = set()
    tag_set = {tag.lower() for tag in tags}
    for _, meta in connected_devices.items():
        meta_tags = meta.get("tags") or []
        if not isinstance(meta_tags, list):
            meta_tags = [meta_tags]
        meta_tag_set = {str(item).lower() for item in meta_tags if item}
        if tag_set & meta_tag_set:
            category = meta.get("category")
            categories = category if isinstance(category, list) else [category]
            for candidate in categories:
                if candidate in schema:
                    matched_devices.add(candidate)
    return matched_devices


def _infer_devices(receiver_tags: list[str], connected_devices: dict[str, Any], schema: dict[str, dict[str, Any]]) -> set[str]:
    devices = {tag for tag in receiver_tags if tag in schema}
    devices.update(_connected_context_devices(connected_devices, receiver_tags, schema))
    return devices


def _resolve_casefold_device_service(
    schema: dict[str, dict[str, Any]],
    device_token: str,
    service_token: str,
) -> tuple[str, str] | None:
    device_lower = str(device_token or "").lower()
    service_lower = lowercase_output_member_name(service_token)
    for schema_device, services in schema.items():
        if schema_device.lower() != device_lower:
            continue
        for schema_service in services:
            if schema_service.lower() == service_lower:
                return schema_device, schema_service
    return None


def _resolve_casefold_service_for_device(
    schema: dict[str, dict[str, Any]],
    device_name: str,
    member: str,
) -> str | None:
    member_lower = lowercase_output_member_name(member)
    for schema_service in schema.get(device_name, {}):
        if schema_service.lower() == member_lower:
            return schema_service
    return None


def resolve_service(usage: dict[str, Any], schema: dict[str, dict[str, Any]], connected_devices: dict[str, Any]) -> dict[str, Any] | None:
    """멤버 토큰을 스키마 서비스로 해석한다. 대소문자는 구분하지 않는다."""
    member = usage["member"]
    inferred_devices = _infer_devices(usage["tags"], connected_devices, schema)
    if "_" in member:
        device_name, service_name = member.split("_", 1)
        resolved_pair = _resolve_casefold_device_service(schema, device_name, service_name)
        if resolved_pair is not None:
            device_name, service_name = resolved_pair
            meta = dict(schema[device_name][service_name])
            return {
                "device": device_name,
                "service": service_name,
                "canonical_name": canonical_service_name(device_name, service_name),
                "meta": meta,
                "inferred_devices": sorted(inferred_devices),
            }
    candidate_devices = sorted(inferred_devices)
    for device_name in candidate_devices:
        resolved_service = _resolve_casefold_service_for_device(schema, device_name, member)
        if resolved_service is not None:
            meta = dict(schema[device_name][resolved_service])
            return {
                "device": device_name,
                "service": resolved_service,
                "canonical_name": canonical_service_name(device_name, resolved_service),
                "meta": meta,
                "inferred_devices": candidate_devices,
            }
    member_lower = lowercase_output_member_name(member)
    raw_matches = [
        device_name
        for device_name, services in schema.items()
        if any(schema_service.lower() == member_lower for schema_service in services)
    ]
    if len(raw_matches) == 1:
        device_name = raw_matches[0]
        resolved_service = _resolve_casefold_service_for_device(schema, device_name, member)
        if resolved_service is None:
            return None
        meta = dict(schema[device_name][resolved_service])
        return {
            "device": device_name,
            "service": resolved_service,
            "canonical_name": canonical_service_name(device_name, resolved_service),
            "meta": meta,
            "inferred_devices": candidate_devices,
        }
    return None


def _literal_kind(arg: str) -> str:
    text = arg.strip()
    if not text:
        return "EMPTY"
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return "BOOL"
    if INTEGER_RE.match(text):
        return "INTEGER"
    if NUMERIC_RE.match(text):
        return "DOUBLE"
    if QUOTED_RE.match(text):
        inner = text[1:-1]
        if INTEGER_RE.match(inner):
            return "STRING_NUMERIC_INT"
        if NUMERIC_RE.match(inner):
            return "STRING_NUMERIC_DOUBLE"
        return "STRING"
    if any(op in text for op in ("+", "-", "*", "/", "(", ")")):
        return "EXPR"
    return "IDENT"


def _expected_types(meta: dict[str, Any]) -> list[str]:
    raw = str(meta.get("argument_type") or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split("|") if item.strip()]


def _score_single_arg(arg: str, expected_type: str, meta: dict[str, Any]) -> float:
    expected = expected_type.upper().strip()
    kind = _literal_kind(arg)
    enums = _extract_enums(meta)
    arg_text = arg.strip().strip('"')
    if expected == "INTEGER":
        if kind == "INTEGER":
            return 1.0
        if kind in {"DOUBLE", "STRING_NUMERIC_INT", "STRING_NUMERIC_DOUBLE"}:
            return 0.5
        if kind in {"IDENT", "EXPR"}:
            return 0.75
        return 0.0
    if expected == "DOUBLE":
        if kind in {"INTEGER", "DOUBLE"}:
            return 1.0
        if kind in {"STRING_NUMERIC_INT", "STRING_NUMERIC_DOUBLE"}:
            return 0.6
        if kind in {"IDENT", "EXPR"}:
            return 0.75
        return 0.0
    if expected == "BOOL":
        if kind == "BOOL":
            return 1.0
        if kind in {"IDENT", "EXPR"}:
            return 0.5
        return 0.0
    if expected == "ENUM":
        if kind in {"STRING", "STRING_NUMERIC_INT", "STRING_NUMERIC_DOUBLE"}:
            if enums and arg_text not in enums:
                return 0.0
            return 1.0
        if kind == "IDENT":
            return 0.5 if not enums or arg_text in enums else 0.0
        return 0.0
    if expected in {"STRING", "BINARY"}:
        if kind in {"STRING", "STRING_NUMERIC_INT", "STRING_NUMERIC_DOUBLE", "IDENT", "EXPR"}:
            return 1.0
        return 0.25
    return 0.5


def score_args(arg_list: list[str], meta: dict[str, Any]) -> float:
    expected = _expected_types(meta)
    if not expected:
        return 1.0 if not arg_list else 0.0
    if not arg_list:
        return 0.0
    if len(expected) == 1:
        return _score_single_arg(arg_list[0], expected[0], meta) if len(arg_list) == 1 else max(0.0, _score_single_arg(arg_list[0], expected[0], meta) - 0.4)
    scores = []
    for idx, expected_type in enumerate(expected):
        if idx >= len(arg_list):
            scores.append(0.0)
            continue
        scores.append(_score_single_arg(arg_list[idx], expected_type, meta))
    if len(arg_list) > len(expected):
        scores.extend([0.0] * (len(arg_list) - len(expected)))
    return sum(scores) / max(len(scores), 1)


def check_candidate(
    candidate_text: str,
    *,
    service_schema: dict[str, dict[str, Any]],
    connected_devices: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """생성 출력 문자열을 검사한다. 결과의 failure_reasons 는 원본 평가기와 같은 이름을 쓴다."""
    connected = connected_devices or {}
    ok, obj, raw = parse_candidate_text(candidate_text)
    result: dict[str, Any] = {
        "valid_json": ok,
        "schema_keys_ok": False,
        "service_match": 0.0,
        "arg_type_ok": 0.0,
        "usages": [],
        "failure_reasons": [],
        "candidate": obj if isinstance(obj, dict) else None,
        "raw_candidate": raw,
    }
    if not ok:
        result["failure_reasons"].append("invalid_json")
        return result
    if not isinstance(obj, dict) or not set(REQUIRED_KEYS).issubset(obj.keys()):
        result["failure_reasons"].append("schema_missing_keys")
        return result
    result["schema_keys_ok"] = True

    code = str(obj.get("code", "") or "")
    usages = extract_uses(code)
    service_match_scores: list[float] = []
    arg_scores: list[float] = []
    for usage in usages:
        resolved = resolve_service(usage, service_schema, connected)
        record = {k: usage[k] for k in ("receiver", "member", "args", "is_call")}
        if resolved is None:
            service_match_scores.append(0.0)
            arg_scores.append(0.0 if usage["is_call"] else 1.0)
            result["failure_reasons"].append(f"unknown_service:{usage['member']}")
            record["resolved"] = None
        else:
            service_match_scores.append(1.0)
            arg_score = score_args(usage["args"], resolved["meta"]) if usage["is_call"] else 1.0
            arg_scores.append(arg_score)
            record["resolved"] = resolved["canonical_name"]
            record["arg_score"] = arg_score
        if usage["member"] != lowercase_output_member_name(usage["member"]):
            record["service_case"] = True
        result["usages"].append(record)

    if usages:
        result["service_match"] = sum(service_match_scores) / len(service_match_scores)
        result["arg_type_ok"] = sum(arg_scores) / len(arg_scores)
    elif code.strip():
        result["failure_reasons"].append("no_parseable_member_access")

    # 원본과 같이 멤버 접근이 하나도 없으면(빈 코드 포함) 두 점수는 0 이고 두 실패 유형이 함께 붙는다.
    if result["service_match"] < 1.0:
        result["failure_reasons"].append("service_match")
    if result["arg_type_ok"] < 1.0:
        result["failure_reasons"].append("arg_type")
    return result
