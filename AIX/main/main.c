#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"
#include "pressure_sensor.h"

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
#include "camera_local.h"
#endif

#if CONFIG_AIX_ENABLE_VISION_UPLINK
#include "vision_uplink.h"
#endif

static const char *TAG = "AIX_BOOT";

void app_main(void)
{
    ESP_LOGI(TAG, "AIX pulse helmet firmware booted");
    ESP_LOGI(TAG, "Target board: ESP32-S3-DevKitC-1, monitor via J4 USB-UART");
    ESP_LOGI(TAG, "Pressure sensor: XGZP6847A 3.3V, OUT -> GPIO1 / ADC1_CH0");
    ESP_LOGI(TAG, "Vision source: OV5640 local capture only");

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

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
#if CONFIG_AIX_ENABLE_VISION_UPLINK
    ret = vision_uplink_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "vision uplink start failed: %s", esp_err_to_name(ret));
    } else {
        camera_local_set_frame_consumer(vision_uplink_submit_frame, NULL);
        ESP_LOGI(TAG, "Wi-Fi vision uplink enabled");
    }
#endif
    ret = camera_local_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "local OV5640 camera task start failed: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Local OV5640 capture enabled; camera status is telemetry only");
    }
#endif

    ESP_LOGI(TAG, "AIX pressure sensing and local camera capture started");
}
