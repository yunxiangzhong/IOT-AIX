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
