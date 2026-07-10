#include <stdio.h>
#include <string.h>

#include "../main/risk_fusion.h"

static int expect_level(const char *name,
                        float looming,
                        float area_rate,
                        float confidence,
                        bool valid,
                        bool stale,
                        bool pressure_safe,
                        int expected_level,
                        int expected_target)
{
    const vision_input_snapshot_t vision = {
        .looming = looming,
        .area_rate = area_rate,
        .center_motion = looming,
        .confidence = confidence,
        .valid = valid,
        .stale = stale,
    };
    const risk_fusion_result_t result = risk_fusion_evaluate(&vision, pressure_safe);
    if (result.level != expected_level || result.target_pct != expected_target) {
        printf("%s: expected level=%d target=%d, got level=%d target=%d reason=%s\n",
               name,
               expected_level,
               expected_target,
               result.level,
               result.target_pct,
               result.reason);
        return 1;
    }
    return 0;
}

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

static int expect_v2_source(const char *name,
                            bool has_detect,
                            bool valid,
                            uint32_t received_ms,
                            uint32_t now_ms,
                            uint32_t stale_ms,
                            bool expected)
{
    vision_detect_result_t detect = {0};
    detect.valid = valid;
    detect.received_ms = received_ms;

    const bool actual = risk_fusion_should_use_v2(
        has_detect, &detect, now_ms, stale_ms);
    if (actual != expected) {
        printf("%s: selected=%d expected=%d\n", name, actual, expected);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;

    failures += expect_level("invalid vision", 0.9f, 0.9f, 0.9f, false, false, true, 0, 0);
    failures += expect_level("stale vision", 0.9f, 0.9f, 0.9f, true, true, true, 0, 0);
    failures += expect_level("weak looming", 0.26f, 0.10f, 0.60f, true, false, true, 20, 20);
    failures += expect_level("stable looming", 0.48f, 0.25f, 0.70f, true, false, true, 50, 50);
    failures += expect_level("fast looming", 0.72f, 0.42f, 0.82f, true, false, true, 80, 80);
    failures += expect_level("critical looming", 0.92f, 0.70f, 0.95f, true, false, true, 100, 100);
    failures += expect_level("pressure unsafe clamps target", 0.92f, 0.70f, 0.95f, true, false, false, 100, 0);

    const vision_input_snapshot_t disabled_pressure_vision = {
        .looming = 0.72f,
        .area_rate = 0.42f,
        .center_motion = 0.72f,
        .confidence = 0.82f,
        .valid = true,
        .stale = false,
    };
    const risk_fusion_result_t disabled_pressure = risk_fusion_evaluate_with_pressure(
        &disabled_pressure_vision,
        false,
        false);
    if (disabled_pressure.level != 80 ||
        disabled_pressure.target_pct != 80 ||
        !disabled_pressure.pressure_safe ||
        disabled_pressure.pressure_state == NULL ||
        disabled_pressure.pressure_state[0] != 'd') {
        printf("pressure disabled keeps target: level=%d target=%d safe=%d state=%s\n",
               disabled_pressure.level,
               disabled_pressure.target_pct,
               disabled_pressure.pressure_safe,
               disabled_pressure.pressure_state == NULL ? "null" : disabled_pressure.pressure_state);
        failures++;
    }

    /* v2 tests */
    failures += expect_v2("v2 no target", -1, -1, true, 0, true, true, 0, 0, "normal");
    failures += expect_v2("v2 far target", 20.0f, 10.0f, true, 1, true, true, 0, 0, "normal");
    failures += expect_v2("v2 approaching", 10.0f, 6.0f, true, 1, true, true, 20, 20, "vision_caution");
    failures += expect_v2("v2 close", 3.0f, 5.0f, true, 1, true, true, 40, 40, "vision_warning");
    failures += expect_v2("v2 ttc critical", 8.0f, 2.0f, true, 1, true, true, 100, 100, "critical");
    failures += expect_v2("v2 pressure unsafe", 10.0f, 6.0f, true, 1, true, false, 100, 0, "safety_stop");

    failures += expect_v2_source("fresh v2 selected", true, true, 1000, 1499, 500, true);
    failures += expect_v2_source("v2 expires at stale boundary", true, true, 1000, 1500, 500, false);
    failures += expect_v2_source("invalid v2 rejected", true, false, 1000, 1200, 500, false);
    failures += expect_v2_source("missing v2 rejected", false, true, 1000, 1200, 500, false);
    failures += expect_v2_source("v2 wraparound remains fresh", true, true,
                                 UINT32_MAX - 100, 100, 500, true);

    const risk_fusion_result_v2_t v2_actuator_source = {
        .level = 40,
        .target_pct = 40,
        .reason = "target_close",
        .pressure_safe = true,
        .pressure_state = "safe",
    };
    const risk_fusion_result_t v2_actuator = risk_fusion_v2_to_actuator_result(&v2_actuator_source);
    if (v2_actuator.level != 40 ||
        v2_actuator.target_pct != 40 ||
        v2_actuator.reason == NULL ||
        strcmp(v2_actuator.reason, "target_close") != 0 ||
        !v2_actuator.pressure_safe ||
        v2_actuator.vision_stale) {
        printf("v2 actuator adapter failed: level=%d target=%d reason=%s safe=%d stale=%d\n",
               v2_actuator.level,
               v2_actuator.target_pct,
               v2_actuator.reason == NULL ? "null" : v2_actuator.reason,
               v2_actuator.pressure_safe,
               v2_actuator.vision_stale);
        failures++;
    }
    return failures;
}
