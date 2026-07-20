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
    config.max_kpa = 12.0f;
    config.max_inflate_ms = 1000;
    return config;
}

static void test_high_risk_starts_pump_holds_then_vents_after_clear(void)
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

    input.pressure_kpa = 8.0f;
    input.pressure_timestamp_ms = 22;
    output = pneumatic_policy_step(&policy, &input, 22);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    assert(!output.pump_on && output.valve_on);

    input.vision_fresh = false;
    input.pressure_timestamp_ms = 23;
    output = pneumatic_policy_step(&policy, &input, 23);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    input.pressure_timestamp_ms = 5023;
    output = pneumatic_policy_step(&policy, &input, 5023);
    assert(output.state == PNEUMATIC_STATE_VENTING);
    assert(!output.pump_on && !output.valve_on);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_NONE);
}

static void test_automatic_inflate_timeout_forces_fault_vent(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;
    pneumatic_policy_step(&policy, &input, 1);
    pneumatic_policy_step(&policy, &input, 21);
    input.pressure_timestamp_ms = 1021;
    const pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1021);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(!output.pump_on && !output.valve_on);
    assert(output.fault == PNEUMATIC_FAULT_INFLATE_TIMEOUT);
}

static void test_high_risk_trigger_latches_until_target_after_signal_clears(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;

    pneumatic_policy_step(&policy, &input, 1);
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 21);
    assert(output.state == PNEUMATIC_STATE_INFLATING);

    input.vision_fresh = false;
    input.pressure_timestamp_ms = 200;
    output = pneumatic_policy_step(&policy, &input, 200);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_VISION_HIGH);

    input.pressure_kpa = config.target_kpa;
    input.pressure_timestamp_ms = 300;
    output = pneumatic_policy_step(&policy, &input, 300);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    assert(!output.pump_on && output.valve_on);
}

static void test_active_risk_refills_when_pressure_drops_below_target(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_HIGH;
    input.vision_fresh = true;

    pneumatic_policy_step(&policy, &input, 1);
    pneumatic_policy_step(&policy, &input, 21);
    input.pressure_kpa = config.target_kpa;
    input.pressure_timestamp_ms = 22;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 22);
    assert(output.state == PNEUMATIC_STATE_HOLDING);

    input.pressure_kpa = config.target_kpa - PNEUMATIC_REFILL_HYSTERESIS_KPA - 0.1f;
    input.pressure_timestamp_ms = 23;
    output = pneumatic_policy_step(&policy, &input, 23);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(!output.pump_on && output.valve_on);
    output = pneumatic_policy_step(&policy, &input, 43);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on && output.valve_on);
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

static void test_attention_does_not_inflate_but_high_starts_full_target(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_state = ACTION_STATE_ATTENTION;
    input.vision_fresh = true;

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_NONE);

    input.vision_state = ACTION_STATE_HIGH;
    input.pressure_timestamp_ms = 2;
    output = pneumatic_policy_step(&policy, &input, 2);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_VISION_HIGH);
    assert(policy.active_target_kpa == config.target_kpa);
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

static void test_stale_pressure_has_startup_grace_then_faults(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();

    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 250);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    assert(output.fault == PNEUMATIC_FAULT_NONE);

    input.pressure_timestamp_ms = 260;
    output = pneumatic_policy_step(&policy, &input, 260);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    assert(output.fault == PNEUMATIC_FAULT_NONE);

    output = pneumatic_policy_step(&policy, &input, 461);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    output = pneumatic_policy_step(&policy, &input, 561);
    assert(output.state == PNEUMATIC_STATE_FAULT_VENT);
    assert(output.fault == PNEUMATIC_FAULT_PRESSURE_STALE);
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

static void test_self_test_can_request_a_longer_calibration_pulse(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.manual_inflate_pulse = true;
    input.manual_inflate_duration_ms = 800;

    pneumatic_policy_step(&policy, &input, 1);
    input.manual_inflate_pulse = false;
    pneumatic_policy_step(&policy, &input, 21);
    input.pressure_timestamp_ms = 222;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 222);
    assert(output.state == PNEUMATIC_STATE_INFLATING);
    assert(output.pump_on);

    input.pressure_timestamp_ms = 822;
    output = pneumatic_policy_step(&policy, &input, 822);
    assert(output.state == PNEUMATIC_STATE_HOLDING);
    assert(!output.pump_on);
}

int main(void)
{
    test_high_risk_starts_pump_holds_then_vents_after_clear();
    test_automatic_inflate_timeout_forces_fault_vent();
    test_high_risk_trigger_latches_until_target_after_signal_clears();
    test_active_risk_refills_when_pressure_drops_below_target();
    test_visual_high_risk_does_not_require_mpu_trigger();
    test_attention_does_not_inflate_but_high_starts_full_target();
    test_invalid_or_stale_pressure_forces_exhaust();
    test_stale_pressure_has_startup_grace_then_faults();
    test_manual_pulse_remains_available_without_automatic_mode();
    test_self_test_can_request_a_longer_calibration_pulse();
    puts("pneumatic_policy_test: PASS");
    return 0;
}
