#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "pneumatic_policy.h"

static pneumatic_policy_input_t safe_input(void)
{
    return (pneumatic_policy_input_t){
        .pressure_valid = true,
        .automatic_permitted = true,
        .vision_trigger_permitted = true,
        .motion_trigger_permitted = true,
        .pressure_kpa = 5.6f,
        .pressure_timestamp_ms = 0,
    };
}

static pneumatic_policy_config_t automatic_config(void)
{
    pneumatic_policy_config_t config = pneumatic_policy_default_config();
    config.automatic_enabled = true;
    config.calibration_valid = true;
    config.target_kpa = 8.0f;
    config.max_kpa = 200.0f;
    config.max_inflate_ms = 1000;
    return config;
}

static void test_high_risk_starts_pump_and_threshold_releases_airbag(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(!output.pump_on && output.valve_on);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_VISION_HIGH);

    output = pneumatic_policy_step(&policy, &input, 21);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);

    // A continuing high-risk callback must not hit max_inflate_ms and fault.
    input.pressure_timestamp_ms = 2022;
    output = pneumatic_policy_step(&policy, &input, 2022);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);
    assert(output.fault == PNEUMATIC_FAULT_NONE);

    input.pressure_kpa = 8.0f;
    input.pressure_timestamp_ms = 2023;
    output = pneumatic_policy_step(&policy, &input, 2023);
    assert(output.state == PNEUMATIC_STATE_VENTING);
    assert(!output.pump_on && !output.valve_on);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_VISION_HIGH);
}

static void test_visual_high_risk_does_not_require_mpu_trigger(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;
    input.vision_trigger_permitted = false;
    input.motion_trigger_permitted = false;

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(!output.pump_on && output.valve_on);
}

static void test_invalid_or_stale_pressure_forces_exhaust(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 1000);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;
    input.pressure_timestamp_ms = 1001;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1001);
    output = pneumatic_policy_step(&policy, &input, 1021);
    assert(output.state == PNEUMATIC_STATE_INFLATING);

    input.pressure_valid = false;
    output = pneumatic_policy_step(&policy, &input, 1022);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);

    output = pneumatic_policy_step(&policy, &input, 1122);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(!output.pump_on && !output.valve_on);
    assert(output.fault == PNEUMATIC_FAULT_PRESSURE_INVALID);
}

static void test_manual_pulse_remains_available_without_automatic_mode(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = pneumatic_policy_default_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.manual_inflate_pulse = true;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    output = pneumatic_policy_step(&policy, &input, 21);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);
}

int main(void)
{
    test_high_risk_starts_pump_and_threshold_releases_airbag();
    test_visual_high_risk_does_not_require_mpu_trigger();
    test_invalid_or_stale_pressure_forces_exhaust();
    test_manual_pulse_remains_available_without_automatic_mode();
    puts("pneumatic_policy_test: PASS");
    return 0;
}
