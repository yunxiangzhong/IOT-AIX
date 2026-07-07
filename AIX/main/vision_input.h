#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t seq;
    uint32_t ts_ms;
    uint32_t received_ms;
    float looming;
    float area_rate;
    float center_motion;
    float confidence;
    bool valid;
    bool stale;
} vision_input_snapshot_t;

bool vision_input_parse_line(const char *line, vision_input_snapshot_t *out);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t vision_input_start_task(void);
bool vision_input_get_snapshot(vision_input_snapshot_t *out);
#endif

#ifdef __cplusplus
}
#endif
