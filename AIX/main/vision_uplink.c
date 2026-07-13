#include "vision_uplink.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

bool vision_uplink_response_matches_frame(const char *json, size_t length, uint32_t frame_seq)
{
    char expected_seq[32];
    const char *sequence;
    int written;

    if (json == NULL || length == 0) {
        return false;
    }

    written = snprintf(expected_seq, sizeof(expected_seq), "\"frame_seq\":%lu", (unsigned long)frame_seq);
    if (written < 0 || (size_t)written >= sizeof(expected_seq)) {
        return false;
    }

    sequence = strstr(json, expected_seq);
    if (sequence == NULL ||
        (sequence[written] != ',' && sequence[written] != '}' && sequence[written] != ' ')) {
        return false;
    }

    return strstr(json, "\"type\":\"vision_depth\"") != NULL &&
           strstr(json, "\"version\":1") != NULL &&
           strstr(json, "\"valid\":true") != NULL;
}

#ifdef ESP_PLATFORM

#include "esp_event.h"
#include "esp_check.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#define VISION_WIFI_CONNECTED_BIT BIT0
#define VISION_RESPONSE_CAPACITY 1024U

#ifndef CONFIG_AIX_WIFI_SSID
#define CONFIG_AIX_WIFI_SSID ""
#endif
#ifndef CONFIG_AIX_WIFI_PASSWORD
#define CONFIG_AIX_WIFI_PASSWORD ""
#endif
#ifndef CONFIG_AIX_VISION_SERVICE_URL
#define CONFIG_AIX_VISION_SERVICE_URL "http://192.168.137.1:8008/v1/infer"
#endif
#ifndef CONFIG_AIX_VISION_UPLOAD_PERIOD_MS
#define CONFIG_AIX_VISION_UPLOAD_PERIOD_MS 1000
#endif
#ifndef CONFIG_AIX_VISION_HTTP_TIMEOUT_MS
#define CONFIG_AIX_VISION_HTTP_TIMEOUT_MS 3000
#endif

typedef struct {
    uint8_t *data;
    size_t length;
    uint16_t width;
    uint16_t height;
    uint32_t frame_seq;
    uint64_t capture_ts_ms;
} vision_frame_t;

typedef struct {
    char data[VISION_RESPONSE_CAPACITY];
    size_t length;
    bool truncated;
} vision_response_t;

static const char *TAG = "AIX_VISION_UPLINK";
static EventGroupHandle_t s_wifi_events;
static SemaphoreHandle_t s_frame_lock;
static TaskHandle_t s_task;
static vision_frame_t s_pending_frame;
static uint64_t s_last_submit_ts_ms;
static bool s_started;

static void emit_invalid(uint32_t frame_seq, uint64_t capture_ts_ms, const char *reason)
{
    printf("{\"type\":\"vision_depth\",\"version\":1,\"frame_seq\":%lu,"
           "\"capture_ts_ms\":%llu,\"model\":\"DA3-SMALL\","
           "\"depth_kind\":\"relative\",\"valid\":false,\"reason\":\"%s\"}\n",
           (unsigned long)frame_seq, (unsigned long long)capture_ts_ms, reason);
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_wifi_events, VISION_WIFI_CONNECTED_BIT);
        esp_wifi_connect();
    }
    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_wifi_events, VISION_WIFI_CONNECTED_BIT);
    }
}

static esp_err_t initialize_wifi(void)
{
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    wifi_config_t config = {0};
    esp_err_t ret;

    if (CONFIG_AIX_WIFI_SSID[0] == '\0') {
        ESP_LOGW(TAG, "Wi-Fi SSID is empty; vision uplink remains disabled");
        return ESP_ERR_INVALID_STATE;
    }
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        return ret;
    }
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init failed");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop init failed");
    esp_netif_create_default_wifi_sta();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "wifi init failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL), TAG, "wifi event register failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL), TAG, "ip event register failed");

    strlcpy((char *)config.sta.ssid, CONFIG_AIX_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_AIX_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "wifi mode failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "wifi config failed");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "wifi start failed");
    return esp_wifi_connect();
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
        if (copy_length != (size_t)event->data_len) {
            response->truncated = true;
        }
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
    esp_err_t ret;

    if (client == NULL) {
        return false;
    }
    snprintf(frame_seq, sizeof(frame_seq), "%lu", (unsigned long)frame->frame_seq);
    snprintf(capture_ts_ms, sizeof(capture_ts_ms), "%llu", (unsigned long long)frame->capture_ts_ms);
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_header(client, "X-Frame-Seq", frame_seq);
    esp_http_client_set_header(client, "X-Capture-Ts-Ms", capture_ts_ms);
    esp_http_client_set_post_field(client, (const char *)frame->data, frame->length);
    ret = esp_http_client_perform(client);
    bool valid = ret == ESP_OK && esp_http_client_get_status_code(client) == 200 && !response.truncated &&
                 vision_uplink_response_matches_frame(response.data, response.length, frame->frame_seq);
    if (valid) {
        printf("%s\n", response.data);
    }
    esp_http_client_cleanup(client);
    return valid;
}

static void vision_uplink_task(void *arg)
{
    (void)arg;
    for (;;) {
        vision_frame_t frame = {0};
        xTaskNotifyWait(0, UINT32_MAX, NULL, portMAX_DELAY);
        xSemaphoreTake(s_frame_lock, portMAX_DELAY);
        frame = s_pending_frame;
        s_pending_frame = (vision_frame_t){0};
        xSemaphoreGive(s_frame_lock);
        if (frame.data == NULL) {
            continue;
        }
        EventBits_t bits = xEventGroupWaitBits(
            s_wifi_events, VISION_WIFI_CONNECTED_BIT, pdFALSE, pdTRUE,
            pdMS_TO_TICKS(CONFIG_AIX_VISION_HTTP_TIMEOUT_MS));
        if ((bits & VISION_WIFI_CONNECTED_BIT) == 0 || !post_frame(&frame)) {
            emit_invalid(frame.frame_seq, frame.capture_ts_ms, "uplink_failed");
        }
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
    uint8_t *copy;
    (void)context;
    if (!s_started || data == NULL || length == 0 ||
        capture_ts_ms - s_last_submit_ts_ms < CONFIG_AIX_VISION_UPLOAD_PERIOD_MS) {
        return false;
    }
    copy = malloc(length);
    if (copy == NULL) {
        return false;
    }
    memcpy(copy, data, length);
    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    free(s_pending_frame.data);
    s_pending_frame = (vision_frame_t){
        .data = copy,
        .length = length,
        .width = width,
        .height = height,
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
    s_wifi_events = xEventGroupCreate();
    s_frame_lock = xSemaphoreCreateMutex();
    if (s_wifi_events == NULL || s_frame_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(initialize_wifi(), TAG, "Wi-Fi setup failed");
    if (xTaskCreate(vision_uplink_task, "vision_uplink", 8192, NULL, 4, &s_task) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

#endif
