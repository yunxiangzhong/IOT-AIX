#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef ESP_PLATFORM
#include "esp_err.h"
#else
typedef int esp_err_t;
#endif

bool camera_preview_make_url(char *buffer, size_t buffer_size, const char *ip, uint16_t port);

#ifdef ESP_PLATFORM
esp_err_t camera_preview_start(void);
bool camera_preview_submit_frame(
    const uint8_t *data,
    size_t length,
    uint16_t width,
    uint16_t height,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    void *context);
#endif
