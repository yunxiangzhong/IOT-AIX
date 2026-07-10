#pragma once

#include <stdbool.h>

#include "vision_detect.h"
#include "vision_input.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int level;
    int target_pct;
    const char *reason;
    bool vision_stale;
    bool pressure_safe;
    const char *pressure_state;
} risk_fusion_result_t;

risk_fusion_result_t risk_fusion_evaluate(const vision_input_snapshot_t *vision,
                                          bool pressure_safe);
risk_fusion_result_t risk_fusion_evaluate_with_pressure(const vision_input_snapshot_t *vision,
                                                        bool pressure_enabled,
                                                        bool pressure_safe);

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

bool risk_fusion_should_use_v2(bool has_detect,
                               const vision_detect_result_t *detect,
                               uint32_t now_ms,
                               uint32_t stale_ms);

risk_fusion_result_t risk_fusion_v2_to_actuator_result(const risk_fusion_result_v2_t *result);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t risk_fusion_start_task(void);
#endif

#ifdef __cplusplus
}
#endif
