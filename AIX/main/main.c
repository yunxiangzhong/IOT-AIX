#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"
#include "action_controller.h"
#include "device_identity.h"
#include "network_runtime.h"
#include "mpu6050_sensor.h"
#include "pneumatic_controller.h"
#include "pressure_sensor.h"
#include "risk_receiver.h"

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
#include "camera_local.h"
#endif

#if CONFIG_AIX_ENABLE_VISION_UPLINK
#include "vision_uplink.h"
#endif

#if CONFIG_AIX_ENABLE_CAMERA_PREVIEW
#include "camera_preview.h"
#endif

static const char *TAG = "AIX_BOOT";

static void network_status_changed(bool connected, void *context)
{
    (void)context;
    action_controller_set_fault(ACTION_FAULT_NETWORK, !connected);
}

static void camera_status_changed(bool healthy, void *context)
{
    (void)context;
    action_controller_set_fault(ACTION_FAULT_CAMERA, !healthy);
}

void app_main(void)
{
    esp_err_t ret;
    bool network_ready;

    ESP_LOGI(TAG, "AIX pulse helmet firmware booted");
    ESP_LOGI(TAG, "Target board: ESP32-S3-DevKitC-1, monitor via J4 USB-UART");
    ESP_LOGI(TAG, "Pressure sensor: XGZP6847A 3.3V, OUT -> GPIO1 / ADC1_CH0");
    ESP_LOGI(TAG, "Vision chain: OV5640 -> PC async inference -> RGB action");

    ESP_ERROR_CHECK(device_identity_init());
    ESP_LOGI(TAG, "device=%s boot=%s", device_identity_device_id(), device_identity_boot_id());
    ESP_ERROR_CHECK(action_controller_start(device_identity_device_id(), device_identity_boot_id()));
    network_runtime_set_status_callback(network_status_changed, NULL);
    ret = network_runtime_start();
    network_ready = ret == ESP_OK;
    if (ret != ESP_OK) {
        action_controller_set_fault(ACTION_FAULT_NETWORK, true);
        ESP_LOGW(TAG, "network runtime unavailable: %s", esp_err_to_name(ret));
    }

    ret = pressure_sensor_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "pressure sensor init failed: %s", esp_err_to_name(ret));
        return;
    }

    ret = pressure_sensor_start_task();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "pressure sensor task start failed: %s", esp_err_to_name(ret));
        return;
    }

    ret = mpu6050_sensor_start();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "MPU6050 unavailable; visual protection remains available: %s", esp_err_to_name(ret));
    }

#if CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL
    ret = pneumatic_controller_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "pneumatic controller start failed; outputs remain disabled: %s", esp_err_to_name(ret));
    }
#endif

#if CONFIG_AIX_ENABLE_RISK_RECEIVER
    if (network_ready) {
        esp_err_t risk_ret = risk_receiver_start();
        if (risk_ret != ESP_OK) {
            ESP_LOGE(TAG, "risk receiver start failed: %s", esp_err_to_name(risk_ret));
        }
    }
#endif

#if CONFIG_AIX_ENABLE_LOCAL_CAMERA
    camera_local_set_health_callback(camera_status_changed, NULL);
#if CONFIG_AIX_ENABLE_CAMERA_PREVIEW
    ret = camera_preview_start();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "camera preview unavailable: %s", esp_err_to_name(ret));
    } else {
        camera_local_set_frame_consumer(camera_preview_submit_frame, NULL);
        ESP_LOGI(TAG, "Wi-Fi camera preview enabled");
    }
#endif
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
        ESP_LOGI(TAG, "Local OV5640 capture enabled");
    }
#endif

    ESP_LOGI(TAG, "AIX active vision closed loop started");
}
