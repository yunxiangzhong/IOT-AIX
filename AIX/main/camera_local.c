#include "camera_local.h"

bool camera_local_frame_is_valid_jpeg(const uint8_t *data, size_t length)
{
    return data != NULL && length >= 4 &&
           data[0] == 0xff && data[1] == 0xd8 &&
           data[length - 2] == 0xff && data[length - 1] == 0xd9;
}

#ifdef ESP_PLATFORM

#include <stdio.h>

#include "esp_camera.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sensor.h"

#include "camera_board_devkitc1_ov5640.h"

#ifndef CONFIG_AIX_CAMERA_CAPTURE_PERIOD_MS
#define CONFIG_AIX_CAMERA_CAPTURE_PERIOD_MS 200
#endif

#define CAMERA_INIT_RETRY_MS 2000U
#define CAMERA_REINIT_FAILURES 3U
#define CAMERA_STATUS_PERIOD_MS 1000U
#define OV5640_SENSOR_PID 0x5640U

static const char *TAG = "AIX_CAMERA";
static camera_local_status_t s_status = {
    .width = 320,
    .height = 240,
};
static bool s_task_started;
static uint32_t s_status_seq;
static uint64_t s_last_status_us;
static uint32_t s_status_frames_ok;

static uint64_t now_us(void)
{
    return (uint64_t)esp_timer_get_time();
}

static camera_config_t make_camera_config(void)
{
    camera_config_t config = {
        .pin_pwdn = AIX_CAMERA_PIN_PWDN,
        .pin_reset = AIX_CAMERA_PIN_RESET,
        .pin_xclk = AIX_CAMERA_PIN_XCLK,
        .pin_sccb_sda = AIX_CAMERA_PIN_SIOD,
        .pin_sccb_scl = AIX_CAMERA_PIN_SIOC,
        .pin_d7 = AIX_CAMERA_PIN_D7,
        .pin_d6 = AIX_CAMERA_PIN_D6,
        .pin_d5 = AIX_CAMERA_PIN_D5,
        .pin_d4 = AIX_CAMERA_PIN_D4,
        .pin_d3 = AIX_CAMERA_PIN_D3,
        .pin_d2 = AIX_CAMERA_PIN_D2,
        .pin_d1 = AIX_CAMERA_PIN_D1,
        .pin_d0 = AIX_CAMERA_PIN_D0,
        .pin_vsync = AIX_CAMERA_PIN_VSYNC,
        .pin_href = AIX_CAMERA_PIN_HREF,
        .pin_pclk = AIX_CAMERA_PIN_PCLK,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = FRAMESIZE_QVGA,
        .jpeg_quality = 12,
        .fb_count = 1,
        .fb_location = CAMERA_FB_IN_DRAM,
        .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
    };
    return config;
}

static void mark_capture_failure(void)
{
    s_status.capture_failures++;
    s_status.consecutive_failures++;
    s_status.valid = false;
    if (s_status.consecutive_failures >= CAMERA_REINIT_FAILURES && s_status.initialized) {
        ESP_LOGW(TAG, "three consecutive capture failures; restarting camera driver");
        esp_camera_deinit();
        s_status.initialized = false;
    }
}

esp_err_t camera_local_init(void)
{
    if (s_status.initialized) {
        return ESP_OK;
    }

    camera_config_t config = make_camera_config();
    esp_err_t ret = esp_camera_init(&config);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "OV5640 init failed: %s", esp_err_to_name(ret));
        s_status.valid = false;
        return ret;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor == NULL || sensor->id.PID != OV5640_SENSOR_PID) {
        ESP_LOGW(TAG, "expected OV5640 but detected an unsupported sensor");
        esp_camera_deinit();
        s_status.valid = false;
        return ESP_ERR_NOT_SUPPORTED;
    }

    s_status.initialized = true;
    s_status.valid = true;
    s_status.width = 320;
    s_status.height = 240;
    s_status.psram_enabled = esp_psram_is_initialized();
    s_status.consecutive_failures = 0;
    ESP_LOGI(TAG, "OV5640 ready: 320x240 JPEG, XCLK 20MHz, DRAM single buffer");
    return ESP_OK;
}

esp_err_t camera_local_acquire_frame(camera_local_frame_t *frame)
{
    if (frame == NULL || !s_status.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    *frame = (camera_local_frame_t){0};
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == NULL) {
        return ESP_FAIL;
    }
    if (fb->format != PIXFORMAT_JPEG || !camera_local_frame_is_valid_jpeg(fb->buf, fb->len)) {
        esp_camera_fb_return(fb);
        return ESP_ERR_INVALID_RESPONSE;
    }

    frame->data = fb->buf;
    frame->length = fb->len;
    frame->width = fb->width;
    frame->height = fb->height;
    frame->native_handle = fb;
    return ESP_OK;
}

void camera_local_release_frame(camera_local_frame_t *frame)
{
    if (frame != NULL && frame->native_handle != NULL) {
        esp_camera_fb_return((camera_fb_t *)frame->native_handle);
    }
    if (frame != NULL) {
        *frame = (camera_local_frame_t){0};
    }
}

void camera_local_get_status(camera_local_status_t *status)
{
    if (status != NULL) {
        *status = s_status;
    }
}

static void emit_status(uint64_t current_us)
{
    const uint64_t elapsed_us = s_last_status_us == 0 ? 0 : current_us - s_last_status_us;
    const uint32_t completed_frames = s_status.frames_ok - s_status_frames_ok;
    s_status.measured_fps = elapsed_us == 0 ? 0.0f : (float)completed_frames * 1000000.0f / (float)elapsed_us;
    s_last_status_us = current_us;
    s_status_frames_ok = s_status.frames_ok;
    s_status_seq++;

    printf("{\"type\":\"camera_status\",\"version\":1,\"seq\":%lu,\"ts_ms\":%llu,"
           "\"sensor\":\"OV5640\",\"width\":%u,\"height\":%u,\"pixel_format\":\"jpeg\","
           "\"frame_bytes\":%lu,\"fps\":%.2f,\"frames_ok\":%lu,\"capture_failures\":%lu,"
           "\"psram\":%s,\"valid\":%s}\n",
           (unsigned long)s_status_seq, (unsigned long long)(current_us / 1000U),
           (unsigned)s_status.width, (unsigned)s_status.height,
           (unsigned long)s_status.last_frame_bytes, s_status.measured_fps,
           (unsigned long)s_status.frames_ok, (unsigned long)s_status.capture_failures,
           s_status.psram_enabled ? "true" : "false", s_status.valid ? "true" : "false");
}

static void camera_capture_task(void *arg)
{
    (void)arg;
    uint64_t next_init_us = 0;
    uint64_t next_status_us = 0;

    for (;;) {
        const uint64_t current_us = now_us();
        if (!s_status.initialized && current_us >= next_init_us) {
            if (camera_local_init() != ESP_OK) {
                next_init_us = current_us + (uint64_t)CAMERA_INIT_RETRY_MS * 1000U;
            }
        }

        if (s_status.initialized) {
            camera_local_frame_t frame = {0};
            if (camera_local_acquire_frame(&frame) == ESP_OK) {
                s_status.frames_ok++;
                s_status.consecutive_failures = 0;
                s_status.last_frame_bytes = (uint32_t)frame.length;
                s_status.width = frame.width;
                s_status.height = frame.height;
                s_status.valid = true;
                camera_local_release_frame(&frame);
            } else {
                mark_capture_failure();
                if (!s_status.initialized) {
                    next_init_us = current_us + (uint64_t)CAMERA_INIT_RETRY_MS * 1000U;
                }
            }
        }

        if (current_us >= next_status_us) {
            emit_status(current_us);
            next_status_us = current_us + (uint64_t)CAMERA_STATUS_PERIOD_MS * 1000U;
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_AIX_CAMERA_CAPTURE_PERIOD_MS));
    }
}

esp_err_t camera_local_start_task(void)
{
    if (s_task_started) {
        return ESP_OK;
    }
    BaseType_t created = xTaskCreate(camera_capture_task, "camera_capture", 4096, NULL, 5, NULL);
    if (created != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_task_started = true;
    return ESP_OK;
}

#endif
