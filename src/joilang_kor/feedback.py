"""실패 유형 → 보강 가이드 → 관련 블록 수정 (프롬프트 피드백 예제, 기본 1회).

원본:
- 실패 유형별 규칙 문장과 대상 블록: 원본 prompt_surgery_rules.py
  (DET_FEEDBACK_RULES; ga_block_model.FEEDBACK_RULES 가 참조) — prompts/feedback_rules.json 에 그대로 둔다.
- 블록 파일 뒤에 규칙을 붙이는 방식: scripts/run_feedback_loop.py 의 _append_patch_rules /
  _strip_auto_sections (제목 "AUTO-PATCH MICRO-RULES", 중복 규칙 제거).
원본 프롬프트 파일은 수정하지 않고 실행 결과 디렉터리에 수정본을 쓴다. 기준 코드는 가이드에
넣지 않는다. 이 모듈은 GA 탐색(모집단·교차·변이)을 포함하지 않는다.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from .prompts import BLOCK_FILE_MAP, resolve_block_path

AUTO_PATCH_TITLE = "AUTO-PATCH MICRO-RULES"
AUTO_SECTION_MARKERS = (
    "\nAUTO-PATCH MICRO-RULES\n",
    "\nAUTO-GENERATED EXEMPLARS FROM GT FAILURES\n",
    "\nMANUAL FOCUS RULES\n",
)


def load_feedback_rules(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload["det_feedback_rules"]


def base_failure_reason(reason: str) -> str:
    token = str(reason or "").strip()
    if ":" in token:
        token = token.split(":", 1)[0]
    return token or "unknown"


def build_guides(failure_reasons: list[str], rules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """검출된 실패 유형마다 (대상 블록, 규칙 문장)을 고른다. 규칙이 없는 유형은 '진단 불가'로 남긴다."""
    guides: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for reason in failure_reasons:
        base = base_failure_reason(reason)
        rule = rules.get(base)
        if rule is None:
            guides.append({"failure_reason": reason, "failure_type": base, "block_id": None,
                           "block_family": None, "rule": None, "status": "no_rule"})
            continue
        key = (rule["prompt_block_id"], rule["rule"])
        if key in seen:
            continue
        seen.add(key)
        guides.append({
            "failure_reason": reason,
            "failure_type": rule["failure_type"],
            "block_id": rule["prompt_block_id"],
            "block_family": rule["affected_block_family"],
            "rule": rule["rule"],
            "status": "guide",
        })
    return guides


def _strip_auto_sections(text: str) -> str:
    cut_points = [text.find(marker) for marker in AUTO_SECTION_MARKERS if text.find(marker) != -1]
    if not cut_points:
        return text
    return text[: min(cut_points)].rstrip() + "\n"


def _append_patch_rules(original_text: str, rules: list[str], title: str) -> str:
    unique_rules = []
    seen = set()
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            unique_rules.append(rule)
    if not unique_rules:
        return original_text
    patch_body = "\n".join(f"- {rule}" for rule in unique_rules)
    return original_text.rstrip() + f"\n\n{title}\n{patch_body}\n"


def apply_feedback(
    genome: dict[str, Any],
    guides: list[dict[str, Any]],
    *,
    blocks_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """가이드를 대상 블록 뒤에 붙인 수정본을 out_dir/blocks/ 에 쓰고, 수정본을 가리키는 유전형을 돌려준다.

    같은 규칙을 다시 적용해도 기존 AUTO-PATCH 절을 걷어낸 뒤 붙이므로 중복되지 않는다.
    가이드가 가리키는 블록이 유전형에 없으면 그 블록을 목록 끝에 추가한다(원본 GA 의 보강 블록 추가에 해당).
    """
    out_blocks = Path(out_dir) / "blocks"
    out_blocks.mkdir(parents=True, exist_ok=True)
    patched = json.loads(json.dumps(genome))
    patched.setdefault("blocks", [])
    patched.setdefault("block_params", {})
    rules_by_block: dict[str, list[str]] = {}
    for guide in guides:
        if guide.get("status") != "guide":
            continue
        rules_by_block.setdefault(guide["block_id"], []).append(guide["rule"])

    changes: list[dict[str, Any]] = []
    for block_id, rules in rules_by_block.items():
        source_path = resolve_block_path(block_id, patched["block_params"].get(block_id, {}), blocks_dir)
        original = source_path.read_text(encoding="utf-8")
        stripped = _strip_auto_sections(original)
        updated = _append_patch_rules(stripped, rules, AUTO_PATCH_TITLE)
        new_path = out_blocks / BLOCK_FILE_MAP[block_id]
        new_path.write_text(updated, encoding="utf-8")
        patched["block_params"].setdefault(block_id, {})["source_file"] = str(new_path.resolve())
        if block_id not in patched["blocks"]:
            patched["blocks"].append(block_id)
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=str(source_path),
                tofile=str(new_path),
            )
        )
        changes.append({"block_id": block_id, "source": str(source_path), "patched": str(new_path),
                        "rules": rules, "diff": diff})
    base_id = str(genome.get("id", "genome"))
    patched["id"] = base_id if base_id.endswith("+feedback") else base_id + "+feedback"
    return {"genome": patched, "changes": changes}
