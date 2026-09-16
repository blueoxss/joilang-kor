from __future__ import annotations

import hashlib
import io
import json
import urllib.error
from pathlib import Path

import pytest

from joilang_kor import feedback, postprocess, prompts, validation
from joilang_kor.data import parse_connected_devices
from joilang_kor.pipeline import case_input_row, load_case
from joilang_kor.schema import Bm25Retriever, build_service_snippet_payload


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeResponse(io.BytesIO):
    """urllib.request.urlopen 대역: with 문에서 쓸 수 있는 바이트 응답."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ---- 서비스 문맥 ------------------------------------------------------------------

def test_service_context_matches_original(parity, rows, schema):
    for case in parity["service_context"]:
        row = rows[case["row_no"] - 1]
        values = prompts.build_prompt_values(case["row_no"], row, schema)
        assert _sha(values["service_list_snippet"]) == case["sha256"], case["row_no"]
        assert values["service_list_snippet_source"] == case["snippet_source"]
        assert values["service_list_device_count"] == case["device_count"]


def test_service_context_depends_on_input(rows, schema, repo_root):
    with_devices = rows[213]      # category 7 index 34: WindowCovering 만
    without = rows[3]             # category 1 index 4: connected_devices 없음
    snippet_a, _ = build_service_snippet_payload(with_devices["command_eng"], parse_connected_devices(with_devices["connected_devices"]), schema)
    snippet_b, _ = build_service_snippet_payload(without["command_eng"], {}, schema)
    assert snippet_a["snippet_source"] == "connected_devices_only"
    assert {g["categories"][0] for g in snippet_a["device_groups"]} == {"WindowCovering"}
    assert snippet_b["snippet_source"] == "service_schema_fallback" and len(snippet_b["device_groups"]) == 50
    retriever = Bm25Retriever(repo_root / "schemas/service_retrieval_corpus.json")
    snippet_c, _ = build_service_snippet_payload(without["command_eng"], {}, schema, context_mode="bm25_fallback", retriever=retriever)
    assert snippet_c["snippet_source"] == "service_retrieval_fallback"
    assert "Siren" in {g["categories"][0] for g in snippet_c["device_groups"]}
    assert len(snippet_c["device_groups"]) <= 10


def test_bm25_matches_original(parity, repo_root):
    from joilang_kor.schema import SimpleBM25
    corpus = json.loads((repo_root / "schemas/service_retrieval_corpus.json").read_text(encoding="utf-8"))
    bm25 = SimpleBM25(corpus["texts"])
    for case in parity["bm25"]:
        scores = bm25.get_scores(case["query"])
        top10 = [corpus["keys"][i] for i in sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:10]]
        assert top10 == case["expected_top10"], case["query"]
        assert max(abs(a - b) for a, b in zip(scores, case["expected_scores_float32"])) < 1e-4


# ---- 프롬프트 조립 ----------------------------------------------------------------

def test_prompt_rendering_matches_original(parity, rows, schema, repo_root):
    assets = prompts.load_source_prompt_assets(repo_root / "prompts/source_prompt")
    for case in parity["prompts"]:
        row = rows[case["row_no"] - 1]
        values = prompts.build_prompt_values(case["row_no"], row, schema)
        if case["prompt_mode"] == "source":
            system, user, _ = prompts.render_source_prompt(values=values, command_text=values["command_text"], assets=assets)
            assert _sha(system) == case["system_sha256"] and user == case["user"]
        else:
            system, user, _ = prompts.render_block_prompt(prompts.DEFAULT_GENOME, values=values, blocks_dir=repo_root / "prompts/initial_blocks")
            assert system == case["system"] and _sha(user) == case["user_sha256"]


def test_reference_never_enters_prompts(rows, schema, repo_root, pipeline):
    assets = prompts.load_source_prompt_assets(repo_root / "prompts/source_prompt")
    for row_no in (4, 9, 214, 250):
        row = rows[row_no - 1]
        ref_code = json.loads(row["gt"])["script"].strip()
        values = prompts.build_prompt_values(row_no, row, schema)
        assert "gt" not in values
        for mode in ("source", "blocks"):
            rendered = pipeline.render(values, prompt_mode=mode, genome=prompts.DEFAULT_GENOME)
            assert ref_code not in rendered["system"] + rendered["user"]
    case = load_case(repo_root / "examples/scenario.json")
    assert "reference" not in case_input_row(case)


def test_blocks_prompt_follows_genome(rows, schema, repo_root):
    values = prompts.build_prompt_values(214, rows[213], schema)
    short, _ = prompts.render_blocks_for_genome({"blocks": ["01", "02"]}, values=values, blocks_dir=repo_root / "prompts/initial_blocks")
    full, manifest = prompts.render_blocks_for_genome(prompts.DEFAULT_GENOME, values=values, blocks_dir=repo_root / "prompts/initial_blocks")
    assert len(short) < len(full) and [m["id"] for m in manifest] == ["01", "02", "03", "06"]
    fewer, _ = prompts.render_blocks_for_genome({"blocks": ["02"], "block_params": {"02": {"few_shot_count": 1}}}, values=values, blocks_dir=repo_root / "prompts/initial_blocks")
    assert fewer.count("### EXEMPLAR") == 1 and full.count("### EXEMPLAR") == 3


# ---- 후처리·검사 -------------------------------------------------------------------

def test_normalization_matches_original(parity, schema):
    funcs = {
        "normalize_receiver_quantifiers_in_code": lambda c: postprocess.normalize_receiver_quantifiers_in_code(c),
        "lowercase_service_members_in_code": lambda c: postprocess.lowercase_service_members_in_code(c),
        "normalize_receiver_tag_case_in_code": lambda c: postprocess.normalize_receiver_tag_case_in_code(c, schema),
        "normalize_receiver_tag_order_in_code": lambda c: postprocess.normalize_receiver_tag_order_in_code(c, schema),
        "canonicalize_member_aliases_in_code": lambda c: postprocess.canonicalize_member_aliases_in_code(c, schema),
        "normalize_clock_delay_calls_in_code": lambda c: postprocess.normalize_clock_delay_calls_in_code(c),
        "normalize_function_argument_separators_in_code": lambda c: postprocess.normalize_function_argument_separators_in_code(c, schema),
        "normalize_integer_like_numeric_literals_in_code": lambda c: postprocess.normalize_integer_like_numeric_literals_in_code(c),
    }
    for case in parity["normalization"]:
        assert funcs[case["function"]](case["code"]) == case["expected"], (case["function"], case["code"])


def test_validation_matches_original(parity, schema):
    keys = {"invalid_json", "schema_missing_keys", "service_match", "arg_type", "no_parseable_member_access", "unknown_service"}
    for case in parity["validation"]:
        result = validation.check_candidate(case["candidate"], service_schema=schema, connected_devices=parse_connected_devices(case["connected_devices"]))
        got = sorted({r for r in result["failure_reasons"] if r.split(":")[0] in keys})
        assert got == case["expected_failure_reasons"], case["row_no"]
        assert round(result["service_match"], 6) == case["expected_service_match"]
        assert round(result["arg_type_ok"], 6) == case["expected_arg_type_ok"]


def test_validation_detects_and_limits(schema):
    ok = validation.check_candidate('{"name":"","cron":"","period":0,"code":"(#Siren).siren_setsirenmode(\\"emergency\\")"}', service_schema=schema)
    assert ok["failure_reasons"] == []
    bad_type = validation.check_candidate('{"name":"","cron":"","period":0,"code":"(#Speaker).speaker_setvolume(\\"30\\")"}', service_schema=schema)
    assert "arg_type" in bad_type["failure_reasons"]  # INTEGER 인자에 문자열 리터럴
    # 함수 항목에 허용값 목록이 없으면(예: Siren.SetSirenMode) 잘못된 열거값을 검출하지 못한다
    assert validation.check_candidate('{"name":"","cron":"","period":0,"code":"(#Siren).siren_setsirenmode(\\"loud\\")"}', service_schema=schema)["failure_reasons"] == []
    unknown = validation.check_candidate('{"name":"","cron":"","period":0,"code":"(#Siren).siren_playsound(\\"x\\")"}', service_schema=schema)
    assert "unknown_service:siren_playsound" in unknown["failure_reasons"] and "service_match" in unknown["failure_reasons"]
    missing = validation.check_candidate('{"name":"","code":"(#Siren).siren_setsirenmode(\\"fire\\")"}', service_schema=schema)
    assert missing["failure_reasons"] == ["schema_missing_keys"]
    assert validation.check_candidate("```json\n{\"name\":\"\",\"cron\":\"\",\"period\":0,\"code\":\"(#Light).switch_on()\"}\n```", service_schema=schema)["valid_json"]
    # 검출하지 않는 것: JOILang 문법(while) — 멤버 접근이 스키마에 맞으면 통과한다
    loop = validation.check_candidate('{"name":"","cron":"","period":0,"code":"while (true) { (#Light).switch_on() }"}', service_schema=schema)
    assert loop["failure_reasons"] == []
    # 멤버 접근이 전혀 없는 코드·빈 코드: 원본과 같이 service_match/arg_type 이 붙는다
    empty = validation.check_candidate('{"name":"","cron":"","period":0,"code":""}', service_schema=schema)
    assert empty["failure_reasons"] == ["service_match", "arg_type"]
    prose = validation.check_candidate('{"name":"","cron":"","period":0,"code":"turn on the light"}', service_schema=schema)
    assert prose["failure_reasons"] == ["no_parseable_member_access", "service_match", "arg_type"]
    assert validation.check_candidate("[1, 2]", service_schema=schema)["failure_reasons"] == ["schema_missing_keys"]


def test_postprocess_repairs_service_name_and_records_rules(schema):
    text = '```json\n{"name": "S", "cron": "", "period": -1, "code": "(#Siren).sirenMode_setSirenMode(\\"emergency\\")"}\n```'
    out = postprocess.normalize_candidate_json_text(text, service_schema=schema)
    assert out["parsed"] and json.loads(out["text"])["code"] == '(#Siren).siren_setsirenmode("emergency")'
    assert out["applied"][:2] == ["lowercase_service_members", "canonicalize_member_aliases"] and "schedule_defaults" in out["applied"]
    assert json.loads(out["text"])["period"] == 0
    untouched = postprocess.normalize_candidate_json_text('{"name":"","cron":"","period":0,"code":"(#Siren).siren_setsirenmode(\\"fire\\")"}', service_schema=schema)
    assert untouched["applied"] == []
    assert postprocess.normalize_candidate_json_text("not json", service_schema=schema)["parsed"] is False


# ---- 피드백 -------------------------------------------------------------------------

def test_feedback_guides_and_block_patch_are_idempotent(repo_root, tmp_path):
    rules = feedback.load_feedback_rules(repo_root / "prompts/feedback_rules.json")
    guides = feedback.build_guides(["invalid_json", "unknown_service:siren_playsound", "service_match", "no_parseable_member_access"], rules)
    actionable = [g for g in guides if g["status"] == "guide"]
    assert [g["block_id"] for g in actionable] == ["03", "02", "02"]
    assert actionable[0]["failure_type"] == "invalid_json"
    assert actionable[1]["failure_reason"].startswith("unknown_service") and actionable[1]["rule"] != actionable[2]["rule"]
    assert [g["failure_reason"] for g in guides if g["status"] == "no_rule"] == ["no_parseable_member_access"]
    first = feedback.apply_feedback(prompts.DEFAULT_GENOME, guides, blocks_dir=repo_root / "prompts/initial_blocks", out_dir=tmp_path / "r1")
    again = feedback.apply_feedback(first["genome"], guides, blocks_dir=repo_root / "prompts/initial_blocks", out_dir=tmp_path / "r2")
    assert again["genome"]["id"] == first["genome"]["id"]
    for change in again["changes"]:
        assert Path(change["patched"]).read_text().count(feedback.AUTO_PATCH_TITLE) == 1
    assert (repo_root / "prompts/initial_blocks/03_postprocessor.txt").read_text().count(feedback.AUTO_PATCH_TITLE) == 0
    assert feedback.apply_feedback(prompts.DEFAULT_GENOME, [], blocks_dir=repo_root / "prompts/initial_blocks", out_dir=tmp_path / "r3")["changes"] == []


# ---- 오프라인 데모 -------------------------------------------------------------------

def test_offline_demo_invalid_json_case(repo_root, pipeline, tmp_path):
    case = load_case(repo_root / "examples/scenario.json")
    saved = json.loads((repo_root / "examples/saved_output.json").read_text(encoding="utf-8"))
    summary = pipeline.run_case(case, mode="offline", out_dir=tmp_path, saved_output=saved)
    assert summary["initial_failure_reasons"] == ["invalid_json"]
    assert summary["feedback"] == "applied" and summary["patched_blocks"] == ["03"]
    assert summary["regeneration"] == "not_performed" and summary["regeneration_reason"] == "offline mode"
    assert summary["status"] == "completed"
    assert (tmp_path / "prompt_patched.json").exists() and not (tmp_path / "output_after_feedback.json").exists()
    patched = json.loads((tmp_path / "prompt_patched.json").read_text())
    assert "AUTO-PATCH MICRO-RULES" in patched["user"]
    assert summary["evaluation"]["initial_parsed"]["det_pass"] is False


def test_offline_demo_siren_case(repo_root, pipeline, tmp_path):
    case = load_case(repo_root / "examples/scenario_siren.json")
    saved = json.loads((repo_root / "examples/saved_output_siren.json").read_text(encoding="utf-8"))
    summary = pipeline.run_case(case, mode="offline", out_dir=tmp_path, saved_output=saved)
    check = json.loads((tmp_path / "check_initial.json").read_text())
    assert "unknown_service:sirenMode_setSirenMode" in check["check_raw"]["failure_reasons"]
    assert check["check_raw"]["usages"][0]["service_case"] is True
    assert check["check_postprocessed"]["failure_reasons"] == []
    assert summary["feedback"] == "not_needed"
    assert summary["evaluation"]["initial_postprocessed"] == {"e": 1.0, "det_pass": True}
    assert summary["evaluation"]["initial_parsed"]["det_pass"] is False   # 파싱만 하면 sirenMode_setSirenMode 가 기준과 다름


def test_live_mode_reports_connection_failure(repo_root, pipeline, tmp_path, monkeypatch):
    import urllib.request
    from joilang_kor.llm import LLMCallError

    case = load_case(repo_root / "examples/scenario.json")
    with pytest.raises(LLMCallError, match="requires an endpoint"):
        pipeline.run_case(case, mode="live", out_dir=tmp_path, endpoint="", model="m")

    def refused(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(LLMCallError, match="cannot reach"):
        pipeline.run_case(case, mode="live", out_dir=tmp_path, endpoint="http://127.0.0.1:9/v1", model="m")
    assert not (tmp_path / "output_initial.json").exists()
    failed = json.loads((tmp_path / "summary.json").read_text())
    assert failed["status"] == "failed" and failed["failed_step"] == "generate_initial" and failed["steps"] == ["prompt_initial"]


def test_live_non_json_body_is_reported(monkeypatch):
    import urllib.request
    from joilang_kor import llm

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"<html>proxy</html>"))
    with pytest.raises(llm.LLMCallError, match="non-JSON"):
        llm.call_chat_completion(endpoint="http://127.0.0.1:9/v1", model="m", system="s", user="u")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps({"choices": [{"message": {"content": None}}]}).encode()))
    with pytest.raises(llm.LLMCallError, match="non-text"):
        llm.call_chat_completion(endpoint="http://127.0.0.1:9/v1", model="m", system="s", user="u")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": "n/a"}}).encode()))
    with pytest.raises(llm.LLMCallError, match="unexpected payload"):
        llm.call_chat_completion(endpoint="http://127.0.0.1:9/v1", model="m", system="s", user="u")


def test_live_regeneration_failure_keeps_partial_summary(repo_root, pipeline, tmp_path, monkeypatch):
    import urllib.request
    from joilang_kor import llm

    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            body = json.dumps({"choices": [{"message": {"content": "not json at all"}, "finish_reason": "stop"}], "usage": {}})
            return FakeResponse(body.encode())
        raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    case = load_case(repo_root / "examples/scenario.json")
    with pytest.raises(llm.LLMCallError):
        pipeline.run_case(case, mode="live", out_dir=tmp_path, endpoint="http://127.0.0.1:9/v1", model="m")
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["status"] == "failed" and summary["failed_step"] == "regeneration"
    assert summary["steps"] == ["prompt_initial", "check_initial", "prompt_patched"] and summary["feedback"] == "applied"
    assert (tmp_path / "evaluation.json").exists() and "initial_parsed" in summary["evaluation"]
    assert calls["n"] == 2


def test_offline_run_ignores_stale_after_files(repo_root, pipeline, tmp_path):
    case = load_case(repo_root / "examples/scenario.json")
    saved = json.loads((repo_root / "examples/saved_output.json").read_text(encoding="utf-8"))
    (tmp_path / "output_after_feedback.json").write_text('{"text": "stale"}')
    (tmp_path / "check_after_feedback.json").write_text('{"postprocess": {"text": "stale"}}')
    summary = pipeline.run_case(case, mode="offline", out_dir=tmp_path, saved_output=saved)
    assert set(summary["evaluation"]) == {"initial_parsed", "initial_postprocessed"}
    assert not (tmp_path / "output_after_feedback.json").exists()
    # 이전 실행의 피드백 산출물도 다음 실행(피드백 불필요)에서는 남지 않는다
    siren = load_case(repo_root / "examples/scenario_siren.json")
    saved_siren = json.loads((repo_root / "examples/saved_output_siren.json").read_text(encoding="utf-8"))
    summary = pipeline.run_case(siren, mode="offline", out_dir=tmp_path, saved_output=saved_siren)
    assert summary["feedback"] == "not_needed"
    assert not (tmp_path / "prompt_patched.json").exists() and not list((tmp_path / "blocks").glob("*"))
