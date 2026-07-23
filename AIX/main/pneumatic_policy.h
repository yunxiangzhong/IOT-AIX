#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "action_policy.h"

#define PNEUMATIC_PRESSURE_STALE_MS 200ULL
#define PNEUMATIC_PRESSURE_INVALID_GRACE_MS 100ULL
#define PNEUMATIC_PRIME_VALVE_MS 20ULL
#define PNEUMATIC_CALIBRATION_PULSE_MS 200ULL
#define PNEUMATIC_CALIBRATION_TOTAL_PUMP_MS 2000ULL
#define PNEUMATIC_CALIBRATION_CEILING_KPA 20.0f
#define PNEUMATIC_RELEASE_HYSTERESIS_KPA 1.0f
#define PNEUMATIC_REFILL_HYSTERESIS_KPA 0.3f
#define PNEUMATIC_HOLD_MAX_MS 15000ULL
#define PNEUMATIC_CLEAR_CONFIRM_MS 5000ULL
#define PNEUMATIC_VENT_TIMEOUT_MS 5000ULL
#define PNEUMATIC_COOLDOWN_MS 1000ULL
#define PNEUMATIC_VENTED_PRESSURE_KPA 0.5f
#define PNEUMATIC_PREVENTIVE_RISE_KPA 0.8f
#define PNEUMATIC_CONFIG_HARD_LIMIT_KPA 20.0f

typedef enum {
    PNEUMATIC_STATE_DISABLED = 0,
    PNEUMATIC_STATE_VENTED,
    PNEUMATIC_STATE_PRIME_VALVE,
    PNEUMATIC_STATE_INFLATING,
    PNEUMATIC_STATE_HOLDING,
    PNEUMATIC_STATE_VENTING,
    PNEUMATIC_STATE_COOLDOWN,
    PNEUMATIC_STATE_FAULT_VENT,
} pneumatic_state_t;

typedef enum {
    PNEUMATIC_FAULT_NONE = 0,
    PNEUMATIC_FAULT_EMERGENCY_STOP = 1,
    PNEUMATIC_FAULT_PRESSURE_INVALID = 2,
    PNEUMATIC_FAULT_PRESSURE_STALE = 3,
    PNEUMATIC_FAULT_PRESSURE_OVER_MAX = 4,
    /* Value 5 is intentionally reserved to preserve the wire enum. */
    PNEUMATIC_FAULT_HOLD_TIMEOUT = 6,
    PNEUMATIC_FAULT_CONFIGURATION = 7,
} pneumatic_fault_t;

typedef enum {
    PNEUMATIC_TRIGGER_NONE = 0,
    PNEUMATIC_TRIGGER_VISION_CRITICAL,
    PNEUMATIC_TRIGGER_VISION_HIGH,
    PNEUMATIC_TRIGGER_VISION_ATTENTION,
    PNEUMATIC_TRIGGER_MPU_IMPACT,
    PNEUMATIC_TRIGGER_MPU_RAPID_TILT,
    PNEUMATIC_TRIGGER_MANUAL_CALIBRATION,
} pneumatic_trigger_t;

typedef enum {
    PNEUMATIC_OPERATION_NONE = 0,
    PNEUMATIC_OPERATION_AUTOMATIC,
    PNEUMATIC_OPERATION_CALIBRATION,
} pneumatic_operation_t;

typedef struct {
    bool calibration_enabled;
    bool automatic_enabled;
    bool calibration_valid;
    float target_kpa;
    float max_kpa; /* Software control limit, at most 20 kPa; sensor range is defined separately. */
} pneumatic_policy_config_t;

typedef struct {
    action_state_t vision_state;
    bool vision_fresh;
    bool motion_impact;
    bool motion_rapid_tilt;
    bool automatic_permitted;
    bool vision_trigger_permitted;
    bool motion_trigger_permitted;
    bool pressure_valid;
    float pressure_kpa;
    uint64_t pressure_timestamp_ms;
    bool manual_inflate_pulse;
    uint32_t manual_inflate_duration_ms;
    bool vent_request;
    bool emergency_stop;
    bool reset_fault;
    bool actuation_hazard_present;
    bool actuation_hazard_active;
} pneumatic_policy_input_t;

typedef struct {
    pneumatic_policy_config_t config;
    pneumatic_state_t state;
    pneumatic_fault_t fault;
    pneumatic_trigger_t trigger_source;
    pneumatic_operation_t operation;
    uint64_t state_started_ms;
    uint64_t pressure_invalid_started_ms;
    uint64_t clear_started_ms;
    uint32_t calibration_pump_on_ms;
    float active_target_kpa;
} pneumatic_policy_t;

typedef struct {
    pneumatic_state_t state;
    pneumatic_fault_t fault;
    pneumatic_trigger_t trigger_source;
    pneumatic_operation_t operation;
    bool pump_on;
    bool valve_on;
} pneumatic_policy_output_t;

pneumatic_policy_config_t pneumatic_policy_default_config(void);
bool pneumatic_policy_config_is_valid(const pneumatic_policy_config_t *config);
void pneumatic_policy_init(pneumatic_policy_t *policy, const pneumatic_policy_config_t *config, uint64_t now_ms);
pneumatic_policy_output_t pneumatic_policy_step(
    pneumatic_policy_t *policy,
    const pneumatic_policy_input_t *input,
    uint64_t now_ms);
const char *pneumatic_state_name(pneumatic_state_t state);
const char *pneumatic_fault_name(pneumatic_fault_t fault);
const char *pneumatic_trigger_name(pneumatic_trigger_t trigger);
