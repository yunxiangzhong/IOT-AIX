idf_component_register(SRCS "camera_local.c" "camera_preview.c" "main.c" "pressure_sensor.c" "vision_uplink.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_event esp_http_client esp_http_server esp_netif esp_wifi nvs_flash
                    PRIV_REQUIRES esp_adc esp_psram esp_timer)
