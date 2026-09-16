"""CLI: python -m joilang_kor <check-data|render-prompt|demo|score> ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import evaluation, paths, postprocess, prompts
from .data import check_dataset, load_dataset_rows, select_rows
from .llm import LLMCallError
from .pipeline import Pipeline, case_input_row, evaluate_parsed, evaluate_postprocessed, load_case, write_json
from .schema import load_service_schema


def _pipeline(args: argparse.Namespace) -> Pipeline:
    if args.retrieval_corpus and args.context_mode != "bm25_fallback":
        raise SystemExit("--retrieval-corpus needs --context-mode bm25_fallback")
    return Pipeline(
        schema_path=paths.default_path(paths.SCHEMA_FILE, args.schema),
        blocks_dir=paths.default_path(paths.BLOCKS_DIR, args.blocks_dir),
        source_prompt_dir=paths.default_path(paths.SOURCE_PROMPT_DIR, args.source_prompt_dir),
        feedback_rules_path=paths.default_path(paths.FEEDBACK_RULES_FILE, args.feedback_rules),
        retrieval_corpus_path=paths.default_path(paths.RETRIEVAL_CORPUS_FILE, args.retrieval_corpus)
        if args.context_mode == "bm25_fallback" else None,
        context_mode=args.context_mode,
    )


def _add_asset_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--schema", default=None, help="서비스 스키마 JSON (기본: schemas/service_list_ver2.0.1.json)")
    parser.add_argument("--blocks-dir", default=None, help="블록 디렉터리 (기본: prompts/initial_blocks)")
    parser.add_argument("--source-prompt-dir", default=None, help="원 프롬프트 디렉터리 (기본: prompts/source_prompt)")
    parser.add_argument("--feedback-rules", default=None, help="피드백 규칙 JSON (기본: prompts/feedback_rules.json)")
    parser.add_argument("--retrieval-corpus", default=None, help="BM25 문서 JSON (기본: schemas/service_retrieval_corpus.json)")
    parser.add_argument("--context-mode", default="schema_fallback", choices=["schema_fallback", "bm25_fallback"],
                        help="connected_devices 가 없을 때의 서비스 문맥: 전체 스키마 또는 BM25 shortlist")


def cmd_check_data(args: argparse.Namespace) -> int:
    report = check_dataset(paths.default_path(paths.DATASET_FILE, args.dataset))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_render_prompt(args: argparse.Namespace) -> int:
    pipe = _pipeline(args)
    if args.case:
        row, row_no = case_input_row(load_case(args.case)), 0
    else:
        rows = load_dataset_rows(paths.default_path(paths.DATASET_FILE, args.dataset))
        selected = select_rows(rows, start_row=args.row, end_row=args.row)
        if not selected:
            raise SystemExit(f"row {args.row} not found")
        row_no, row = selected[0]
    values = pipe.prompt_values(row, row_no)
    genome = json.loads(Path(args.genome).read_text(encoding="utf-8")) if args.genome else prompts.DEFAULT_GENOME
    rendered = pipe.render(values, prompt_mode=args.prompt_mode, genome=genome)
    rendered["service_context_source"] = values["service_list_snippet_source"]
    rendered["service_context_device_count"] = values["service_list_device_count"]
    if args.out:
        write_json(Path(args.out), rendered)
        print(f"wrote {args.out} ({rendered['chars']} chars, context={rendered['service_context_source']}, "
              f"device_groups={rendered['service_context_device_count']})")
    else:
        print(rendered["system"])
        print("\n===== USER =====\n")
        print(rendered["user"])
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    pipe = _pipeline(args)
    case = load_case(args.case)
    saved = None
    if args.mode == "offline":
        if args.saved_output:
            saved_path = Path(args.saved_output)                       # CLI 인자는 현재 디렉터리 기준
        elif case.get("saved_output"):
            saved_path = Path(args.case).resolve().parent / case["saved_output"]   # 사례 파일 안의 경로는 사례 파일 기준
        else:
            raise SystemExit("offline mode needs --saved-output (or a 'saved_output' path in the case file)")
        if not saved_path.is_file():
            raise SystemExit(f"saved output file not found: {saved_path}")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        if args.endpoint or args.model:
            raise SystemExit("--endpoint/--model apply to live mode only")
    elif args.saved_output:
        raise SystemExit("--saved-output applies to offline mode only")
    genome = json.loads(Path(args.genome).read_text(encoding="utf-8")) if args.genome else None
    try:
        summary = pipe.run_case(
            case,
            mode=args.mode,
            out_dir=args.out,
            prompt_mode=args.prompt_mode,
            genome=genome,
            saved_output=saved,
            endpoint=args.endpoint or "",
            model=args.model or "",
            timeout_sec=args.timeout,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            feedback_rounds=args.feedback_rounds,
        )
    except LLMCallError as exc:
        print(f"error: {exc}", file=sys.stderr)          # 단계별 요약은 run_case 가 summary.json 에 이미 남겼다
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    rows = load_dataset_rows(paths.default_path(paths.DATASET_FILE, args.dataset))
    predictions_path = Path(args.predictions)
    if not predictions_path.is_file():
        raise SystemExit(f"predictions file not found: {predictions_path} (JSONL lines: {{\"row_no\": 1, \"output\": \"...\"}})")
    predictions = []
    for line_no, line in enumerate(predictions_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            pred = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"line {line_no}: not valid JSON: {exc}")
        row_no = pred.get("row_no") if isinstance(pred, dict) else None
        if not isinstance(row_no, int) or isinstance(row_no, bool):
            raise SystemExit(f"line {line_no}: row_no must be an integer")
        if not 1 <= row_no <= len(rows):
            raise SystemExit(f"line {line_no}: row_no {row_no} out of range 1..{len(rows)}")
        predictions.append((row_no, str(pred.get("output", ""))))
    schema = None
    if args.candidate == "postprocessed":
        schema = load_service_schema(paths.default_path(paths.SCHEMA_FILE, args.schema))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with (out / "rows.jsonl").open("w", encoding="utf-8") as handle:
        for row_no, text in predictions:
            row = rows[row_no - 1]
            if schema is not None:
                item = evaluate_postprocessed(row["gt"], postprocess.normalize_candidate_json_text(text, service_schema=schema)["text"],
                                              threshold=args.threshold)
            else:
                item = evaluate_parsed(row["gt"], text, threshold=args.threshold)
            item.update({"row_no": row_no, "category": row["category"], "index": row["index"]})
            results.append(item)
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    summary = evaluation.aggregate(results)
    summary.update({"threshold": args.threshold, "evaluated_on": args.candidate, "rows_file": str(out / "rows.jsonl")})
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="joilang_kor")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check-data", help="JOICommands-280 정합성 검사")
    p.add_argument("--dataset", default=None)
    p.set_defaults(func=cmd_check_data)

    p = sub.add_parser("render-prompt", help="행 또는 사례 파일의 프롬프트 조립 결과 출력")
    p.add_argument("--dataset", default=None)
    p.add_argument("--row", type=int, default=1, help="1부터 세는 CSV 행 번호")
    p.add_argument("--case", default=None, help="examples/scenario.json 형식의 사례 파일")
    p.add_argument("--prompt-mode", default="blocks", choices=["source", "blocks"])
    p.add_argument("--genome", default=None, help="blocks 모드 유전형 JSON (기본: 01,02,03,06)")
    p.add_argument("--out", default=None)
    _add_asset_args(p)
    p.set_defaults(func=cmd_render_prompt)

    p = sub.add_parser("demo", help="검사→가이드→블록 보강(→live 재생성) 예제")
    p.add_argument("--mode", required=True, choices=["offline", "live"])
    p.add_argument("--case", required=True)
    p.add_argument("--saved-output", default=None, help="offline 모드의 저장 출력 JSON(현재 디렉터리 기준 경로; 생략 시 사례 파일의 saved_output 을 사례 파일 기준으로 읽음)")
    p.add_argument("--out", required=True)
    p.add_argument("--prompt-mode", default="blocks", choices=["source", "blocks"])
    p.add_argument("--genome", default=None)
    p.add_argument("--endpoint", default=None, help="OpenAI 호환 base URL 또는 chat/completions URL (live 필수; 인증 헤더는 JOILANG_KOR_HTTP_AUTH_BEARER 가 있을 때만)")
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--feedback-rounds", type=int, choices=[0, 1], default=1)
    _add_asset_args(p)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("score", help="저장된 출력(JSONL: row_no, output)을 DET 로 채점")
    p.add_argument("--dataset", default=None)
    p.add_argument("--schema", default=None)
    p.add_argument("--predictions", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=evaluation.DEFAULT_THRESHOLD)
    p.add_argument("--candidate", default="parsed", choices=["parsed", "postprocessed"],
                   help="parsed: 응답에서 JSON 블록만 잘라 내어 채점(기본), postprocessed: 스키마 기반 정규화까지 적용")
    p.set_defaults(func=cmd_score)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
