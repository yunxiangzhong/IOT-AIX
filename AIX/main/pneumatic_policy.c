#include "pneumatic_policy.h"

#include <stddef.h>

static bool pressure_is_fresh(const pneumatic_policy_input_t *input, uint64_t now_ms) {
    if (!input->pressure_valid || now_ms < input->pressure_timestamp_ms) {
        return false;
    }
    return (now_ms - input->pressure_timestamp_ms) <= PNEUMATIC_PRESSURE_STALE_MS;
}

static pneumatic_trigger_t current_automatic_trigger(const pneumatic_policy_input_t *input) {
    if (input->vision_fresh && input->vision_state == ACTION_STATE_CRITICAL) {
        return PNEUMATIC_TRIGGER_VISION_CRITICAL;
    }
    if (input->vision_fresh && input->vision_state == ACTION_STATE_HIGH) {
        return PNEUMATIC_TRIGGER_VISION_HIGH;
    }
    if (input->motion_impact) {
        return PNEUMATIC_TRIGGER_MPU_IMPACT;
    }
    if (input->motion_rapid_tilt) {
        return PNEUMATIC_TRIGGER_MPU_RAPID_TILT;
    }
    return PNEUMATIC_TRIGGER_NONE;
}

static void enter_state(pneumatic_policy_t *policy, pneumatic_state_t state, uint64_t now_ms) {
    policy->state = state;
    policy->state_started_ms = now_ms;
    policy->clear_started_ms = 0;
    if (state == PNEUMATIC_STATE_INFLATING) {
        policy->inflate_started_ms = now_ms;
    }
}

static void enter_fault(pneumatic_policy_t *policy, pneumatic_fault_t fault, uint64_t now_ms) {
    policy->fault = fault;
    policy->operation = PNEUMATIC_OPERATION_NONE;
    policy->trigger_source = PNEUMATIC_TRIGGER_NONE;
    enter_state(policy, PNEUMATIC_STATE_FAULT_VENT, now_ms);
}

static pneumatic_policy_output_t output_from_policy(const pneumatic_policy_t *policy) {
    pneumatic_policy_output_t output = {
        .state = policy->state,
        .fault = policy->fault,
        .trigger_source = policy->trigger_source,
        .operation = policy->operation,
        .pump_on = policy->state == PNEUMATIC_STATE_INFLATING,
        .valve_on = policy->state == PNEUMATIC_STATE_PRIME_VALVE ||
                    policy->state == PNEUMATIC_STATE_INFLATING ||
                    policy->state == PNEUMATIC_STATE_HOLDING,
    };
    return output;
}

pneumatic_policy_config_t pneumatic_policy_default_config(void) {
    return (pneumatic_policy_config_t){
        .calibration_enabled = true,
        .automatic_enabled = false,
        .calibration_valid = false,
        .target_kpa = 2.0f,
        .max_kpa = 4.0f,
        .max_inflate_ms = 2000,
    };
}

bool pneumatic_policy_config_is_valid(const pneumatic_policy_config_t *config) {
    if (config == NULL || config->target_kpa < 2.0f || config->target_kpa > 30.0f) {
        return false;
    }
    if (config->max_kpa < config->target_kpa + 2.0f || config->max_kpa > 40.0f) {
        return false;
    }
    return config->max_inflate_ms >= 200U && config->max_inflate_ms <= 5000U;
}

void pneumatic_policy_init(pneumatic_policy_t *policy, const pneumatic_policy_config_t *config, uint64_t now_ms) {
    if (policy == NULL) {
        return;
    }

    policy->config = config == NULL ? pneumatic_policy_default_config() : *config;
    policy->state = policy->config.calibration_enabled || policy->config.automatic_enabled
                        ? PNEUMATIC_STATE_VENTED
                        : PNEUMATIC_STATE_DISABLED;
    policy->fault = pneumatic_policy_config_is_valid(&policy->config)
                        ? PNEUMATIC_FAULT_NONE
                        : PNEUMATIC_FAULT_CONFIGURATION;
    policy->trigger_source = PNEUMATIC_TRIGGER_NONE;
    policy->operation = PNEUMATIC_OPERATION_NONE;
    policy->state_started_ms = now_ms;
    policy->inflate_started_ms = 0;
    policy->clear_started_ms = 0;
    policy->calibration_pump_on_ms = 0;
    if (policy->fault != PNEUMATIC_FAULT_NONE) {
        policy->state = PNEUMATIC_STATE_FAULT_VENT;
    }
}

pneumatic_policy_output_t pneumatic_policy_step(
    pneumatic_policy_t *policy,
    const pneumatic_policy_input_t *input,
    uint64_t now_ms) {
    if (policy == NULL || input == NULL) {
        return (pneumatic_policy_output_t){
            .state = PNEUMATIC_STATE_FAULT_VENT,
            .fault = PNEUMATIC_FAULT_CONFIGURATION,
        };
    }

    if (policy->state == PNEUMATIC_STATE_DISABLED) {
        return output_from_policy(policy);
    }

    const pneumatic_trigger_t automatic_trigger = current_automatic_trigger(input);
    const bool pressure_fresh = pressure_is_fresh(input, now_ms);
    const bool automatic_allowed = policy->config.automatic_enabled && policy->config.calibration_valid;

    if (policy->state == PNEUMATIC_STATE_FAULT_VENT) {
        if (input->reset_fault && pressure_fresh && input->pressure_kpa <= PNEUMATIC_VENTED_PRESSURE_KPA &&
            automatic_trigger == PNEUMATIC_TRIGGER_NONE) {
            policy->fault = PNEUMATIC_FAULT_NONE;
            enter_state(policy, PNEUMATIC_STATE_VENTED, now_ms);
        }
        return output_from_policy(policy);
    }

    if (input->emergency_stop) {
        enter_fault(policy, PNEUMATIC_FAULT_EMERGENCY_STOP, now_ms);
        return output_from_policy(policy);
    }
    if (!input->pressure_valid) {
        enter_fault(policy, PNEUMATIC_FAULT_PRESSURE_INVALID, now_ms);
        return output_from_policy(policy);
    }
    if (!pressure_fresh) {
        enter_fault(policy, PNEUMATIC_FAULT_PRESSURE_STALE, now_ms);
        return output_from_policy(policy);
    }
    if (input->pressure_kpa > policy->config.max_kpa) {
        enter_fault(policy, PNEUMATIC_FAULT_PRESSURE_OVER_MAX, now_ms);
        return output_from_policy(policy);
    }
    if (input->vent_request) {
        policy->operation = PNEUMATIC_OPERATION_NONE;
        policy->trigger_source = PNEUMATIC_TRIGGER_NONE;
        enter_state(policy, PNEUMATIC_STATE_VENTING, now_ms);
        return output_from_policy(policy);
    }

    switch (policy->state) {
        case PNEUMATIC_STATE_VENTED:
            if (automatic_allowed && automatic_trigger != PNEUMATIC_TRIGGER_NONE) {
                policy->operation = PNEUMATIC_OPERATION_AUTOMATIC;
                policy->trigger_source = automatic_trigger;
                enter_state(policy, PNEUMATIC_STATE_PRIME_VALVE, now_ms);
            } else if (policy->config.calibration_enabled && input->manual_inflate_pulse &&
                       input->pressure_kpa < PNEUMATIC_CALIBRATION_CEILING_KPA &&
                       policy->calibration_pump_on_ms < PNEUMATIC_CALIBRATION_TOTAL_PUMP_MS) {
                policy->operation = PNEUMATIC_OPERATION_CALIBRATION;
                policy->trigger_source = PNEUMATIC_TRIGGER_MANUAL_CALIBRATION;
                enter_state(policy, PNEUMATIC_STATE_PRIME_VALVE, now_ms);
            }
            break;

        case PNEUMATIC_STATE_PRIME_VALVE:
            if (now_ms - policy->state_started_ms >= PNEUMATIC_PRIME_VALVE_MS) {
                enter_state(policy, PNEUMATIC_STATE_INFLATING, now_ms);
            }
            break;

        case PNEUMATIC_STATE_INFLATING: {
            const uint64_t elapsed_ms = now_ms - policy->inflate_started_ms;
            const uint64_t maximum_ms = policy->operation == PNEUMATIC_OPERATION_CALIBRATION
                                            ? PNEUMATIC_CALIBRATION_PULSE_MS
                                            : policy->config.max_inflate_ms;
            if (policy->operation == PNEUMATIC_OPERATION_AUTOMATIC && input->pressure_kpa >= policy->config.target_kpa) {
                enter_state(policy, PNEUMATIC_STATE_HOLDING, now_ms);
            } else if (policy->operation == PNEUMATIC_OPERATION_CALIBRATION &&
                       input->pressure_kpa >= PNEUMATIC_CALIBRATION_CEILING_KPA) {
                enter_state(policy, PNEUMATIC_STATE_HOLDING, now_ms);
            } else if (elapsed_ms >= maximum_ms) {
                if (policy->operation == PNEUMATIC_OPERATION_CALIBRATION) {
                    policy->calibration_pump_on_ms += (uint32_t)elapsed_ms;
                    enter_state(policy, PNEUMATIC_STATE_HOLDING, now_ms);
                } else {
                    enter_fault(policy, PNEUMATIC_FAULT_INFLATE_TIMEOUT, now_ms);
                }
            }
            break;
        }

        case PNEUMATIC_STATE_HOLDING:
            if (policy->operation == PNEUMATIC_OPERATION_AUTOMATIC) {
                if (automatic_trigger == PNEUMATIC_TRIGGER_NONE) {
                    if (policy->clear_started_ms == 0) {
                        policy->clear_started_ms = now_ms;
                    } else if (now_ms - policy->clear_started_ms >= PNEUMATIC_CLEAR_CONFIRM_MS) {
                        policy->operation = PNEUMATIC_OPERATION_NONE;
                        policy->trigger_source = PNEUMATIC_TRIGGER_NONE;
                        enter_state(policy, PNEUMATIC_STATE_VENTING, now_ms);
                    }
                } else {
                    policy->clear_started_ms = 0;
                    policy->trigger_source = automatic_trigger;
                }
            }
            if (policy->state == PNEUMATIC_STATE_HOLDING &&
                now_ms - policy->state_started_ms >= PNEUMATIC_HOLD_MAX_MS) {
                if (policy->operation == PNEUMATIC_OPERATION_CALIBRATION) {
                    policy->operation = PNEUMATIC_OPERATION_NONE;
                    policy->trigger_source = PNEUMATIC_TRIGGER_NONE;
                    enter_state(policy, PNEUMATIC_STATE_VENTING, now_ms);
                } else {
                    enter_fault(policy, PNEUMATIC_FAULT_HOLD_TIMEOUT, now_ms);
                }
            }
            break;

        case PNEUMATIC_STATE_VENTING:
            if (input->pressure_kpa <= PNEUMATIC_VENTED_PRESSURE_KPA ||
                now_ms - policy->state_started_ms >= PNEUMATIC_VENT_TIMEOUT_MS) {
                enter_state(policy, PNEUMATIC_STATE_COOLDOWN, now_ms);
            }
            break;

        case PNEUMATIC_STATE_COOLDOWN:
            if (now_ms - policy->state_started_ms >= PNEUMATIC_COOLDOWN_MS) {
                enter_state(policy, PNEUMATIC_STATE_VENTED, now_ms);
            }
            break;

        case PNEUMATIC_STATE_DISABLED:
        case PNEUMATIC_STATE_FAULT_VENT:
        default:
            break;
    }

    return output_from_policy(policy);
}

const char *pneumatic_state_name(pneumatic_state_t state) {
    switch (state) {
        case PNEUMATIC_STATE_DISABLED: return "disabled";
        case PNEUMATIC_STATE_VENTED: return "vented";
        case PNEUMATIC_STATE_PRIME_VALVE: return "prime_valve";
        case PNEUMATIC_STATE_INFLATING: return "inflating";
        case PNEUMATIC_STATE_HOLDING: return "holding";
        case PNEUMATIC_STATE_VENTING: return "venting";
        case PNEUMATIC_STATE_COOLDOWN: return "cooldown";
        case PNEUMATIC_STATE_FAULT_VENT: return "fault_vent";
        default: return "unknown";
    }
}

const char *pneumatic_fault_name(pneumatic_fault_t fault) {
    switch (fault) {
        case PNEUMATIC_FAULT_NONE: return "none";
        case PNEUMATIC_FAULT_EMERGENCY_STOP: return "emergency_stop";
        case PNEUMATIC_FAULT_PRESSURE_INVALID: return "pressure_invalid";
        case PNEUMATIC_FAULT_PRESSURE_STALE: return "pressure_stale";
        case PNEUMATIC_FAULT_PRESSURE_OVER_MAX: return "pressure_over_max";
        case PNEUMATIC_FAULT_INFLATE_TIMEOUT: return "inflate_timeout";
        case PNEUMATIC_FAULT_HOLD_TIMEOUT: return "hold_timeout";
        case PNEUMATIC_FAULT_CONFIGURATION: return "configuration";
        default: return "unknown";
    }
}

const char *pneumatic_trigger_name(pneumatic_trigger_t trigger) {
    switch (trigger) {
        case PNEUMATIC_TRIGGER_NONE: return "none";
        case PNEUMATIC_TRIGGER_VISION_CRITICAL: return "vision_critical";
        case PNEUMATIC_TRIGGER_VISION_HIGH: return "vision_high";
        case PNEUMATIC_TRIGGER_MPU_IMPACT: return "mpu_impact";
        case PNEUMATIC_TRIGGER_MPU_RAPID_TILT: return "mpu_rapid_tilt";
        case PNEUMATIC_TRIGGER_MANUAL_CALIBRATION: return "manual_calibration";
        default: return "unknown";
    }
}
