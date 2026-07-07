#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"
#include "pressure_sensor.h"
#include "risk_fusion.h"
#include "vision_input.h"

static const char *TAG = "AIX_BOOT";

void app_main(void)
{
    ESP_LOGI(TAG, "AIX pulse helmet firmware booted");
    ESP_LOGI(TAG, "Target board: ESP32-S3-DevKitC-1, monitor via J4 USB-UART");
    ESP_LOGI(TAG, "Pressure sensor: XGZP6847A 3.3V, OUT -> GPIO1 / ADC1_CH0");
    ESP_LOGI(TAG, "Vision source: PC camera features over USB-UART NDJSON");

    esp_err_t ret = pressure_sensor_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "pressure sensor init failed: %s", esp_err_to_name(ret));
        return;
    }

    ret = pressure_sensor_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "pressure sensor task start failed: %s", esp_err_to_name(ret));
        return;
    }

    ret = vision_input_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "vision input task start failed: %s", esp_err_to_name(ret));
        return;
    }

    ret = risk_fusion_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "risk fusion task start failed: %s", esp_err_to_name(ret));
        return;
    }

    ESP_LOGI(TAG, "AIX sensing and local risk loop started");
}
