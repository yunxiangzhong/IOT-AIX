#include "motion_detector.h"

#include <math.h>
#include <stddef.h>

#define MOTION_DETECTOR_RAD_TO_DEG 57.29577951308232f

static float vector_norm(float x, float y, float z) {
    return sqrtf(x * x + y * y + z * z);
}

static float relative_tilt_deg(
    const motion_detector_t *detector,
    const motion_sample_t *sample,
    float accel_norm_g) {
    const float gravity_norm = vector_norm(
        detector->gravity_x_g,
        detector->gravity_y_g,
        detector->gravity_z_g);
    if (accel_norm_g <= 0.01f || gravity_norm <= 0.01f) {
        return 0.0f;
    }
    float cosine = (sample->accel_x_g * detector->gravity_x_g +
                    sample->accel_y_g * detector->gravity_y_g +
                    sample->accel_z_g * detector->gravity_z_g) /
                   (accel_norm_g * gravity_norm);
    if (cosine > 1.0f) {
        cosine = 1.0f;
    } else if (cosine < -1.0f) {
        cosine = -1.0f;
    }
    return acosf(cosine) * MOTION_DETECTOR_RAD_TO_DEG;
}

static motion_output_t build_output(
    const motion_detector_t *detector,
    float accel_norm_g,
    float accel_delta_g,
    float gyro_norm_dps,
    float tilt_deg,
    uint32_t sample_interval_ms,
    bool impact_event) {
    return (motion_output_t){
        .calibrated = detector->calibrated,
        .calibration_samples = detector->calibration_samples,
        .accel_norm_g = accel_norm_g,
        .accel_delta_g = accel_delta_g,
        .gyro_norm_dps = gyro_norm_dps,
        .tilt_deg = tilt_deg,
        .sample_interval_ms = sample_interval_ms,
        .impact_event = impact_event,
        .impact_count = detector->impact_count,
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
    float tilt_deg = 0.0f;

    if (!detector->calibrated) {
        const bool stationary = accel_norm_g >= 0.9f && accel_norm_g <= 1.1f && gyro_norm_dps < 10.0f;
        detector->calibration_window_stationary &= stationary;
        detector->calibration_accel_x_sum += sample->accel_x_g;
        detector->calibration_accel_y_sum += sample->accel_y_g;
        detector->calibration_accel_z_sum += sample->accel_z_g;
        detector->calibration_samples++;
        if (detector->calibration_samples >= MOTION_DETECTOR_CALIBRATION_SAMPLES) {
            if (detector->calibration_window_stationary) {
                const float sample_count = (float)detector->calibration_samples;
                detector->gravity_x_g = detector->calibration_accel_x_sum / sample_count;
                detector->gravity_y_g = detector->calibration_accel_y_sum / sample_count;
                detector->gravity_z_g = detector->calibration_accel_z_sum / sample_count;
                detector->calibrated = true;
                detector->previous_accel_norm_g = accel_norm_g;
                detector->previous_sample_ms = now_ms;
                detector->has_previous_sample = true;
            } else {
                detector->calibration_samples = 0;
                detector->calibration_window_stationary = true;
                detector->calibration_accel_x_sum = 0.0f;
                detector->calibration_accel_y_sum = 0.0f;
                detector->calibration_accel_z_sum = 0.0f;
            }
        }
        return build_output(detector, accel_norm_g, 0.0f, gyro_norm_dps, tilt_deg, 0U, false);
    }

    tilt_deg = relative_tilt_deg(detector, sample, accel_norm_g);
    float accel_delta_g = 0.0f;
    uint32_t sample_interval_ms = 0U;
    bool impact_event = false;

    if (detector->has_previous_sample && now_ms > detector->previous_sample_ms) {
        const uint64_t interval_ms = now_ms - detector->previous_sample_ms;
        sample_interval_ms = interval_ms > UINT32_MAX ? UINT32_MAX : (uint32_t)interval_ms;
        if (interval_ms <= MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS) {
            accel_delta_g = fabsf(accel_norm_g - detector->previous_accel_norm_g);
            const bool refractory_complete = detector->impact_count == 0U ||
                                             (now_ms >= detector->last_impact_ms &&
                                              now_ms - detector->last_impact_ms >=
                                                  MOTION_DETECTOR_IMPACT_REFRACTORY_MS);
            if (accel_delta_g >= MOTION_DETECTOR_IMPACT_DELTA_G && refractory_complete) {
                impact_event = true;
                detector->impact_latched = true;
                detector->impact_count++;
                detector->last_impact_ms = now_ms;
                detector->stable_started_ms = 0;
            }
        }
    }
    detector->previous_accel_norm_g = accel_norm_g;
    detector->previous_sample_ms = now_ms;
    detector->has_previous_sample = true;

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
        const bool stable = tilt_deg < 30.0f && accel_norm_g >= 0.8f && accel_norm_g <= 1.2f &&
                            gyro_norm_dps < 20.0f;
        if (stable && !impact_event) {
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

    return build_output(
        detector,
        accel_norm_g,
        accel_delta_g,
        gyro_norm_dps,
        tilt_deg,
        sample_interval_ms,
        impact_event);
}
