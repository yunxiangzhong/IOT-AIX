#include "distance_estimator.h"

float distance_estimator_estimate(int bbox_w_px, float focal_length_px, float known_width_m)
{
    if (bbox_w_px <= 0 || focal_length_px <= 0.0f || known_width_m <= 0.0f) {
        return -1.0f;
    }
    return (known_width_m * focal_length_px) / (float)bbox_w_px;
}

bool distance_estimator_approaching(float prev_distance_m, float curr_distance_m, float threshold)
{
    if (prev_distance_m < 0.0f || curr_distance_m < 0.0f) {
        return false;
    }
    return (prev_distance_m - curr_distance_m) > threshold;
}

float distance_estimator_ttc(float distance_m, float approach_speed_mps)
{
    if (distance_m <= 0.0f || approach_speed_mps <= 0.0f) {
        return -1.0f;
    }
    return distance_m / approach_speed_mps;
}
