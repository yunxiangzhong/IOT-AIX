#pragma once

#include <stdbool.h>
#include <stdint.h>

#define MOTION_DETECTOR_CALIBRATION_SAMPLES 200U
#define MOTION_DETECTOR_IMPACT_DELTA_G 1.2f
#define MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS 20ULL
#define MOTION_DETECTOR_IMPACT_REFRACTORY_MS 200ULL
#define MOTION_DETECTOR_RAPID_TILT_DEG 45.0f
#define MOTION_DETECTOR_RAPID_TILT_DPS 80.0f
#define MOTION_DETECTOR_RAPID_TILT_MS 200ULL
#define MOTION_DETECTOR_CLEAR_MS 5000ULL

typedef struct {
    float accel_x_g;
    float accel_y_g;
    float accel_z_g;
    float gyro_x_dps;
    float gyro_y_dps;
    float gyro_z_dps;
} motion_sample_t;

typedef struct {
    bool calibrated;
    uint16_t calibration_samples;
    float accel_norm_g;
    float accel_delta_g;
    float gyro_norm_dps;
    float tilt_deg;
    uint32_t sample_interval_ms;
    bool impact_event;
    uint32_t impact_count;
    bool impact;
    bool rapid_tilt;
    bool danger_latched;
} motion_output_t;

typedef struct {
    bool calibrated;
    uint16_t calibration_samples;
    bool calibration_window_stationary;
    float calibration_accel_x_sum;
    float calibration_accel_y_sum;
    float calibration_accel_z_sum;
    float gravity_x_g;
    float gravity_y_g;
    float gravity_z_g;
    float previous_accel_norm_g;
    uint64_t previous_sample_ms;
    uint64_t last_impact_ms;
    uint32_t impact_count;
    bool has_previous_sample;
    uint64_t rapid_tilt_started_ms;
    uint64_t stable_started_ms;
    bool impact_latched;
    bool rapid_tilt_latched;
} motion_detector_t;

void motion_detector_init(motion_detector_t *detector, uint64_t now_ms);
motion_output_t motion_detector_step(
    motion_detector_t *detector,
    const motion_sample_t *sample,
    uint64_t now_ms);
