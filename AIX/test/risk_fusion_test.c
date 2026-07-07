#include <stdio.h>

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

    return failures;
}

