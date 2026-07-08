# vision_detect Protocol Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the vision_detect protocol loop — firmware generates simulated vision_detect events, risk_fusion v2 consumes them, and the PC host app parses and displays the full event chain (vision_detect -> risk v2 -> voice -> actuator) without requiring real camera hardware.

**Architecture:** Add `vision_detect` and `voice` event types to both firmware and host app. Firmware adds `distance_estimator.c/h` as a pure-function single-object distance estimator, a `voice_prompt.c/h` stub, and a simulated `vision_detect` generator task. `risk_fusion` gains a v2 path that consumes vision_detect + pressure to output risk v2 with category/nearest_class/ttc_s. Host app adds corresponding dataclasses, parsers, and UI panels.

**Tech Stack:** C (ESP-IDF firmware, GCC-hosted pure-function tests), Python 3.10+ / PySide6 (host app), unittest (Python tests), GCC (C tests)

## Global Constraints

- All new JSON events must follow the format specified in `ProjectFile/README.md` (vision_detect v1, risk v2, voice v1)
- Firmware pure-function code must compile on both ESP32-S3 and host GCC (no ESP headers in pure-function files)
- Host app Python code must pass `python -m compileall -q` and all existing tests before and after changes
- No new external Python dependencies — only stdlib + PySide6
- New firmware C files must be added to `AIX/main/CMakeLists.txt` SRCS list

---

## Task 1: Firmware — vision_detect data structure and parser

**Covers:** README §"规划中：vision_detect", §"ESP32-S3 视觉处理层"

**Files:**
- Create: `AIX/main/vision_detect.h`
- Create: `AIX/main/vision_detect.c`
- Create: `AIX/test/vision_detect_parse_test.c`

**Interfaces:**
- Produces: `vision_detect_object_t`, `vision_detect_result_t`, `vision_detect_parse_line()`

- [ ] **Step 1: Create vision_detect.h**

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char class_name[32];
    float confidence;
    int16_t bbox_x;
    int16_t bbox_y;
    int16_t bbox_w;
    int16_t bbox_h;
    float distance_m;
    bool approaching;
} vision_detect_object_t;

typedef struct {
    uint32_t seq;
    uint32_t ts_ms;
    char source[32];
    vision_detect_object_t objects[8];
    int object_count;
    float nearest_distance_m;
    float ttc_s;
    bool valid;
} vision_detect_result_t;

bool vision_detect_parse_line(const char *line, vision_detect_result_t *out);

#ifdef __cplusplus
}
#endif
```

- [ ] **Step 2: Create vision_detect.c (pure-function parser)**

The parser must handle the JSON format from README. Use simple string scanning (same pattern as `vision_input.c`) to avoid JSON library dependency. Parse `type`, `seq`, `ts_ms`, `source`, `objects[]`, `nearest_distance_m`, `ttc_s`, `valid`.

```c
#include "vision_detect.h"

#include <stdlib.h>
#include <string.h>

static const char *find_key(const char *line, const char *key)
{
    const char *cursor = line;
    while ((cursor = strstr(cursor, key)) != NULL) {
        const char *after = cursor + strlen(key);
        if (*after == ':' || *after == ' ') {
            return after;
        }
        cursor = after;
    }
    return NULL;
}

static bool parse_u32(const char *line, const char *key, uint32_t *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    char *end = NULL;
    unsigned long v = strtoul(val, &end, 10);
    if (end == val) return false;
    *out = (uint32_t)v;
    return true;
}

static bool parse_float(const char *line, const char *key, float *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    char *end = NULL;
    float v = strtof(val, &end);
    if (end == val) return false;
    *out = v;
    return true;
}

static bool parse_bool(const char *line, const char *key, bool *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    if (strncmp(val, "true", 4) == 0) { *out = true; return true; }
    if (strncmp(val, "false", 5) == 0) { *out = false; return true; }
    if (*val == '1') { *out = true; return true; }
    if (*val == '0') { *out = false; return true; }
    return false;
}

bool vision_detect_parse_line(const char *line, vision_detect_result_t *out)
{
    if (!line || !out) return false;
    if (strstr(line, "\"vision_detect\"") == NULL) return false;

    memset(out, 0, sizeof(*out));
    if (!parse_u32(line, "\"seq\"", &out->seq)) return false;
    if (!parse_u32(line, "\"ts_ms\"", &out->ts_ms)) return false;
    if (!parse_float(line, "\"nearest_distance_m\"", &out->nearest_distance_m)) return false;
    if (!parse_float(line, "\"ttc_s\"", &out->ttc_s)) return false;
    if (!parse_bool(line, "\"valid\"", &out->valid)) return false;

    /* Parse source if present */
    const char *src = find_key(line, "\"source\"");
    if (src) {
        while (*src == ':' || *src == ' ') src++;
        if (*src == '"') {
            src++;
            int i = 0;
            while (*src && *src != '"' && i < 31) {
                out->source[i++] = *src++;
            }
            out->source[i] = '\0';
        }
    }

    /* Parse first object's class and distance if present */
    const char *cls = find_key(line, "\"class\"");
    if (cls) {
        while (*cls == ':' || *cls == ' ') cls++;
        if (*cls == '"') {
            cls++;
            int i = 0;
            while (*cls && *cls != '"' && i < 31) {
                out->objects[0].class_name[i++] = *cls++;
            }
            out->objects[0].class_name[i] = '\0';
            out->object_count = 1;
        }
        parse_float(line, "\"confidence\"", &out->objects[0].confidence);
        parse_float(line, "\"distance_m\"", &out->objects[0].distance_m);
        parse_bool(line, "\"approaching\"", &out->objects[0].approaching);
    }

    return true;
}
```

- [ ] **Step 3: Write the test**

```c
#include <stdio.h>
#include <string.h>
#include "../main/vision_detect.h"

int main(void)
{
    int failures = 0;

    /* Test: valid vision_detect line */
    const char *line1 =
        "{\"type\":\"vision_detect\",\"version\":1,\"seq\":42,\"ts_ms\":50000,"
        "\"source\":\"ov5640\",\"objects\":[{\"class\":\"truck\",\"confidence\":0.82,"
        "\"bbox\":[78,42,65,48],\"distance_m\":5.2,\"approaching\":true}],"
        "\"nearest_distance_m\":5.2,\"ttc_s\":4.1,\"valid\":true}";

    vision_detect_result_t r1 = {0};
    if (!vision_detect_parse_line(line1, &r1)) {
        printf("FAIL: parse valid line returned false\n");
        failures++;
    } else {
        if (r1.seq != 42) { printf("FAIL: seq=%lu expected 42\n", (unsigned long)r1.seq); failures++; }
        if (r1.ts_ms != 50000) { printf("FAIL: ts_ms=%lu expected 50000\n", (unsigned long)r1.ts_ms); failures++; }
        if (r1.nearest_distance_m < 5.1f || r1.nearest_distance_m > 5.3f) {
            printf("FAIL: nearest_distance_m=%.1f expected 5.2\n", r1.nearest_distance_m); failures++;
        }
        if (r1.ttc_s < 4.0f || r1.ttc_s > 4.2f) {
            printf("FAIL: ttc_s=%.1f expected 4.1\n", r1.ttc_s); failures++;
        }
        if (!r1.valid) { printf("FAIL: valid=false expected true\n"); failures++; }
        if (r1.object_count != 1) { printf("FAIL: object_count=%d expected 1\n", r1.object_count); failures++; }
        if (strcmp(r1.objects[0].class_name, "truck") != 0) {
            printf("FAIL: class='%s' expected 'truck'\n", r1.objects[0].class_name); failures++;
        }
    }

    /* Test: non-vision_detect line returns false */
    const char *line2 = "{\"type\":\"pressure\",\"version\":1,\"seq\":1}";
    vision_detect_result_t r2 = {0};
    if (vision_detect_parse_line(line2, &r2)) {
        printf("FAIL: non-vision_detect line parsed as vision_detect\n");
        failures++;
    }

    /* Test: missing valid field returns false */
    const char *line3 =
        "{\"type\":\"vision_detect\",\"version\":1,\"seq\":1,\"ts_ms\":1000,"
        "\"nearest_distance_m\":3.0,\"ttc_s\":2.0}";
    vision_detect_result_t r3 = {0};
    if (vision_detect_parse_line(line3, &r3)) {
        printf("FAIL: missing valid parsed successfully\n");
        failures++;
    }

    /* Test: NULL inputs return false */
    if (vision_detect_parse_line(NULL, &r1)) {
        printf("FAIL: NULL line parsed\n");
        failures++;
    }
    if (vision_detect_parse_line(line1, NULL)) {
        printf("FAIL: NULL out parsed\n");
        failures++;
    }

    if (failures == 0) {
        printf("vision_detect_parse_test: ALL PASSED\n");
    }
    return failures;
}
```

- [ ] **Step 4: Compile and run the test on host**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
gcc -o test\vision_detect_parse_test.exe main\vision_detect.c test\vision_detect_parse_test.c -I main -Wall -Wextra
.\test\vision_detect_parse_test.exe
```

Expected: `vision_detect_parse_test: ALL PASSED`

- [ ] **Step 5: Add vision_detect.c to CMakeLists.txt**

Edit `AIX/main/CMakeLists.txt` line 1 to add `vision_detect.c`:

```
idf_component_register(SRCS "main.c" "pressure_sensor.c" "vision_input.c" "vision_detect.c" "config_input.c" "risk_fusion.c" "airbag_control.c"
                    INCLUDE_DIRS ".")
```

- [ ] **Step 6: Commit**

```bash
git add AIX/main/vision_detect.h AIX/main/vision_detect.c AIX/test/vision_detect_parse_test.c AIX/main/CMakeLists.txt
git commit -m "feat(firmware): add vision_detect data structure and JSON parser"
```

---

## Task 2: Firmware — distance_estimator pure function

**Covers:** README §"单目距离估计", §"ESP32-S3 视觉处理层 → distance_estimator"

**Files:**
- Create: `AIX/main/distance_estimator.h`
- Create: `AIX/main/distance_estimator.c`
- Create: `AIX/test/distance_estimator_test.c`

**Interfaces:**
- Produces: `distance_estimator_estimate()` — takes bbox_w pixels, focal_length_px, known_object_width_m → returns distance_m; `distance_estimator_approaching()` — compares current vs previous distance, returns true if decreasing

- [ ] **Step 1: Create distance_estimator.h**

```c
#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

float distance_estimator_estimate(int bbox_w_px, float focal_length_px, float known_width_m);
bool distance_estimator_approaching(float prev_distance_m, float curr_distance_m, float threshold);
float distance_estimator_ttc(float distance_m, float approach_speed_mps);

#ifdef __cplusplus
}
#endif
```

- [ ] **Step 2: Create distance_estimator.c**

```c
#include "distance_estimator.h"

float distance_estimator_estimate(int bbox_w_px, float focal_length_px, float known_width_m)
{
    if (bbox_w_px <= 0 || focal_length_px <= 0.0f || known_width_m <= 0.0f) {
        return -1.0f;
    }
    return (known_width_m * focal_length_px) / (float)bbox_w_px;
}

bool distance_estimator_approaching(float prev_distance_m, float curr_distance_m, float threshold)
{
    if (prev_distance_m < 0.0f || curr_distance_m < 0.0f) {
        return false;
    }
    return (prev_distance_m - curr_distance_m) > threshold;
}

float distance_estimator_ttc(float distance_m, float approach_speed_mps)
{
    if (distance_m <= 0.0f || approach_speed_mps <= 0.0f) {
        return -1.0f;
    }
    return distance_m / approach_speed_mps;
}
```

- [ ] **Step 3: Write the test**

```c
#include <stdio.h>
#include "../main/distance_estimator.h"

int main(void)
{
    int failures = 0;

    /* Test: normal estimation — a 1.8m wide truck at 50px bbox with 800px focal */
    float d = distance_estimator_estimate(50, 800.0f, 1.8f);
    if (d < 28.5f || d > 29.0f) {
        printf("FAIL: estimate=%.1f expected ~28.8\n", d); failures++;
    }

    /* Test: zero bbox returns -1 */
    d = distance_estimator_estimate(0, 800.0f, 1.8f);
    if (d >= 0.0f) {
        printf("FAIL: zero bbox should return negative, got %.1f\n", d); failures++;
    }

    /* Test: approaching detection */
    if (!distance_estimator_approaching(10.0f, 8.0f, 0.5f)) {
        printf("FAIL: should detect approaching 10->8\n"); failures++;
    }
    if (distance_estimator_approaching(10.0f, 9.8f, 0.5f)) {
        printf("FAIL: should not detect approaching 10->9.8 (threshold 0.5)\n"); failures++;
    }
    if (distance_estimator_approaching(-1.0f, 5.0f, 0.5f)) {
        printf("FAIL: negative prev should return false\n"); failures++;
    }

    /* Test: TTC */
    float ttc = distance_estimator_ttc(20.0f, 5.0f);
    if (ttc < 3.9f || ttc > 4.1f) {
        printf("FAIL: ttc=%.1f expected 4.0\n", ttc); failures++;
    }
    ttc = distance_estimator_ttc(0.0f, 5.0f);
    if (ttc >= 0.0f) {
        printf("FAIL: zero distance TTC should return negative\n"); failures++;
    }

    if (failures == 0) {
        printf("distance_estimator_test: ALL PASSED\n");
    }
    return failures;
}
```

- [ ] **Step 4: Compile and run the test**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
gcc -o test\distance_estimator_test.exe main\distance_estimator.c test\distance_estimator_test.c -I main -Wall -Wextra
.\test\distance_estimator_test.exe
```

Expected: `distance_estimator_test: ALL PASSED`

- [ ] **Step 5: Add distance_estimator.c to CMakeLists.txt**

Edit `AIX/main/CMakeLists.txt` SRCS to add `distance_estimator.c`:

```
idf_component_register(SRCS "main.c" "pressure_sensor.c" "vision_input.c" "vision_detect.c" "distance_estimator.c" "config_input.c" "risk_fusion.c" "airbag_control.c"
                    INCLUDE_DIRS ".")
```

- [ ] **Step 6: Commit**

```bash
git add AIX/main/distance_estimator.h AIX/main/distance_estimator.c AIX/test/distance_estimator_test.c AIX/main/CMakeLists.txt
git commit -m "feat(firmware): add distance_estimator pure function for single-camera ranging"
```

---

## Task 3: Firmware — voice_prompt stub

**Covers:** README §"语音播报", §"ESP32-S3 决策与执行层 → voice_prompt"

**Files:**
- Create: `AIX/main/voice_prompt.h`
- Create: `AIX/main/voice_prompt.c`

**Interfaces:**
- Produces: `voice_prompt_say(const char *text)` — prints voice JSON event to stdout on ESP32, pure function on host

- [ ] **Step 1: Create voice_prompt.h**

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms);

#ifdef __cplusplus
}
#endif
```

- [ ] **Step 2: Create voice_prompt.c**

```c
#include "voice_prompt.h"

#include <stdio.h>
#include <string.h>

bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms)
{
    if (text == NULL || text[0] == '\0') {
        return false;
    }
    printf("{\"type\":\"voice\",\"version\":1,\"seq\":%lu,\"ts_ms\":%lu,"
           "\"text\":\"%s\",\"played\":true}\n",
           (unsigned long)seq, (unsigned long)ts_ms, text);
    fflush(stdout);
    return true;
}
```

- [ ] **Step 3: Add voice_prompt.c to CMakeLists.txt**

Edit `AIX/main/CMakeLists.txt` SRCS to add `voice_prompt.c`:

```
idf_component_register(SRCS "main.c" "pressure_sensor.c" "vision_input.c" "vision_detect.c" "distance_estimator.c" "voice_prompt.c" "config_input.c" "risk_fusion.c" "airbag_control.c"
                    INCLUDE_DIRS ".")
```

- [ ] **Step 4: Commit**

```bash
git add AIX/main/voice_prompt.h AIX/main/voice_prompt.c AIX/main/CMakeLists.txt
git commit -m "feat(firmware): add voice_prompt stub that prints voice JSON events"
```

---

## Task 4: Firmware — risk_fusion v2 path

**Covers:** README §"规划中：risk v2", §"ESP32-S3 决策与执行层 → risk_fusion"

**Files:**
- Modify: `AIX/main/risk_fusion.h` — add `risk_fusion_result_v2_t`, `risk_fusion_evaluate_v2()`
- Modify: `AIX/main/risk_fusion.c` — add v2 evaluation logic, update task to print v2 format
- Modify: `AIX/test/risk_fusion_test.c` — add v2 test cases

**Interfaces:**
- Consumes: `vision_detect_result_t` from Task 1
- Produces: `risk_fusion_result_v2_t` with `category`, `nearest_class`, `nearest_distance_m`, `ttc_s`

- [ ] **Step 1: Add v2 types to risk_fusion.h**

Add after existing types (keep existing v1 types untouched):

```c
typedef struct {
    int level;
    int target_pct;
    const char *reason;
    const char *category;
    const char *nearest_class;
    float nearest_distance_m;
    float ttc_s;
    bool pressure_safe;
    const char *pressure_state;
} risk_fusion_result_v2_t;

risk_fusion_result_v2_t risk_fusion_evaluate_v2(const vision_detect_result_t *detect,
                                                  bool pressure_enabled,
                                                  bool pressure_safe);
```

Add `#include "vision_detect.h"` at the top of the header.

- [ ] **Step 2: Implement v2 logic in risk_fusion.c**

Add the v2 evaluation function. Rules from README:
- pressure invalid or over_pressure → category="safety_stop", target_pct=0
- ttc_s < 3.0 → critical (100%)
- nearest_distance_m < 5.0 → warning (40%)
- nearest_distance_m < 15.0 → caution (20%)
- else → normal (10%)

```c
risk_fusion_result_v2_t risk_fusion_evaluate_v2(const vision_detect_result_t *detect,
                                                  bool pressure_enabled,
                                                  bool pressure_safe)
{
    risk_fusion_result_v2_t result = {0};
    result.pressure_state = pressure_state_name(pressure_enabled, pressure_safe);

    const bool effective_safe = !pressure_enabled || pressure_safe;
    result.pressure_safe = effective_safe;

    if (!effective_safe) {
        result.level = 100;
        result.target_pct = 0;
        result.reason = "pressure_unsafe";
        result.category = "safety_stop";
        return result;
    }

    if (detect == NULL || !detect->valid || detect->object_count == 0) {
        result.level = 10;
        result.target_pct = 10;
        result.reason = "no_target";
        result.category = "normal";
        result.nearest_distance_m = -1.0f;
        result.ttc_s = -1.0f;
        return result;
    }

    result.nearest_distance_m = detect->nearest_distance_m;
    result.ttc_s = detect->ttc_s;
    if (detect->object_count > 0) {
        result.nearest_class = detect->objects[0].class_name;
    }

    if (detect->ttc_s >= 0.0f && detect->ttc_s < 3.0f) {
        result.level = 100;
        result.target_pct = 100;
        result.category = "critical";
        result.reason = "ttc_critical";
    } else if (detect->nearest_distance_m >= 0.0f && detect->nearest_distance_m < 5.0f) {
        result.level = 40;
        result.target_pct = 40;
        result.category = "vision_warning";
        result.reason = "target_close";
    } else if (detect->nearest_distance_m >= 0.0f && detect->nearest_distance_m < 15.0f) {
        result.level = 20;
        result.target_pct = 20;
        result.category = "vision_caution";
        result.reason = "target_approaching";
    } else {
        result.level = 10;
        result.target_pct = 10;
        result.category = "normal";
        result.reason = "target_far";
    }

    return result;
}
```

- [ ] **Step 3: Update risk_fusion_task to emit v2 format when vision_detect is available**

In `risk_fusion_task()`, add logic to check for vision_detect data and emit v2 format. Keep v1 fallback when no vision_detect data is present. The task should:
1. Check for vision_detect snapshot (new module, similar pattern to vision_input)
2. If available, use `risk_fusion_evaluate_v2()` and print v2 JSON
3. If not available, fall back to existing v1 logic

This requires a `vision_detect` snapshot module. For the MVP, create a minimal `vision_detect_input.c/h` that works like `vision_input.c` — reads from stdin, stores latest snapshot. The simulated vision_detect task (Task 5) will feed into this.

*Note: Task 5 creates the simulated source. For now, add the v2 print path that uses vision_detect data when available. The task code will be refined in Task 5.*

- [ ] **Step 4: Add v2 tests to risk_fusion_test.c**

Add after existing tests:

```c
/* === v2 tests === */
#include "../main/vision_detect.h"

static int expect_v2(const char *name,
                     float nearest_distance,
                     float ttc,
                     bool valid,
                     int obj_count,
                     bool pressure_enabled,
                     bool pressure_safe,
                     int expected_level,
                     int expected_target,
                     const char *expected_category)
{
    vision_detect_result_t detect = {0};
    detect.valid = valid;
    detect.nearest_distance_m = nearest_distance;
    detect.ttc_s = ttc;
    detect.object_count = obj_count;
    if (obj_count > 0) {
        strncpy(detect.objects[0].class_name, "truck", 31);
    }

    risk_fusion_result_v2_t result = risk_fusion_evaluate_v2(
        &detect, pressure_enabled, pressure_safe);

    int ok = 1;
    if (result.level != expected_level || result.target_pct != expected_target) {
        printf("%s: level=%d target=%d expected=%d/%d reason=%s\n",
               name, result.level, result.target_pct,
               expected_level, expected_target, result.reason);
        ok = 0;
    }
    if (expected_category && result.category &&
        strcmp(result.category, expected_category) != 0) {
        printf("%s: category='%s' expected '%s'\n",
               name, result.category, expected_category);
        ok = 0;
    }
    return ok ? 0 : 1;
}
```

Add test calls in `main()`:

```c
failures += expect_v2("v2 no target", -1, -1, true, 0, true, true, 10, 10, "normal");
failures += expect_v2("v2 far target", 20.0f, 10.0f, true, 1, true, true, 10, 10, "normal");
failures += expect_v2("v2 approaching", 10.0f, 6.0f, true, 1, true, true, 20, 20, "vision_caution");
failures += expect_v2("v2 close", 3.0f, 5.0f, true, 1, true, true, 40, 40, "vision_warning");
failures += expect_v2("v2 ttc critical", 8.0f, 2.0f, true, 1, true, true, 100, 100, "critical");
failures += expect_v2("v2 pressure unsafe", 10.0f, 6.0f, true, 1, true, false, 100, 0, "safety_stop");
```

- [ ] **Step 5: Compile and run updated test**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
gcc -o test\risk_fusion_test.exe main\risk_fusion.c main\vision_detect.c test\risk_fusion_test.c -I main -Wall -Wextra -lm
.\test\risk_fusion_test.exe
```

Expected: all existing + new tests pass.

- [ ] **Step 6: Commit**

```bash
git add AIX/main/risk_fusion.h AIX/main/risk_fusion.c AIX/test/risk_fusion_test.c
git commit -m "feat(firmware): add risk_fusion v2 path for vision_detect + pressure"
```

---

## Task 5: Firmware — simulated vision_detect generator task

**Covers:** README §"演示验收：无需摄像头", §"ESP32-S3 视觉处理层"

**Files:**
- Create: `AIX/main/vision_detect_input.h`
- Create: `AIX/main/vision_detect_input.c`
- Modify: `AIX/main/main.c` — start vision_detect_input task

**Interfaces:**
- Produces: `vision_detect_input_get_snapshot()`, simulated vision_detect JSON output on stdout

- [ ] **Step 1: Create vision_detect_input.h**

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "vision_detect.h"

#ifdef __cplusplus
extern "C" {
#endif

bool vision_detect_input_get_snapshot(vision_detect_result_t *out);

#ifdef ESP_PLATFORM
#include "esp_err.h"
esp_err_t vision_detect_input_start_task(void);
#endif

#ifdef __cplusplus
}
#endif
```

- [ ] **Step 2: Create vision_detect_input.c with simulated scenario**

The simulated task cycles through a demo scenario:
1. Object far (20m), slowly approaching
2. Object gets closer (10m, 5m, 3m)
3. TTC drops below 3s → critical
4. Reset and repeat

On ESP32, this runs as a FreeRTOS task. On host (test), only the pure-function parts are used.

```c
#include "vision_detect_input.h"

#include <stdio.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#define VISION_DETECT_TASK_STACK 4096
#define VISION_DETECT_TASK_PRIORITY 5
#define VISION_DETECT_PERIOD_MS 200

static const char *TAG = "AIX_VISION_DET";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static vision_detect_result_t s_latest;
static bool s_has_data;
static bool s_task_started;

bool vision_detect_input_get_snapshot(vision_detect_result_t *out)
{
    if (!out) return false;
    taskENTER_CRITICAL(&s_lock);
    bool ok = s_has_data;
    if (ok) *out = s_latest;
    taskEXIT_CRITICAL(&s_lock);
    return ok;
}

static void vision_detect_sim_task(void *arg)
{
    (void)arg;
    uint32_t seq = 0;
    float distance = 25.0f;
    const float approach_speed = 0.8f;  /* m per cycle */
    const float cycle_period = VISION_DETECT_PERIOD_MS / 1000.0f;

    while (1) {
        const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);
        seq++;

        /* Simulate approach */
        distance -= approach_speed * cycle_period;
        if (distance < 1.0f) {
            distance = 25.0f;  /* reset */
        }

        const float ttc = (approach_speed > 0.0f) ? distance / approach_speed : -1.0f;

        printf("{\"type\":\"vision_detect\",\"version\":1,\"seq\":%lu,\"ts_ms\":%lu,"
               "\"source\":\"simulated\",\"objects\":[{\"class\":\"truck\","
               "\"confidence\":0.85,\"bbox\":[100,60,80,60],\"distance_m\":%.1f,"
               "\"approaching\":true}],\"nearest_distance_m\":%.1f,"
               "\"ttc_s\":%.1f,\"valid\":true}\n",
               (unsigned long)seq, (unsigned long)now_ms,
               distance, distance, ttc);
        fflush(stdout);

        vision_detect_result_t snap = {0};
        snap.seq = seq;
        snap.ts_ms = now_ms;
        strncpy(snap.source, "simulated", 31);
        snap.valid = true;
        snap.nearest_distance_m = distance;
        snap.ttc_s = ttc;
        snap.object_count = 1;
        strncpy(snap.objects[0].class_name, "truck", 31);
        snap.objects[0].confidence = 0.85f;
        snap.objects[0].distance_m = distance;
        snap.objects[0].approaching = true;

        taskENTER_CRITICAL(&s_lock);
        s_latest = snap;
        s_has_data = true;
        taskEXIT_CRITICAL(&s_lock);

        vTaskDelay(pdMS_TO_TICKS(VISION_DETECT_PERIOD_MS));
    }
}

esp_err_t vision_detect_input_start_task(void)
{
    if (s_task_started) return ESP_OK;
    BaseType_t ok = xTaskCreate(vision_detect_sim_task, "vision_det",
                                VISION_DETECT_TASK_STACK, NULL,
                                VISION_DETECT_TASK_PRIORITY, NULL);
    if (ok != pdPASS) return ESP_ERR_NO_MEM;
    s_task_started = true;
    ESP_LOGI(TAG, "simulated vision_detect task started");
    return ESP_OK;
}
#else
/* Host stub: no snapshot available without ESP platform */
bool vision_detect_input_get_snapshot(vision_detect_result_t *out)
{
    (void)out;
    return false;
}
#endif
```

- [ ] **Step 3: Update main.c to start the task**

Add after `risk_fusion_start_task()`:

```c
#include "vision_detect_input.h"

/* In app_main, after risk_fusion_start_task(): */
ret = vision_detect_input_start_task();
if (ret != ESP_OK) {
    ESP_LOGE(TAG, "vision detect input task start failed: %s", esp_err_to_name(ret));
}
```

- [ ] **Step 4: Add vision_detect_input.c to CMakeLists.txt**

```
idf_component_register(SRCS "main.c" "pressure_sensor.c" "vision_input.c" "vision_detect.c" "distance_estimator.c" "voice_prompt.c" "vision_detect_input.c" "config_input.c" "risk_fusion.c" "airbag_control.c"
                    INCLUDE_DIRS ".")
```

- [ ] **Step 5: Commit**

```bash
git add AIX/main/vision_detect_input.h AIX/main/vision_detect_input.c AIX/main/main.c AIX/main/CMakeLists.txt
git commit -m "feat(firmware): add simulated vision_detect generator task"
```

---

## Task 6: Host app — add VisionDetect and Voice models

**Covers:** README §"规划中：vision_detect", §"规划中：voice"

**Files:**
- Modify: `host_app/aix_host_app/models.py` — add `VisionDetectObject`, `VisionDetectEvent`, `VoiceEvent`
- Modify: `host_app/aix_host_app/parsers.py` — add parsing for `vision_detect` and `voice` event types

**Interfaces:**
- Consumes: JSON lines matching README formats
- Produces: `VisionDetectEvent`, `VoiceEvent` dataclasses

- [ ] **Step 1: Add models**

Append to `models.py`:

```python
@dataclass(frozen=True)
class VisionDetectObject:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    distance_m: float
    approaching: bool


@dataclass(frozen=True)
class VisionDetectEvent:
    seq: int
    ts_ms: int
    source: str
    objects: tuple[VisionDetectObject, ...]
    nearest_distance_m: float
    ttc_s: float
    valid: bool


@dataclass(frozen=True)
class VoiceEvent:
    seq: int
    ts_ms: int
    text: str
    played: bool
```

- [ ] **Step 2: Update RiskEvent model for v2 fields**

Add optional v2 fields to `RiskEvent`:

```python
@dataclass(frozen=True)
class RiskEvent:
    seq: int
    ts_ms: int
    level: int
    target_pct: int
    reason: str
    vision_stale: bool
    pressure_safe: bool
    pressure_state: str = "enabled"
    version: int = 1
    category: str = ""
    nearest_class: str = ""
    nearest_distance_m: float = -1.0
    ttc_s: float = -1.0
```

- [ ] **Step 3: Add parsers for vision_detect and voice**

In `parsers.py`:

1. Add import: `from .models import ActuatorEvent, MotionEvent, PressureSample, RiskEvent, VisionDetectEvent, VisionDetectObject, VoiceEvent`

2. Add required field tuples:

```python
_VISION_DETECT_REQUIRED = ("seq", "ts_ms", "nearest_distance_m", "ttc_s", "valid")
_VOICE_REQUIRED = ("seq", "ts_ms", "text", "played")
```

3. Update `parse_event_line` to dispatch:

```python
if event_type == "vision_detect":
    return _parse_vision_detect_payload(payload)
if event_type == "voice":
    return _parse_voice_payload(payload)
```

4. Add `_parse_vision_detect_payload`:

```python
def _parse_vision_detect_payload(payload: dict[str, Any]) -> VisionDetectEvent:
    missing = [k for k in _VISION_DETECT_REQUIRED if k not in payload]
    if missing:
        raise ParseError(f"vision_detect missing fields: {', '.join(missing)}")
    objects = []
    for obj in payload.get("objects", []):
        bbox = obj.get("bbox", [0, 0, 0, 0])
        objects.append(VisionDetectObject(
            class_name=str(obj.get("class", "")),
            confidence=_as_float(obj.get("confidence", 0.0), "confidence"),
            bbox=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
            distance_m=_as_float(obj.get("distance_m", -1.0), "distance_m"),
            approaching=_as_bool(obj.get("approaching", False), "approaching"),
        ))
    return VisionDetectEvent(
        seq=_as_int(payload["seq"], "seq"),
        ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
        source=str(payload.get("source", "")),
        objects=tuple(objects),
        nearest_distance_m=_as_float(payload["nearest_distance_m"], "nearest_distance_m"),
        ttc_s=_as_float(payload["ttc_s"], "ttc_s"),
        valid=_as_bool(payload["valid"], "valid"),
    )
```

5. Add `_parse_voice_payload`:

```python
def _parse_voice_payload(payload: dict[str, Any]) -> VoiceEvent:
    missing = [k for k in _VOICE_REQUIRED if k not in payload]
    if missing:
        raise ParseError(f"voice missing fields: {', '.join(missing)}")
    return VoiceEvent(
        seq=_as_int(payload["seq"], "seq"),
        ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
        text=str(payload["text"]),
        played=_as_bool(payload["played"], "played"),
    )
```

6. Update `_parse_risk_payload` to handle v2 fields:

```python
def _parse_risk_payload(payload: dict[str, Any]) -> RiskEvent:
    missing = [key for key in _RISK_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"risk json missing fields: {', '.join(missing)}")
    version = _as_int(payload.get("version", 1), "version")
    return RiskEvent(
        seq=_as_int(payload["seq"], "seq"),
        ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
        level=_as_int(payload["level"], "level"),
        target_pct=_as_int(payload["target_pct"], "target_pct"),
        reason=str(payload["reason"]),
        vision_stale=_as_bool(payload["vision_stale"], "vision_stale"),
        pressure_safe=_as_bool(payload["pressure_safe"], "pressure_safe"),
        pressure_state=str(payload.get("pressure_state", "enabled")),
        version=version,
        category=str(payload.get("category", "")),
        nearest_class=str(payload.get("nearest_class", "")),
        nearest_distance_m=_as_float(payload.get("nearest_distance_m", -1.0), "nearest_distance_m"),
        ttc_s=_as_float(payload.get("ttc_s", -1.0), "ttc_s"),
    )
```

7. Update `parse_event_line` return type annotation:

```python
def parse_event_line(line: str) -> PressureSample | RiskEvent | ActuatorEvent | MotionEvent | VisionDetectEvent | VoiceEvent:
```

- [ ] **Step 4: Commit**

```bash
git add host_app/aix_host_app/models.py host_app/aix_host_app/parsers.py
git commit -m "feat(host_app): add VisionDetectEvent, VoiceEvent models and parsers"
```

---

## Task 7: Host app — tests for vision_detect and voice parsing

**Covers:** README §"上位机测试"

**Files:**
- Modify: `host_app/tests/test_parsers.py` — add test cases

**Interfaces:**
- Consumes: `parse_event_line` from Task 6
- Produces: passing tests

- [ ] **Step 1: Add test cases**

Append to `test_parsers.py`:

```python
class VisionDetectParserTests(unittest.TestCase):
    def test_parses_vision_detect_event(self):
        line = (
            '{"type":"vision_detect","version":1,"seq":42,"ts_ms":50000,'
            '"source":"simulated","objects":[{"class":"truck","confidence":0.82,'
            '"bbox":[78,42,65,48],"distance_m":5.2,"approaching":true}],'
            '"nearest_distance_m":5.2,"ttc_s":4.1,"valid":true}'
        )
        from aix_host_app.models import VisionDetectEvent
        event = parse_event_line(line)
        self.assertIsInstance(event, VisionDetectEvent)
        self.assertEqual(event.seq, 42)
        self.assertEqual(event.source, "simulated")
        self.assertEqual(len(event.objects), 1)
        self.assertEqual(event.objects[0].class_name, "truck")
        self.assertAlmostEqual(event.objects[0].distance_m, 5.2)
        self.assertTrue(event.objects[0].approaching)
        self.assertAlmostEqual(event.nearest_distance_m, 5.2)
        self.assertAlmostEqual(event.ttc_s, 4.1)
        self.assertTrue(event.valid)

    def test_parses_vision_detect_no_objects(self):
        line = (
            '{"type":"vision_detect","version":1,"seq":1,"ts_ms":1000,'
            '"source":"sim","objects":[],'
            '"nearest_distance_m":-1,"ttc_s":-1,"valid":true}'
        )
        from aix_host_app.models import VisionDetectEvent
        event = parse_event_line(line)
        self.assertIsInstance(event, VisionDetectEvent)
        self.assertEqual(len(event.objects), 0)

    def test_rejects_vision_detect_missing_fields(self):
        with self.assertRaises(ParseError):
            parse_event_line('{"type":"vision_detect","version":1,"seq":1}')

    def test_rejects_vision_detect_invalid_json(self):
        with self.assertRaises(ParseError):
            parse_event_line('{"type":"vision_detect",bad json')


class VoiceParserTests(unittest.TestCase):
    def test_parses_voice_event(self):
        line = (
            '{"type":"voice","version":1,"seq":43,"ts_ms":50030,'
            '"text":"前方大货车接近，请减速","played":true}'
        )
        from aix_host_app.models import VoiceEvent
        event = parse_event_line(line)
        self.assertIsInstance(event, VoiceEvent)
        self.assertEqual(event.seq, 43)
        self.assertEqual(event.text, "前方大货车接近，请减速")
        self.assertTrue(event.played)

    def test_rejects_voice_missing_text(self):
        with self.assertRaises(ParseError):
            parse_event_line('{"type":"voice","version":1,"seq":1,"ts_ms":1000,"played":true}')


class RiskV2ParserTests(unittest.TestCase):
    def test_parses_risk_v2_event(self):
        line = (
            '{"type":"risk","version":2,"seq":43,"ts_ms":50020,'
            '"level":40,"target_pct":40,"reason":"target_close",'
            '"category":"vision_warning","nearest_class":"truck",'
            '"nearest_distance_m":5.2,"ttc_s":4.1,'
            '"pressure_safe":true,"pressure_state":"safe"}'
        )
        event = parse_event_line(line)
        self.assertIsInstance(event, RiskEvent)
        self.assertEqual(event.version, 2)
        self.assertEqual(event.category, "vision_warning")
        self.assertEqual(event.nearest_class, "truck")
        self.assertAlmostEqual(event.nearest_distance_m, 5.2)
        self.assertAlmostEqual(event.ttc_s, 4.1)

    def test_parses_risk_v1_backward_compat(self):
        line = (
            '{"type":"risk","version":1,"seq":35,"ts_ms":43100,'
            '"level":80,"target_pct":80,"reason":"vision_looming",'
            '"vision_stale":false,"pressure_safe":true}'
        )
        event = parse_event_line(line)
        self.assertIsInstance(event, RiskEvent)
        self.assertEqual(event.version, 1)
        self.assertEqual(event.category, "")
```

- [ ] **Step 2: Run all host app tests**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\python.exe -m unittest discover -s host_app\tests -v
```

Expected: all tests pass including new ones.

- [ ] **Step 3: Compile check**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\python.exe -m compileall -q host_app\aix_host_app host_app\tests
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add host_app/tests/test_parsers.py
git commit -m "test(host_app): add vision_detect, voice, and risk v2 parser tests"
```

---

## Task 8: Host app — VisionPanel update for vision_detect display

**Covers:** README §"上位机同步展示目标类别、bbox、距离、TTC"

**Files:**
- Modify: `host_app/aix_host_app/widgets/vision_panel.py`

**Interfaces:**
- Consumes: `VisionDetectEvent` from Task 6

- [ ] **Step 1: Read current vision_panel.py and update it**

The vision panel should display:
- Object class labels and confidence
- Distance and TTC
- Bounding box info
- Source

Add a new method `update_vision_detect(event: VisionDetectEvent)` that shows the structured detection results.

- [ ] **Step 2: Update app.py to route vision_detect events to the panel**

In `app.py`, when a `VisionDetectEvent` is parsed, call `vision_panel.update_vision_detect(event)`.

- [ ] **Step 3: Commit**

```bash
git add host_app/aix_host_app/widgets/vision_panel.py host_app/aix_host_app/app.py
git commit -m "feat(host_app): update vision panel to display vision_detect events"
```

---

## Task 9: Host app — risk v2 display in sensor overview

**Covers:** README §"上位机同步展示风险和气囊目标"

**Files:**
- Modify: `host_app/aix_host_app/widgets/sensor_overview_panel.py` or `risk` widget

**Interfaces:**
- Consumes: `RiskEvent` with v2 fields

- [ ] **Step 1: Add v2 category display**

When `risk_event.version == 2`, display the `category`, `nearest_class`, `nearest_distance_m`, and `ttc_s` fields alongside existing level/target_pct.

- [ ] **Step 2: Commit**

```bash
git add host_app/aix_host_app/widgets/
git commit -m "feat(host_app): display risk v2 category and vision details"
```

---

## Task 10: Integration verification

**Covers:** README §"验证命令", §"演示验收"

**Files:** None (verification only)

- [ ] **Step 1: Run all host app tests**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\python.exe -m unittest discover -s host_app\tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Compile check**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\python.exe -m compileall -q host_app\aix_host_app host_app\tests
```

Expected: no errors.

- [ ] **Step 3: Compile all firmware tests on host**

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
gcc -o test\vision_detect_parse_test.exe main\vision_detect.c test\vision_detect_parse_test.c -I main -Wall -Wextra
.\test\vision_detect_parse_test.exe

gcc -o test\distance_estimator_test.exe main\distance_estimator.c test\distance_estimator_test.c -I main -Wall -Wextra
.\test\distance_estimator_test.exe

gcc -o test\risk_fusion_test.exe main\risk_fusion.c main\vision_detect.c test\risk_fusion_test.c -I main -Wall -Wextra -lm
.\test\risk_fusion_test.exe
```

Expected: all tests pass.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: integration verification for vision_detect protocol closure"
```
