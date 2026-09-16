# 논문 문장과 공개 자료의 대응

이 문서는 국문 논문(GPS-PromptOps)이 JOILang 기반 자료를 인용하는 문장(R1–R7)마다 이 저장소의 어떤
파일·함수·확인 명령이 근거가 되는지 적는다. 저장소의 공개는 논문의 방법·실험 결과를 재현했다는 뜻이 아니며,
GPS-PromptOps 의 GA 탐색은 이 저장소에 없다. 원본 개발 저장소(비공개)와의 대응은 버전·파일 해시·변경 범위만 적는다.

## 1. 대응표

| 항목 | 원고의 취지 | 공개 자료 | 확인 명령 / 테스트 |
|---|---|---|---|
| R1·R4 | JOILang은 서비스 수준의 IoT DSL | [joilang.md](joilang.md): VALUE/FUNCTION, 태그, `name/cron/period/code`, 조건·시간·반복 예. 스키마 `schemas/service_list_ver2.0.1.json`(50 범주, value 114, function 81), 문법·시간 규칙 원문 `prompts/source_prompt/grammar_ver1.5.10.md`, `tempo_prompt_9.md` | `python -m joilang_kor render-prompt --row 214 --prompt-mode source`; `tests/test_pipeline.py::test_validation_detects_and_limits` |
| R2 | 기존 자연어–JOILang 변환 구현을 기반으로 함: 장치·기능 정보 검색·선별 → 부분 스키마 → 문법·예제와 함께 JSON 생성 → 규칙 검사·수정 | [pipeline.md](pipeline.md). 서비스 선별 `schema.build_service_snippet_payload`(연결 장치 범주 / 전체 스키마 / BM25 shortlist), 조립 `prompts.render_source_prompt`·`render_block_prompt`, 생성 `llm.call_chat_completion`, 후처리 `postprocess.normalize_candidate_json_text`(스키마 기반 코드 규칙 8개 + period 기본값 규칙), 검사 `validation.check_candidate` | `demo --mode offline`, `tests/test_pipeline.py`(원본 대조: 서비스 문맥·프롬프트·정규화·검사) |
| R3 | 클라우드 LLM으로 실행할 때 프롬프트 길이에 따른 비용·전송 부담 | `llm.py` 는 OpenAI 호환 엔드포인트에 system/user 메시지를 보내며 응답의 토큰 수(`usage`)를 기록한다. 원 프롬프트는 행 214에서 약 90k자, 문맥 없는 행에서 약 166k자([pipeline.md](pipeline.md) 3절). 클라우드 전용이라고 단정하지 않는다(로컬 서버에도 같은 방식으로 연결). | `render-prompt --out ...` 의 `chars` |
| R5 | 실험에 사용한 원 프롬프트와 초기 블록 모음의 공개 | 원 프롬프트: `prompts/source_prompt/` 5개 파일(원본 그대로, `MANIFEST.json` 에 SHA-256·조립 순서·재현 실행과의 프롬프트 해시 일치), 조립 코드 `prompts.render_source_prompt`. 초기 블록: `prompts/initial_blocks/` 6개 파일(원본 그대로, `initial_blocks.json` 에 원본 예제 유전형 포함), 조립 코드 `prompts.render_block_prompt` | `tests/test_pipeline.py::test_prompt_rendering_matches_original`(원본 조립 결과와 바이트 동일) |
| R6 | JOICommands-280 과 사용 방법 | `datasets/JOICommands-280.csv`(280행, SHA-256 `b6f5a7a2…`), [dataset.md](dataset.md): 필드, 범주 구성, 장치 문맥·기준 코드의 연결, 불러오기·채점 | `python -m joilang_kor check-data`; `tests/test_dataset.py` |
| R7 | 공개 자료의 서지 | `CITATION.cff`, `docs/references.bib` 의 `REF_JOILANG_REPOSITORY`(기여자 Mingi Jeong, GitHub 주소, 버전 0.1.0). DOI·release 는 없다. 원고의 `REF_JOILANG_PIPELINE` 인용 4곳(R1·R2·R4·R6)은 게시 후 이 키로 교체하고 R5 에서 1곳을 더한다. | 게시 후 태그/커밋을 서지에 추가 |

## 2. R2 의 범위 구분

원고는 "관련 장치·기능 정보를 찾고 필요한 서비스만 추린다"고 설명한다. 이 저장소가 제공하는 것:

- 준비된 장치 문맥(`connected_devices`)에서 범주를 골라 부분 스키마를 만드는 경로 — 원본 코드 그대로.
- 문맥이 없을 때의 BM25 검색 경로(`--context-mode bm25_fallback`) — 원본 검색 구현의 BM25 부분과 필수 범주
  규칙 그대로. 검색 문서(`schemas/service_retrieval_corpus.json`)는 원본 검색 번들의 범주 설명 텍스트다.
- 제공하지 않는 것: 검색의 dense 부분(선행 구현의 dense+BM25 하이브리드, 옮긴 구현의 bge-m3 하이브리드 기본값 —
  [pipeline.md](pipeline.md) 2절의 표). 공개 BM25 경로는 원본 점수식·필수 범주 규칙을 옮긴 것이며 numpy 없이 다시 썼다
  (원본 BM25 와의 대조 fixture 는 `tests/fixtures/parity_cases.json` 의 `bm25` 항목).
- 실험 기록과의 대응: DirectTransfer 재현 실행 3건(2026-08-27 시작, 2026-09-01 완료)은 문맥이 없는 행에 전체 스키마
  (`schema_fallback`)를 넣는 구성을 썼고, 기록된 프롬프트 SHA-256 이 그 조건의 공개 조립 결과와 일치한다(§3). 원고 표의 값을 만든 실행이 어느 구성을
  썼는지는 원고의 "재현성 확인 상태" 문단대로 실행 기록으로 확인해야 하며 이 저장소는 그 확인을 대신하지 않는다.

검색 단계의 문장 범위를 공개 구현에 맞추려면 다음을 제안한다.

> Before(원고 원문): 이 파이프라인은 먼저 사용자 명령과 관련된 장치·기능 정보를 찾고, 전체 서비스 스키마에서 필요한 항목만 추려 프롬프트에 제공한다.
> After: 이 구현은 먼저 제공된 장치 정보 또는 명령 문구 검색으로 관련 서비스 범주를 고르고, 전체 서비스 스키마에서 그 범주의 항목만 추려 프롬프트에 제공한다.

"규칙 검사와 수정 절차로 서비스와 인자, 대상 태그, 시간 조건 및 출력 형식을 보완한다"에 대응하는 공개 코드:

| 원고의 항목 | 검사 (`validation`) | 수정 (`postprocess`) |
|---|---|---|
| 서비스와 인자 | `unknown_service`, `service_match`, `arg_type` | 멤버 소문자화, 정식 서비스명 해석, 인자 구분자 |
| 대상 태그 | (태그 해석은 서비스 해석에 사용) | 태그 대소문자·순서, `any`→`all` |
| 시간 조건 | 없음 | `clock_delay(ms)`→`delay(...)`, period 기본값 |
| 출력 형식 | `invalid_json`, `schema_missing_keys`, `service_case` | JSON 블록 추출, 네 키로 직렬화 |

원본 후처리에는 자연어 명령 문구에 따라 코드를 고쳐 쓰는 규칙 30여 개가 더 있으며 이 저장소에는 없다
([pipeline.md](pipeline.md) 5절). 따라서 원고의 문장은 "규칙 검사와 수정 절차"의 존재와 대상 항목을 뒷받침하는
범위에서 공개 코드와 대응하고, 원본 전체 후처리와 동일한 결과를 낸다는 뜻은 아니다. 문장 범위를 좁힐 필요가
있으면 다음을 제안한다.

> Before: 이후 규칙 검사와 수정 절차로 서비스와 인자, 대상 태그, 시간 조건 및 출력 형식을 보완한다.
> After: 이후 스키마 기반 규칙 검사와 정규화로 서비스와 인자, 대상 태그, 시간 표기 및 출력 형식을 보완한다.

R3(클라우드 실행 조건)의 문장 범위를 좁히는 제안(새 측정값 없음):

> Before(원고 원문): \meaningchange{기존 파이프라인은 클라우드 LLM을 사용하므로, 프롬프트가 길어짐에 따라 API 토큰 비용이 증가하고 응답 시간이 지연되게 된다. 아울러}
> After: \meaningchange{이 변환 구현을 클라우드 LLM으로 실행하는 경우, 프롬프트가 길어짐에 따라 API 토큰 비용과 응답 지연이 증가할 수 있다. 아울러}

## 3. 원본과의 대응과 변경 범위

원본은 비공개 개발 저장소의 두 위치에서 왔다. 파일은 그대로 복사했고, 코드는 함수 단위로 옮기면서 경로·포장만
바꿨다. 아래 대조 테스트가 원본 함수와 같은 입력에서 같은 출력을 내는지 고정한다(`tests/fixtures/parity_cases.json`;
원본 코드를 직접 실행해 만든 기대값이며 생성 스크립트는 공개본에 없다).

| 공개 파일 | 원본 위치(버전) | 변경 |
|---|---|---|
| `datasets/JOICommands-280.csv` | 원본 저장소 `datasets/JOICommands-280.csv` | 없음(해시 동일). 재현 실행 manifest 의 `dataset_sha256`(`85651d35…`)은 열 순서·인코딩·파생 열(`gt_converted`)만 다른 다른 위치의 사본이며 여섯 열의 내용은 280행 모두 같다 |
| `schemas/service_list_ver2.0.1.json` | `datasets/service_list_ver2.0.1.json` | 없음 |
| `schemas/service_retrieval_corpus.json` | 원본 검색 번들 `metadata.json` 의 `keys`/`texts` | 그대로 복사(원본 코드가 별도 영문 설명 파일에서 만든 텍스트) |
| `prompts/source_prompt/*.md` | 원본 저장소(커밋 ebac3937)의 프롬프트 자산 5개 | 없음(MANIFEST 해시) |
| `prompts/initial_blocks/*.txt` | 원본 저장소(커밋 ebac3937)의 블록 파일 6개 | 없음 |
| `prompts/feedback_rules.json` | 원본 `prompt_surgery_rules.DET_FEEDBACK_RULES`, `run_feedback_loop.PATCH_RULES` | 사전을 JSON 으로. `patch_rules` 는 코드가 읽지 않는 원본 자료 |
| `src/joilang_kor/data.py`, `schema.py`, `prompts.py` | 원본 조립·문맥 모듈(`pipeline_common.py`), 원본 검색 모듈(`retrieval_context.py`) | 검색 설정·worker 제거, BM25 를 numpy 없이 |
| `src/joilang_kor/validation.py` | 원본 12항 strict 평가기(`det_evaluator.py`, 구현 스냅샷)의 스키마 검사부 | 점수 계산 제거. 실패 유형 계약은 원본과 동일(멤버 대문자 여부는 usage 표시로만) |
| `src/joilang_kor/postprocess.py` | 원본 `normalize_candidate_json_text` 와 하위 함수 8개(+period 기본값) | 명령 문구·장치별 규칙 제외, 적용 규칙 기록 |
| `src/joilang_kor/evaluation.py` | 원본 8항 평가기(`det_evaluator.py`, 루트 utils) | 0–1 점수·τ=0.90 래퍼 `evaluate_item` 추가; 원본 결과 형식은 `original_det_evaluate_row` 로 재현 |
| `src/joilang_kor/feedback.py` | 원본 피드백 루프(`run_feedback_loop.py`, 규칙 부착)와 실패→블록 매핑(`prompt_surgery_rules.py`) | 1회 피드백으로 축소, 실행 디렉터리에만 기록 |
| `src/joilang_kor/llm.py` | 원본 `local_llm_client._call_openai_compatible` | worker backend 제거, 인증 헤더는 전용 환경변수만 |
| `src/joilang_kor/pipeline.py`, `__main__.py` | (공개용 신규) | 실행 순서·기록·CLI |

원 프롬프트 자산에는 더 오래된 변형(프롬프트 프로필 0.6 계열)이 있으며 내용이 다르다(예: `service_prompt_10.md`
158줄 차이). 이 저장소는 실제 조립 코드(`render_legacy_v13_monolithic_prompt`)가 읽는 자산(원본 저장소 커밋 ebac3937,
디렉터리 생성 2026-03-27, 마지막 내용 수정 2026-05-08)을 공개한다. DirectTransfer 재현 실행 3건(run 20260827T031703,
20260827T031704, 20260901T170319; 2026-08-27 시작·2026-09-01 완료)의 실행 기록(행별 `prompt_sha256`)은 첫 행(연결 장치
없음 → 전체 스키마 문맥)의 system prompt SHA-256(`f4c259cb…`) 하나를 전 행에 기록했고, 이 값은 공개 조립 코드가 같은
조건의 행에 만드는 prompt 와 바이트 단위로 같다. 연결 장치가 있는 행의 행별 프롬프트는 그 기록으로 대조할 수 없다. 반면
`examples/saved_output_siren.json` 과 대조 fixture 의 출력을 낸 2026-07-31 실행(`fullprompt_v06_ver201`)은 0.6 계열
병합 프롬프트를 썼으며 그 프롬프트는 공개하지 않았다(그 실행의 출력은 검사·평가 예제로만 쓴다).

원 프롬프트·초기 블록의 정적 예제와 기준 코드의 중복 행 목록과 판정 기준은 [dataset.md](dataset.md) 에 있다(원 프롬프트 7행, 블록 02 7행, 블록 05 2행; 예제 사례 행 4 포함).

## 4. 확인 범위

| 구분 | 내용 |
|---|---|
| 정적 확인 | 데이터 280행·범주·해시, 스키마·프롬프트·블록 해시, 원본 대조(평가 43건, 정규화 320건, 검사 53건 = 실행 기록 43 + 합성 경계 10, 문맥·프롬프트 5행×2경로), `gt` 열의 프롬프트 유입 없음(위 예제 중복은 별도), 네트워크 차단 아래 테스트 |
| 저장 출력 재채점 | 원본 실행 기록의 로컬 모델 출력 280건(Qwen2.5-Coder-7B, DirectTransfer, 2026-07-31 run)을 `score`(parsed, τ=0.70)로 채점한 결과가 그 기록의 집계와 일치(통과 75/280, 평균 점수 0.5896). 평가기 경로 확인일 뿐 논문 표 값의 재현이 아니다 |
| 예제 실행 | `demo --mode offline` 2건(실험 기록의 실제 모델 출력): JSON 오류→블록 03 보강, 등록되지 않은 서비스명→후처리 정정 |
| 전체 실험 재현 | 하지 않음. 논문의 DETPass·토큰·지연·민감도 수치는 이 저장소로 재현되지 않으며 그 근거는 논문의 실험 기록이다. 위 280건 재채점 수치도 공개하지 않은 실행 기록에서 나온 값이다 |
| live 실행 | 어댑터와 명령을 제공한다. 이 저장소를 준비하면서 실제 서버에 대한 live 실행은 하지 않았고, HTTP 경로(연결 실패·비JSON 응답·재생성 실패)는 urllib 을 대역으로 바꾼 테스트로만 확인했다(`tests/test_pipeline.py` 의 `test_live_mode_reports_connection_failure`, `test_live_non_json_body_is_reported`, `test_live_regeneration_failure_keeps_partial_summary`) |

## 5. 인용할 버전

게시 뒤 인용은 저장소 주소와 함께 태그 또는 커밋 해시를 적는다. `CITATION.cff` 의 `version` 과 `docs/references.bib`
의 `note` 를 게시한 버전에 맞춘다. DOI 는 부여되지 않았다.
