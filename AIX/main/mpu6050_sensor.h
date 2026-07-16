#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "motion_detector.h"

#define MPU6050_I2C_SDA_GPIO 2
#define MPU6050_I2C_SCL_GPIO 6
#define MPU6050_INT_GPIO 39
#define MPU6050_I2C_ADDRESS 0x68

typedef struct {
    motion_sample_t sample;
    motion_output_t motion;
    uint64_t timestamp_ms;
    uint32_t sequence;
} mpu6050_status_t;

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t mpu6050_sensor_start(void);
bool mpu6050_sensor_get_latest(mpu6050_status_t *out);
#endif
