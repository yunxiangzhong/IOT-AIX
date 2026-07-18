idf_component_register(SRCS "action_controller.c" "action_policy.c" "camera_local.c" "camera_preview.c" "dfplayer.c"
                    "device_identity.c" "main.c" "motion_detector.c" "mpu6050_sensor.c" "network_runtime.c"
                    "pneumatic_controller.c" "pneumatic_policy.c" "pressure_sensor.c"
                    "rgb_status.c" "risk_receiver.c" "vision_uplink.c" "voice_prompt.c"
                    INCLUDE_DIRS "."
                    REQUIRES driver esp_driver_uart json esp_event esp_http_client esp_http_server esp_netif esp_wifi led_strip nvs_flash
                    PRIV_REQUIRES esp_adc esp_psram esp_timer)
