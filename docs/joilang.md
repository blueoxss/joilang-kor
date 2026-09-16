# JOILang 언어 설명

JOILang은 서비스 수준의 IoT 자동화 시나리오를 기술하는 도메인 특화 언어다. 서비스 기반 IoT 플랫폼
(예: SoPIoT [`SoPIoT`](references.bib))에서는 사용자가 개별 장치를 직접 지정하는 대신 원하는 서비스를
기술하고 플랫폼이 그 서비스를 수행하는 장치를 찾는다. JOILang도 **서비스**(장치가 제공하는 기능)와
**태그**(서비스 유형, 공간, 그룹 등)로 대상을 지정하고, 실행 시점에 플랫폼이 태그와 일치하는 장치를 연결한다.

이 문서는 이 저장소의 실제 자산에 맞춰 쓴다: 서비스 스키마 [`schemas/service_list_ver2.0.1.json`](../schemas/service_list_ver2.0.1.json),
문법 프롬프트 [`prompts/source_prompt/grammar_ver1.5.10.md`](../prompts/source_prompt/grammar_ver1.5.10.md),
시간·조건 규칙 [`prompts/source_prompt/tempo_prompt_9.md`](../prompts/source_prompt/tempo_prompt_9.md),
기준 코드 [`datasets/JOICommands-280.csv`](../datasets/JOICommands-280.csv). 이 저장소는 파서나 실행기를
제공하지 않으므로, 아래 설명은 실제 구현이 사용하는 표기 규약이지 완전한 정식 문법이나 실행 검증기가 아니다
(마지막 절 참조).

## 1. 서비스: VALUE 와 FUNCTION

서비스 스키마는 장치 범주(예: `AirConditioner`, `DoorLock`, `Clock`) 아래에 서비스를 나열한다.
각 서비스는 두 유형 중 하나다.

| 유형 | 뜻 | 스키마 필드 | 예 |
|---|---|---|---|
| `value` | 상태·센서값 읽기 | `return_type`, `return_descriptor`, `enums_descriptor`(허용 상태값) | `TemperatureSensor.Temperature`, `DoorLock.DoorLockState` |
| `function` | 장치 제어 | `argument_type`(예: `ENUM`, `DOUBLE`, `INTEGER \| INTEGER`), `argument_descriptor`, `argument_bounds` | `AirConditioner.SetTargetTemperature`, `Switch.Off` |

스키마에는 50개 범주, value 서비스 114개, function 서비스 81개가 있다. 코드에서 서비스는
**정식 명칭** `범주_서비스`(예: `AirConditioner_SetTargetTemperature`)를 소문자로 쓴 멤버 토큰으로
호출한다: `(#AirConditioner).airconditioner_settargettemperature(23)`. 이 소문자화 규칙은 원 프롬프트
(`service_prompt_10.md`, "Current Service Naming Policy")와 후처리 규칙 `lowercase_service_members` 에 있다.

- value 읽기: `(#Tags).member` — 인자 없음. 조건식이나 변수 대입에 쓴다.
- function 호출: `(#Tags).member(args)` — 인자의 수와 자료형은 `argument_type`을 따른다. 여러 인자는
  쉼표로 구분한다(`Light.MoveToRGB` 는 `INTEGER | INTEGER | INTEGER` → `light_movetorgb(255, 0, 0)`).
  열거형 인자는 문자열로 쓴다(`siren_setsirenmode("emergency")`).

## 2. 대상 지정: 태그

수신자는 `(#Tag1 #Tag2 ...)` 형태이며, 나열한 태그를 모두 가진 장치를 가리킨다.

- 서비스 유형 태그: 스키마의 범주명(`#Light`, `#DoorLock`). 수신자에는 범주 태그가 하나 있어야 한다.
- 사용자 지정 태그: 공간·그룹·범위(`#LivingRoom`, `#Odd`, `#Group1`). 데이터셋의 `connected_devices`
  열이 각 장치의 `category` 와 `tags` 를 준다(예: `{"Odd_Blind": {"category": ["WindowCovering"], "tags": ["Odd", "Blind", "WindowCovering"]}}`).
- 표기: 태그는 영문이며 `#` 뒤 첫 글자는 대문자다. 후처리는 스키마 범주명과 대소문자가 다른 태그를
  범주명으로, 그 밖의 태그를 첫 글자 대문자로 맞추고, 선택자 태그를 범주 태그 앞에 둔다(`(#Odd #Blind).…`).
- 범위: `(#Tag).f()` 는 일치하는 장치 중 일부(기본), `all(#Tag).f()` 는 전체에 적용한다. 조건에서는
  `all(#Tag).v == x` (전부), `any(#Tag).v == x` (하나라도)로 쓴다. 후처리는 원본 구현대로 `any(` 를
  `all(` 로 바꾼다(규칙 `normalize_receiver_quantifiers`).

예: `(#living #AirConditioner)` 는 거실(`living`)에 있으면서 에어컨 서비스를 제공하는 장치다. 실제 장치와의
연결은 실행 시점의 플랫폼 기능이며, 이 공개 패키지는 장치를 실행하지 않는다.

## 3. 시나리오 JSON: name, cron, period, code

생성 결과는 네 필드를 가진 하나의 JSON 객체다. 기준 코드(데이터셋 `gt` 열)는 `code` 대신 `script` 키를
쓴다; 평가기는 두 키를 같이 받는다.

| 필드 | 형식 | 의미와 기본값 |
|---|---|---|
| `name` | 문자열 | 시나리오 이름. 기준 코드 280개 모두 `""` 이다. 평가에 쓰지 않는다. |
| `cron` | 문자열 | 시작 일정. UNIX cron 5필드(`분 시 일 월 요일`). `""` 이면 즉시 시작. 기준 코드 280개 중 40개가 cron을 가진다. |
| `period` | 정수(ms) | cron 트리거 뒤의 반복 주기. `0`: cron 마다 한 번, `-1`: 한 번 실행 후 종료, `>= 100`: 그 밀리초마다 반복. 기준 코드는 반복이 없으면 `0` 을 쓴다(212개). |
| `code` | 문자열 | 실행 코드. 줄바꿈으로 문장을 구분한다. |

원 프롬프트의 문법 설명(`grammar_ver1.5.10.md`, "Timing Control")은 `period: -1` 을 "한 번 실행"으로
정의하고, 데이터셋 기준 코드와 후처리는 반복 없는 명령을 `period: 0` 으로 통일한다(후처리 규칙 `schedule_defaults`
가 음수 period 를 0 으로 바꾼다). 이 두 값의 차이는 평가에서 `schedule_match` 항목에 반영된다.

## 4. 코드 구문

문법 프롬프트가 허용하는 구문은 다음과 같다. 허용 키워드: `if`, `else if`, `else`, `>=`, `<=`, `==`, `!=`,
`not`, `and`, `or`, `wait until`, 지연 함수. `for`/`while` 반복문은 없고 반복은 `cron`/`period` 로 표현한다.

```text
if ((#DoorLock).doorlock_doorlockstate == "closed") { ... } else { ... }   # 현재 상태 검사
wait until ((#DoorLock).doorlock_doorlockstate == "closed")                # 상태 전이를 기다림
delay(10 MIN)                                                              # 지연 (SEC|MIN|HOUR)
(#Clock).clock_delay(600000)                                               # 지연(밀리초) — 원 프롬프트가 쓰는 옛 표기
flag := false                                                              # 전역 변수 선언 (code 첫머리, period 반복 간 유지)
temp = (#TemperatureSensor).temperaturesensor_temperature                  # 지역 변수 대입 (현재 실행에만 유효)
break                                                                      # 다음 cron 까지 period 반복 중단
```

- 조건은 명시적 비교로 쓴다(`== true`). `and`/`or` 로 결합한다.
- `if` 는 평가 시점의 상태를 검사하고, `wait until` 은 조건이 참이 될 때까지 뒤 문장을 멈춘다. 자연어의
  "~이면(상태)"과 "~하면/되면(전이)"의 구분이 이 둘의 선택을 결정한다(`tempo_prompt_9.md`).
- 서비스 값을 함수 인자로 넘길 때는 변수에 먼저 대입한다. 문자열 연결·템플릿은 쓰지 않는다.
- 지연: 원 프롬프트는 `(#Clock).clock_delay(ms)` 와 `delay(N SEC|MIN|HOUR)` 를 모두 설명하며, 기준 코드는
  `delay(...)` 형식을 쓴다. 스키마의 `Clock.Delay` 는 `INTEGER | INTEGER | INTEGER`(시·분·초) 서명이라 밀리초 한 개를
  넘기는 `clock_delay(ms)` 는 검사에서 `arg_type` 으로 표시되고, 후처리가 `delay(...)` 로 바꾼다(규칙 `normalize_clock_delay_calls`).
- 허용 키워드 목록과 `while` 금지는 원 프롬프트의 역할·과제 절(`prompts.render_source_prompt`)과 문법 파일에서 온다.

### 예: 문이 닫히면 10분 뒤 거실 에어컨 끄기

원고 서론의 예시를 이 저장소의 스키마 명칭으로 쓰면 다음과 같다. 문이 열렸다가 닫히는 전이를 두 개의
`wait until` 로 기다리고, 10분(600000 ms)을 지연한 뒤 거실 태그가 붙은 에어컨을 끈다.

```json
{
  "name": "DoorAcOff",
  "cron": "",
  "period": 0,
  "code": "wait until ((#DoorLock).doorlock_doorlockstate == \"open\")\nwait until ((#DoorLock).doorlock_doorlockstate == \"closed\")\ndelay(10 MIN)\n(#living #AirConditioner).switch_off()"
}
```

`DoorLock.DoorLockState` 의 허용값은 스키마의 `enums_descriptor`(`closed`, `closing`, `open`, `opening`, `unknown`)에서 온다.
에어컨 전원은 스키마에 `AirConditioner.Off` 가 없으므로 공용 `Switch.Off`(`switch_off`) 로 쓴다. 후처리는 태그 `#living` 을 `#Living` 으로 바꾼다(첫 글자 대문자 규칙). 이 코드는 `validation.check_candidate` 를 통과한다. 이 해석은
이 벤치마크의 규약이며 모든 자연어 사용자의 유일한 의도로 일반화하지 않는다. 이 명령은 JOICommands-280 에
들어 있지 않다(데이터셋에서 가까운 항목: 범주 7 index 1 "10분마다 확인해서 온도가 30도 이상이면 에어컨을 쿨모드로").

### 데이터셋 기준 코드 예

```text
# 범주 1 index 4  "Set the siren to emergency mode."
(#Siren).siren_setsirenmode("emergency")

# 범주 7 index 34 "Every 8 AM, open all blinds with odd tags, and at 9 AM, open all blinds with even tags."
# cron "0 8 * * *", period 0, connected_devices: Odd_Blind / Even_Blind / Fixed_Window (WindowCovering)
all(#Odd #Blind).windowcovering_uporopen()
delay(1 HOUR)
all(#Even #Blind).windowcovering_uporopen()
```

## 5. 이 저장소가 확인하는 것과 확인하지 않는 것

| 확인함 (`validation.check_candidate`) | 확인하지 않음 |
|---|---|
| JSON 객체로 읽히는지, 네 필수 키가 있는지 | JOILang 구문(`if`/`wait until` 문법, 괄호 짝, 변수 선언 위치) |
| 수신자 뒤 멤버가 스키마 서비스로 해석되는지 (`unknown_service`) | 태그가 실제 장치와 연결되는지, 태그 조합의 의미 |
| 함수 인자의 수·자료형 (`arg_type`). 허용값 목록은 함수 항목에 `enums_descriptor` 가 있을 때만 검사하며, ver2.0.1 스키마의 함수 항목에는 그 목록이 없다 | 실행 의미·안전성, `while` 같은 금지 구문, value 의 허용 상태값과 비교 리터럴의 일치 |
| 멤버 토큰 대소문자 (`service_case`) | cron 식의 유효성 |

DET 평가(`evaluation.evaluate_item`)는 기준 코드와의 정적 비교이며 실행 동등성을 증명하지 않는다
([docs/pipeline.md](pipeline.md) 5절).
