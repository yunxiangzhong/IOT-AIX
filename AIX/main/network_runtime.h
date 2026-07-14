#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef ESP_PLATFORM
#include "esp_err.h"

typedef void (*network_runtime_status_callback_t)(bool connected, void *context);

esp_err_t network_runtime_start(void);
bool network_runtime_wait_connected(uint32_t timeout_ms);
bool network_runtime_is_connected(void);
void network_runtime_set_status_callback(network_runtime_status_callback_t callback, void *context);
#endif
