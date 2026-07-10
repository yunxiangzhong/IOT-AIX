#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"
#include "pressure_sensor.h"
#include "risk_fusion.h"
#include "vision_input.h"
#include "vision_detect_input.h"

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
#include "camera_local.h"
#endif

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA && CONFIG_AIX_ENABLE_SIMULATED_VISION_DETECT
#error "The local camera and simulated vision_detect source cannot run together."
#endif

static const char *TAG = "AIX_BOOT";

void app_main(void)
{
    ESP_LOGI(TAG, "AIX pulse helmet firmware booted");
    ESP_LOGI(TAG, "Target board: ESP32-S3-DevKitC-1, monitor via J4 USB-UART");
    ESP_LOGI(TAG, "Pressure sensor: XGZP6847A 3.3V, OUT -> GPIO1 / ADC1_CH0");
    ESP_LOGI(TAG, "Vision source: PC features over USB-UART NDJSON (risk input)");

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

#if CONFIG_AIX_ENABLE_SIMULATED_VISION_DETECT
    ret = vision_detect_input_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "vision detect input task start failed: %s", esp_err_to_name(ret));
    }
#else
    ESP_LOGI(TAG, "Simulated vision_detect disabled; waiting for external vision input");
#endif

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
    ret = camera_local_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "local OV5640 camera task start failed: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Local OV5640 capture enabled; camera status is telemetry only");
    }
#endif

    ESP_LOGI(TAG, "AIX sensing and local risk loop started");
}
