# 변환 파이프라인

자연어 명령과 장치 문맥에서 JOILang 시나리오 JSON을 만드는 기존 구현의 최소 경로다. 아래 단계와 함수는
`src/joilang_kor/` 의 실제 코드와 대응한다. 전체 GA 탐색(GPS-PromptOps)과 웹 서버·장치 실행은 포함하지 않는다.

```text
입력(행: command_eng/kor, connected_devices)        data.select_rows, pipeline.case_input_row
  → 서비스 선정·부분 스키마                          schema.build_service_snippet_payload
  → 프롬프트 조립 (source | blocks)                  prompts.render_source_prompt | prompts.render_block_prompt
  → 모델 생성 (live)                                 llm.call_chat_completion
  → 후처리(정규화)                                   postprocess.normalize_candidate_json_text
  → 규칙 검사                                        validation.check_candidate
  → [피드백 예제] 실패 유형→가이드→블록 수정→재생성    feedback.build_guides / apply_feedback, pipeline.Pipeline.run_case
  → 평가(기준 코드와 비교; 생성 입력과 분리)          evaluation.evaluate_item
```

## 1. 입력

한 평가 항목은 `command_kor`, `command_eng`, `connected_devices` 를 생성 입력으로 쓴다. 기준 코드(`gt`)는
`Pipeline.run_case` 에서 `reference` 로만 받아 평가에 쓰고, 프롬프트 값(`prompts.build_prompt_values`)에는
넣지 않는다(테스트 `test_reference_never_enters_prompts`). 두 언어 명령은 함께 넣는다:

```text
English command: Set the siren to emergency mode.
Korean command: 사이렌을 비상 모드로 설정해줘.
```

## 2. 서비스 선정과 부분 스키마

`schema.build_service_snippet_payload(command, connected_devices, schema, context_mode=...)` 가 입력별
서비스 문맥(JSON)을 만든다. 각 장치 그룹에 대해 범주별 **전체 서비스 목록**(정식 명칭, 자료형, 허용값,
설명)과 수신자 예시를 묶는다(`build_capability_binding`).

| 상황 | 동작 | 출처 |
|---|---|---|
| `connected_devices` 가 있음 (140행) | 그 장치들의 범주만 사용(`connected_devices_only`). 검색을 하지 않는다. | 원본과 동일 |
| 없음, `--context-mode schema_fallback` (기본) | 50개 범주 전체를 넣는다(`service_schema_fallback`). | 원본과 동일 |
| 없음, `--context-mode bm25_fallback` | 범주 설명 문서 50건([`schemas/service_retrieval_corpus.json`](../schemas/service_retrieval_corpus.json))에 대한 BM25 검색 상위 10개 + 명령 문구로 정한 필수 범주(`mandatory_retrieval_categories`)를 넣는다(`service_retrieval_fallback`). | 원본 검색 경로 중 `retrieval_mode=bm25` 부분. BM25 구현(`SimpleBM25`)과 필수 범주 규칙은 원본 그대로 |
| **제공하지 않음** | 검색의 dense 부분. 원고가 인용하던 선행 변환 구현의 검색은 dense 임베딩+BM25 하이브리드였고, 이 저장소가 옮긴 구현 스냅샷의 기본값도 파인튜닝 bge-m3 dense 0.9 + BM25 0.1 하이브리드다. 두 경우 모두 비공개 임베딩 번들·모델(2.2 GB)이 필요하다. | 문서로만 기록 |

따라서 "관련 장치·기능 정보를 찾고 필요한 서비스만 추림"은 (1) 준비된 장치 문맥에서 범주를 고르는 경로와
(2) 문맥이 없을 때의 BM25 검색 경로로 제공된다. 서비스 문맥 JSON 의 `retrieval` 메타데이터는 원본과 같은
필드를 기록한다(`mode`/`device` 는 원본 기본 설정값). 원본과의 바이트 단위 대조는 `tests/test_pipeline.py::test_service_context_matches_original`.

## 3. 프롬프트 조립

두 조립 경로가 있으며 둘 다 2절의 문맥을 조립 직전에 넣는다.

**source** — 실험의 출발점인 클라우드용 원 프롬프트. [`prompts/source_prompt/`](../prompts/source_prompt/) 의
다섯 파일을 원본 조립 코드와 같은 순서로 하나의 system prompt 에 넣고(`prompts.render_source_prompt`), 사용자
메시지는 명령 문장이다. 구성 순서와 파일 해시는 [`prompts/source_prompt/MANIFEST.json`](../prompts/source_prompt/MANIFEST.json).
행 214(연결 장치 3개)에서 약 90k자, 문맥이 없는 행에서 전체 스키마를 넣으면 약 166k자가 된다.

**blocks** — [`prompts/initial_blocks/`](../prompts/initial_blocks/) 의 블록 파일을 유전형(genome)의
`blocks` 순서대로 이어 붙여 사용자 메시지로 쓴다(`prompts.render_block_prompt`; system prompt 는 고정 문장).
기본 유전형은 `["01","02","03","06"]`, 블록 설명은 [`prompts/initial_blocks.json`](../prompts/initial_blocks.json).
`block_params` 로 예제 수(`few_shot_count`)와 규칙 추가(`micro_rules`, `source_file`)를 조정할 수 있다.
원본 GA 구현이 후보를 평가할 때 쓰는 조립 경로이며, 이 저장소는 조립만 제공한다.

```bash
python -m joilang_kor render-prompt --row 214 --prompt-mode source --out runs/prompt_source.json
python -m joilang_kor render-prompt --row 214 --prompt-mode blocks --out runs/prompt_blocks.json
python -m joilang_kor render-prompt --row 4 --context-mode bm25_fallback --out runs/prompt_bm25.json
```

## 4. 생성

`llm.call_chat_completion(endpoint, model, system, user, temperature=0, max_tokens=256, timeout_sec)` 는
OpenAI 호환 `chat/completions` 엔드포인트를 한 번 호출한다(`urllib`, 추가 의존성 없음). 원본의 HF worker
서브프로세스 backend 는 옮기지 않았다. 실패하면 `LLMCallError` 를 올리고 다른 backend 로 바꾸지 않는다.

생성 설정: 원고는 탐욕적 디코딩(`do_sample=false`)과 `max_new_tokens=256` 을 쓴다(256 은 원 프롬프트 프로필의 설정값이며,
2026-08-27 재현 실행 기록은 512 를 사용했다). 이 어댑터는 `temperature=0`, `max_tokens=256` 을 API 파라미터로 보낼 뿐이다. 서버가 `temperature=0` 을 어떻게 디코딩하는지
(예: vLLM 은 탐욕적 디코딩으로 처리)는 서버 구현에 달려 있으며 이 패키지가 검증하지 않는다. 상한에 걸려
JSON 이 끝나지 않은 출력은 검사에서 `invalid_json` 이 된다. 인증 헤더는 환경변수 `JOILANG_KOR_HTTP_AUTH_BEARER`
가 있을 때만 `Authorization: Bearer` 로 보내고, 없으면 인증 헤더를 보내지 않는다(다른 환경변수는 읽지 않는다).

## 5. 후처리와 검사

**후처리** `postprocess.normalize_candidate_json_text(text, service_schema=...)`(원본 함수명 유지; `evaluation.normalize_candidate` 는 평가기의 후보 정규화로 다른 함수다) — 응답에서 JSON 블록을 잘라 내고
`code` 에 스키마 기반 정규화를 적용한 뒤 `{"name","cron","period","code"}` 로 직렬화한다. 실제로 코드를 바꾼
규칙 이름을 `applied` 에 남긴다. 옮긴 규칙(원본 순서):

1. `normalize_receiver_quantifiers` — `any(` → `all(`, 중첩 `all(all(...))` 정리
2. `lowercase_service_members` — 수신자 뒤 멤버 토큰 소문자화
3. `normalize_receiver_tag_case` — `#태그` 를 스키마 범주명 또는 첫 글자 대문자로
4. `normalize_receiver_tag_order` — 선택자 태그 → 범주 태그 순서, 중복 제거
5. `canonicalize_member_aliases` — 스키마 정식 서비스명으로 해석(접미 일치 1개일 때)
6. `normalize_clock_delay_calls` — `(#Clock).clock_delay(ms)` → `delay(N SEC|MIN|HOUR)`
7. `normalize_function_argument_separators` — 함수 인자 `|` → `,`
8. `normalize_integer_like_numeric_literals` — `12.0` → `12`
9. `schedule_defaults` — period 정수화, 음수·비정수 period 는 0

옮기지 않은 원본 규칙: (1) 자연어 명령 문구를 보고 코드를 고쳐 쓰는 규칙(창문·조명·토글·시간창·트리거 골격·
에어컨/공기청정기 모드·리포트 조건 등 `normalize_*_in_code(code, command_text)` 함수 20여 개와
`normalize_known_temporal_candidate_fields`, `normalize_connected_selector_tags`, `normalize_cooking_time_arguments`),
(2) 특정 장치의 호출 형태를 고쳐 쓰는 규칙(`normalize_invalid_siren_off_mode_calls`, `normalize_dehumidifier_internal_care_mode`,
`normalize_switch_toggle_blocks`, `normalize_dimmer_switch_pressed_enum`, `normalize_light_colorcontrol_setcolor_calls`,
`normalize_windowcovering_semantic_receivers`, `normalize_semantic_receiver_tag_order`).
둘 다 명령 유형·장치별 의미 재작성이므로 "규칙 검사와 수정"의 일반 경로에서 분리했다. 이 때문에 공개 후처리 결과는 원본 전체 후처리 결과와 다를 수 있다.
옮긴 규칙 8개는 원본 함수와 같은 입력에서 같은 출력을 낸다(`tests/test_pipeline.py::test_normalization_matches_original`, 320건).

**검사** `validation.check_candidate(text, service_schema=..., connected_devices=...)` — 원본 strict 평가기의
스키마 검사 부분이다. 검사 함수는 원본 파이프라인과 같이 먼저 응답에서 JSON 블록을 잘라 낸다(펜스·앞뒤 문장 제거;
원본 평가 함수 자체는 잘라 내지 않는다). 실패 유형: `invalid_json`, `schema_missing_keys`, `unknown_service:<member>`,
`service_match`(서비스 해석 실패가 하나라도 있음), `arg_type`(인자 수·자료형 점수 < 1), `no_parseable_member_access`.
멤버 접근이 하나도 없는 코드(빈 코드 포함)는 원본과 같이 `service_match` 와 `arg_type` 을 함께 받는다. 멤버 토큰의
대문자 여부는 실패 유형이 아니라 `usages[*].service_case` 표시로만 남기고 후처리 규칙 `lowercase_service_members` 가
정정한다. 검출하지 않는 것은 [joilang.md](joilang.md) 5절.

**평가** `evaluation.evaluate_item(reference, candidate, threshold=0.90)` — 여덟 비교값의 가중합 e(0–1)와
통과 판정. 가중치 `(0.30, 0.15, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05)`, τ=0.90. 파싱 실패는 e=0·v=0, 코드가 비면
v=0. 통과 판정은 여덟 가중 항을 원본과 같은 순서로 더한 배정밀도 부동소수 합에 대해 `e >= 0.90` 으로 하며 반올림하지
않는다(정확히 0.90 이 되는 성분 조합은 부동소수 표현에 따라 어느 쪽으로도 떨어질 수 있다). 일정 비교는 원본과 같이
`str(value or "")` 로 문자열화하므로 정수 0 은 "" 이 되고 문자열 "0" 은 "0" 그대로여서 서로 일치하지 않는다(후처리
경로는 period 를 정수화한다). 비교값 계산 함수는 원본 8항 평가기(`det_evaluator.py`)를 그대로 옮겼고, 원본 함수의
결과 형식(0–100 점수, 임계값 70)은 `original_det_evaluate_row` 가 같은 비교값 위에서 재현한다(대조 테스트용). 원고의 계산 예(외부 온도 항목의 간결형 출력,
e = 0.9264397905759162)를 재현한다(`tests/test_evaluation.py::test_golden_worked_example`). 채점 대상은 항상 파싱(응답에서 JSON 블록 추출)을 거친 출력이며, 정규화까지 적용했는지는 결과의 `evaluated_on`
(`parsed`/`postprocessed`) 또는 항목 이름(`initial_parsed`, `initial_postprocessed`)으로 남긴다. 원본 8항 평가기
함수 자체는 펜스를 제거하지 않으므로 원문을 그대로 넣으면 `invalid_json` 이 된다. DET 는 정적 참조 비교이며 실행 동등성을 뜻하지 않는다.

## 6. 피드백 예제 (기본 1회)

코드 후처리(생성된 출력을 바꿈)와 프롬프트 피드백(다음 생성의 블록 지침을 바꿈)은 별개 경로다. 피드백 예제는
blocks 조립에서만 동작한다(source 프롬프트는 블록이 없으므로 `feedback: not_applicable`).

1. 초기 블록 + 명령·서비스 문맥으로 프롬프트를 만든다 → `prompt_initial.json`
2. 생성(live) 또는 저장 출력(offline) → `output_initial.json`. offline 의 저장 출력은 그 파일의 provenance 에 적힌
   프롬프트로 생성된 것이며 1의 `prompt_initial.json` 으로 만든 결과가 아니다(블록 조립과 보강을 보여 주기 위한 프롬프트).
3. 후처리·검사 → `check_initial.json` (`check_raw`, `check_postprocessed`, 적용 규칙)
4. 후처리 후에도 남은 실패 유형마다 [`prompts/feedback_rules.json`](../prompts/feedback_rules.json) 의
   `det_feedback_rules` 에서 대상 블록과 규칙 문장을 고른다 → `guides.json`. 대응: `invalid_json` → 블록 03(출력 형식),
   `schema_missing_keys` → 03, `unknown_service`/`service_match`/`arg_type` → 블록 02(서비스 매핑). 규칙이 없는 유형
   (`no_parseable_member_access`)은 `no_rule`(진단 불가)로 남긴다.
5. 대상 블록 파일 끝에 `AUTO-PATCH MICRO-RULES` 절을 붙인 수정본을 실행 디렉터리 `blocks/` 에 쓴다
   (원본 파일은 바꾸지 않음; 같은 규칙을 다시 적용해도 중복되지 않음) → `block_diff.txt`, `genome_patched.json`, `prompt_patched.json`
6. live 모드에서만 같은 입력으로 한 번 재생성 → `output_after_feedback.json`, `check_after_feedback.json`
7. `reference` 가 있으면 초기/재생성, 파싱/후처리 출력을 각각 평가 → `evaluation.json`

가이드에는 실패 유형과 규칙 문장만 들어가며 기준 코드나 정답 예제는 넣지 않는다. 결과가 좋아지지 않거나
나빠져도 그대로 기록한다. 이 예제는 모집단·교차·변이를 포함한 GA 탐색이 아니다. Self-Refine 이나 Reflexion
([`REF_SELFREFINE`](references.bib), [`REF_REFLEXION`](references.bib))이 모델의 자기 피드백으로 출력을 다시
쓰는 것과 달리, 여기서는 규칙 검사에서 얻은 실패 유형이 다음 생성에 쓰는 블록의 지침을 바꾼다.

```bash
python -m joilang_kor demo --mode offline --case examples/scenario.json --out runs/demo
python -m joilang_kor demo --mode live --case examples/scenario.json --endpoint http://127.0.0.1:8000/v1 --model MODEL_ID --feedback-rounds 1 --out runs/live
```

`examples/saved_output.json`(JSON 파싱 실패 출력)과 `examples/saved_output_siren.json`(등록되지 않은
서비스명 → 후처리로 정정)은 실험 기록에서 그대로 가져온 모델 출력이며 출처를 파일 안에 적었다. 검사 예제
입력이지 성능 수치의 근거가 아니다.

## 7. 실행 기록

`runs/<이름>/` 에 입력(`inputs.json`; connected_devices 를 읽지 못하면 `connected_devices_parse_failed: true`),
서비스 문맥, 초기 프롬프트, 초기 원시 출력, 후처리·검사 결과, 가이드, 블록 diff, 수정 프롬프트, (live) 재생성 출력과
검사, 평가, `summary.json`(모드·수행 단계·피드백/재생성 상태와 사유·`status`)을 남긴다. 실행 시작 시 같은 디렉터리의
이전 실행 산출물 전부(위 파일들과 `blocks/`)를 지운다. live 호출이 실패하면 그때까지의 단계를 담은 `summary.json`
에 `status: failed`, `failed_step`(`generate_initial` 또는 `regeneration`), 오류 문장을 남기며 재시도·대체는 없다.
timeout 과 피드백 횟수(0 또는 1)에 상한이 있다.

## 8. 제공하지 않는 것

전체 GA 탐색과 적합도·비용 측정, dense/hybrid 검색, HF worker backend, 웹 UI·DB·실제 기기 제어, 원본의
명령 문구·장치별 의미 재작성 규칙, 12항 strict 평가기의 점수 계산. `prompts/feedback_rules.json` 의 `patch_rules`
는 원본 자료로 보존한 것이며 공개 코드는 읽지 않는다.
