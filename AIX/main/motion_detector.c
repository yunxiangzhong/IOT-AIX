#include "motion_detector.h"

#include <math.h>
#include <stddef.h>

#define MOTION_DETECTOR_RAD_TO_DEG 57.29577951308232f

static float vector_norm(float x, float y, float z) {
    return sqrtf(x * x + y * y + z * z);
}

static motion_output_t build_output(
    const motion_detector_t *detector,
    float accel_norm_g,
    float gyro_norm_dps,
    float tilt_deg) {
    return (motion_output_t){
        .calibrated = detector->calibrated,
        .calibration_samples = detector->calibration_samples,
        .accel_norm_g = accel_norm_g,
        .gyro_norm_dps = gyro_norm_dps,
        .tilt_deg = tilt_deg,
        .impact = detector->impact_latched,
        .rapid_tilt = detector->rapid_tilt_latched,
        .danger_latched = detector->impact_latched || detector->rapid_tilt_latched,
    };
}

void motion_detector_init(motion_detector_t *detector, uint64_t now_ms) {
    (void)now_ms;
    if (detector == NULL) {
        return;
    }
    *detector = (motion_detector_t){
        .calibration_window_stationary = true,
    };
}

motion_output_t motion_detector_step(
    motion_detector_t *detector,
    const motion_sample_t *sample,
    uint64_t now_ms) {
    if (detector == NULL || sample == NULL) {
        return (motion_output_t){0};
    }

    const float accel_norm_g = vector_norm(sample->accel_x_g, sample->accel_y_g, sample->accel_z_g);
    const float gyro_norm_dps = vector_norm(sample->gyro_x_dps, sample->gyro_y_dps, sample->gyro_z_dps);
    const float horizontal_accel_g = sqrtf(sample->accel_x_g * sample->accel_x_g +
                                           sample->accel_y_g * sample->accel_y_g);
    const float tilt_deg = atan2f(horizontal_accel_g, fabsf(sample->accel_z_g)) * MOTION_DETECTOR_RAD_TO_DEG;

    if (!detector->calibrated) {
        const bool stationary = accel_norm_g >= 0.9f && accel_norm_g <= 1.1f && gyro_norm_dps < 10.0f;
        detector->calibration_window_stationary &= stationary;
        detector->calibration_samples++;
        if (detector->calibration_samples >= MOTION_DETECTOR_CALIBRATION_SAMPLES) {
            if (detector->calibration_window_stationary) {
                detector->calibrated = true;
            } else {
                detector->calibration_samples = 0;
                detector->calibration_window_stationary = true;
            }
        }
        return build_output(detector, accel_norm_g, gyro_norm_dps, tilt_deg);
    }

    if (accel_norm_g >= MOTION_DETECTOR_IMPACT_THRESHOLD_G) {
        if (detector->impact_consecutive_samples < UINT8_MAX) {
            detector->impact_consecutive_samples++;
        }
        if (detector->impact_consecutive_samples >= MOTION_DETECTOR_IMPACT_SAMPLES) {
            detector->impact_latched = true;
        }
    } else {
        detector->impact_consecutive_samples = 0;
    }

    if (tilt_deg > MOTION_DETECTOR_RAPID_TILT_DEG && gyro_norm_dps >= MOTION_DETECTOR_RAPID_TILT_DPS) {
        if (detector->rapid_tilt_started_ms == 0) {
            detector->rapid_tilt_started_ms = now_ms;
        } else if (now_ms - detector->rapid_tilt_started_ms >= MOTION_DETECTOR_RAPID_TILT_MS) {
            detector->rapid_tilt_latched = true;
        }
    } else {
        detector->rapid_tilt_started_ms = 0;
    }

    if (detector->impact_latched || detector->rapid_tilt_latched) {
        const bool stable = tilt_deg < 30.0f && accel_norm_g >= 0.8f && accel_norm_g <= 1.2f && gyro_norm_dps < 20.0f;
        if (stable) {
            if (detector->stable_started_ms == 0) {
                detector->stable_started_ms = now_ms;
            } else if (now_ms - detector->stable_started_ms >= MOTION_DETECTOR_CLEAR_MS) {
                detector->impact_latched = false;
                detector->rapid_tilt_latched = false;
                detector->stable_started_ms = 0;
            }
        } else {
            detector->stable_started_ms = 0;
        }
    }

    return build_output(detector, accel_norm_g, gyro_norm_dps, tilt_deg);
}
