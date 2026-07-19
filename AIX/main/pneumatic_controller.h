#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "pneumatic_policy.h"

#define PNEUMATIC_PUMP_GPIO 40
#define PNEUMATIC_VALVE_GPIO 41
#define PNEUMATIC_COMMAND_ID_CAPACITY 64
#define PNEUMATIC_COMMAND_ERROR_CAPACITY 64

typedef enum {
    PNEUMATIC_COMMAND_INFLATE_PULSE = 0,
    PNEUMATIC_COMMAND_VENT,
    PNEUMATIC_COMMAND_EMERGENCY_STOP,
    PNEUMATIC_COMMAND_RESET_FAULT,
    PNEUMATIC_COMMAND_SAVE_CALIBRATION,
    PNEUMATIC_COMMAND_SELF_TEST,
} pneumatic_command_type_t;

typedef struct {
    pneumatic_command_type_t type;
    char command_id[PNEUMATIC_COMMAND_ID_CAPACITY];
    float target_kpa;
    float max_kpa;
    uint32_t max_inflate_ms;
} pneumatic_command_t;

typedef struct {
    pneumatic_policy_config_t config;
    pneumatic_policy_output_t output;
    float pressure_kpa;
    bool pressure_valid;
    uint32_t pressure_age_ms;
    action_state_t vision_state;
    bool vision_fresh;
    bool mpu_available;
    bool mpu_calibrated;
    bool mpu_impact;
    bool mpu_rapid_tilt;
    bool pump_verified;
    bool valve_verified;
    bool self_test_failed;
    uint64_t timestamp_ms;
} pneumatic_status_t;

typedef struct {
    bool accepted;
    bool duplicate;
    char error[PNEUMATIC_COMMAND_ERROR_CAPACITY];
    pneumatic_status_t status;
} pneumatic_command_result_t;

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t pneumatic_controller_start(void);
bool pneumatic_controller_is_started(void);
bool pneumatic_controller_get_status(pneumatic_status_t *out);
bool pneumatic_controller_get_self_test(bool *pump_verified, bool *valve_verified, bool *self_test_failed);
esp_err_t pneumatic_controller_execute(
    const pneumatic_command_t *command,
    pneumatic_command_result_t *result);
#endif
