#pragma once

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t device_identity_init(void);
const char *device_identity_device_id(void);
const char *device_identity_boot_id(void);
#endif
