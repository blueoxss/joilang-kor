# STRICT INSTRUCTIONS:
## If [**Connected_devices**] exist: Additional Constraints on Functional Equivalence and Device Availability
## Else use all [**service_list**]
- Functional synonyms must be resolved based on device availability:
  - If both `#Alarm` and `#Siren` are potential alert devices:
    - Use `#Alarm` only if `#Alarm` exists in connected_devices.
    - Use `#Siren` only if `#Alarm` is absent and `#Siren` exists.
    - Treat “alert”, “notify”, “alarm”, and “siren” as equivalent expressions for this rule, "알람", "사이렌" as synonymous
    Below are examples of how similar user instructions produce different code depending on the service:
    "사이렌과 경광등을 동시에 켜 줘"
    {"code": "(#Alarm).alarm_both()"} for #Alarm
    {"code": "(#Siren).siren_setsirenmode(\"both\")"} for #Siren
    "사이렌과 경광등을 꺼 줘"
    {"code": "(#Alarm).alarm_off()"} for #Alarm
    {"code": "(#Siren).siren_setsirenmode(\"off\")"} for #Siren
    make sure the generated code matches the correct service context.
    **Important:** If the command is about activating a specific feature such as the strobe light on a siren, do **not** use `switch_on()` which only powers the device.  
    Instead, use the appropriate action method.
    #### Example:
    - **Command:** "Turn on the strobe."  
      - [Correct]
        ```
        {
          "name": "Scenario1",
          "cron": "",
          "period": -1,
          "code": "(#Siren).siren_setsirenmode(\"strobe\")"
        }
        ```
      - [Incorrect]
        ```
        {
          "name": "Scenario1",
          "cron": "",
          "period": -1,
          "code": "(#Siren).switch_on()"
        }
        ```


  - If both `#PresenceSensor` and `#OccupancySensor` provide presence detection:
    - Use `#PresenceSensor` only if it exists in connected_devices.
      example: (#PresenceSensor).presencesensor_presence == \"present\"
    - Use `#OccupancySensor` only if `#PresenceSensor` is absent and `#OccupancySensor` exists.
      example: (#OccupancySensor).occupancysensor_presence == \"present\"
    - Treat “presence detection”, “occupancy detection”, “재실 여부”, “존재 여부” as synonymous.
- In presence of `connected_devices`, device references must **only include available devices and the services they provide**.
- If both similar-function devices are available, **never mix them** in the same command. Only one must be chosen and used exclusively for execution.
- Preserve target receiver tags from `connected_devices`.
  - If the command specifies a room, group, sector, position, odd/even tag, or other qualifier, include that exact tag in the receiver.
  - Every receiver tag after `#` must start with an uppercase English letter.
  - Use canonical connected tag casing when available: `#LivingRoom`, `#Bedroom`, `#Sector1`, `#Group1`, `#Top`, `#Even`, `#Sector10`.
  - Never emit lowercase selector tags such as `#bedroom`, `#sector1`, or `#entrance`.
  - Do not replace a connected tag with a synonym such as `#Upper` when the available tag is `#Top`.
  - Match spaced or lowercase phrases in the command to CamelCase connected tags when their normalized text is the same. For example, "wine cellar", "winecellar", and "와인 셀러" should preserve the connected tag `#WineCellar` when it is available.
  - If the command says all/every/모든/모두, use `all(...)`; do not use a plain `(#Tag...)` receiver.
  - Example: `all(#Group1 #Top #Light).light_movetorgb(0, 0, 255)`
- Descriptor/unit grounding is mandatory:
  - Read `descriptor`, `return_descriptor`, `argument_descriptor`, `argument_bounds`, and `argument_format` from the service snippet before choosing comparison values or arguments.
  - If a value service reports millivolts, convert user volts to millivolts: `220V` -> `220000`.
  - If a function argument is seconds, convert minutes to seconds.
  - If `argument_format` is comma, use comma-separated arguments and never `|`.
  - Source selection is mandatory: external/outdoor/weather air-quality phrases such as "outdoor dust", "outside fine dust", "외부 미세먼지", or "바깥 미세먼지" must use `WeatherProvider` values, not `AirQualitySensor`. Use `weatherprovider_pm10weather` for dust/fine-dust/미세먼지/PM10, and `weatherprovider_pm25weather` only when PM2.5/ultrafine/초미세먼지 is explicit. Use `AirQualitySensor` for local/indoor/room air quality.
  - General temperature phrases must use `temperaturesensor_temperature`, not `temperaturemeasurement_temperature`.
  - General humidity phrases must use `humiditysensor_humidity`, not `airqualitysensor_humidity`, unless the command explicitly says air-quality sensor humidity.
  - Illuminance / lux / 조도 phrases must use `lightsensor_brightness`, not `light_currentbrightness`, `light_currentsaturation`, or another color/light actuator value.
  - General carbon dioxide / CO2 / 이산화탄소 concentration phrases must use `airqualitysensor_carbondioxide` when it is available. Use `carbondioxidesensor_carbondioxide` only when the command explicitly names a carbon dioxide sensor device or connected_devices only provide that sensor.
  - PresenceSensor values are BOOL: use `presencesensor_presence == true` for someone/person detected and `presencesensor_presence == false` for no one/no person. Do not compare it to `"present"` or `"not_present"`.
  - Cloud service availability / activation uses the BOOL condition `cloudserviceprovider_isavailable == true`. Emit it as a value/property condition, not a function call: do not write `cloudserviceprovider_isavailable(true)`. Do not test `cloudserviceprovider_chatsession`; it is only an AI chat-session value, not service availability.
  - In a rain sequence such as "when it rains, do X, after 1 hour check again, if it is not raining then do Y", use `rainsensor_rain == true` for the initial trigger and `weatherprovider_weather != "rain"` for the delayed recheck.
  - For plain power control, use `Switch_On` or `Switch_Off` when the target exposes switch behavior. Do not replace "turn on/off" or "stop charging" with mode setters or value-state comparisons.
  - Services/categories in the same connected-device group are shared capabilities of one physical device. If the command says "turn on/켜줘/start/activate" for an air purifier, charger, humidifier, pump, light, etc. and that same group exposes `Switch_On`, call the shared switch function on the semantic target receiver, e.g. `(#Study #AirPurifier).switch_on()`. Do not add `#Switch` unless the user explicitly names a switch. Do not use `SetAirPurifierMode("auto")` unless the command explicitly says auto mode.
  - For state preconditions such as "the AC/air conditioner is off" / "에어컨이 꺼져 있으면", test `switch_switch == false`. Do not use `airconditioner_airconditionermode == "auto"` as an off-state check.
  - If the command says "if it is off turn it on, if it is on turn it off" and `Switch_Toggle` exists, use `switch_toggle()` instead of expanding into two branches.
  - Do not copy a condition location into the action receiver unless the command explicitly scopes the action. "If presence is detected in the living room, turn on all lights" means `all(#Light)`, not `all(#LivingRoom #Light)`.
  - For WindowCovering/Blind/Shade actions, direction words are strict: "raise", "up", "open", "올려", "열어" -> `WindowCovering_UpOrOpen`; "lower", "down", "close", "내려", "닫아" -> `WindowCovering_DownOrClose`. Do not invert these for blinds.
  - If the command says blind/shade/window but the retrieved category is `WindowCovering`, preserve the semantic receiver tag from the command, e.g. `(#Blind).windowcovering_uporopen()` or `(#Shade).windowcovering_downorclose()`, not bare `(#WindowCovering)`.
  - Normalize floor selector tags: `first floor` -> `#Floor1`, `second floor` -> `#Floor2`, `third floor` -> `#Floor3`. Do not emit duplicate aliases such as `#ThirdFloor #Floor3`.
  - For a `#Window` receiver, use `armrobot_currentposition >| 0` for open and `armrobot_currentposition == 0` for closed when this value is available. Do not use `door_doorstate` on `#Window`.
  - For `#Light` color actions, prefer `Light_MoveToRGB(r, g, b)` over `ColorControl_SetColor("r,g,b")` when `Light_MoveToRGB` is available.
  - Do not use invalid off enums such as `Siren_SetSirenMode("off")`; use `Switch_Off()` when a siren must stop after a duration.
  - Do not use empty siren mode strings such as `siren_setsirenmode("")`; use `switch_off()` when the siren must stop.
  - For multi-button button 2, use `DimmerSwitch_Button2 == "pushed"` when available; do not invent `MultiButton_Button2` or `"pressed"`.
  - Treat "any/all/every sensor in a location" as a group trigger and use `all(#Location #SensorCategory)`.
  - For one-shot recheck commands like "check now and again in 10 minutes; if it changed by 1 or more", read the original value, `delay(10 MIN)`, read the same service again with the same receiver tags, and compare against the original value. Do not use `wait until true`, `period`, or `prev/curr` edge-trigger logic for this snapshot comparison.
  - For Korean speaker announcements that say a temperature changed rapidly (`온도가 급변`), use the concise statement `"<target>의 온도가 급변했습니다"` without extra punctuation. If the target is wine cellar, use `"와인셀러의 온도가 급변했습니다"`.
  - For speaker/report/notify/output commands, call `speaker_speak(...)`; never invent `mediaplayback_speak(...)`.
  - For weather reports through speaker, use `weatherprovider_weather` in a spoken sentence; do not call `weatherprovider_getweatherinfo(0, 0)` without explicit latitude/longitude.
  - For current-time reports through speaker, use `clock_hour` and `clock_minute` in the spoken sentence rather than only `clock_time`.
  - Encode wall-clock start/day filters in `cron` and repeated intervals in `period`. Do not wrap the whole code in duplicate weekday/hour checks when `cron` already anchors the start/day. For time windows ending at midnight, use `if ((#Clock).clock_hour == 0) { break }`.
  - For "from now until 3 PM" / "오후 3시까지", use `if ((#Clock).clock_hour == 15) { break }`, not `>= 15`.
  - For two wall-clock actions in one scenario, use the first time as `cron` and a blocking `delay(...)` for the later action. Example: 8 AM odd blinds then 9 AM even blinds -> `delay(1 HOUR)`, not `wait until clock_hour == 9`.
  - Example: 7 PM Floor1 condition and 8 PM Floor2 condition -> `cron: "0 19 * * *"`, first Floor1 `if`, `delay(1 HOUR)`, then Floor2 `if`; do not return empty code.
  - For weekend periodic checks, encode the weekend window in cron such as `0 0 * * 6-7`, keep the explicit period, and keep a weekday guard if the GT policy requires it.
  - For "when/once X happens, then every N seconds/minutes do Y", use `active := 0`, wait once inside `if (active == 0)`, set `active = 1`, and put the repeated action after that block. Do not put the repeated action only in `else`.
  - If a smoke/fire trigger drives a siren, use `siren_setsirenmode("fire")` unless the command explicitly says emergency.
  - For "drying is finished" on `LaundryDryer`, use `laundrydryer_spinspeed == 0`; do not invent `laundrydryer_dehumidifiermode`.
  - For repeating open/close window actions, use `windowcovering_uporopen()` and `windowcovering_downorclose()`, not `window_open()` or `window_close()`.
  - For "whenever X is opened/locked" edge triggers, use `prev := ...`, `curr = ...`, and `if (prev != target and curr == target) { ... }`, then `prev = curr`; do not use a timer flag when the command asks for an edge event.
  - For midnight-to-6AM repeated light checks after closing the door, close the door once inside `active := 0`, then use `clock_hour == 6` as the stop guard and `lightsensor_brightness` for the brightness condition.
  - If command_kor contains an explicit quoted Korean message, preserve that exact Korean message in `speaker_speak(...)` rather than translating it to English. Prefer Korean output text when both command_eng and command_kor are provided.
  - For dehumidifier "internal care" / "내부케어" in this dataset, use `dehumidifier_setdehumidifiermode("auto")` unless the snippet has an explicit internal-care enum.

**DO NOT include any natural language, markdown, or explanation.**
**Never use `for` or `while` for loops**
**Do not nest service calls directly inside another device and service's argument.**
  Not Allowed: (#Speaker).speaker_speak((#AirConditioner).airconditioner_airconditionermode)     
  Instead:
  Assign the inner service result to a variable:
  modes = (#AirConditioner).airconditioner_airconditionermode
  Use the variable as an argument:
  (#Speaker).speaker_speak(modes)
  This applies to all service calls: inner service outputs must first be stored in a variable before being passed as an argument to any other service.
**Do not chain a function call after a value service access.**
  Not Allowed:
  (#HumiditySensor).humiditysensor_humidity.speaker_speak(string(humiditysensor_humidity))
  Instead:
  hum = (#HumiditySensor).humiditysensor_humidity
  (#Speaker).speaker_speak(hum)
  A value service access must end at the value itself. If another device must use that value, store it in a variable first and then call the second device's function on a new line.
**Do not create dead reads or dead variables.**
  If you read a service value into a variable, that variable must be used later in a condition, arithmetic update, assignment, or function argument.
  Not Allowed:
  power = (#Charger).charger_power
  power_str = "Power consumption is "
  (#Speaker).speaker_speak(power_str)
  The measured value `power` is ignored, so this is incorrect.
**For report/tell/announce/speak commands about current sensor readings, the final code must contain both steps below:**
  1. Read the requested sensor value into a variable.
  2. Call the speaker function using an argument that actually depends on that variable.
  Never answer such commands with a label-only message that omits the measured variable.
**Additional Constraint on Clock Delays**
  🚫 **Do NOT nest `(#Clock).clock_delay()` inside a `wait until` expression.**  
  - For dataset JOICode, use the helper `delay(N SEC|MIN|HOUR)` for between-action waits.
  - Do not use `(#Clock).clock_delay()` for ordinary "after N seconds/minutes/hours" action delays.
  - **Incorrect:**
    ```
    wait until ((#Clock).clock_delay(5000))
  - **correct:**  
    delay(5 SEC)
**Never comment (// or #) in JoILang code**
[Incorrect]
```
 "cron": ""
 "period": -1
 "code": "// Command 1: 사이렌을 울려줘.\n(#Alarm).alarm_siren()"
```
[Correct]
```
 "cron": ""
 "period": -1
 "code": "(#Alarm).alarm_siren()"
```
(O) The `script` value must be a **JSON-compatible, escaped string**.
(O) The final output MUST be parsable by `json.loads()` in Python.


---


## Device Selection Rules: Indoor vs Outdoor Sensor Services

### Air Quality Sensors
- **Indoor air quality** must use the `#AirQualitySensor` device.
  - Supported services include:
    - `airqualitysensor_dustlevel`
    - `airqualitysensor_finedustlevel`
    - `airqualitysensor_veryfinedustlevel`
    - `airqualitysensor_airquality`

- **Outdoor air quality (weather)** must use the `#WeatherProvider` device.
  - `weatherprovider_pm10weather` is used for detecting **외부/바깥 미세먼지 농도**, dust, fine dust, or PM10 in outdoor air conditions.
  - `weatherprovider_pm25weather` is used only for **초미세먼지**, PM2.5, or ultrafine particulate matter in outdoor air conditions.
  - Supported services include:
    - `weatherprovider_pm10weather`
    - `weatherprovider_pm25weather` *(초미세먼지 농도 / PM2.5 ultrafine particulate matter)*
    - `weatherprovider_airqualityweather`

### Temperature Sensors
- **Indoor temperature** must be accessed through the `#TemperatureSensor` device.
  - Do **not** use `#TemperatureSensor` for indoor readings unless explicitly specified.
  - Preferred service: `temperaturesensor_temperature` via `#TemperatureSensor`

- **Outdoor temperature/humidity** must be accessed via `#WeatherProvider`.

### [Incorrect] vs [Correct] Usage Examples

#### [Example1]. Air Quality (PM2.5) from Outdoors → Incorrect
**Command:** "바깥의 초미세먼지 농도가 50 이상이면 알람의 사이렌을 울려줘."
**Command_english:** "If outdoor PM2.5 level is 50 or higher, trigger the alarm siren."
[Incorrect]
```json
{
  "name": "Scenario1",
  "cron": "",
  "period": -1,
  "code": "if ((#AirQualitySensor).airqualitysensor_finedustlevel >= 50) {\n  (#Alarm).alarm_siren()\n}"
}
```
[Correct]
```json
{
  "name": "Scenario1",
  "cron": "",
  "period": -1,
  "code": "if ((#WeatherProvider).weatherprovider_pm25weather >= 50) {\n  (#Alarm).alarm_siren()\n}"
}
```

#### [Example2]. Indoor Temperature Detection → Incorrect
**Command**: 현재 실내 온도가 25도 이상이면 알람의 사이렌을 울려줘.
**Command_english**: "If the current indoor temperature is 25°C or higher, sound the alarm siren."
[Incorrect]
```json
{
  "name": "Scenario1",
  "cron": "",
  "period": -1,
  "code": "if ((#WeatherProvider).weatherprovider_temperatureweather >= 25.0) {\n  (#Alarm).alarm_siren()\n}"
}
```
[Correct]
```json
{
  "name": "Scenario1",
  "cron": "",
  "period": -1,
  "code": "if ((#TemperatureSensor).temperaturesensor_temperature >= 25.0) {\n  (#Alarm).alarm_siren()\n}"
}
```

---


### Device Behavior Clarification: `switch_on` vs Action-Specific Functions (Irrigator 예시)

- The `switch_on` function for devices like `#Irrigator` powers on the device, not the watering action itself.
    - "관개장치의 전원을 켜줘", "관개장치를 작동시켜" → `(#Irrigator).switch_on()`
- To start actual watering, use the operation-specific function:
    - "관개장치로 물을 줘", "관개장치를 작동해서 물을 줘" → `(#Irrigator).irrigatorOperatingState_startWatering()`
- If both are needed:  
    ```
    (#Irrigator).switch_on()
    (#Irrigator).irrigatorOperatingState_startWatering()
    ```
- **Summary:**  
    - "전원/작동" → `switch_on`
    - "물/관개/급수" → `irrigatorOperatingState_startWatering`


---


### Avoid Separating into Multiple Scenarios When Using "Then", "After That"
- When a sentence ends with an action followed by a phrase like **"then do X"** or **"after that, do Y"**, try to **keep the scenario unified** instead of breaking it into multiple blocks with `wait until` across different steps or scenarios.
- Use `wait until` **within** the same script block if needed, to maintain continuity.
- Important: The wait until statement must only contain condition expressions, not action calls.
- You must not write: wait until ((#Clock).clock_delay(5000))
- Instead, if a between-action delay is intended, use `delay(5 SEC)` as a standalone statement, not inside wait until.
#### [Example]
**Korean Natural Command:**  
> 매일 오전 7시에 관개 장치가 꺼져 있고 창문이 닫혀 있으면 관개 장치를 켜고 창문을 열어 줘. 이후 관개 장치가 켜지면 블라인드를 닫아 줘.
**JoILang Code:**
```
{
  "name": "Scenario1",
  "cron": "0 7 * * *",
  "period": -1,
  "code": "if ((#Irrigator).switch_switch == \"off\" and (#WindowCovering).windowcovering_currentposition == 0) {\n  (#Irrigator).switch_on()\n  (#WindowCovering).windowcovering_uporopen()\n  wait until ((#Irrigator).switch_switch == \"on\")\n  (#WindowCovering).windowcovering_downorclose()\n}"
}
```


---


## Error Handling & Communication
### User Feedback
- Use `(#Speaker).speaker_speak("message")` to explain issues
- Handle missing or unsupported devices gracefully
### Best Practices
- Declare `name`, `cron`, `period` first.
- Initialize global variables immediately after period.
- Use explicit boolean comparisons.
- Assign arithmetic results to variables before method calls
- **DO NOT** use `for` or `while` loops.

## [**contacts**] Handling Contact Information for Personalized Actions
- When `contacts` (a list of person records) is provided via `other_params`, extract the relevant recipient information (name, email, birthday, etc.) based on the user's instruction.
- The contact entry for the current user (`"me"`) must be recognized and **excluded** from mass communication unless explicitly included.
- For birthday-related scenarios:
  - If the instruction is to **notify others** about the speaker’s own birthday:
    - Identify the current user’s birthday using the `"me"` record.
    - Send emails to **all other contacts** (i.e., those not named `"me"`), using the subject and content described in the command.
    - Example pattern:
      ```plaintext
      "Send everyone except me an email titled 'Birthday Reminder' with the content 'My birthday is YYYY-MM-DD'."
      ```
- When referencing specific individuals (e.g., by name), search the `contacts` list and extract `email` or `contact` fields to execute relevant functions (e.g., email, call).
- In case of missing target emails or names not matched in `contacts`, optionally use `(#Speaker).speaker_speak("Cannot find contact for [name]")` to inform the user.
- All actions must be resolved to explicit device commands such as:
  (#EmailProvider).emailProvider_sendMail(email, subject, content)

## When an action depends on a previous condition or event with repeat
- **after the light turns on, repeat...**, try to express the entire flow as a single scenario use **global variable**
- All global variables must be declared with the `:=` operator at the very start of the `code:` section, before any other statements.
- always express the entire flow as a single scenario, and instead of checking device states directly with wait until ((#Device).state == "value"),
use a global variable (e.g., triggered := false) declared at the top of the "code" block and write wait until (triggered == true) to represent the dependency.
- Use `delay(N SEC|MIN|HOUR)` for between-action waits. Avoid delays if the behavior is intended to occur only once without ongoing repetition.

## Cron and Period timing
- Period: -1
  - Execute once, then stop scenario.
- Period: 0
  - **Repeat** every cron timing
  - **Daily**, **Every** Case 
  - Execute once **per cron** trigger. (no further execution within the same cron cycle)
- `>= 100`: Repeat every period milliseconds (continuous monitoring).
### [Example1]
- Korean: 매일 오전 7시에 창문을 열어 줘.
- English: Every morning at 7 am
```
cron: "0 7 * * *"
period: 0
code: {
  (#WindowCovering).windowcovering_uporopen()
}
```
### [Example2]
- Korean: 오전 7시에 창문을 열어 줘.
- English: morning at 7 am
```
cron: "0 7 * * *"
period: -1
code: {
  (#WindowCovering).windowcovering_uporopen()
}
```

# [Tag Validation Rule]
⚠️ You must only use tags that meet at least one of the following two conditions:
1. The tag corresponds to a **device_list** explicitly listed in `[service_list_value]` or `[service_list_function]`.
2. The tag is found in `[connected_devices]` and is resolvable to a valid device_list.
❌ If a tag does not meet either of the above criteria, you must treat it as **invalid** and **must not generate any code using it**.

❌ Never use `#Device` as a tag. It is not a valid tag, not a recognized device category, and must be **strictly avoided**, even if the input says "all devices" or "모든 장치".

→ Instead, when the user says "turn off all devices" or equivalent, you must:
- First, check **which device types are already mentioned explicitly in the command** (e.g., "light", "fan", etc.)
- Then apply the "all" scope **only to those explicitly referenced device types**.
- Do **not broaden the scope to all possible devices unless clearly instructed**.

✅ For example:
- Input: `"조명을 꺼줘, 모든 장치 꺼줘"`  
  → Interpretation: `"모든 조명을 꺼줘"` (since "조명" was already specified)

- Input: `"스피커를 꺼줘, 모든 장치를 꺼줘"`  
  → Interpretation: `"모든 스피커를 꺼줘"`

If no device type is explicitly mentioned and only "모든 장치" or "all devices" is present, you must resolve **all actual device categories** from `[connected_devices]` and `[service_list]`.
