#pragma once

#include <stdbool.h>
#include <stdint.h>

#define PRESSURE_SENSOR_ADC_GPIO 1
#define PRESSURE_SENSOR_MIN_MV 200
#define PRESSURE_SENSOR_MAX_MV 2700
#define PRESSURE_SENSOR_FULL_SCALE_KPA 200.0f
#define PRESSURE_SENSOR_OVER_PRESSURE_KPA 180.0f

typedef struct {
    int raw;
    int voltage_mv;
    float pressure_kpa;
    float filtered_kpa;
    bool over_pressure;
    bool valid;
    uint32_t sample_count;
} pressure_sensor_sample_t;

static inline float pressure_sensor_voltage_to_kpa(int voltage_mv)
{
    float pressure = ((float)(voltage_mv - PRESSURE_SENSOR_MIN_MV) *
                      PRESSURE_SENSOR_FULL_SCALE_KPA) /
                     (float)(PRESSURE_SENSOR_MAX_MV - PRESSURE_SENSOR_MIN_MV);

    if (pressure < 0.0f) {
        return 0.0f;
    }
    if (pressure > PRESSURE_SENSOR_FULL_SCALE_KPA) {
        return PRESSURE_SENSOR_FULL_SCALE_KPA;
    }
    return pressure;
}

static inline bool pressure_sensor_is_over_pressure(float pressure_kpa)
{
    return pressure_kpa >= PRESSURE_SENSOR_OVER_PRESSURE_KPA;
}

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t pressure_sensor_init(void);
esp_err_t pressure_sensor_read(pressure_sensor_sample_t *out);
esp_err_t pressure_sensor_start_task(void);
#endif
