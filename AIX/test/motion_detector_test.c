#include <assert.h>
#include <math.h>
#include <stdio.h>

#include "motion_detector.h"

static motion_sample_t stationary_sample(void) {
    return (motion_sample_t){
        .accel_z_g = 1.0f,
    };
}

static void calibrate(motion_detector_t *detector, uint64_t start_ms) {
    const motion_sample_t sample = stationary_sample();
    for (uint16_t index = 0; index < MOTION_DETECTOR_CALIBRATION_SAMPLES; ++index) {
        const motion_output_t output = motion_detector_step(detector, &sample, start_ms + (uint64_t)index * 10U);
        if (index + 1 == MOTION_DETECTOR_CALIBRATION_SAMPLES) {
            assert(output.calibrated);
        }
    }
}

static void test_calibration_retries_after_nonstationary_window(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);

    motion_sample_t moving = stationary_sample();
    moving.gyro_x_dps = 11.0f;
    for (uint16_t index = 0; index < MOTION_DETECTOR_CALIBRATION_SAMPLES; ++index) {
        const motion_output_t output = motion_detector_step(&detector, &moving, (uint64_t)index * 10U);
        assert(!output.calibrated);
    }

    calibrate(&detector, 2000);
}

static void test_collision_delta_threshold_latches_impact(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t sample = stationary_sample();
    motion_output_t output = motion_detector_step(&detector, &sample, 2000);
    assert(!output.impact_event);

    sample.accel_z_g = 2.19f;
    output = motion_detector_step(&detector, &sample, 2010);
    assert(!output.impact_event);
    assert(!output.impact);
    assert(fabsf(output.accel_delta_g - 1.19f) < 0.001f);

    output = motion_detector_step(&detector, &sample, 2020);
    assert(!output.impact_event);
    assert(!output.impact);

    sample.accel_z_g = 0.99f;
    output = motion_detector_step(&detector, &sample, 2030);
    assert(output.impact_event);
    assert(output.impact);
    assert(output.danger_latched);
    assert(output.impact_count == 1U);
    assert(output.sample_interval_ms == 10U);
    assert(fabsf(output.accel_delta_g - 1.20f) < 0.001f);
}

static void test_invalid_sample_intervals_refresh_collision_baseline(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t sample = stationary_sample();
    motion_detector_step(&detector, &sample, 2000);

    sample.accel_z_g = 2.3f;
    motion_output_t output = motion_detector_step(&detector, &sample, 2021);
    assert(!output.impact_event);
    output = motion_detector_step(&detector, &sample, 2031);
    assert(!output.impact_event);

    sample.accel_z_g = 1.0f;
    output = motion_detector_step(&detector, &sample, 2031);
    assert(!output.impact_event);
    output = motion_detector_step(&detector, &sample, 2041);
    assert(!output.impact_event);

    sample.accel_z_g = 2.3f;
    output = motion_detector_step(&detector, &sample, 2000);
    assert(!output.impact_event);
    output = motion_detector_step(&detector, &sample, 2010);
    assert(!output.impact_event);
    assert(output.impact_count == 0U);
}

static void test_collision_refractory_period_merges_ringing(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t sample = stationary_sample();
    motion_detector_step(&detector, &sample, 2000);

    sample.accel_z_g = 2.3f;
    motion_output_t output = motion_detector_step(&detector, &sample, 2010);
    assert(output.impact_event);
    assert(output.impact_count == 1U);

    sample.accel_z_g = 1.0f;
    output = motion_detector_step(&detector, &sample, 2020);
    assert(!output.impact_event);
    assert(output.impact_count == 1U);

    output = motion_detector_step(&detector, &sample, 2200);
    assert(!output.impact_event);
    sample.accel_z_g = 2.3f;
    output = motion_detector_step(&detector, &sample, 2210);
    assert(output.impact_event);
    assert(output.impact_count == 2U);
}

static void test_collision_is_not_detected_before_calibration(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);

    motion_sample_t sample = stationary_sample();
    motion_output_t output = motion_detector_step(&detector, &sample, 0);
    assert(!output.impact_event);
    sample.accel_z_g = 2.3f;
    output = motion_detector_step(&detector, &sample, 10);
    assert(!output.impact_event);
    assert(!output.impact);
    assert(output.impact_count == 0U);
}

static void test_rapid_tilt_latches_and_clears_only_after_stable_five_seconds(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t tilt = {
        .accel_x_g = 0.77f,
        .accel_z_g = 0.64f,
        .gyro_y_dps = 90.0f,
    };
    motion_output_t output = {0};
    for (int index = 0; index <= 20; ++index) {
        output = motion_detector_step(&detector, &tilt, 2000U + (uint64_t)index * 10U);
    }
    assert(output.rapid_tilt);
    assert(output.tilt_deg > 45.0f);

    motion_sample_t stable = stationary_sample();
    output = motion_detector_step(&detector, &stable, 2300);
    assert(output.danger_latched);
    output = motion_detector_step(&detector, &stable, 7300);
    assert(!output.impact);
    assert(!output.rapid_tilt);
    assert(!output.danger_latched);
}

static void test_sideways_mount_uses_relative_tilt_and_can_clear(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    const motion_sample_t sideways = {
        .accel_x_g = 1.0f,
    };
    for (uint16_t index = 0; index < MOTION_DETECTOR_CALIBRATION_SAMPLES; ++index) {
        motion_detector_step(&detector, &sideways, (uint64_t)index * 10U);
    }
    assert(detector.calibrated);

    motion_sample_t impact = sideways;
    impact.accel_x_g = 2.3f;
    motion_output_t output = motion_detector_step(&detector, &impact, 2000);
    assert(output.impact_event);
    assert(output.impact);

    output = motion_detector_step(&detector, &sideways, 2010);
    assert(output.tilt_deg < 1.0f);
    output = motion_detector_step(&detector, &sideways, 7010);
    assert(!output.danger_latched);
}

static void test_sideways_rest_does_not_clear_collision_danger(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t impact = stationary_sample();
    impact.accel_z_g = 2.3f;
    motion_output_t output = motion_detector_step(&detector, &impact, 2000);
    assert(output.impact_event);

    const motion_sample_t sideways = {
        .accel_x_g = 1.0f,
    };
    output = motion_detector_step(&detector, &sideways, 2010);
    assert(output.tilt_deg > 89.0f);
    output = motion_detector_step(&detector, &sideways, 7010);
    assert(output.danger_latched);
}

int main(void) {
    test_calibration_retries_after_nonstationary_window();
    test_collision_delta_threshold_latches_impact();
    test_invalid_sample_intervals_refresh_collision_baseline();
    test_collision_refractory_period_merges_ringing();
    test_collision_is_not_detected_before_calibration();
    test_rapid_tilt_latches_and_clears_only_after_stable_five_seconds();
    test_sideways_mount_uses_relative_tilt_and_can_clear();
    test_sideways_rest_does_not_clear_collision_danger();
    puts("motion_detector_test: PASS");
    return 0;
}
