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

static void test_pressure_feedback_allows_automatic_mode_without_self_test(void)
{
    const hardware_health_input_t input = ready_input();
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_HEALTHY);
    assert(health.automatic_ready);
    assert(health.pump == HARDWARE_HEALTH_HEALTHY);
    assert(health.valve == HARDWARE_HEALTH_HEALTHY);
}

static void test_unverified_pump_and_valve_remain_non_blocking(void)
{
    hardware_health_input_t input = ready_input();
    input.pump_verified = false;
    input.valve_verified = false;
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_HEALTHY);
    assert(health.automatic_ready);
    assert(health.pump == HARDWARE_HEALTH_HEALTHY);
    assert(health.valve == HARDWARE_HEALTH_HEALTHY);
}

static void test_self_test_result_does_not_change_pressure_feedback_mode(void)
{
    hardware_health_input_t input = ready_input();
    input.pump_verified = false;
    input.valve_verified = false;
    input.self_test_failed = true;
    const hardware_health_snapshot_t health = hardware_health_evaluate(&input);
    assert(health.overall == HARDWARE_HEALTH_HEALTHY);
    assert(health.automatic_ready);
    assert(health.pump == HARDWARE_HEALTH_HEALTHY);
    assert(health.valve == HARDWARE_HEALTH_HEALTHY);
}

int main(void)
{
    test_pressure_feedback_allows_automatic_mode_without_self_test();
    test_unverified_pump_and_valve_remain_non_blocking();
    test_self_test_result_does_not_change_pressure_feedback_mode();
    puts("hardware_health_test: PASS");
    return 0;
}
