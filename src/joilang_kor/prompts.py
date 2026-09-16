"""프롬프트 조립.

두 경로를 제공한다.
- source: 실험의 출발점인 클라우드용 원 프롬프트(prompts/source_prompt/ 5개 파일)를 원본 조립
  코드(pipeline_common.render_legacy_v13_monolithic_prompt)대로 하나의 system prompt 로 만든다.
  사용자 메시지는 자연어 명령이다.
- blocks: 블록 파일(prompts/initial_blocks/)을 유전형(genome)의 blocks 순서대로 이어 붙인다
  (pipeline_common.render_blocks_for_genome / render_prompt_bundle). 원본 GA 구현이 후보를
  평가할 때 쓰는 조립 경로다. 이 공개본은 조립만 제공하고 GA 탐색은 포함하지 않는다.

두 경로 모두 입력별 서비스 문맥(schema.build_service_snippet_payload)을 조립 직전에 넣는다.
기준 출력(gt)은 어느 경로에도 들어가지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .data import parse_connected_devices
from .schema import (
    Bm25Retriever,
    build_service_snippet_payload,
    normalize_string_list,
    unique_preserve_order,
)

BLOCK_FILE_MAP = {
    "01": "01_preamble.txt",
    "02": "02_generator_prompt.txt",
    "03": "03_postprocessor.txt",
    "04": "04_reranker_prompt.txt",
    "05": "05_repair_prompt.txt",
    "06": "06_det_helper.txt",
}

SOURCE_PROMPT_FILES = {
    "grammar": "grammar_ver1.5.10.md",
    "service_prompt": "service_prompt_10.md",
    "tempo": "tempo_prompt_9.md",
    "caution": "caution_prompt_8.md",
    "response_prompt": "response_prompt_baseline_cot.md",
}

# 공개용 기본 유전형: 원본 예제 유전형(prompts/initial_blocks.json 의 original_example_genome)의 블록 순서만 쓴다.
DEFAULT_GENOME = {
    "id": "initial-blocks",
    "blocks": ["01", "02", "03", "06"],
    "block_params": {},
}

# 원본 run_generate._system_prompt (blocks 경로의 system prompt)
GENERATOR_SYSTEM_PROMPT = (
    "You are a deterministic JOILang generation engine. "
    "The natural-language command may be written in English or Korean. "
    "If it is Korean, translate it internally to the closest intent-preserving English meaning before reasoning. "
    "Follow the user instructions exactly and return only the requested JSON object."
)

LANGUAGE_BRIDGE = (
    "Language handling rule:\n"
    "- The command may be English or Korean.\n"
    "- If it is Korean, translate it internally to the closest English command intent first.\n"
    "- Do not output the translation. Output only the final JOI JSON object.\n"
)
RETURN_SUFFIX = "Return the final JSON object now."


# ---------------------------------------------------------------------------
# 입력값 구성 (pipeline_common.build_prompt_values)
# ---------------------------------------------------------------------------

def extract_optional_schedule(row: dict[str, str]) -> tuple[str, str]:
    cron = row.get("cron", "")
    period = row.get("period", "0")
    if cron is None or cron == "":
        cron = ""
    if period in (None, ""):
        period = "0"
    return str(cron), str(period)


def combined_command_text(row: dict[str, str]) -> str:
    command_eng = str(row.get("command_eng", "") or "").strip()
    command_kor = str(row.get("command_kor", "") or "").strip()
    if command_eng and command_kor and command_eng != command_kor:
        return f"English command: {command_eng}\nKorean command: {command_kor}"
    return command_eng or command_kor


CANDIDATE_STRATEGY = "direct"   # 공개 경로는 원본 후보 전략 중 direct 하나만 쓴다(블록 02 의 {candidate_strategy})


def build_prompt_values(
    row_no: int,
    row: dict[str, str],
    service_schema: dict[str, dict[str, Any]],
    *,
    context_mode: str = "schema_fallback",
    retriever: Bm25Retriever | None = None,
    retrieval_topk: int = 10,
) -> dict[str, Any]:
    """행(명령·장치 문맥)에서 프롬프트 자리표시자 값을 만든다. gt 열은 읽지 않는다."""
    connected_devices = parse_connected_devices(row.get("connected_devices", ""))
    cron, period = extract_optional_schedule(row)
    command_text = combined_command_text(row)
    service_snippet_payload, snippet_meta = build_service_snippet_payload(
        command_text,
        connected_devices,
        service_schema,
        context_mode=context_mode,
        retriever=retriever,
        retrieval_topk=retrieval_topk,
    )
    values = {
        "row_no": row_no,
        "command_eng": command_text,
        "command_kor": row.get("command_kor", ""),
        "command_text": command_text,
        "connected_devices": json.dumps(connected_devices, ensure_ascii=False, indent=2),
        "service_list_snippet": json.dumps(service_snippet_payload, ensure_ascii=False, indent=2),
        "optional_cron": cron,
        "optional_period": period,
        "cron": cron,
        "period": period,
        "candidate_strategy": CANDIDATE_STRATEGY,
        "det_diagnostics": "",
        "best_candidate": "",
        "failure_summary": "",
    }
    values.update(snippet_meta)
    return values


# ---------------------------------------------------------------------------
# blocks 경로
# ---------------------------------------------------------------------------

def parse_block_file(path: str | Path) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    in_header = True
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if in_header and line.startswith("# ") and ":" in line:
                key, value = line[2:].split(":", 1)
                metadata[key.strip()] = value.strip()
                continue
            in_header = False
            body_lines.append(line)
    return metadata, "".join(body_lines).lstrip("\n")


def resolve_block_path(block_id: str, block_params: dict[str, Any] | None, blocks_dir: str | Path) -> Path:
    block_params = block_params or {}
    source_file = block_params.get("source_file")
    if source_file:
        path = Path(source_file)
        if not path.is_absolute():
            path = Path(blocks_dir) / source_file
        return path
    filename = BLOCK_FILE_MAP[block_id]
    return Path(blocks_dir) / filename


def limit_exemplars(block_text: str, *, few_shot_count: int | None) -> str:
    if few_shot_count is None or few_shot_count >= 3:
        return block_text
    pattern = re.compile(r"(?=^### EXEMPLAR \d+\b)", re.MULTILINE)
    pieces = pattern.split(block_text)
    if len(pieces) <= 1:
        return block_text
    prefix = pieces[0]
    exemplars = [piece for piece in pieces[1:] if piece.strip()]
    kept = exemplars[: max(0, few_shot_count)]
    return prefix + "".join(kept)


def render_placeholders(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def render_block(
    block_id: str,
    *,
    values: dict[str, Any],
    block_params: dict[str, Any] | None,
    blocks_dir: str | Path,
) -> tuple[dict[str, str], str, Path]:
    block_params = block_params or {}
    path = resolve_block_path(block_id, block_params, blocks_dir)
    metadata, body = parse_block_file(path)
    body = limit_exemplars(body, few_shot_count=block_params.get("few_shot_count"))
    micro_rules = block_params.get("micro_rules") or []
    if micro_rules:
        micro_rule_text = "\n".join(f"- {rule}" for rule in micro_rules)
        body += f"\n\nACTIVE MICRO-RULES\n{micro_rule_text}\n"
    body = render_placeholders(body, values)
    return metadata, body, path


def render_blocks_for_genome(
    genome: dict[str, Any],
    *,
    values: dict[str, Any],
    blocks_dir: str | Path,
) -> tuple[str, list[dict[str, Any]]]:
    blocks = genome.get("blocks") or []
    block_params_map = genome.get("block_params") or {}
    rendered_blocks: list[str] = []
    manifest: list[dict[str, Any]] = []
    for block_id in blocks:
        metadata, body, path = render_block(
            block_id,
            values=values,
            block_params=block_params_map.get(block_id, {}),
            blocks_dir=blocks_dir,
        )
        rendered_blocks.append(body.rstrip())
        manifest.append({"id": block_id, "path": str(path), "metadata": metadata})
    return "\n\n".join(block for block in rendered_blocks if block.strip()), manifest


def render_block_prompt(
    genome: dict[str, Any],
    *,
    values: dict[str, Any],
    blocks_dir: str | Path,
) -> tuple[str, str, list[dict[str, Any]]]:
    """(system, user, manifest). 원본 render_prompt_bundle(blocks 모드, generate 단계)."""
    rendered_prompt, manifest = render_blocks_for_genome(genome, values=values, blocks_dir=blocks_dir)
    user_prompt = LANGUAGE_BRIDGE + "\n" + rendered_prompt.rstrip() + "\n\n" + RETURN_SUFFIX
    return GENERATOR_SYSTEM_PROMPT, user_prompt, manifest


# ---------------------------------------------------------------------------
# source 경로 (pipeline_common.render_legacy_v13_monolithic_prompt, generate 단계)
# ---------------------------------------------------------------------------

def load_source_prompt_assets(prompt_dir: str | Path) -> dict[str, str]:
    assets: dict[str, str] = {}
    for key, filename in SOURCE_PROMPT_FILES.items():
        path = Path(prompt_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"source prompt asset not found: {path}")
        assets[key] = path.read_text(encoding="utf-8")
    return assets


def _connected_device_summary(connected_devices: dict[str, Any]) -> str:
    if not connected_devices:
        return ""
    categories: list[str] = []
    for meta in connected_devices.values():
        categories.extend(normalize_string_list(meta.get("category")))
    categories = unique_preserve_order(categories)
    if not categories:
        return ""
    category_tags_str = "[" + ", ".join(f"#{cat}" for cat in sorted(categories)) + "]"
    return f"\n\n---\n[connected_devices]\n {category_tags_str}"


def _userinfo_block(values: dict[str, Any]) -> str:
    payload: dict[str, Any] = {}
    cron = str(values.get("optional_cron", "") or "")
    period = str(values.get("optional_period", "0") or "0")
    if cron:
        payload["cron"] = cron
    if period not in {"", "0"}:
        try:
            payload["period"] = int(period)
        except (TypeError, ValueError):
            payload["period"] = period
    if not payload:
        return ""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"\n\n---\n[userinfo]\n {text}"


def flatten_service_lists(snippet_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    value_rows: list[dict[str, Any]] = []
    function_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in snippet_payload.get("device_groups") or []:
        for binding in group.get("capability_bindings") or []:
            category = str(binding.get("category", "") or "")
            for service in binding.get("services") or []:
                raw_type = str(service.get("type", "") or "").strip().lower()
                raw_service = str(service.get("raw_service", "") or service.get("service", "")).strip()
                canonical_name = str(service.get("canonical_name", "") or service.get("service", "")).strip()
                if not category or not canonical_name:
                    continue
                item = {
                    "device": category,
                    "service": canonical_name,
                    "raw_service": raw_service,
                    "canonical_name": canonical_name,
                    "type": raw_type,
                }
                for key in (
                    "descriptor",
                    "argument_descriptor",
                    "argument_type",
                    "argument_bounds",
                    "argument_format",
                    "return_descriptor",
                    "return_type",
                    "return_bounds",
                    "enums",
                ):
                    value = service.get(key)
                    if value not in (None, "", []):
                        item[key] = value
                signature = (category, canonical_name, raw_type)
                if signature in seen:
                    continue
                seen.add(signature)
                if raw_type == "value":
                    value_rows.append(item)
                elif raw_type == "function":
                    function_rows.append(item)
    return value_rows, function_rows


REASONING_CONTRACT = """
---
[Baseline-CoT Internal Reasoning Contract]
Before writing the final answer, reason step by step internally using this hidden checklist:
[REASONING]
INTENT: <one sentence>
DEVICES_AND_SERVICES:
- <device/service candidates>
TIMING:
- <cron/period implications or none>
CONDITIONS:
- <if / wait until logic or none>
STATE:
- <persistent vars, flags, reset rules, or none>
PLAN:
- <ordered JOILang construction plan>
[/REASONING]

Output rules:
- Keep the reasoning completely hidden.
- Return ONLY one final JOILang JSON object.
- Do not print markdown fences, analysis, bullet lists, or explanations.
- The final JSON must be directly parseable by Python json.loads().
""".strip()


def render_source_prompt(
    *,
    values: dict[str, Any],
    command_text: str,
    assets: dict[str, str],
    prompt_dir: str | Path | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """원 프롬프트 조립: (system, user, manifest). 서비스 목록은 입력별 문맥에서 펼친다."""
    connected_devices = parse_connected_devices(values.get("connected_devices", ""))
    snippet_payload = json.loads(str(values.get("service_list_snippet", "{}") or "{}"))
    service_list_value, service_list_function = flatten_service_lists(snippet_payload)
    connected_devices_str = _connected_device_summary(connected_devices)
    other_params_str = _userinfo_block(values)
    response_prompt = assets["response_prompt"]

    system_prompt = f"""
You are a JOILang programmer. JOILang is a programming language used to control IoT devices.
Use the following knowledge to convert natural language into valid JOILang code.
This prompt uses a baseline-CoT style workflow, but the chain-of-thought must stay private.

Make sure to follow syntax rules strictly. Only use allowed keywords:
if, else if, else, >=, <=, ==, !=, not, and, or, wait until, (#Clock).clock_delay()
The delay function (#Clock).clock_delay() only accepts values in milliseconds (ms).
Do not use while or any unlisted constructs.
**Never use `while` in code**

---

[Device and Service Mapping]
IMPORTANT: You MUST extract all device tags mentioned as subjects or objects in the input sentence, including those connected by conjunctions.
For each extracted device tag, retrieve all associated services exactly as defined in the service lists below.
{assets["service_prompt"]}
[service_list_value]
{json.dumps(service_list_value, ensure_ascii=False, indent=2)}
[service_list_function]
{json.dumps(service_list_function, ensure_ascii=False, indent=2)}

---
[Grammar]
{assets["grammar"]}

---
[Condition Combination Rules]
{assets["tempo"]}

---
[Important Cautions]
{assets["caution"]}
{connected_devices_str}
{other_params_str}

---
{response_prompt}
{REASONING_CONTRACT}
- **Never use `while` in code**

--- JOILang Code Output Format Guide ---
Every scenario generated will follow this structure:
```json
{{
  "name": "<A brief and intuitive scenario name>",
  "cron": "<Time-based trigger to start execution>",
  "period": <Execution interval in milliseconds or -1>,
  "code": "<Main logic block written in JOILang>"
}}
```
""".strip()

    manifest = [
        {
            "id": "source_prompt",
            "path": str(prompt_dir or ""),
            "metadata": {
                "role": "generate",
                "prompt_render_mode": "source",
                "component_files": json.dumps(SOURCE_PROMPT_FILES, ensure_ascii=False),
                "service_list_value_count": str(len(service_list_value)),
                "service_list_function_count": str(len(service_list_function)),
            },
        }
    ]
    return system_prompt, str(command_text or ""), manifest
