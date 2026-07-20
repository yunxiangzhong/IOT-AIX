#include <assert.h>
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

static void test_two_high_acceleration_samples_latch_impact(void) {
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t impact = stationary_sample();
    impact.accel_z_g = 2.1f;

    motion_output_t output = motion_detector_step(&detector, &impact, 2000);
    assert(!output.impact);
    output = motion_detector_step(&detector, &impact, 2010);
    assert(output.impact);
    assert(output.danger_latched);
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
    impact.accel_x_g = 2.1f;
    motion_detector_step(&detector, &impact, 2000);
    motion_output_t output = motion_detector_step(&detector, &impact, 2010);
    assert(output.impact);

    output = motion_detector_step(&detector, &sideways, 2020);
    assert(output.tilt_deg < 1.0f);
    output = motion_detector_step(&detector, &sideways, 7020);
    assert(!output.danger_latched);
}

int main(void) {
    test_calibration_retries_after_nonstationary_window();
    test_two_high_acceleration_samples_latch_impact();
    test_rapid_tilt_latches_and_clears_only_after_stable_five_seconds();
    test_sideways_mount_uses_relative_tilt_and_can_clear();
    puts("motion_detector_test: PASS");
    return 0;
}
