## Step-by-Step Guide for Separating `value` and `function` in Natural Language Commands (Prompt Guide)

---

## Purpose
Your task is to:
1. Clearly separate **conditions (`value` services)** and **actions (`function` services)**.
2. Respect and preserve the **logical order** and **pairing** of condition → action in the original sentence.
3. Output must be **valid JOI Lang syntax**, with strictly defined structure and service names.

---

## Current Service Naming Policy
- The injected `[service_list]`, `[service_list_value]`, and `[service_list_function]` snippets are authoritative.
- When a service entry has a `canonical_name`, use that device-prefixed service name and lowercase the final JOILang member after the dot.
  - `Siren_SetSirenMode` -> `(#Siren).siren_setsirenmode("siren")`
  - `TemperatureSensor_Temperature` -> `(#TemperatureSensor).temperaturesensor_temperature`
  - `Speaker_Speak` -> `(#Speaker).speaker_speak(message)`
  - `RobotVacuumCleaner_SetRobotVacuumCleanerModeMode` -> `(#RobotVacuumCleaner).robotvacuumcleaner_setrobotvacuumcleanermodemode("auto")`
- Do not use older capability-style service names when the injected current service list provides a device-prefixed canonical service.
- Do not spell service names from memory. Copy the exact current canonical service name and only lowercase it for the final JOILang member.
- Never insert, remove, or reorder words inside a service member name. For example, `setrobotvacuumcleanermodemode` must not become `setrobotvacuumcleanermodermode`.

## Descriptor and Unit Grounding Policy
- The service entry fields `descriptor`, `return_descriptor`, `argument_descriptor`, `argument_type`, `argument_bounds`, and `argument_format` are authoritative.
- Before writing any comparison value or argument literal, read these descriptor fields and convert the user value to the service unit.
  - If `return_descriptor` says `millivolts`, convert volts to millivolts: `220V` -> `220000`.
  - If a cooking-time argument is described in seconds, convert minutes to seconds: `30 minutes` -> `1800`.
  - If an argument format says comma, use comma-separated arguments, never `|`.
- Source selection is part of descriptor grounding:
  - External/outdoor/weather air-quality phrases such as "outdoor dust", "outside fine dust", "외부 미세먼지", or "바깥 미세먼지" must use `WeatherProvider` values, not `AirQualitySensor`. Use `WeatherProvider_Pm10Weather` for dust/fine-dust/미세먼지/PM10, and use `WeatherProvider_Pm25Weather` only when PM2.5/ultrafine/초미세먼지 is explicit.
  - Local/indoor/room air-quality phrases must use `AirQualitySensor` values.
  - General temperature phrases must use `TemperatureSensor_Temperature`, not `TemperatureMeasurement_Temperature`.
  - General humidity phrases must use `HumiditySensor_Humidity`, not `AirQualitySensor_Humidity`, unless the command explicitly says air-quality sensor humidity.
  - Illuminance / lux / 조도 phrases must use `LightSensor_Brightness`, not `Light_CurrentBrightness`, `Light_CurrentSaturation`, or another color/light actuator value.
  - General carbon dioxide / CO2 / 이산화탄소 concentration phrases must use `AirQualitySensor_CarbonDioxide` when it is available. Use `CarbonDioxideSensor_CarbonDioxide` only when the command explicitly names a carbon dioxide sensor device or connected_devices only provide that sensor.
  - PresenceSensor values are BOOL. Use `presencesensor_presence == true` for someone/person detected and `presencesensor_presence == false` for no one/no person. Do not compare it to `"present"` or `"not_present"`.
  - Cloud service availability / activation phrases such as "cloud service is activated", "cloud service is available", "클라우드 서비스가 활성화" must use `CloudServiceProvider_IsAvailable == true` as a boolean condition. Emit it as `(#CloudServiceProvider).cloudserviceprovider_isavailable == true`; do not call it with an argument such as `isavailable(true)`. Do not use `CloudServiceProvider_ChatSession` for availability checks; `ChatSession` only represents an AI chat session.
  - For a rain-triggered sequence that says to check again after a delay and then act if it is not raining, keep the initial rain trigger as `RainSensor_Rain == true`, but use `WeatherProvider_Weather != "rain"` for the delayed recheck.
- For plain power commands, prefer `Switch_On`/`Switch_Off` when the target exposes switch behavior. Use mode setters only for explicit mode requests such as "set to drying mode" or "set to high mode".
- Services/categories in the same connected-device group are shared capabilities of one physical device. If the user says "turn on/켜줘/start/activate" for a semantic target such as `#AirPurifier` and the same group exposes `Switch_On`, emit `(#AirPurifier).switch_on()` or `(#Study #AirPurifier).switch_on()`. Do not add `#Switch` to the receiver unless the user explicitly names a switch. Do not use enum mode setters such as `SetAirPurifierMode("auto")` just because the enum descriptor says the fan is on auto; mode setters are only for explicit mode requests.
- For state preconditions such as "the AC/air conditioner is off" / "에어컨이 꺼져 있으면", test the shared switch state: `(#AirConditioner).switch_switch == false`. Do not infer off-state from `AirConditionerMode == "auto"` or another mode value.
- If the command says "if it is off turn it on, if it is on turn it off" and the target exposes `Switch_Toggle`, use the single toggle action instead of expanding to two branches.
- Do not copy a condition location into a later action unless the command explicitly scopes that action. Example: "if presence is detected in the living room, turn on all lights" means the condition receiver is `(#LivingRoom #PresenceSensor)` but the action target is global `all(#Light)`, not `all(#LivingRoom #Light)`.
- For charger stop commands, use `Charger` with `Switch_Off` when switch behavior is available. A value comparison such as `charger_chargingstate == "stopped"` is not an action.
- For connected devices with multiple categories, use sibling capabilities on the semantic target receiver when appropriate. Examples: `(#AirPurifier).switch_on()` when an air purifier device also exposes Switch, and `all(#Hallway #Light).colorcontrol_setcolor("128,0,128")` when a light device also exposes ColorControl.
- Do not copy a natural-language unit directly when the service descriptor uses a different unit.
- For WindowCovering/Blind/Shade actions, direction words are strict: "raise", "up", "open", "올려", "열어" -> `WindowCovering_UpOrOpen`; "lower", "down", "close", "내려", "닫아" -> `WindowCovering_DownOrClose`. Do not invert these for blinds or shades.
- If the command says blind/shade/window but the retrieved category is `WindowCovering`, keep the semantic receiver tag from the command: use `(#Blind).windowcovering_uporopen()`, `(#Shade).windowcovering_downorclose()`, or `(#Window).windowcovering_currentposition` rather than bare `(#WindowCovering)` when the natural-language target is specific.
- For floor selector tags, normalize English variants to the dataset tag: `first floor` -> `#Floor1`, `second floor` -> `#Floor2`, `third floor` -> `#Floor3`. Do not emit duplicate tags such as `#FirstFloor #Floor1`.
- For window open/closed state in this dataset, use the position value convention when available: open means `armrobot_currentposition >| 0`, closed means `armrobot_currentposition == 0`. Do not use `door_doorstate` for a `#Window` receiver.
- For `#Light` color actions, prefer `Light_MoveToRGB(r, g, b)` over `ColorControl_SetColor("r,g,b")` when `Light_MoveToRGB` is available.
- Do not use invalid off enums such as `Siren_SetSirenMode("off")`; use `Switch_Off()` when a siren must stop after a duration.
- Do not use empty siren mode strings such as `siren_setsirenmode("")`; use `switch_off()` when the siren must stop.
- For multi-button button 2, use `DimmerSwitch_Button2 == "pushed"` when available; do not invent `MultiButton_Button2` or `"pressed"`.
- For "check/read/measure now and again after N minutes; if it changed by T or more" commands, use a snapshot pattern: read the original value into a variable, `delay(N MIN)`, read the same value service again from the same receiver tags, then compare `new >= original + T or new <= original - T`. Do not use `wait until true`, `period`, or `prev/curr` edge-trigger logic for this one-shot recheck pattern.
- For speaker/report/notify/output commands, call `Speaker_Speak(...)`; never invent `MediaPlayback_Speak`.
- For "weather information through the speaker" / "날씨 정보를 스피커로 알려줘", use the current weather value: `(#Speaker).speaker_speak("현재 날씨는 " + (#WeatherProvider).weatherprovider_weather + "입니다")`. Do not call `WeatherProvider_GetWeatherInfo(0, 0)` unless explicit latitude/longitude arguments are provided.
- For "current time through the speaker" / "현재 시각을 스피커로 출력", use `Clock_Hour` and `Clock_Minute` in the spoken text, not only the raw `Clock_Time` string.
- If command_kor contains an explicit quoted Korean message, preserve that exact Korean message in `speaker_speak(...)` rather than translating it to English. Prefer Korean output text when both command_eng and command_kor are provided.
- For dehumidifier "internal care" / "내부케어" in this dataset, use `Dehumidifier_SetDehumidifierMode("auto")` unless the snippet has an explicit internal-care enum.

## Receiver Tag Preservation Policy
- Receiver tags select target devices. Preserve every target qualifier from the user command when it maps to a tag in `[connected_devices]`.
- Use connected-device tag spelling when available, and every `#Tag` in final code must start with an uppercase English letter.
  - `#bedroom` -> `#Bedroom`
  - `#sector1` -> `#Sector1`
  - `#temperaturesensor` -> `#TemperatureSensor`
- Do not translate or invent synonyms in the receiver.
  - living room -> use existing tag `#LivingRoom`, not only `#Light`
  - wine cellar -> use existing tag `#WineCellar`, not only `#TemperatureSensor`
  - even tags -> use existing tag `#Even`, not `#even`
  - upper-level / upper lights -> if connected devices contain `#Top`, use `#Top`, not `#Upper`
  - Sector 10 -> use existing tag `#Sector10`
- Match spaced or lowercase phrases in the command to CamelCase connected tags when their normalized text is the same. For example, "wine cellar", "winecellar", and "와인 셀러" should preserve the connected tag `#WineCellar` when it is available.
- If the command includes "all", "every", "모든", "모두", or equivalent, the receiver must use `all(...)`.
  - Correct: `all(#Even #RobotVacuumCleaner).robotvacuumcleaner_setrobotvacuumcleanermodemode("auto")`
  - Incorrect: `(#RobotVacuumCleaner #Even).robotvacuumcleaner_setrobotvacuumcleanermodemode("auto")`
- If there are multiple connected devices in the same category, include enough target tags to identify the intended subset. Do not drop location/group/sector/position tags.
- For Korean speaker announcements that say a temperature changed rapidly (`온도가 급변`), use the concise statement `"<target>의 온도가 급변했습니다"` and avoid adding extra punctuation. If the target is wine cellar, use `"와인셀러의 온도가 급변했습니다"`.

---

## Step 1: Distinguish Conditional vs. Action Phrases
### Conditions: Characteristics of `value` Phrases
Purpose: Used for state evaluation or comparison conditions
- Used for evaluating the state of sensors or devices.
- Includes expressions like: "if", "when", "greater than", "in case", "is on", "equals", "during", etc.
- You must only use `value` services defined in [service_list_value]
- Both device tags and service names must exactly match the entries
- Do NOT create or assume any service name that is not explicitly listed
- If a device does not exist in the full list, use a device only if it exists in [connected_devices]
- Do not use undefined or legacy value services in condition expressions
#### [Correct Examples]
- if ((#Door).door_doorstate == "closed")
#### [Incorrect Examples]
- (#Light).switch_switch == "on"      
- This is a value, not a function


### Actions: Characteristics of `function` Phrases
Purpose: Used for device control or command execution
- Used for executing control commands on devices.
- Includes verbs like: "turn on", "turn off", "open", "close", "send", "activate", etc.
- You must only use `function` services defined in [service_list_function]
- Both device tags and function names must exactly match the entries
- If a device is not available in the full list, use only those available in [connected_devices]
- Do not use value-type services as functions
#### [Correct Examples]
- (#Switch).switch_on()
- (#WindowCovering).windowcovering_downorclose()
#### [Incorrect Examples]
- (#Window).legacy_windowcontrol()    
- This function does not exist



---


## Step 2: Prepare extracted `value`/`function` for JOI Lang processing
### Split compound natural language commands into:
- `value` expressions (conditions) → Convert into sensor evaluation expression:  
  `if ((#Sensor).attribute >= value)`
- `function` expressions (actions) → Convert into device command expression:  
  `(#Tag).function_on()`
#### [Example]  
Command: “If it’s raining and the window is open, close the window.”
- `value`:
  - “It’s raining”
  - “The window is open”
- `function`:
  - “Close the window”


---


## Step 3: Extract `value` and `function` + Preserve Temporal **Execution Order**
### General Patterns of Execution Flow
- Your job is not just to separate them, but also to **preserve the execution order as implied by the natural sentence**, not just by grammar structure.
- Natural language commands can appear in different logical forms.  
- The model must handle the correct **temporal relationship** between condition and action.

#### ✅ Pattern 1: Condition → Action (Most common)
- Evaluate condition first, then execute one or more actions.
[Example]:  
> “If it’s raining and the window is open, close the window.”
```
if ((#RainSensor).rainsensor_rain == true and (#Door).door_doorstate == "open") {
    (#Door).door_close()
}
```
#### ✅ Pattern 2: Action → Condition → Termination or Follow-up
- The command begins with an action, and later introduces a condition for stopping, switching, or repeating.
[Example]:  
> “Turn on the irrigator. When the light exceeds 500 lux, turn it off and stop.“
```
(#Irrigator).switch_on()
wait until ((#LightSensor).lightsensor_brightness >= 500)
(#Irrigator).switch_off()
break
```
#### ✅ Pattern 3: Multiple Independent Condition → Action Pairs
- Each condition controls its own action. They are not necessarily sequential or nested.
- Always **evaluate the condition before executing any related action**.
- Never reverse the order from the original command unless explicitly indicated.
[Example]:  
> “If soil is dry, start irrigation. If temperature is high, turn on the fan.”
```
if ((#SoilSensor).moisture < 30) {
    (#Irrigator).switch_on()
}
if ((#TemperatureSensor).temperaturesensor_temperature >= 30) {
    (#Fan).switch_on()
}
```
#### ✅ Pattern 4: Mixed or Nested Execution Flow
- Commands can involve a **combination of patterns**, such as:
  - A condition triggering multiple actions,
  - Then a follow-up condition for termination,
  - Or nested conditions within an action block.
[Example]:  
> “If it's morning and no one is home, open the curtains. Then, when the light exceeds 800 lux, turn them off.”
```
if ((#Clock).clock_hour >= 6 and (#PresenceSensor).presencesensor_presence == "not_present") {
    (#WindowCovering).windowcovering_uporopen()
    wait until ((#LightSensor).lightsensor_brightness >= 800)
    (#WindowCovering).windowcovering_downorclose()
}
```


---


## Additional Syntax Rules for Mapping
### For **value services**:
Use the **return_descriptor** to determine comparison format and semantics.

#### [Example]
- If "device": "Clock", "service": "clock_time" has return_descriptor = {"format": "hhmm"},
then use:
"code": if ((#Clock).clock_time == 1515)

### For **function services**:
Use **argument_type** or **argument_format** to determine the correct format.
Use **argument_bounds** or **argument_descriptor** to determine the correct format.
- Function call arguments are always comma-separated in JOILang.
- If `argument_type` contains `|`, treat it only as a schema type-list delimiter, not as the function call separator.
- If a function takes positional arguments, keep comma-separated JOILang syntax.
  - Correct: `(#Light).light_movetorgb(255, 255, 0)`
- RGB-like functions must also use comma-separated JOILang arguments.
- For `Oven_SetCookingParameters` and `RiceCooker_SetCookingParameters`, the second argument is cooking time in seconds. Convert minutes to seconds, e.g. 30 minutes -> 1800. Do not use milliseconds and do not leave raw minutes.

#### [Example1]
- If "device": "Light", "service": "colorControl_setColor" has argument type DICT
with bounds key/value pairs: "RED,GREEN,BLUE" and example "255,255,255",
then use:
(#Light).colorControl_setColor("255,0,0")

#### [Example2]
If "device": "Calculator", "service": "calculator_mod" function service has
  "argument_type": "DOUBLE | DOUBLE",
  "argument_format": ",",
then use:
- "code": {"name": "Scenario1", "cron": "", "period": -1, "code": "(#Calculator).calculator_mod(10, 3)"}

#### [Example3]
If the command is "Start the rice cooker on cooking mode for 30 minutes" and the service is `RiceCooker_SetCookingParameters`,
then use:
- "code": {"name": "Scenario1", "cron": "", "period": 0, "code": "(#RiceCooker).ricecooker_setcookingparameters(\"cooking\", 1800)"}

### MenuProvider specificity rule
- Use `MenuProvider_TodayMenu` only for broad requests such as "tell me today's menu" when no specific place and no specific meal-time are present.
- If the command explicitly includes date/day, place, and meal-time, use `MenuProvider_GetMenu("<date> <place> <meal>")`.
  - Example: "오늘의 301동 점심 메뉴를 스피커로 알려줘." -> `menu = (#MenuProvider).menuprovider_getmenu("오늘 301동식당 점심")`
  - Then speak the returned variable: `(#Speaker).speaker_speak(menu)`

### Schedule and period policy
- Encode wall-clock start times and day filters in `cron`, not by adding duplicate weekday/hour checks around the whole code.
- If a command says "from X to Y every N minutes", set `cron` to the start time, set `period` to N minutes in milliseconds, and keep only the stop boundary in code. Example: from 10 PM to midnight every 10 minutes -> `cron: "0 22 * * *"`, `period: 600000`, code starts with `if ((#Clock).clock_hour == 0) { break }`.
- For "from now until 3 PM" / "오후 3시까지", use the exact boundary guard `if ((#Clock).clock_hour == 15) { break }`, not `>= 15`.
- If a command says "from now until midnight every N minutes", keep `cron: ""`, set `period`, and stop with `if ((#Clock).clock_hour == 0) { break }`.
- If a command says "weekend afternoons every N minutes", encode weekend/start in cron such as `0 12 * * 6,7`, set `period`, and use code only for the end boundary.
- If a command has two wall-clock actions in one scenario, use the first time as `cron` and a blocking `delay(...)` for the later action. Example: "8 AM odd blinds, 9 AM even blinds" -> `cron: "0 8 * * *"`, then `delay(1 HOUR)`, not `wait until clock_hour == 9`.
- Example: "Every 7 PM, if no one is detected on the 1st floor, turn off all lights; for the 2nd floor, check at 8 PM and turn off all its lights if no one is present." -> `cron: "0 19 * * *"`, `period: 0`, first check `#Floor1`, then `delay(1 HOUR)`, then check `#Floor2`.
- For weekend periodic checks, encode the weekend window in cron such as `0 0 * * 6-7`, keep the explicit period, and keep a weekday guard if the GT policy requires it.
- If a command has `cron`, set `period` to `0` unless there is an explicit repeated interval.

### Trigger-then-repeat skeleton
- For commands like "when/once X happens, then every N seconds/minutes do Y", set `period` to N milliseconds and use this skeleton:
  ```
  active := 0
  if (active == 0) {
      wait until (<trigger condition>)
      active = 1
  }
  <repeated action>
  ```
- Do not put the repeated action only in an `else` branch. Do not reset the trigger flag unless the command explicitly says to stop when the trigger becomes false.
- If there is a one-time immediate announcement before a later repeated action, keep the one-time announcement inside the `active == 0` block before `active = 1`, and put only the repeated action outside.
- For smoke-triggered sirens in this dataset, use `siren_setsirenmode("fire")` for fire/smoke alarms, not `"emergency"`, unless the command explicitly says emergency.
- For "drying is finished" on `LaundryDryer`, use `laundrydryer_spinspeed == 0`; do not invent `laundrydryer_dehumidifiermode`.
- For repeating open/close window actions, use `windowcovering_uporopen()` and `windowcovering_downorclose()` with a state variable; do not use `window_open()` or `window_close()`.
- For "whenever X is opened/locked" edge triggers, use `prev := ...`, `curr = ...`, and `if (prev != target and curr == target) { ... }`, then `prev = curr`; do not use a timer flag when the command asks for an edge event.
- For midnight-to-6AM repeated light checks after closing the door, close the door once inside `active := 0`, then use `clock_hour == 6` as the stop guard and `lightsensor_brightness` for the brightness condition.
- If a required slot is missing, do not invent it. Use the best generic value service from the injected service list.


---


## Summary Table of Examples

| Natural Language Command                               | value                          | function       |
|--------------------------------------------------------|--------------------------------|----------------|
| If the door is open, trigger the alarm                 | Check door status              | Trigger alarm  |
| If the window is closed and temperature exceeds 30°C   | Window status, temp condition  | Turn on fan    |
| When the button is pressed, turn off the lights        | Button press                   | Turn off light |
| If any humidity sensor in Group 1 reads below 30       | Group 1 humidity condition     | Water the area |

---

## Proceeding to the Next Step

1. Use `value` -> map only from the injected current [`service_list_value`].
2. Use `function` -> map only from the injected current [`service_list_function`].
3. Assemble both into a complete JOILang code block.
