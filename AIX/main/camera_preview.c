#include "camera_preview.h"

#include <stdio.h>

bool camera_preview_make_url(char *buffer, size_t buffer_size, const char *ip, uint16_t port)
{
    int written;
    if (buffer == NULL || buffer_size == 0 || ip == NULL || ip[0] == '\0' || port == 0) {
        return false;
    }
    written = snprintf(buffer, buffer_size, "http://%s:%u/capture.jpg", ip, (unsigned int)port);
    return written >= 0 && (size_t)written < buffer_size;
}

#ifdef ESP_PLATFORM

#include <stdlib.h>
#include <string.h>

#include "esp_check.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "network_runtime.h"

#ifndef CONFIG_AIX_CAMERA_PREVIEW_PORT
#define CONFIG_AIX_CAMERA_PREVIEW_PORT 8081
#endif

static const char *TAG = "AIX_CAMERA_PREVIEW";
static SemaphoreHandle_t s_frame_lock;
static uint8_t *s_latest_jpeg;
static size_t s_latest_jpeg_length;
static uint32_t s_latest_frame_seq;
static uint64_t s_latest_capture_ts_ms;
static bool s_started;
static httpd_handle_t s_server;

static esp_err_t capture_handler(httpd_req_t *request)
{
    uint8_t *copy = NULL;
    size_t length = 0;
    uint32_t frame_seq = 0;
    uint64_t capture_ts_ms = 0;
    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    if (s_latest_jpeg != NULL && s_latest_jpeg_length > 0) {
        copy = malloc(s_latest_jpeg_length);
        if (copy != NULL) {
            length = s_latest_jpeg_length;
            frame_seq = s_latest_frame_seq;
            capture_ts_ms = s_latest_capture_ts_ms;
            memcpy(copy, s_latest_jpeg, length);
        }
    }
    xSemaphoreGive(s_frame_lock);
    if (copy == NULL) {
        httpd_resp_set_status(request, "503 Service Unavailable");
        return httpd_resp_sendstr(request, "camera frame unavailable");
    }
    char value[32];
    httpd_resp_set_type(request, "image/jpeg");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    snprintf(value, sizeof(value), "%lu", (unsigned long)frame_seq);
    httpd_resp_set_hdr(request, "X-Frame-Seq", value);
    snprintf(value, sizeof(value), "%llu", (unsigned long long)capture_ts_ms);
    httpd_resp_set_hdr(request, "X-Capture-Ts-Ms", value);
    esp_err_t ret = httpd_resp_send(request, (const char *)copy, length);
    free(copy);
    return ret;
}

bool camera_preview_submit_frame(
    const uint8_t *data,
    size_t length,
    uint16_t width,
    uint16_t height,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    void *context)
{
    (void)width;
    (void)height;
    (void)context;
    if (!s_started || data == NULL || length == 0) {
        return false;
    }
    uint8_t *copy = malloc(length);
    if (copy == NULL) {
        return false;
    }
    memcpy(copy, data, length);
    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    free(s_latest_jpeg);
    s_latest_jpeg = copy;
    s_latest_jpeg_length = length;
    s_latest_frame_seq = frame_seq;
    s_latest_capture_ts_ms = capture_ts_ms;
    xSemaphoreGive(s_frame_lock);
    return true;
}

esp_err_t camera_preview_start(void)
{
    if (s_started) {
        return ESP_OK;
    }
    s_frame_lock = xSemaphoreCreateMutex();
    if (s_frame_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(network_runtime_start(), TAG, "shared network setup failed");
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = CONFIG_AIX_CAMERA_PREVIEW_PORT;
    httpd_uri_t uri = {
        .uri = "/capture.jpg",
        .method = HTTP_GET,
        .handler = capture_handler,
        .user_ctx = NULL,
    };
    ESP_RETURN_ON_ERROR(httpd_start(&s_server, &config), TAG, "preview server start failed");
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &uri), TAG, "preview URI failed");
    s_started = true;
    return ESP_OK;
}

#endif
