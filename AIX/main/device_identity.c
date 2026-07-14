#include "device_identity.h"

#ifdef ESP_PLATFORM

#include <stdio.h>

#include "esp_random.h"

#ifndef CONFIG_AIX_DEVICE_ID
#define CONFIG_AIX_DEVICE_ID "aix-helmet-01"
#endif
static char s_boot_id[17];

esp_err_t device_identity_init(void)
{
    uint64_t value = ((uint64_t)esp_random() << 32U) | esp_random();
    if (snprintf(s_boot_id, sizeof(s_boot_id), "%016llx", (unsigned long long)value) != 16) {
        return ESP_FAIL;
    }
    return ESP_OK;
}

const char *device_identity_device_id(void)
{
    return CONFIG_AIX_DEVICE_ID;
}

const char *device_identity_boot_id(void)
{
    return s_boot_id;
}

#endif
