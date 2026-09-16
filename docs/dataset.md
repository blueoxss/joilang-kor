# JOICommands-280

자연어 명령 → JOILang 시나리오 변환의 평가 데이터. 파일: [`datasets/JOICommands-280.csv`](../datasets/JOICommands-280.csv)
(UTF-8 with BOM, 280행, SHA-256 `b6f5a7a2d05a4522f8f27f32ef73997e587bcf5c45a7926cddbeedd0fa1a65ce`).
재현 실행 manifest 가 기록한 다른 위치의 사본(SHA-256 `85651d35…`)은 열 순서·인코딩·파생 열(`gt_converted`) 하나만
다르고 여기 실은 여섯 열의 내용은 280행 모두 같다.
평가 항목 하나는 자연어 명령(한국어·영어), 그 명령을 처리할 때 제공하는 장치·기능 정보, 비교 기준
JOILang 코드의 묶음이다.

## 필드

| 열 | 내용 |
|---|---|
| `index` | 범주 안에서의 번호(1..30 또는 1..50). 범주 사이에는 중복되므로 전역 식별자는 `(category, index)` 또는 CSV 행 번호(1부터)다. |
| `category` | 1–8. 명령 복잡도 범주. 1–6은 각 30개, 7–8은 각 50개. |
| `command_kor` | 한국어 명령. |
| `command_eng` | 영어 명령. 프롬프트에는 두 언어를 함께 넣는다(`prompts.combined_command_text`). |
| `connected_devices` | 장치 문맥. 비어 있거나(140행) `{"장치ID": {"category": 범주 또는 목록, "tags": [태그...]}}` 형식의 Python/JSON 리터럴(140행). |
| `gt` | 기준 시나리오 JSON: `name`(모두 `""`), `cron`, `period`(정수), `script`(JOILang 코드). |

범주별 내용은 단일 장치 제어(1)부터 상태 조건, 지연, 일정과 반복을 포함한 자동화(7–8)까지다. 기준 코드 중
cron 이 있는 행은 40개, period > 0 인 행은 68개다. 이메일 명령의 주소는 자리표시자 `test@example.com` 이다.

## 장치 문맥과 기준 코드의 연결

- `connected_devices` 가 있으면 변환 구현은 그 장치의 범주로만 서비스 문맥을 만든다(`schema.build_connected_device_groups`).
  태그(`tags`)는 수신자 선택자 예시(`(#Odd #WindowCovering)`)로 프롬프트에 들어간다. 기준 코드의 태그도 이 목록과 대응한다.
- `connected_devices` 가 없으면 전체 스키마(50개 범주) 또는 BM25 shortlist 를 사용한다([pipeline.md](pipeline.md) 2절).
- 기준 코드(`gt`)는 생성 입력에 넣지 않고 평가에만 쓴다. 정적 예제와의 중복은 아래 참조.

## 프롬프트 예제와 기준 코드의 중복

원 프롬프트·초기 블록의 정적 예제(명령–코드 쌍) 중 JOICommands-280 의 기준 코드와 같은 것이 있다. 기준: 기준 코드(`script`,
8자 이상)를 공백 제거 후 각 프롬프트 파일(JSON 이스케이프 해제본 포함)에서 부분 문자열로 찾음(280행 전수, 파일별).
원 프롬프트: `service_prompt_10.md` 행 3, 21, 23, 36, 191; `caution_prompt_8.md` 행 53; `tempo_prompt_9.md` 행 221.
블록 02(기본 유전형에 포함): 행 4, 8, 21, 183, 205, 224, 275. 블록 05(수정용, 기본 유전형에 없음): 행 30, 101.
생성 입력이 `gt` 열을 읽지는 않지만 이 항목들에서는 프롬프트의 정적 예제가 기준 코드와 일치하므로 결과 해석 시 고려한다
(원본 자료는 바꾸지 않는다). 예제 `examples/scenario_siren.json`(행 4)도 여기에 해당한다.

## 불러오기와 검사

```bash
python -m joilang_kor check-data --dataset datasets/JOICommands-280.csv
```

행 수·범주 구성·필수 열·기준 JSON 파싱·`(category, index)` 유일성·파일 해시를 출력한다. 파일을 수정하지 않는다.

```python
from joilang_kor.data import load_dataset_rows, select_rows, parse_connected_devices, parse_reference
rows = load_dataset_rows("datasets/JOICommands-280.csv")
row_no, row = select_rows(rows, start_row=214, end_row=214)[0]      # 1부터 세는 행 번호
devices = parse_connected_devices(row["connected_devices"])
reference = parse_reference(row["gt"])                                # {"name","cron","period","script"}
```

## 평가

저장된 출력(JSONL, 행마다 `{"row_no": 214, "output": "<모델 출력 문자열>"}`)을 DET 로 채점한다.

```bash
python -m joilang_kor score --predictions outputs.jsonl --out runs/score                             # 파싱(JSON 블록 추출)만 하고 채점
python -m joilang_kor score --predictions outputs.jsonl --out runs/score --candidate postprocessed   # 스키마 기반 정규화까지 적용하고 채점
```

`runs/score/rows.jsonl` 에 행별 여덟 비교값·점수·통과 여부, `summary.json` 에 DETPass(통과 비율)와
S_DET(점수 평균)이 남는다. 평가 정의는 [pipeline.md](pipeline.md) 5절.

## 사용 범위

원고의 실험은 프롬프트 탐색과 최종 비교에 같은 280개를 사용했다. 이 저장소는 새 train/test 분할을 만들지
않으며, 명령·문맥·기준 코드를 원자료 그대로 둔다(번역·익명화·재생성 없음).
