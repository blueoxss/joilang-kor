"""생성 출력의 정규화(기존 변환 구현의 '규칙 검사와 수정' 중 스키마 기반 부분).

원본: pipeline_common.normalize_candidate_json_text 와
그 하위 함수. 원본은 아래 항목 외에도 자연어 명령 문구를 보고 코드를 고쳐 쓰는 규칙
(예: 창문/조명/토글/시간창 관련 재작성)을 30여 개 더 적용한다. 그 규칙들은 특정 명령 유형에
맞춘 의미 재작성이므로 이 공개본에 옮기지 않았다(docs/pipeline.md 의 목록 참조).

옮긴 규칙(원본 적용 순서와 같다):
1. normalize_receiver_quantifiers: any(...) → all(...), 중첩 all 정리
2. lowercase_service_members: 수신자 뒤 멤버 토큰 소문자화
3. normalize_receiver_tag_case: #태그를 스키마 범주명 또는 첫 글자 대문자로
4. normalize_receiver_tag_order: 선택자 태그 → 범주 태그 순서, 중복 제거
5. canonicalize_member_aliases: 스키마 정식 서비스명으로 접미 일치 해석
6. normalize_clock_delay_calls: (#Clock).clock_delay(ms) → delay(N SEC|MIN|HOUR)
7. normalize_function_argument_separators: 함수 인자의 '|' 구분자 → ','
8. normalize_integer_like_numeric_literals: 12.0 → 12 (문자열 내부 제외)
9. period/cron 기본값·정수화 (원본 normalize_candidate_json_text 끝부분)
"""
from __future__ import annotations

import json
import re
from typing import Any

from .schema import canonical_service_name, function_member_names_from_schema, lowercase_output_member_name
from .validation import extract_json_block

MEMBER_AFTER_RECEIVER_RE = re.compile(
    r"(?P<receiver>all\([^\n\r()]+\)|\([^\n\r()]+\))\.(?P<member>[A-Za-z_][A-Za-z0-9_]*)"
)
FUNCTION_CALL_OPEN_RE = re.compile(
    r"(?P<head>(?:all\([^\n\r()]+\)|\([^\n\r()]+\))\.(?P<member>[A-Za-z_][A-Za-z0-9_]*)\()"
)
CLOCK_DELAY_CALL_RE = re.compile(r"\(#Clock\)\.clock_delay\(\s*(?P<millis>\d+(?:\.0+)?)\s*\)")
EXPLICIT_MEMBER_ALIASES = {
    "leaksensor_leak": "leaksensor_leakage",
    "airconditioner_setairconditionermodemode": "airconditioner_setairconditionermode",
    "airpurifier_setairpurifermode": "airpurifier_setairpurifiermode",
    "multibutton_button2": "dimmerswitch_button2",
}
RECEIVER_TAG_ALIASES = {
    "firstfloor": "Floor1",
    "1stfloor": "Floor1",
    "secondfloor": "Floor2",
    "2ndfloor": "Floor2",
    "thirdfloor": "Floor3",
    "3rdfloor": "Floor3",
}


def _compact_text_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(value or "")).casefold()


def lowercase_service_members_in_code(code: str) -> str:
    text = str(code or "")
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        return f"{match.group('receiver')}.{lowercase_output_member_name(match.group('member'))}"

    return MEMBER_AFTER_RECEIVER_RE.sub(repl, text)


def normalize_receiver_quantifiers_in_code(code: str) -> str:
    text = re.sub(r"\bany\(", "all(", str(code or ""))
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"all\(\s*all\((#[^\n\r()]*)\)\s*\)", r"all(\1)", text)
    return text


def _format_delay_from_millis(millis_text: str) -> str:
    millis = int(float(millis_text))
    if millis % 3_600_000 == 0:
        return f"delay({millis // 3_600_000} HOUR)"
    if millis % 60_000 == 0:
        return f"delay({millis // 60_000} MIN)"
    if millis % 1_000 == 0:
        return f"delay({millis // 1_000} SEC)"
    return f"delay({millis} MS)"


def normalize_clock_delay_calls_in_code(code: str) -> str:
    text = str(code or "")
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        return _format_delay_from_millis(match.group("millis"))

    return CLOCK_DELAY_CALL_RE.sub(repl, text)


def normalize_integer_like_numeric_literals_in_code(code: str) -> str:
    text = str(code or "")
    if not text:
        return text

    def normalize_segment(segment: str) -> str:
        return re.sub(r"(?<![\w.])(-?\d+)\.0+\b", r"\1", segment)

    string_re = r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
    parts = re.split(string_re, text)
    normalized: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith(("'", '"')):
            normalized.append(part)
        else:
            normalized.append(normalize_segment(part))
    return "".join(normalized)


def _normalize_receiver_tag_case(tag: str, service_schema: dict[str, Any] | None = None) -> str:
    raw = str(tag or "")
    if not raw:
        return raw
    alias_match = RECEIVER_TAG_ALIASES.get(_compact_text_key(raw))
    if alias_match:
        return alias_match
    schema_devices = {str(device).lower(): str(device) for device in (service_schema or {})}
    schema_match = schema_devices.get(raw.lower())
    if schema_match:
        return schema_match
    return raw[:1].upper() + raw[1:]


def normalize_receiver_tag_case_in_code(code: str, service_schema: dict[str, Any] | None = None) -> str:
    text = str(code or "")
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        return "#" + _normalize_receiver_tag_case(match.group(1), service_schema)

    return re.sub(r"#([A-Za-z_][A-Za-z0-9_]*)", repl, text)


def normalize_receiver_tag_order_in_code(code: str, service_schema: dict[str, Any] | None = None) -> str:
    text = str(code or "")
    if not text or not service_schema:
        return text
    schema_devices = {str(device).lower(): str(device) for device in service_schema}

    def repl(match: re.Match[str]) -> str:
        tags = re.findall(r"#([A-Za-z_][A-Za-z0-9_]*)", match.group("body"))
        if len(tags) < 2:
            return match.group(0)
        tags = [_normalize_receiver_tag_case(tag, service_schema) for tag in tags]
        deduped_tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in tags:
            key = str(tag).lower()
            if key in seen_tags:
                continue
            seen_tags.add(key)
            deduped_tags.append(tag)
        tags = deduped_tags
        selector_tags = [tag for tag in tags if str(tag).lower() not in schema_devices]
        device_tags = [schema_devices[str(tag).lower()] for tag in tags if str(tag).lower() in schema_devices]
        prefix = "all(" if match.group("all") else "("
        return prefix + " ".join(f"#{tag}" for tag in selector_tags + device_tags) + ")"

    return re.sub(
        r"(?P<all>\ball)?\((?P<body>\s*#[A-Za-z_][A-Za-z0-9_]*(?:\s+#[A-Za-z_][A-Za-z0-9_]*)+\s*)\)",
        repl,
        text,
    )


def canonicalize_member_aliases_in_code(code: str, service_schema: dict[str, Any] | None = None) -> str:
    text = str(code or "")
    if not text or not service_schema:
        return text
    schema_devices = {str(device).lower(): str(device) for device in service_schema}

    def repl(match: re.Match[str]) -> str:
        receiver = match.group("receiver")
        member = lowercase_output_member_name(match.group("member"))
        member = EXPLICIT_MEMBER_ALIASES.get(member, member)
        tags = re.findall(r"#([A-Za-z_][A-Za-z0-9_]*)", receiver)
        receiver_device = ""
        for tag in reversed(tags):
            receiver_device = schema_devices.get(str(tag).lower(), "")
            if receiver_device:
                break
        if not receiver_device:
            return f"{receiver}.{member}"
        services = service_schema.get(receiver_device, {})
        if not isinstance(services, dict):
            return f"{receiver}.{member}"
        canonical_members: dict[str, str] = {}
        for service_name in services:
            service_lower = lowercase_output_member_name(str(service_name))
            canonical_lower = lowercase_output_member_name(canonical_service_name(receiver_device, str(service_name)))
            canonical_members[service_lower] = canonical_lower
        if member in set(canonical_members.values()):
            return f"{receiver}.{member}"
        if member in canonical_members:
            return f"{receiver}.{canonical_members[member]}"
        suffix_matches = [
            canonical_lower
            for service_lower, canonical_lower in canonical_members.items()
            if member.endswith(f"_{service_lower}")
        ]
        if len(suffix_matches) == 1:
            return f"{receiver}.{suffix_matches[0]}"
        return f"{receiver}.{member}"

    return MEMBER_AFTER_RECEIVER_RE.sub(repl, text)


def _find_call_close(text: str, open_index: int) -> int:
    depth = 1
    quote = ""
    escaped = False
    for index in range(open_index + 1, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _replace_top_level_pipe_separators(args: str) -> str:
    output: list[str] = []
    quote = ""
    escaped = False
    nested_depth = 0
    index = 0
    while index < len(args):
        char = args[index]
        if quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            output.append(char)
            index += 1
            continue
        if char in "([{":
            nested_depth += 1
            output.append(char)
            index += 1
            continue
        if char in ")]}":
            nested_depth = max(0, nested_depth - 1)
            output.append(char)
            index += 1
            continue
        if char == "|" and nested_depth == 0:
            while output and output[-1].isspace():
                output.pop()
            output.append(",")
            index += 1
            while index < len(args) and args[index].isspace():
                index += 1
            if index < len(args):
                output.append(" ")
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _normalize_colorcontrol_setcolor_rgb_argument(args: str, member: str) -> str:
    if member != lowercase_output_member_name(canonical_service_name("ColorControl", "SetColor")):
        return args
    match = re.fullmatch(
        r'(?P<leading>\s*)(?P<quote>["\'])(?P<r>\d{1,3})\|(?P<g>\d{1,3})\|(?P<b>\d{1,3})(?P=quote)(?P<trailing>\s*)',
        args,
    )
    if not match:
        return args
    return (
        f'{match.group("leading")}{match.group("quote")}'
        f'{match.group("r")},{match.group("g")},{match.group("b")}'
        f'{match.group("quote")}{match.group("trailing")}'
    )


def normalize_function_argument_separators_in_code(code: str, service_schema: dict[str, Any] | None = None) -> str:
    function_members = function_member_names_from_schema(service_schema)
    if not function_members or "|" not in str(code or ""):
        return str(code or "")

    text = str(code or "")
    pieces: list[str] = []
    cursor = 0
    for match in FUNCTION_CALL_OPEN_RE.finditer(text):
        if match.start() < cursor:
            continue
        member = lowercase_output_member_name(match.group("member"))
        if member not in function_members:
            continue
        open_index = match.end() - 1
        close_index = _find_call_close(text, open_index)
        if close_index < 0:
            continue
        args = text[open_index + 1 : close_index]
        normalized_args = _replace_top_level_pipe_separators(args)
        normalized_args = _normalize_colorcontrol_setcolor_rgb_argument(normalized_args, member)
        if normalized_args == args:
            continue
        pieces.append(text[cursor : open_index + 1])
        pieces.append(normalized_args)
        cursor = close_index
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


CODE_RULES: list[tuple[str, Any]] = [
    ("normalize_receiver_quantifiers", lambda code, schema: normalize_receiver_quantifiers_in_code(code)),
    ("lowercase_service_members", lambda code, schema: lowercase_service_members_in_code(code)),
    ("normalize_receiver_tag_case", normalize_receiver_tag_case_in_code),
    ("normalize_receiver_tag_order", normalize_receiver_tag_order_in_code),
    ("canonicalize_member_aliases", canonicalize_member_aliases_in_code),
    ("normalize_clock_delay_calls", lambda code, schema: normalize_clock_delay_calls_in_code(code)),
    ("normalize_function_argument_separators", normalize_function_argument_separators_in_code),
    ("normalize_integer_like_numeric_literals", lambda code, schema: normalize_integer_like_numeric_literals_in_code(code)),
]


def normalize_candidate_json_text(
    text: str,
    *,
    service_schema: dict[str, Any] | None = None,
    default_period: int = 0,
) -> dict[str, Any]:
    """생성 출력을 정규화한다(원본 함수명 유지). cron 은 원본과 같이 문자열화만 하고 기본값을 넣지 않는다.

    반환: {"text": 정규화된 JSON 문자열(파싱 실패 시 원문 그대로), "parsed": bool,
           "applied": 코드를 실제로 바꾼 규칙 이름 목록, "code_before", "code_after"}
    """
    raw = (text or "").strip()
    result: dict[str, Any] = {"text": raw, "parsed": False, "applied": [], "code_before": "", "code_after": ""}
    if not raw:
        return result
    candidate = extract_json_block(raw)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return result
    if isinstance(parsed, list):
        if not parsed or not isinstance(parsed[0], dict):
            return result
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        return result
    result["parsed"] = True

    code = str(parsed.get("code", "") or "")
    result["code_before"] = code
    for name, rule in CODE_RULES:
        updated = rule(code, service_schema)
        if updated != code:
            result["applied"].append(name)
        code = updated
    result["code_after"] = code

    normalized = {
        "name": str(parsed.get("name", "") or ""),
        "cron": str(parsed.get("cron", "") or ""),
        "period": parsed.get("period", default_period),
        "code": code,
    }
    try:
        normalized["period"] = int(normalized["period"])
    except (TypeError, ValueError):
        normalized["period"] = default_period
    if normalized["period"] < 0:
        normalized["period"] = default_period
    if normalized["cron"] == "":
        normalized["period"] = default_period if normalized["period"] < 0 else normalized["period"]
    if normalized["period"] != parsed.get("period") or normalized["cron"] != parsed.get("cron"):
        result["applied"].append("schedule_defaults")
    result["text"] = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return result
