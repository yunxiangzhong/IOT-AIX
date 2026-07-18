#include "vision_uplink.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef CONFIG_AIX_VISION_UPLOAD_PERIOD_MS
#define CONFIG_AIX_VISION_UPLOAD_PERIOD_MS 1000
#endif

uint32_t vision_uplink_default_period_ms(void)
{
    return CONFIG_AIX_VISION_UPLOAD_PERIOD_MS;
}

bool vision_uplink_response_matches_frame(
    const char *json,
    size_t length,
    const char *device_id,
    const char *boot_id,
    uint32_t frame_seq)
{
    char expected_seq[32];
    char expected_device[96];
    char expected_boot[64];
    int sequence_length;
    const char *sequence;

    if (json == NULL || length == 0 || device_id == NULL || boot_id == NULL) {
        return false;
    }
    sequence_length = snprintf(expected_seq, sizeof(expected_seq), "\"frame_seq\":%lu", (unsigned long)frame_seq);
    if (sequence_length < 0 || (size_t)sequence_length >= sizeof(expected_seq)) {
        return false;
    }
    sequence = strstr(json, expected_seq);
    if (sequence == NULL ||
        (sequence[sequence_length] != ',' && sequence[sequence_length] != '}' && sequence[sequence_length] != ' ')) {
        return false;
    }
    if (snprintf(expected_device, sizeof(expected_device), "\"device_id\":\"%s\"", device_id) < 0 ||
        snprintf(expected_boot, sizeof(expected_boot), "\"boot_id\":\"%s\"", boot_id) < 0) {
        return false;
    }
    return strstr(json, "\"type\":\"frame_ack\"") != NULL &&
           strstr(json, "\"version\":1") != NULL &&
           strstr(json, expected_device) != NULL &&
           strstr(json, expected_boot) != NULL &&
           strstr(json, "\"accepted\":true") != NULL;
}

bool vision_uplink_response_model_failed(const char *json, size_t length)
{
    return json != NULL && length > 0 && strstr(json, "\"model_state\":\"error\"") != NULL;
}

#ifdef ESP_PLATFORM

#include "action_controller.h"
#include "device_identity.h"
#include "esp_check.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "network_runtime.h"

#define VISION_RESPONSE_CAPACITY 1024U
#define VISION_MAX_JPEG_BYTES (256U * 1024U)

#ifndef CONFIG_AIX_VISION_SERVICE_URL
#define CONFIG_AIX_VISION_SERVICE_URL "http://192.168.137.1:8008/v1/frames"
#endif
#ifndef CONFIG_AIX_VISION_HTTP_TIMEOUT_MS
#define CONFIG_AIX_VISION_HTTP_TIMEOUT_MS 1500
#endif
#ifndef CONFIG_AIX_LINK_TOKEN
#define CONFIG_AIX_LINK_TOKEN ""
#endif

typedef struct {
    uint8_t *data;
    size_t length;
    uint32_t frame_seq;
    uint64_t capture_ts_ms;
} vision_frame_t;

typedef struct {
    char data[VISION_RESPONSE_CAPACITY];
    size_t length;
    bool truncated;
} vision_response_t;

static const char *TAG = "AIX_VISION_UPLINK";
static SemaphoreHandle_t s_frame_lock;
static TaskHandle_t s_task;
static vision_frame_t s_pending_frame;
static uint64_t s_last_submit_ts_ms;
static bool s_started;

static void emit_uplink_status(const vision_frame_t *frame, bool valid, const char *reason)
{
    printf("{\"type\":\"uplink_status\",\"version\":1,\"frame_seq\":%lu,"
           "\"capture_ts_ms\":%llu,\"valid\":%s,\"reason\":\"%s\"}\n",
           (unsigned long)frame->frame_seq,
           (unsigned long long)frame->capture_ts_ms,
           valid ? "true" : "false",
           reason);
    fflush(stdout);
}

static esp_err_t response_event_handler(esp_http_client_event_t *event)
{
    vision_response_t *response = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && response != NULL) {
        size_t remaining = sizeof(response->data) - response->length - 1U;
        size_t copy_length = event->data_len < (int)remaining ? (size_t)event->data_len : remaining;
        if (copy_length > 0) {
            memcpy(response->data + response->length, event->data, copy_length);
            response->length += copy_length;
            response->data[response->length] = '\0';
        }
        response->truncated = copy_length != (size_t)event->data_len;
    }
    return ESP_OK;
}

static bool post_frame(const vision_frame_t *frame)
{
    char frame_seq[16];
    char capture_ts_ms[24];
    vision_response_t response = {0};
    esp_http_client_config_t config = {
        .url = CONFIG_AIX_VISION_SERVICE_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = CONFIG_AIX_VISION_HTTP_TIMEOUT_MS,
        .event_handler = response_event_handler,
        .user_data = &response,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        return false;
    }
    snprintf(frame_seq, sizeof(frame_seq), "%lu", (unsigned long)frame->frame_seq);
    snprintf(capture_ts_ms, sizeof(capture_ts_ms), "%llu", (unsigned long long)frame->capture_ts_ms);
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_header(client, "X-AIX-Token", CONFIG_AIX_LINK_TOKEN);
    esp_http_client_set_header(client, "X-Device-Id", device_identity_device_id());
    esp_http_client_set_header(client, "X-Boot-Id", device_identity_boot_id());
    esp_http_client_set_header(client, "X-Frame-Seq", frame_seq);
    esp_http_client_set_header(client, "X-Capture-Ts-Ms", capture_ts_ms);
    esp_http_client_set_post_field(client, (const char *)frame->data, frame->length);
    esp_err_t ret = esp_http_client_perform(client);
    bool valid = ret == ESP_OK && esp_http_client_get_status_code(client) == 202 && !response.truncated &&
                 vision_uplink_response_matches_frame(
                     response.data,
                     response.length,
                     device_identity_device_id(),
                     device_identity_boot_id(),
                     frame->frame_seq);
    if (valid) {
        action_controller_set_fault(ACTION_FAULT_MODEL, vision_uplink_response_model_failed(response.data, response.length));
        printf("%s\n", response.data);
        fflush(stdout);
    }
    esp_http_client_cleanup(client);
    return valid;
}

static void uplink_task(void *arg)
{
    (void)arg;
    for (;;) {
        vision_frame_t frame = {0};
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        xSemaphoreTake(s_frame_lock, portMAX_DELAY);
        frame = s_pending_frame;
        s_pending_frame = (vision_frame_t){0};
        xSemaphoreGive(s_frame_lock);
        if (frame.data == NULL) {
            continue;
        }
        bool connected = network_runtime_wait_connected(CONFIG_AIX_VISION_HTTP_TIMEOUT_MS);
        bool valid = connected && post_frame(&frame);
        action_controller_set_fault(ACTION_FAULT_NETWORK, !valid);
        emit_uplink_status(&frame, valid, valid ? "accepted" : (connected ? "http_failed" : "wifi_disconnected"));
        free(frame.data);
    }
}

bool vision_uplink_submit_frame(
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
    if (!s_started || data == NULL || length < 4U || length > VISION_MAX_JPEG_BYTES ||
        (s_last_submit_ts_ms != 0 && capture_ts_ms - s_last_submit_ts_ms < CONFIG_AIX_VISION_UPLOAD_PERIOD_MS)) {
        return false;
    }
    uint8_t *copy = malloc(length);
    if (copy == NULL) {
        return false;
    }
    memcpy(copy, data, length);
    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    free(s_pending_frame.data);
    s_pending_frame = (vision_frame_t){
        .data = copy,
        .length = length,
        .frame_seq = frame_seq,
        .capture_ts_ms = capture_ts_ms,
    };
    s_last_submit_ts_ms = capture_ts_ms;
    xSemaphoreGive(s_frame_lock);
    xTaskNotifyGive(s_task);
    return true;
}

esp_err_t vision_uplink_start_task(void)
{
    if (s_started) {
        return ESP_OK;
    }
    if (CONFIG_AIX_LINK_TOKEN[0] == '\0') {
        ESP_LOGE(TAG, "link token is empty");
        return ESP_ERR_INVALID_STATE;
    }
    s_frame_lock = xSemaphoreCreateMutex();
    if (s_frame_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(network_runtime_start(), TAG, "network setup failed");
    if (xTaskCreate(uplink_task, "vision_uplink", 8192, NULL, 4, &s_task) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

#endif
