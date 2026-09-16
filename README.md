# joilang-kor

JOILang 언어 설명, 자연어→JOILang 변환 구현의 최소 경로, 실험에 사용한 원 프롬프트와 초기 블록, 평가 데이터
JOICommands-280 을 담은 저장소다. GPS-PromptOps(로컬 LLM 별 프롬프트 탐색) 논문이 인용하는 기반 자료의 공개
출처이며, 논문의 새로운 기여인 GA 탐색과 실험 결과는 여기에 포함하지 않는다. 논문 문장과 자료의 대응은
[docs/paper-support.md](docs/paper-support.md) 에 있다.

## 설치

Python 3.10 이상, 추가 의존성 없음(테스트는 pytest).

```bash
git clone https://github.com/blueoxss/joilang-kor.git
cd joilang-kor
python -m pip install -e .
```

일반 설치(`pip install .`)도 되지만 데이터·스키마·프롬프트 파일은 패키지에 포함되지 않으므로 저장소 checkout
안에서 실행하거나 `--dataset`, `--schema`, `--blocks-dir`, `--source-prompt-dir`, `--feedback-rules`
(`--context-mode bm25_fallback` 이면 `--retrieval-corpus` 도)로 경로를 지정한다. 아래 clone 주소와 인용 정보는
저장소가 게시된 뒤에 유효하다.

## 모델 없이 실행하는 점검

```bash
python -m joilang_kor check-data --dataset datasets/JOICommands-280.csv
```

```text
{
  "dataset": ".../datasets/JOICommands-280.csv",
  "sha256": "b6f5a7a2d05a4522f8f27f32ef73997e587bcf5c45a7926cddbeedd0fa1a65ce",
  "rows": 280,
  "columns": ["index", "category", "command_kor", "command_eng", "connected_devices", "gt"],
  "category_counts": {"1": 30, "2": 30, "3": 30, "4": 30, "5": 30, "6": 30, "7": 50, "8": 50},
  "unique_category_index_pairs": 280,
  "rows_with_connected_devices": 140,
  "problems": [],
  "ok": true
}
```
(실제 출력은 JSON 을 한 항목씩 여러 줄로 찍는다. 위는 같은 값을 줄여 적은 것이다.)

저장된 모델 출력으로 검사→오류 유형→보강 가이드→블록 수정까지 확인한다(재생성은 하지 않는다).

```bash
python -m joilang_kor demo --mode offline --case examples/scenario.json --out runs/demo
```

```text
"initial_failure_reasons": ["invalid_json"],
"feedback": "applied",
"patched_blocks": ["03"],
"regeneration": "not_performed",
"regeneration_reason": "offline mode"
```
(요약 출력 중 다섯 줄. 실제 출력에서 배열은 여러 줄로 찍힌다.)

`runs/demo/` 에 입력, 서비스 문맥, 프롬프트, 검사 결과, 가이드, 블록 diff, 수정 프롬프트, 평가가 남는다.
저장 출력(`examples/saved_output.json`)은 그 파일의 provenance 에 적힌 프롬프트로 만들어진 실험 기록이며,
`runs/demo/prompt_initial.json` 은 블록 조립과 보강을 보여 주기 위해 함께 만든 프롬프트다.
두 번째 예제 `examples/scenario_siren.json` 은 등록되지 않은 서비스명이 후처리로 정정되는 경우다.

## 로컬 LLM 연결 (선택)

OpenAI 호환 `chat/completions` 엔드포인트(예: vLLM)를 준비한 뒤 실행한다. `MODEL_ID` 는 서버에 올린 모델 ID 다.

```bash
python -m joilang_kor demo --mode live --case examples/scenario.json \
  --endpoint http://127.0.0.1:8000/v1 --model MODEL_ID --feedback-rounds 1 --out runs/live
```

초기 생성 → 검사 → 블록 보강 → 같은 입력으로 1회 재생성을 수행하고 전후 결과를 모두 기록한다. 연결에 실패하면
`error: ...` 한 줄과 `runs/live/summary.json`(`status: failed`, 실패 단계)을 남기고 끝난다(재시도·대체 없음).
서버 인증이 필요하면 환경변수 `JOILANG_KOR_HTTP_AUTH_BEARER` 에 토큰을 두면 `Authorization: Bearer` 로 보내고,
없으면 인증 헤더를 보내지 않는다.
생성 설정은 `temperature=0`, `max_tokens=256` 이며 서버의 디코딩 구현은 검증하지 않는다([docs/pipeline.md](docs/pipeline.md) 4절).
이 저장소를 준비하면서 live 모드는 실행하지 않았다(연결 실패 경로만 테스트했다).

프롬프트만 보려면:

```bash
python -m joilang_kor render-prompt --row 214 --prompt-mode source --out runs/prompt_source.json
python -m joilang_kor render-prompt --row 214 --prompt-mode blocks --out runs/prompt_blocks.json
```

## JOICommands-280

`datasets/JOICommands-280.csv` — 280개 평가 항목(범주 1–6 각 30개, 7–8 각 50개). 열: `index`, `category`,
`command_kor`, `command_eng`, `connected_devices`, `gt`(기준 시나리오 JSON). 구성·불러오기·평가 방법은
[docs/dataset.md](docs/dataset.md). 저장된 출력의 채점 — 입력은 JSONL 이며 한 줄이 `{"row_no": <1부터 세는 CSV 행 번호>, "output": "<모델 출력 문자열>"}` 이다:

```bash
printf '%s\n' '{"row_no": 4, "output": "{\"name\": \"\", \"cron\": \"\", \"period\": 0, \"code\": \"(#Siren).siren_setsirenmode(\\\"emergency\\\")\"}"}' > outputs.jsonl
python -m joilang_kor score --predictions outputs.jsonl --out runs/score
```

`runs/score/summary.json` 에 통과 수와 DETPass, S_DET 가 남는다(위 예는 1행, 통과 1).

## 문서

- [docs/joilang.md](docs/joilang.md) — 언어: VALUE/FUNCTION 서비스, 태그, `name/cron/period/code`, 조건·시간·반복
- [docs/pipeline.md](docs/pipeline.md) — 서비스 선정 → 프롬프트 조립 → 생성 → 후처리·검사 → 피드백 예제 → 평가
- [docs/dataset.md](docs/dataset.md) — 데이터 필드, 장치 문맥과 기준 코드의 연결, 검사·평가
- [docs/paper-support.md](docs/paper-support.md) — 논문 문장별 근거 자료, 공개 범위, 원본과의 대응
- [docs/references.bib](docs/references.bib) — 문서가 인용하는 문헌과 이 저장소의 인용 항목
- `prompts/source_prompt/` — 원 프롬프트 구성 파일(원본 그대로, `MANIFEST.json` 에 해시)
- `prompts/initial_blocks/` — 초기 블록 모음(원본 그대로, `initial_blocks.json` 에 설명)

## 테스트

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

원본 구현과 같은 입력에서 같은 결과를 내는지(`tests/fixtures/parity_cases.json`), 기준 코드가 생성 입력에
들어가지 않는지, 오프라인 데모가 네트워크 없이 끝나는지 검사한다.

## 인용

```bibtex
@misc{REF_JOILANG_REPOSITORY,
  author       = {Jeong, Mingi},
  title        = {{joilang-kor}},
  howpublished = {GitHub repository ({JOILang} language reference, conversion implementation, experiment prompts and {JOICommands-280}). [Online]. Available: \url{https://github.com/blueoxss/joilang-kor}},
  year         = {2026},
  note         = {Version 0.1.0}
}
```

`CITATION.cff` 에 같은 제목·기여자·주소·버전이 있다. 인용할 때는 실제로 게시된 버전(태그 또는 커밋)을 함께 적는다.

## 이용 조건

이 저장소의 라이선스는 아직 정해지지 않았다(`LICENSE` 파일 없음). 라이선스가 정해지기 전에는 저작권법이
기본으로 적용되므로 재배포·수정 전에 저자에게 확인한다.
