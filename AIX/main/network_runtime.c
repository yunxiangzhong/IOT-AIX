#include "network_runtime.h"

#ifdef ESP_PLATFORM

#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"

#define NETWORK_CONNECTED_BIT BIT0

#ifndef CONFIG_AIX_WIFI_SSID
#define CONFIG_AIX_WIFI_SSID ""
#endif
#ifndef CONFIG_AIX_WIFI_PASSWORD
#define CONFIG_AIX_WIFI_PASSWORD ""
#endif
static const char *TAG = "AIX_NETWORK";
static EventGroupHandle_t s_events;
static bool s_started;
static network_runtime_status_callback_t s_callback;
static void *s_callback_context;

static void publish_status(bool connected)
{
    if (s_callback != NULL) {
        s_callback(connected, s_callback_context);
    }
}

static void event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, NETWORK_CONNECTED_BIT);
        publish_status(false);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_events, NETWORK_CONNECTED_BIT);
        publish_status(true);
        const ip_event_got_ip_t *event = data;
        ESP_LOGI(TAG, "station ready: " IPSTR, IP2STR(&event->ip_info.ip));
    }
}

esp_err_t network_runtime_start(void)
{
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    wifi_config_t config = {0};
    esp_err_t ret;

    if (s_started) {
        return ESP_OK;
    }
    if (CONFIG_AIX_WIFI_SSID[0] == '\0') {
        return ESP_ERR_INVALID_STATE;
    }
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "NVS erase failed");
        ret = nvs_flash_init();
    }
    ESP_RETURN_ON_ERROR(ret, TAG, "NVS init failed");
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "netif init failed");
    ret = esp_event_loop_create_default();
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        return ret;
    }
    esp_netif_create_default_wifi_sta();
    s_events = xEventGroupCreate();
    if (s_events == NULL) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "Wi-Fi init failed");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, event_handler, NULL, NULL),
        TAG, "Wi-Fi handler failed");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, event_handler, NULL, NULL),
        TAG, "IP handler failed");
    strlcpy((char *)config.sta.ssid, CONFIG_AIX_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_AIX_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "Wi-Fi mode failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "Wi-Fi config failed");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Wi-Fi start failed");
    s_started = true;
    return esp_wifi_connect();
}

bool network_runtime_wait_connected(uint32_t timeout_ms)
{
    if (!s_started || s_events == NULL) {
        return false;
    }
    EventBits_t bits = xEventGroupWaitBits(
        s_events, NETWORK_CONNECTED_BIT, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms));
    return (bits & NETWORK_CONNECTED_BIT) != 0;
}

bool network_runtime_is_connected(void)
{
    return s_events != NULL && (xEventGroupGetBits(s_events) & NETWORK_CONNECTED_BIT) != 0;
}

void network_runtime_set_status_callback(network_runtime_status_callback_t callback, void *context)
{
    s_callback = callback;
    s_callback_context = context;
}

#endif
