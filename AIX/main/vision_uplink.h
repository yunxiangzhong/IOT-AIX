#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef ESP_PLATFORM
#include "esp_err.h"

typedef bool (*vision_uplink_frame_consumer_t)(
    const uint8_t *data,
    size_t length,
    uint16_t width,
    uint16_t height,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    void *context);

esp_err_t vision_uplink_start_task(void);
bool vision_uplink_submit_frame(
    const uint8_t *data,
    size_t length,
    uint16_t width,
    uint16_t height,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    void *context);
#endif

bool vision_uplink_response_matches_frame(const char *json, size_t length, uint32_t frame_seq);
