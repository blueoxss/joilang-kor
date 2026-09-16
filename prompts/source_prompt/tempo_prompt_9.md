### 1. Static condition (state check): ~였으면, ~인 상태면, ~라면 (If)
   - This applies when the condition is already true at the time of evaluation.
   - The system simply checks the current state and executes immediately if the condition is met.
   - It assumes that the state has already been sustained for some time.
   Common Expressions:
      "if it is...", "if the state is...", "in case of..."
   #### Caution:
   - if (...) only checks the current state.
   - It does not detect or care about any prior changes.
   - It will not trigger if the system is waiting for a transition (e.g., from "off" to "on").
   **Applies when the state is already true at evaluation time.**
   #### [example]
   - “if the door is closed” → if ((#Door).doorControl_door == "closed")
   - “if the light is on” → if ((#Light).switch_switch == "on")
   - Korean command: “문이 닫혀 있으면”
   - English translated command: "if the door is closed"
   - → if ((#Door).doorControl_door == "closed")
   - 현재 상태가 닫힘일 때 즉시 실행

### 2. Dynamic transition (state change detection): ~하면, ~되면, ~하게 되면 (When)
   **Triggers only when the condition becomes true from the opposite state.**
   **If the condition implies a **transition** from a previous numeric state (e.g., below threshold → above threshold)**
   - This triggers only when a condition changes from false to true.
   - It captures a moment of change, not just a static state.
   - This is important for event-driven scenarios where the system must wait for a state to become true.
   - **Important**: Even though this looks like a numeric threshold, it still implies a **change in state** (from <80 to >=80), and must be treated as **Dynamic Transition**.
   - And uses words like “되면”, “넘으면”, “이상이 되면”, “떨어지면”,
   - Then use:  
   → `wait until (...)`
   #### [incorrect]
   - DO NOT use `if (humidity >= 80)` for:
   - "습도가 80% 이상이 되면"  
   - Instead, use `wait until (humidity >= 80)`
   #### [example2]
   - “습도가 80% 이상이 되면 블라인드를 내려 줘.”  
   → `wait until ((#HumiditySensor).relativeHumidityMeasurement_humidity >= 80.0)`  
   → `(#Blind).windowShade_close()`
   - Korean command: "습도가 80% 이상이 되면"
   - English translated command: "when humidity becomes greater than or equal to 80%"
   - → `wait until((#HumiditySensor).relativeHumidityMeasurement_humidity >= 80.0)`
   - DO NOT use `if (...)` for threshold-based transitions unless the command explicitly implies the condition is already true at evaluation time.
   #### [example2]
   - Korean command: “문이 닫히면”
   - English translated command: "when the door closes"
   - → wait until ((#Door).doorControl_door == "closed"), 
   - Korean command: "제습기가 꺼지면"
   - → wait until((#Dehumidifier).switch_switch == "off")
   **Also used for one-time triggering events** in below **4. One-Time Trigger + Repeating Action** patterns.  
   - For example, in:  
   > "When the door closes, then every 5 seconds do X"  
   The phrase "when the door closes" is classified as a **Dynamic transition** - a one-time trigger that leads to a repeating action loop.
   - Therefore, **Step 4 should treat any such one-time event detection via `wait until (...)` as a [2] Dynamic transition**, regardless of what follows.

### 3-1. [Combined condition]: ~였다가 ~하면, ~였거나 ~하면, ~이거나 ~하면 (If + when, If + And then)
   - Korean command: "비어있다가 누군가 감지되면"
   - "**비어있다가**" is **state check(과거 상태 검사)** + "누군가 감지되면" **state change(미래 변화 감지)**를 모두 수용
   - Korean command: “문이 닫혀있거나 닫히면”
   - English translated command: "if or when the door is closed"
   - → if ((#Door).doorControl_door == "closed") { ... } else { wait until ((#Door).doorControl_door == "closed") }
   - 현재 상태가 이미 참인지 확인하고, 아니라면 그 상태가 미래에 될 때까지 기다리는 방식
   - 즉, **state check(현재 상태 검사)**와 **state change(미래 변화 감지)**를 모두 수용
   - 이 두 조건은 시간상 연속되지 않아도 되며, 서로 독립적으로 만족될 수 있음
   #### [Example]: “토양 습도가 20% 이상인데 알람이 켜지게 되면 물을 줘” → 토양 상태와 알람 이벤트는 독립적이며, 둘 다 충족되었을 때 실행
   - Use: if (토양 습도 state check) { wait until (알람 state change) }
   - Reacts to either current satisfaction or future transition—whichever happens—ensuring coverage of both temporal paths.

### 3-2. [Combined condition]: = ~하고 ~하면, (When + When)   
   - Separately,When a condition involves **two consecutive state changes**, like “A happened, and then B happens” 
   - Korean command: "**비었다가** 누군가 감지되면"
   - "**비었다가**" is **state check(현재 변화 감지)** + "누군가 감지되면" **state change(미래 변화 감지)**를 모두 수용

   - Korean example: “문이 닫혔다 열리면”, “비가 오는데 창문이 열려 있으면”  
   - → Use **two `wait until` statements** to capture both transitions when events must occur in sequence.  
   - If the condition requires simultaneous truth (e.g., “if it's raining and the window is open”), use a single `if (...) and (...)` block instead.
   #### [Example] "문이 열렸다 닫히면 알림을 울려줘."
   ```
   {"name": "DoorClosedAlert", "cron": "", "period": -1, "code": 
   "wait until((#DoorLock).doorControl_door == \"open\")\n
   wait until((#DoorLock).doorControl_door == \"closed\")\n(#Alarm).alarm_siren()"}
   ```

### 4. [One-Time Trigger (Dynamic transition) + Subsequent Repeating Action]
- When the natural language includes phrases like “after ~, repeat every N seconds”,  
it should be interpreted as a **one-time condition trigger** is Dynamic transition. and, followed by a **periodic loop** of actions.
#### Key Principles
- Detect the **triggering event** only once using **Dynamic transition (state change detection)** `wait until (...)` or **Static condition (state check)** `if`.
- Control repeated actions using `period > 0` and a Boolean flag variable.
- Use flags like `triggered := false` or `action := false` to maintain state inside the loop.
#### [Example]  
**Command**:  
- "When the front door closes, immediately turn off the light, and then flash the strobe every 3 seconds."
**Interpretation**:
- `"when the door closes"` → single detection via `wait until (...)`
- `"every 3 seconds"` → continuous action with `period: 3000`
```
{
  "name": "Scenario1",
  "cron": "",
  "period": 3000,
  "code": "
   action := false\n
   if (action == false) {\n
      wait until ((#Door).doorControl_door == \"closed\")\n
      (#Light).switch_off()\n
      action = true\n
   }\n
   else {\n
      (#Alarm).alarm_strobe()\n
   }"
}
```

### 5. [Combined condition + Repeating condition] (dynamic + periodic): ~할 때마다, ~하게 될 때마다 + 주기적으로 ~해줘 (loop는 period를 의미).
   - Korean command: “문이 열릴 때마다”
   - English translated command: "whenever the door opens"
   - → use with period > 0 loop:
     if ((#Door).doorControl_door == "closed") { wait until ((#Door).doorControl_door == "open") }
   - Korean command: “문이 열릴 때마다”, “문이 닫혔다 열릴 때마다 사진을 5초 단위로 찍어줘”
   - English translated command: "whenever the door opens", "after the door closes and opens, take a photo every 5 seconds"
   - **If the sentence explicitly mentions a specific repeating interval (such as "every 5 seconds", "5초마다"), always convert this interval to milliseconds and set it as the period value (e.g., period = 5000 for 5 seconds).**
   - **If the sentence describes a repeating, continuous, or monitoring action but does not mention a specific interval, or obviously requires a period but no interval is stated, always set the period to 100 (ms) by default.**
   - → Use with "period": 100 to continuously monitor state transitions and respond in real time.
   - → Combine state change detection with `period` and state variables. For a between-action wait, use `delay(N SEC|MIN|HOUR)`.
   [example]
   ```
   "name": "Scenario",
   "cron": "",
   "period": 5000,
   "code": "
      phase := false\n
      if (phase == false) {\n
         wait until((#DoorLock).doorControl_door == 'closed')\n
         wait until((#DoorLock).doorControl_door == 'open')\n
         phase = true\n
      } else {\n
         (#Camera).camera_take()\n
      }
   "
   ```
   - Use this pattern when a condition leads to continuous behavior (e.g., taking photos every N seconds) rather than a one-time reaction.
   - When a command includes both a **"state-based trigger" (~할 때마다)** and a **"fixed time loop" (e.g., every 2 seconds)**, you **must use `period` with a state flag variable** to prevent repeated triggering within the same state.  
   - This ensures actions occur **only once per transition** while still checking repeatedly.  
   - You must initialize a **boolean variable** using `:=` and reset it appropriately to track state transitions accurately.
   #### [Example]
   **Korean:** `2초마다 상태를 확인해서 TV가 켜질 때마다 스피커도 켜 줘.`  
   **JoILang:**
   ```
      "name": "Scenario1",
      "cron": "",
      "period": 2000,
      "code": "
      triggered := false
      if ((#Television).switch_switch == "on") {
         if (triggered == false) {
         (#Speaker).switch_on()
         triggered = true
         }
         } else {
         triggered = false
      }
   ```

### 6. [Periodic Monitoring / Repeating Execution]: 실시간으로 ~할 때마다, 계속 ~하면 ~해줘, ~동안 ~하면 ~해줘
   - These expressions describe conditions that must be repeatedly checked over time.
   - Common phrases include:
   - "실시간으로 ~할 때마다"
   - "계속 ~하면"
   - "계속 확인해서 ~할 때마다"
   - "~동안 ~하면"

   #### 🧠 Key Principle:
   - If **no explicit interval** is provided (e.g., “매 5초마다”), then **"실시간", "계속" 등 표현이 있을 경우 `period: 100`이 기본값(default)**으로 적용되어야 합니다.
   - This ensures that the system **monitors state changes frequently and promptly**, as expected from real-time behavior.

   #### ✅ Correct Default:
   - `"실시간으로 확인하여 ~할 때마다"` → `period: 100`
   - `"계속 확인해서 ~할 때마다"` → `period: 100`

   #### ❌ Incorrect (Do NOT use by default):
   - `"실시간"인데 period: 10000` → too slow; not real-time.

   ---

   ### ⚠️ 문맥 구분 가이드:

   #### 1️⃣ “실시간으로 확인하여 **현재 상태가 참일 때마다** 행동”
   - → 현재 상태를 주기적으로 검사하고, 조건이 참이면 실행
   - → `if ((#Sensor).sensor_value == "on") { ... }`
   - → 반복 실행 필요 → `period: 100`
   - ✅ 상태 유지 기반 루프

   #### 2️⃣ “실시간으로 확인하여 **변화가 발생할 때마다** (ex. '되다', '변하다')”
   - → 이전과 다른 상태로 바뀔 때마다 반응
   - → 상태 전이 감지를 위한 flag 필요
   - ✅ JoILang에서는 `triggered := false` 등 Boolean flag로 transition 감지
   - ✅ 역시 `period: 100` 필요

   #### [예시 1]  
   **Command**:  
   > 실시간으로 확인하여 재실 센서가 감지 상태일 때마다 10초 대기 후 조명의 밝기를 현재 밝기로 맞춰줘.

   - 반복 체크 → `period: 100`  
   - 조건이 항상 true일 수 있으므로 flag 필요  
   - → 상태 유지 기반

   #### [예시 2]  
   **Command**:  
   > 실시간으로 확인하여 재실 센서가 감지 상태가 될 때마다 조명을 켜줘.

   - 상태 변화 → `off → on` 전이 탐지  
   - → `triggered := false` 등 flag 사용  
   - → `period: 100`

   ```json
   {
   "name": "PresenceTrigger",
   "cron": "",
   "period": 100,
   "code": "
      triggered := false
      if ((#Presence).presenceSensor_presence == \"present\") {
         if (triggered == false) {
         (#Light).switch_on()
         triggered = true
         }
      } else {
         triggered = false
      }
   "
   }
   ```
   - Requires periodic check or loop (period) to react to each occurrence.
   - Use "period": 100 (or another value > 0) to repeatedly check the condition at regular intervals.
   - When using variables to count time or duration inside "code", such as lightOnTime = lightOnTime + 100, the period value directly determines the unit of increment.
   - Therefore, if no specific interval is given, **you must set `period": 100` as the default** to ensure accurate time tracking (e.g., 1800000ms = 30 minutes) as `real time` (`실시간`).
   - Important distinction: If the command describes a one-time event followed by a delay, 
   - The `delay(N SEC|MIN|HOUR)` helper suspends execution for the specified duration without needing to be used with `wait until`. It must be a standalone blocking statement.
   - If a command includes a numeric time condition (e.g., "5초 내에, within 5 seconds"), you must ensure the logic enforces that constraint explicitly in code.
   - → This is not a repeating condition. It should be handled using "period": -1 and an explicit delay call like:
   - [Example]
      Korean: “불이 켜져있으면 30분 후에 알림을 울려줘”
      English: "If the light is on, trigger an alarm 30 minutes later."
      ```
      "cron": ""
      "period": -1
      "code": "if ((#Light).switch_switch == \"on\") { (#clock).delay(1800000); (#Alarm).alarm_siren() }"
      ```

### General Mapping Principles:
- Use `if (...)` for **instantaneous execution based on current state**.
- Use `wait until (...)` for **monitoring future state transitions**.
- Combine `if (...)` and `wait until (...)` using `if-else` to **cover both present and future satisfaction**.
- Use `"period": > 0` to **enable repeated detection** for expressions like "every time", "whenever", or “~할 때마다”.
