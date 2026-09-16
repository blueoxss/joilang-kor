# Timing Control
## cron
- `cron` (String): UNIX cron syntax for trigger. 
  - cron = '': Start immediately. No further cron triggers.
  - Resets scenario regardless of blocking.
  - Use "cron": "* * * * *", and specify other fields (hour, day, etc.) as needed in standard  
  - UNIX cron order: minute, hour, day, month, weekday.
  - Use cron for scenarios triggered at specific time schedules, such as:
  - "매일", "매주", "매월" 같은 정기적인 시간 기반 반복
## [Example] "매일 아침 9시에 실행" → cron: "0 9 * * *"
### Warning
  - The cron field only determines when the scenario starts. Once triggered, the period field controls how frequently the code repeats.
  - Without a proper termination condition (break), the scenario may continue running indefinitely, even when the original cron condition is no longer valid.
  - Use the following condition at the start of your code block to stop execution on weekdays:
### ✅ Required Behavior  
- **Always insert a `break` statement when the repetition condition is no longer valid.**  
- For scenarios that should only run on specific days (e.g., weekends), include logic such as:
```
'cron': '0 0 * * 0,6', 
'period': 5000
'code':
weekday = (#Clock).clock_weekday
if ((weekday != 'saturday') and (weekday != 'sunday')) {
    break
}
```

## period
- `period` (Integer): Controls execution loop after cron trigger
  - `-1`: Execute once, then stop.
  - `0`: Execute once per cron trigger. (no further execution within the same cron cycle)
  - `>= 100`: Repeat every period milliseconds (continuous monitoring).

## *break*: Stops current/future periods until next cron.
  - **If the user command includes instructions to stop or terminate the repetition (for example, "반복을 중단해", "더 이상 반복하지 마", "중단", "until stopped", etc.), you must ensure the periodic execution loop is interrupted by using `break` inside the code block at the appropriate condition.**
  - With cron = "": stops permanently after break
  - With scheduled cron: stops until next cron trigger

### [Example]
```
code:
  <flag> := true
  if (<stop_condition>) {
    break
  }
  if (<flag> == true) {
    (#Tag).<action>()
    <flag> = false
  }
```

## When to Use `period` over `cron`
- If the user command includes "매초마다", "매 5분마다", "15초마다" 등 반복 주기 표현이 포함된 경우, You must always control repeated intervals **using period first**, not cron.
  **반드시 `cron`이 아닌 `period`로 주기 반복을 제어해야 합니다.**
- **Never use `while` in code**

## Periodic Execution within Time Range in cron scenario
To run a scenario repeatedly **only within a specific hour range** (e.g., between 18:00 and 19:00), use `(#Clock).clock_hour` to conditionally check current time.
### [Example]
```
{
name : "Scenario1"
cron : "<start hour cron>"
period : <period ms>
code :
  if (((#Clock).clock_hour >= <startHour>) and ((#Clock).clock_hour < <endHour>)) {
    ...
  } else {
    break
  }
}
```



## [Example]
### Cron and period use case1: Run once now
```
{
"cron": ""
"period": -1
"code: "action1, ..."
}
```
### Cron and period use case2: Run at 9 AM once
```
{
"cron": "0 9 * * *"
"period": -1
"code": "action1, ..."
}
```
###  Daily 9 AM execution
```
{
"cron": "0 9 * * *"
"period": 0
"code": "action1, ..."
}
```
###  Continuous 10-second monitoring
```
{
"cron": ""
"period": 10000
"code": "action1, ..."
}
```

# Variable Management
- all variables Declared with := after "name", "cron", and "period".
- all variables Must be declared only inside the "code" block, do not place them inside or next to "period".

## Global variables
- Global variables must be declared **strictly at the very beginning** of the "code" block, before any logic, if, or service (value or function) calls.
- All variables must be declared once at the very beginning of the "code" block using :=, and **must be updated later using = during execution**.
- Do not declare variables like curtainOpen := true in the middle of the "code" logic.
- This ensures proper initialization and consistent scoping across executions.
Declared using :=, and persist across period executions within the same cron cycle.
- Automatically reset on new cron trigger.
- **Reassigned with `=`**.
- Variable values are preserved and updated across all executions within the same period loop.
- Used for tracking global state across periods, such as counts, toggles, durations, triggers, and flags.

## Local Variables
- Declared within code blocks using `=`
- Scoped to current period execution only
### [Example]
```
{
"cron": ""
"period": 100
"code":
  status = (#Tag).value_service
  if (status == value) {
      // ... Execute code only at the moment the condition turns true
  } else {
    // Reset the flag when the condition is no longer true
  }
}
```


# Device Control
## Device Selection
- **Every tag name is english**
- Every receiver tag after `#` must start with an uppercase English letter.
  - Correct: `#Bedroom`, `#Sector1`, `#Entrance`, `#TemperatureSensor`
  - Incorrect: `#bedroom`, `#sector1`, `#entrance`, `#temperaturesensor`
- The tags can be combined from command.
- Each device has pre-defined Tags (**device**, **location**, **group**...).
- (#Tag1 #Tag2 ...) selects devices with ALL specified tags (AND logic, separated by spaces).
- Access: `(#Tags).service_value` (read-only) or `(#Tags).service_function(args)` (control)
- When using numeric comparisons or function arguments, follow the service descriptor units exactly. For example, if a voltage value has `return_descriptor` saying millivolts, compare `220V` as `220000`.
- Tags must be accurately **extracted from the command**, typically consisting of one device tag and a combination of user-defined tags like location, group, or multiple user-defined tags only.
- A valid device selection typically consists of one device tag (e.g., #Light) and one or more user-defined tags such as #location, #group, etc.
### [Example]
Command: "Turn on the lights in the odd group"
→ #Light is the device tag for "lights"
→ #Odd is a user-defined group tag
→ Combined expression: (#Light #Odd).switch_on()

## Additional Rule: When Tag is Not a Device Type
[Step1] If the **tag** in the command is not found in the **device list** from **[service_list_value] or [service_list_function]** as a device tag:
[Step2] Look up the tag in the [connected_devices] list.
- Identify which devices contain the tag and extract their category (e.g., Light, Alarm).
[Step3] - For each discovered category:
- Check available control **function list** OR the **value list** for conditional checks and control actions  
  (e.g., `switch_off()`, `alarm_off()`, `relativeHumidityMeasurement_humidity()`, etc.)
[Step4] Generate all control commands per device type using the tag as a shared filter.
**Note: Treat "모든 불을 꺼줘" and "불을 다 꺼줘" as equivalent. Both should be interpreted as requests to control all relevant devices, and represented using `all(#Light)` in the code. Do not distinguish between these phrasings.**


---


## !Rule: Device selection must always include valid device type tags
- Any bracket-based selector like `(#...)`, `all(#...)`, `(#TagA #TagB)` must include **at least one valid device type**.
- A **device type** is one explicitly defined in `service_list`, or resolvable via `connected_devices`.
### Invalid Usage (must be avoided):
```
(#).switch_on()
all().switch_on()
().alarm_siren()
```
## !Rule: Reject tags not found in device list or connected devices
- If a tag used in device selection (e.g., `(#Tag)`, `all(#Tag)`) is:
  1. Not listed as a valid device type in `service_list`, **AND**
  2. Cannot be resolved to a device category via `connected_devices`
→ Then that tag is considered **invalid**, and **must not appear in any generated code**.


---


### [Example1]
- Command: "Turn off all devices with tag Group1"
- `#Group1` is not a device-type tag.  
- From [connected_devices], we find:
  {
    "Group1_Light_Lower_Center": {
      "category": "Light",
      "tags": ["Group1", "Lower", "Center", "Light"]
    },
    "Group1_Alarm_Upper_Left": {
      "category": "Alarm",
      "tags": ["Group1", "Upper", "Left", "Alarm"]
    }
  }
- Devices of category Light and Alarm both support switch_off() and alarm_off() respectively.
- → Final JoILang code:
  all(#Group1).switch_off()
  all(#Group1).alarm_off()
- Use this pattern to support generalized group operations when tag-only identifiers are used in the user's command:
```
{
  "name": "Scenario1",
  "cron": "",
  "period": -1,
  "code": "all(#Group1).switch_off()\nall(#Group1).alarm_off()"
}
```
### [Example2]
  - Command: "하우스A 모두 닫아줘."
  [Step1] **Tag** SectorA can not searched in **device list**.
  [Step2] with SectorA, it can find blind device in the [connected_devices] list.
  [Step3] And blind device has blind_close function.
  "s_blind_1": {
    "category": "Blind",
    "tags": ["SectorA", "odd", "Blind"]
  },
  [Step4] Finally,
  ```
  {"name": "Scenario1", "cron": "", "period": -1, "code": "all(#SectorA).blind_close()"}
  ```
### [Example3]
  - Command: "If any Group2 exceeds 80, turn off Group2"
  [Step1] #Group2 is not found in the device list
  [Step2] From [connected_devices] we find:
  {"Group2_HumiditySensor_Upper_Left": {
    "category": "HumiditySensor",
    "tags": ["Group2", "Upper", "Left", "HumiditySensor"]
  }}
  [Step3] From the service [value, function] list, we find that HumiditySensor provides relativeHumidityMeasurement_humidity
  [Step4] → Final JoILang Code:
  ```
  {
  "name": "<Set the "name" field using a **brief and intuitive summary** of the command's intent.>",
  "cron": "",
  "period": -1,
  "code": "if(any(#Group2).relativeHumidityMeasurement_humidity > 80) {\n
    (#Group2).switch_off()\n}"
  }
  ```

## Collective Operations
Use `all(...)` or `any(...)` **only if** explicitly requested for all/any devices.
- `(#Tag).function()`: Apply function to some of matching devices(default)
- `all(#Tag).function()`: Apply function to ALL matching devices
- `all(#Tag).attribute == value`: True if ALL devices match condition
- `any(#Tag).attribute == value`: True if ANY device matches condition
- If any temperature sensor in sector A reads above 30 degrees, turn on all fans.
```
if (any(#SectorA).temperaturesensor_temperature > 30.0) {
  all(#Fan).switch_on()
}
```


# Control Flow

## Condition Logic
- `if (cond) { }`, `if (cond) { } else { }`
- `if ((condA) and (condB))`, `if ((condA) or (condB))`
- Use explicit boolean comparisons for conditions (e.g., `attribute == true`).

## Loop Control
- **No `for` loops allowed**
- **No `while` loops allowed**
- All repetition controlled via `cron` and `period`
- `break`: Stops current/future periods until next cron.
  - With cron = "": stops permanently after break
  - With scheduled cron: stops until next cron trigger

## Blocking Operations
- `wait until(condition)`: Pauses the execution of all subsequent statements in the current period until the specified condition becomes true. Once the condition is satisfied, the next lines are executed sequentially. While waiting, no other commands run, even if the period interval elapses. New triggers within the same cron cycle are ignored during this wait.
- `delay(N SEC|MIN|HOUR)`: Delays execution for the specified duration, then continues with the next statement. Use this helper for between-action waits in dataset JOICode. It must be a standalone statement and must not be used with `wait until` or passed as an argument.
- This enables event-driven behavior in periodic scenarios (period >= 100).


## Expression Rules
### Arithmetic Operations
- Operators: `+`, `-`, `*`, `/`, `=`
- Must assign to variable before using in methods (value/function) calls
- String concatenation is not allowed. No Template Literals. Only static strings or single variable messages are allowed.

### Service Value & Function Arguments Best Practice

- Whenever you use a service_value as a function argument, assign it to a variable first and then pass the variable as the argument.  
  (Do not pass service_value expressions directly in function calls.)
- A service_value access must never be followed by another method call using dot chaining.
  - Incorrect:
    `(#HumiditySensor).humiditysensor_humidity.speaker_speak(string(humiditysensor_humidity))`
  - Correct:
    `hum = (#HumiditySensor).humiditysensor_humidity`
    `(#Speaker).speaker_speak(hum)`
- If a variable is created from a service_value, that variable must be consumed later.
  - Incorrect:
    `power = (#Charger).charger_power`
    `(#Speaker).speaker_speak("Power consumption is ")`
  - Correct:
    `power = (#Charger).charger_power`
    `(#Speaker).speaker_speak(power)`
- For simple numbers or text, you can use literals directly, or assign to a variable first if desired.
- Example:
    ```
    temp = (#TemperatureSensor).temperaturesensor_temperature
    (#AirConditioner).airconditioner_settargettemperature(temp)
    (#Speaker).speaker_speak("Hello")
    ```

### [Example]
#### Valid Case:
```
temp = (#TemperatureSensor).temperaturesensor_temperature
adjusted = temp - 5
(#AirConditioner).airconditioner_settargettemperature(adjusted)
```

#### Invalid Case:
```
temperature = (#TemperatureSensor).temperaturesensor_temperature + 5
(#AirConditioner).airconditioner_settargettemperature( temperature )
```


### Boolean Operations
- Comparisons: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Logic: `and`, `or`
- All conditions must evaluate to explicit boolean values

### [Example]
#### Valid Case:
```
if ((#Tag).booleanService == true) {
  // do something
}
if ((#Tag).integerService > 25) {
    // do something
}
```

#### Invalid Case:
```
if ((#Tag).booleanService) {
  action, ...
}
```

## Error Handling & Communication

### User Feedback
- Use `(#Speaker).speaker_speak("message")` to explain issues
- Handle missing or unsupported devices gracefully

### Device Alternatives
- Multiple devices may provide same functionality:
  - Alerts: `(#Alarm).alarm_siren()` or `(#Siren).siren_setsirenmode('siren')`
  - Presence: `(#PresenceSensor).presencesensor_presence` or an equivalent current presence service from the injected schema

## Best Practices
- Declare `name`, `cron`, `period` first.
- Initialize global variables immediately after period.
- Use explicit boolean comparisons.
- Assign arithmetic results to variables before method (service/function) calls
- **DO NOT** use `for` or `while` loops.
</GRAMMAR>

## FORMAT
### Input
```
Current Time: "YYYY-MM-DD HH:MM:SS"
Generate JOI Lang code for: <user_command>
[Additional context: <optional_info>]
```

### Output
```
name = "Scenario1"
cron = <cron_expression>
period = <integer>
code = 
[global_var := <initial_value>]
[local_var = <changed_value_for_each_period>]
<code_block>
```

Key Rules:
- Each scenario executes independently and concurrently.
- No data sharing between scenarios.

## Generation Guidelines

### Language Interpretation
- Follow user commands literally and precisely, avoiding over-interpretation.
- "When A happens": Use `wait until` (state change/suspension).
- "If A is true": Use `if/else` (single-time condition check).
- "Every": Use appropriate `cron` and `period` settings.
