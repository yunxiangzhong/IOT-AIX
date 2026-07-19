#pragma once

#include <stdbool.h>

typedef enum {
    HARDWARE_HEALTH_INITIALIZING = 0,
    HARDWARE_HEALTH_HEALTHY,
    HARDWARE_HEALTH_DEGRADED,
    HARDWARE_HEALTH_FAULT,
    HARDWARE_HEALTH_STALE,
    HARDWARE_HEALTH_DISABLED,
    HARDWARE_HEALTH_PENDING,
} hardware_health_state_t;

typedef struct {
    bool camera_healthy;
    bool network_healthy;
    bool mpu_healthy;
    bool pressure_healthy;
    bool dfplayer_healthy;
    bool rgb_healthy;
    bool pneumatic_started;
    bool pump_verified;
    bool valve_verified;
    bool self_test_failed;
} hardware_health_input_t;

typedef struct {
    hardware_health_state_t overall;
    bool automatic_ready;
    hardware_health_state_t ov5640;
    hardware_health_state_t mpu6050;
    hardware_health_state_t pressure;
    hardware_health_state_t dfplayer;
    hardware_health_state_t rgb;
    hardware_health_state_t pump;
    hardware_health_state_t valve;
    const char *reason;
} hardware_health_snapshot_t;

hardware_health_snapshot_t hardware_health_evaluate(const hardware_health_input_t *input);
const char *hardware_health_state_name(hardware_health_state_t state);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t hardware_health_start(void);
bool hardware_health_automatic_ready(void);
#endif
