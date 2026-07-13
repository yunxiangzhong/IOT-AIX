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

#include "esp_err.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs_flash.h"

#define CAMERA_PREVIEW_URL_CAPACITY 80U

#ifndef CONFIG_AIX_WIFI_SSID
#define CONFIG_AIX_WIFI_SSID ""
#endif
#ifndef CONFIG_AIX_WIFI_PASSWORD
#define CONFIG_AIX_WIFI_PASSWORD ""
#endif
#ifndef CONFIG_AIX_CAMERA_PREVIEW_PORT
#define CONFIG_AIX_CAMERA_PREVIEW_PORT 8080
#endif

static const char *TAG = "AIX_CAMERA_PREVIEW";
static SemaphoreHandle_t s_frame_lock;
static uint8_t *s_latest_jpeg;
static size_t s_latest_jpeg_length;
static bool s_started;
static httpd_handle_t s_server;
static bool s_wifi_ready;
static char s_wifi_ip[16];
static uint64_t s_last_preview_event_ts_ms;

static void emit_preview_event(bool valid, const char *ip, const char *reason)
{
    char url[CAMERA_PREVIEW_URL_CAPACITY] = {0};
    bool has_url = valid && camera_preview_make_url(
        url, sizeof(url), ip, CONFIG_AIX_CAMERA_PREVIEW_PORT);

    printf("{\"type\":\"camera_preview\",\"version\":1,\"valid\":%s,"
           "\"url\":\"%s\",\"ip\":\"%s\",\"port\":%d,\"reason\":\"%s\"}\n",
           has_url ? "true" : "false",
           has_url ? url : "",
           ip != NULL ? ip : "",
           CONFIG_AIX_CAMERA_PREVIEW_PORT,
           reason != NULL ? reason : "unavailable");
    fflush(stdout);
}

static esp_err_t capture_handler(httpd_req_t *request)
{
    uint8_t *copy = NULL;
    size_t length = 0;
    esp_err_t ret;

    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    if (s_latest_jpeg != NULL && s_latest_jpeg_length > 0) {
        copy = malloc(s_latest_jpeg_length);
        if (copy != NULL) {
            length = s_latest_jpeg_length;
            memcpy(copy, s_latest_jpeg, length);
        }
    }
    xSemaphoreGive(s_frame_lock);

    if (copy == NULL) {
        httpd_resp_set_status(request, "503 Service Unavailable");
        return httpd_resp_sendstr(request, "camera frame unavailable");
    }
    httpd_resp_set_type(request, "image/jpeg");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    ret = httpd_resp_send(request, (const char *)copy, length);
    free(copy);
    return ret;
}

static esp_err_t start_http_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    httpd_uri_t capture_uri = {
        .uri = "/capture.jpg",
        .method = HTTP_GET,
        .handler = capture_handler,
        .user_ctx = NULL,
    };

    config.server_port = CONFIG_AIX_CAMERA_PREVIEW_PORT;
    ESP_RETURN_ON_ERROR(httpd_start(&s_server, &config), TAG, "HTTP server start failed");
    return httpd_register_uri_handler(s_server, &capture_uri);
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected; retrying");
        esp_wifi_connect();
        return;
    }
    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *got_ip = event_data;
        char ip[16];
        snprintf(ip, sizeof(ip), IPSTR, IP2STR(&got_ip->ip_info.ip));
        ESP_LOGI(TAG, "Wi-Fi ready: %s", ip);
        strlcpy(s_wifi_ip, ip, sizeof(s_wifi_ip));
        s_wifi_ready = true;
        s_last_preview_event_ts_ms = 0;
        emit_preview_event(true, ip, "ready");
    }
}

static esp_err_t initialize_wifi(void)
{
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    wifi_config_t config = {0};
    esp_err_t ret;

    if (CONFIG_AIX_WIFI_SSID[0] == '\0') {
        ESP_LOGW(TAG, "Wi-Fi SSID is empty; preview remains unavailable");
        emit_preview_event(false, "", "ssid_empty");
        return ESP_ERR_INVALID_STATE;
    }
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "NVS erase failed");
        ret = nvs_flash_init();
    }
    ESP_RETURN_ON_ERROR(ret, TAG, "NVS init failed");
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init failed");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop init failed");
    esp_netif_create_default_wifi_sta();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "Wi-Fi init failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(
                            WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL),
                        TAG, "Wi-Fi event register failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(
                            IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL),
                        TAG, "IP event register failed");

    strlcpy((char *)config.sta.ssid, CONFIG_AIX_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_AIX_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "Wi-Fi mode failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "Wi-Fi config failed");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Wi-Fi start failed");
    return esp_wifi_connect();
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
    uint8_t *copy;
    (void)width;
    (void)height;
    (void)frame_seq;
    (void)capture_ts_ms;
    (void)context;

    if (!s_started || data == NULL || length == 0) {
        return false;
    }
    copy = malloc(length);
    if (copy == NULL) {
        return false;
    }
    memcpy(copy, data, length);
    xSemaphoreTake(s_frame_lock, portMAX_DELAY);
    free(s_latest_jpeg);
    s_latest_jpeg = copy;
    s_latest_jpeg_length = length;
    xSemaphoreGive(s_frame_lock);
    if (s_wifi_ready &&
        (s_last_preview_event_ts_ms == 0 ||
         capture_ts_ms - s_last_preview_event_ts_ms >= 1000U)) {
        emit_preview_event(true, s_wifi_ip, "ready");
        s_last_preview_event_ts_ms = capture_ts_ms;
    }
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
    ESP_RETURN_ON_ERROR(initialize_wifi(), TAG, "Wi-Fi setup failed");
    ESP_RETURN_ON_ERROR(start_http_server(), TAG, "preview server start failed");
    s_started = true;
    ESP_LOGI(TAG, "OV5640 preview endpoint armed on port %d", CONFIG_AIX_CAMERA_PREVIEW_PORT);
    return ESP_OK;
}

#endif
