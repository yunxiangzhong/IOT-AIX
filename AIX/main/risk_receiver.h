#pragma once

#include <stdbool.h>

bool risk_receiver_token_matches(const char *expected, const char *provided);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t risk_receiver_start(void);
#endif
