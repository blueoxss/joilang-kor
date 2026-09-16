"""변환 경로의 실행: 입력 준비 → 서비스 문맥 → 프롬프트 조립 → 생성 → 후처리·검사 → (피드백 1회).

- offline 모드: 모델을 호출하지 않는다. 저장된 출력(출처 명시)에 후처리·검사·가이드·블록 수정을
  적용하고 수정 프롬프트까지 만들어 기록한다. 재생성은 하지 않는다. 저장 출력은 그 출처의 프롬프트로
  만들어진 것이며 prompt_initial.json 으로 만든 출력이 아니다.
- live 모드: OpenAI 호환 endpoint 로 초기 생성 → 검사 → 오류가 있으면 블록 보강 → 같은 입력으로
  한 번 재생성. 두 결과와 변경 블록을 모두 남긴다. 결과가 나빠져도 그대로 기록한다.
기준 출력(gt)은 생성 입력에 넣지 않으며, 평가(evaluation.json)에만 쓴다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import evaluation, feedback, llm, postprocess, prompts, validation
from .data import parse_connected_devices
from .schema import Bm25Retriever, load_service_schema

INPUT_FIELDS = ("category", "index", "command_kor", "command_eng", "connected_devices")
RUN_ARTIFACTS = ("inputs.json", "service_context.json", "prompt_initial.json", "output_initial.json", "check_initial.json",
                 "guides.json", "genome_patched.json", "block_diff.txt", "prompt_patched.json",
                 "output_after_feedback.json", "check_after_feedback.json", "evaluation.json", "summary.json")
RETRIEVAL_TOPK = 10


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate_parsed(reference: Any, raw_text: str, *, threshold: float = evaluation.DEFAULT_THRESHOLD) -> dict[str, Any]:
    """응답에서 JSON 블록만 잘라 낸 뒤 채점한다(원본 파이프라인의 '파싱' 단계; 코드 정규화는 하지 않음)."""
    item = evaluation.evaluate_item(reference, validation.extract_json_block(raw_text), threshold=threshold)
    item["evaluated_on"] = "parsed"
    return item


def evaluate_postprocessed(reference: Any, normalized_text: str, *, threshold: float = evaluation.DEFAULT_THRESHOLD) -> dict[str, Any]:
    item = evaluation.evaluate_item(reference, normalized_text, threshold=threshold)
    item["evaluated_on"] = "postprocessed"
    return item


def load_case(path: str | Path) -> dict[str, Any]:
    case = json.loads(Path(path).read_text(encoding="utf-8"))
    if not str(case.get("command_eng", "")).strip():
        raise ValueError("case is missing command_eng")
    return case


def case_input_row(case: dict[str, Any]) -> dict[str, str]:
    """생성 입력으로 쓰는 행. reference 등 평가 전용 필드는 넣지 않는다."""
    row = {field: str(case.get(field, "") or "") for field in INPUT_FIELDS}
    cd = case.get("connected_devices", "")
    row["connected_devices"] = json.dumps(cd, ensure_ascii=False) if isinstance(cd, dict) else str(cd or "")
    return row


class Pipeline:
    def __init__(
        self,
        *,
        schema_path: str | Path,
        blocks_dir: str | Path,
        source_prompt_dir: str | Path,
        feedback_rules_path: str | Path,
        retrieval_corpus_path: str | Path | None = None,
        context_mode: str = "schema_fallback",
    ):
        self.schema = load_service_schema(schema_path)
        self.blocks_dir = Path(blocks_dir)
        self.source_prompt_dir = Path(source_prompt_dir)
        self.source_assets = prompts.load_source_prompt_assets(source_prompt_dir)
        self.feedback_rules = feedback.load_feedback_rules(feedback_rules_path)
        self.context_mode = context_mode
        self.retriever = None
        if context_mode == "bm25_fallback":
            if not retrieval_corpus_path:
                raise ValueError("bm25_fallback requires retrieval corpus path")
            self.retriever = Bm25Retriever(retrieval_corpus_path)

    # ---- 입력·프롬프트 -------------------------------------------------------------
    def prompt_values(self, row: dict[str, str], row_no: int = 0) -> dict[str, Any]:
        return prompts.build_prompt_values(
            row_no,
            row,
            self.schema,
            context_mode=self.context_mode,
            retriever=self.retriever,
            retrieval_topk=RETRIEVAL_TOPK,
        )

    def render(self, values: dict[str, Any], *, prompt_mode: str, genome: dict[str, Any]) -> dict[str, Any]:
        command_text = values["command_text"]
        if prompt_mode == "source":
            system, user, manifest = prompts.render_source_prompt(
                values=values, command_text=command_text, assets=self.source_assets, prompt_dir=self.source_prompt_dir
            )
        elif prompt_mode == "blocks":
            system, user, manifest = prompts.render_block_prompt(genome, values=values, blocks_dir=self.blocks_dir)
        else:
            raise ValueError("prompt_mode must be 'source' or 'blocks'")
        return {"prompt_mode": prompt_mode, "system": system, "user": user, "manifest": manifest,
                "chars": len(system) + len(user)}

    # ---- 후처리·검사 -----------------------------------------------------------------
    def check_output(self, raw_text: str, *, connected_devices: dict[str, Any]) -> dict[str, Any]:
        # 공개 입력에는 일정 힌트(optional_cron/period)가 없으므로 period 기본값은 0 이다.
        normalized = postprocess.normalize_candidate_json_text(raw_text, service_schema=self.schema)
        check_raw = validation.check_candidate(raw_text, service_schema=self.schema, connected_devices=connected_devices)
        check_post = validation.check_candidate(normalized["text"], service_schema=self.schema, connected_devices=connected_devices)
        return {
            "raw_text": raw_text,
            "postprocess": normalized,
            "check_raw": check_raw,
            "check_postprocessed": check_post,
            "failure_reasons": check_post["failure_reasons"],
        }

    # ---- 생성 ----------------------------------------------------------------------------
    @staticmethod
    def _generate_live(prompt: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        response = llm.call_chat_completion(
            endpoint=settings["endpoint"], model=settings["model"], system=prompt["system"], user=prompt["user"],
            temperature=settings["temperature"], max_tokens=settings["max_tokens"], timeout_sec=settings["timeout_sec"],
        )
        return {
            "source": "live",
            "provenance": {k: settings[k] for k in ("endpoint", "model", "temperature", "max_tokens")},
            "text": response["content"],
            "usage": {k: response[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens", "finish_reason")},
        }

    # ---- 실행 --------------------------------------------------------------------------
    def run_case(
        self,
        case: dict[str, Any],
        *,
        mode: str,
        out_dir: str | Path,
        prompt_mode: str = "blocks",
        genome: dict[str, Any] | None = None,
        saved_output: dict[str, Any] | None = None,
        endpoint: str = "",
        model: str = "",
        timeout_sec: int = 120,
        max_tokens: int = llm.DEFAULT_MAX_TOKENS,
        temperature: float = llm.DEFAULT_TEMPERATURE,
        feedback_rounds: int = 1,
    ) -> dict[str, Any]:
        """사례 하나를 실행하고 out_dir 에 기록한다. summary.json 은 단계마다 갱신되며, live 호출이 실패하면
        그때까지의 요약에 status=failed 와 failed_step 을 적어 남기고 LLMCallError 를 다시 올린다."""
        if mode not in ("offline", "live"):
            raise ValueError("mode must be 'offline' or 'live'")
        if feedback_rounds not in (0, 1):
            raise ValueError("feedback_rounds must be 0 or 1")
        if mode == "offline" and not (saved_output and str(saved_output.get("text", "")).strip()):
            raise ValueError("offline mode requires a saved output with a non-empty 'text'")
        if mode == "live" and not (endpoint and model):
            raise llm.LLMCallError("live mode requires an endpoint and a model id")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name in RUN_ARTIFACTS:                    # 이전 실행의 기록이 이번 결과와 섞이지 않게 한다
            (out / name).unlink(missing_ok=True)
        shutil.rmtree(out / "blocks", ignore_errors=True)
        settings = {"endpoint": endpoint, "model": model, "temperature": temperature,
                    "max_tokens": max_tokens, "timeout_sec": timeout_sec}
        row = case_input_row(case)
        connected = parse_connected_devices(row["connected_devices"])
        values = self.prompt_values(row)
        genome = genome or prompts.DEFAULT_GENOME
        summary: dict[str, Any] = {"mode": mode, "prompt_mode": prompt_mode, "status": "running", "steps": []}

        def checkpoint(step: str) -> None:
            summary["steps"].append(step)
            write_json(out / "summary.json", summary)

        write_json(out / "inputs.json", {"row": row, "source": case.get("source", {}),
                                         "connected_devices_parse_failed": bool(row["connected_devices"].strip()) and not connected})
        write_json(out / "service_context.json", json.loads(values["service_list_snippet"]))
        initial_prompt = self.render(values, prompt_mode=prompt_mode, genome=genome)
        write_json(out / "prompt_initial.json", initial_prompt)
        checkpoint("prompt_initial")

        try:
            if mode == "offline":
                initial = {"source": "saved_output", "provenance": saved_output.get("provenance", {}),
                           "text": str(saved_output["text"]), "usage": None,
                           "note": "저장 출력은 provenance 의 프롬프트로 생성된 것이며 prompt_initial.json 으로 생성한 결과가 아니다."}
            else:
                initial = self._generate_live(initial_prompt, settings)
        except llm.LLMCallError as exc:
            summary.update({"status": "failed", "failed_step": "generate_initial", "error": str(exc)})
            write_json(out / "summary.json", summary)
            raise
        write_json(out / "output_initial.json", initial)
        check_initial = self.check_output(initial["text"], connected_devices=connected)
        write_json(out / "check_initial.json", check_initial)
        summary["initial_failure_reasons"] = check_initial["failure_reasons"]
        checkpoint("check_initial")

        guides = feedback.build_guides(check_initial["failure_reasons"], self.feedback_rules)
        write_json(out / "guides.json", guides)
        actionable = [g for g in guides if g["status"] == "guide"]
        summary["guides"] = len(actionable)
        summary["undiagnosed_failures"] = [g["failure_reason"] for g in guides if g["status"] != "guide"]
        patched_prompt = None
        if prompt_mode != "blocks":
            summary["feedback"], summary["feedback_reason"] = "not_applicable", "prompt_mode=source has no blocks"
        elif not actionable:
            summary["feedback"], summary["feedback_reason"] = "not_needed", "no actionable failure after post-processing"
        elif feedback_rounds < 1:
            summary["feedback"], summary["feedback_reason"] = "disabled", "feedback_rounds=0"
        else:
            applied = feedback.apply_feedback(genome, actionable, blocks_dir=self.blocks_dir, out_dir=out)
            write_json(out / "genome_patched.json", applied["genome"])
            (out / "block_diff.txt").write_text("".join(c["diff"] for c in applied["changes"]), encoding="utf-8")
            patched_prompt = self.render(values, prompt_mode=prompt_mode, genome=applied["genome"])
            write_json(out / "prompt_patched.json", patched_prompt)
            summary["feedback"] = "applied"
            summary["patched_blocks"] = [c["block_id"] for c in applied["changes"]]
            checkpoint("prompt_patched")

        after = check_after = None
        if patched_prompt is not None and mode == "live":
            try:
                after = self._generate_live(patched_prompt, settings)
            except llm.LLMCallError as exc:
                summary.update({"status": "failed", "failed_step": "regeneration", "error": str(exc),
                                "regeneration": "failed"})
                self._evaluate(case, out, summary, initial, check_initial, None, None)
                write_json(out / "summary.json", summary)
                raise
            write_json(out / "output_after_feedback.json", after)
            check_after = self.check_output(after["text"], connected_devices=connected)
            write_json(out / "check_after_feedback.json", check_after)
            summary["regeneration"] = "performed"
            summary["after_failure_reasons"] = check_after["failure_reasons"]
            checkpoint("regeneration")
        else:
            summary["regeneration"] = "not_performed"
            summary["regeneration_reason"] = "offline mode" if mode == "offline" else "no feedback applied"

        self._evaluate(case, out, summary, initial, check_initial, after, check_after)
        summary["status"] = "completed"
        write_json(out / "summary.json", summary)
        return summary

    @staticmethod
    def _evaluate(case, out, summary, initial, check_initial, after, check_after) -> None:
        reference = case.get("reference")
        if not reference:
            return
        items = {
            "initial_parsed": evaluate_parsed(reference, initial["text"]),
            "initial_postprocessed": evaluate_postprocessed(reference, check_initial["postprocess"]["text"]),
        }
        if after is not None and check_after is not None:
            items["after_parsed"] = evaluate_parsed(reference, after["text"])
            items["after_postprocessed"] = evaluate_postprocessed(reference, check_after["postprocess"]["text"])
        write_json(out / "evaluation.json", {
            "threshold": evaluation.DEFAULT_THRESHOLD,
            "note": "parsed = 응답에서 JSON 블록만 잘라 낸 출력, postprocessed = 스키마 기반 정규화까지 적용한 출력",
            "items": items,
        })
        summary["evaluation"] = {k: {"e": v["e"], "det_pass": v["det_pass"]} for k, v in items.items()}
