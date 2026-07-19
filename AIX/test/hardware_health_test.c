#include <assert.h>
#include <stdio.h>

#include "hardware_health.h"

static hardware_health_input_t ready_input(void)
{
    return (hardware_health_input_t){
        .camera_healthy = true,
        .network_healthy = true,
        .mpu_healthy = true,
        .pressure_healthy = true,
        .dfplayer_healthy = true,
        .rgb_healthy = true,
        .pneumatic_started = true,
        .pump_verified = true,
        .valve_verified = true,
    };
}

static void test_all_verified_modules_allow_automatic_mode(void)
{
    const hardware_health_input_t input = ready_input();
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_HEALTHY);
    assert(health.automatic_ready);
    assert(health.pump == HARDWARE_HEALTH_HEALTHY);
    assert(health.valve == HARDWARE_HEALTH_HEALTHY);
}

static void test_unverified_pump_and_valve_do_not_block_pressure_release_mode(void)
{
    hardware_health_input_t input = ready_input();
    input.pump_verified = false;
    input.valve_verified = false;
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_DEGRADED);
    assert(health.automatic_ready);
    assert(health.pump == HARDWARE_HEALTH_PENDING);
    assert(health.valve == HARDWARE_HEALTH_PENDING);
}

static void test_failed_self_test_is_reported_as_a_real_pneumatic_fault(void)
{
    hardware_health_input_t input = ready_input();
    input.pump_verified = false;
    input.valve_verified = false;
    input.self_test_failed = true;
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_FAULT);
    assert(health.pump == HARDWARE_HEALTH_FAULT);
    assert(health.valve == HARDWARE_HEALTH_FAULT);
}

int main(void)
{
    test_all_verified_modules_allow_automatic_mode();
    test_unverified_pump_and_valve_do_not_block_pressure_release_mode();
    test_failed_self_test_is_reported_as_a_real_pneumatic_fault();
    puts("hardware_health_test: PASS");
    return 0;
}
