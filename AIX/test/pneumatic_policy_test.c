#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "pneumatic_policy.h"

static pneumatic_policy_input_t safe_input(void) {
    pneumatic_policy_input_t input = {
        .pressure_valid = true,
        .pressure_kpa = 0.0f,
        .pressure_timestamp_ms = 0,
    };
    return input;
}

static pneumatic_policy_config_t automatic_config(void) {
    pneumatic_policy_config_t config = pneumatic_policy_default_config();
    config.automatic_enabled = true;
    config.calibration_valid = true;
    config.target_kpa = 2.0f;
    config.max_kpa = 4.0f;
    config.max_inflate_ms = 1000;
    return config;
}

static void test_visual_high_primes_then_inflates_and_holds_at_target(void) {
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);

    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(!output.pump_on);
    assert(output.valve_on);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_VISION_HIGH);

    output = pneumatic_policy_step(&policy, &input, 21);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on);
    assert(output.valve_on);

    input.pressure_kpa = 2.0f;
    input.pressure_timestamp_ms = 22;
    output = pneumatic_policy_step(&policy, &input, 22);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    assert(!output.pump_on);
    assert(output.valve_on);
}

static void test_invalid_or_stale_pressure_never_turns_pump_on(void) {
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 1000);

    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_CRITICAL;
    input.vision_fresh = true;
    input.pressure_valid = false;

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1001);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(!output.pump_on);
    assert(!output.valve_on);
    assert(output.fault == PNEUMATIC_FAULT_PRESSURE_INVALID);

    pneumatic_policy_init(&policy, &config, 1000);
    input = safe_input();
    input.vision_state = ACTION_STATE_CRITICAL;
    input.vision_fresh = true;
    input.pressure_timestamp_ms = 500;

    output = pneumatic_policy_step(&policy, &input, 1001);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(!output.pump_on);
    assert(!output.valve_on);
    assert(output.fault == PNEUMATIC_FAULT_PRESSURE_STALE);
}

static void test_mpu_trigger_holds_then_automatically_vents_and_cools_down(void) {
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);

    pneumatic_policy_input_t input = safe_input();
    input.motion_impact = true;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_MPU_IMPACT);

    output = pneumatic_policy_step(&policy, &input, 21);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    input.pressure_kpa = 2.0f;
    input.pressure_timestamp_ms = 22;
    output = pneumatic_policy_step(&policy, &input, 22);
    assert(output.state == PNEUMATIC_STATE_HOLDING);

    input.motion_impact = false;
    input.pressure_timestamp_ms = 23;
    output = pneumatic_policy_step(&policy, &input, 23);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    input.pressure_timestamp_ms = 5023;
    output = pneumatic_policy_step(&policy, &input, 5023);
    assert(output.state == PNEUMATIC_STATE_VENTING);
    assert(!output.pump_on);
    assert(!output.valve_on);

    input.pressure_kpa = 0.4f;
    input.pressure_timestamp_ms = 5024;
    output = pneumatic_policy_step(&policy, &input, 5024);
    assert(output.state == PNEUMATIC_STATE_COOLDOWN);
    input.pressure_timestamp_ms = 15024;
    output = pneumatic_policy_step(&policy, &input, 15024);
    assert(output.state == PNEUMATIC_STATE_VENTED);
}

static void test_overpressure_fault_is_latched_until_safe_reset(void) {
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);

    pneumatic_policy_input_t input = safe_input();
    input.pressure_kpa = 4.1f;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(output.fault == PNEUMATIC_FAULT_PRESSURE_OVER_MAX);
    assert(!output.pump_on);
    assert(!output.valve_on);

    input.pressure_kpa = 0.4f;
    input.pressure_timestamp_ms = 2;
    output = pneumatic_policy_step(&policy, &input, 2);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    input.reset_fault = true;
    output = pneumatic_policy_step(&policy, &input, 2);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    assert(output.fault == PNEUMATIC_FAULT_NONE);
}

int main(void) {
    test_visual_high_primes_then_inflates_and_holds_at_target();
    test_invalid_or_stale_pressure_never_turns_pump_on();
    test_mpu_trigger_holds_then_automatically_vents_and_cools_down();
    test_overpressure_fault_is_latched_until_safe_reset();
    puts("pneumatic_policy_test: PASS");
    return 0;
}
