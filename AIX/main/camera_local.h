#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef ESP_PLATFORM
#include "esp_err.h"
#else
typedef int esp_err_t;
#endif

typedef struct {
    const uint8_t *data;
    size_t length;
    uint16_t width;
    uint16_t height;
    void *native_handle;
} camera_local_frame_t;

typedef struct {
    bool initialized;
    bool valid;
    bool psram_enabled;
    uint16_t width;
    uint16_t height;
    uint32_t frames_ok;
    uint32_t capture_failures;
    uint32_t consecutive_failures;
    uint32_t last_frame_bytes;
    float measured_fps;
} camera_local_status_t;

typedef bool (*camera_local_frame_consumer_t)(
    const uint8_t *data,
    size_t length,
    uint16_t width,
    uint16_t height,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    void *context);

bool camera_local_frame_is_valid_jpeg(const uint8_t *data, size_t length);

#ifdef ESP_PLATFORM
esp_err_t camera_local_init(void);
esp_err_t camera_local_start_task(void);
esp_err_t camera_local_acquire_frame(camera_local_frame_t *frame);
void camera_local_release_frame(camera_local_frame_t *frame);
void camera_local_get_status(camera_local_status_t *status);
void camera_local_set_frame_consumer(camera_local_frame_consumer_t consumer, void *context);
#endif
