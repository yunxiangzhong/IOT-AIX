#pragma once

#include "action_policy.h"

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t rgb_status_start(void);
void rgb_status_set_pattern(rgb_pattern_t pattern);
bool rgb_status_is_ready(void);
rgb_pattern_t rgb_status_get_pattern(void);
#endif
