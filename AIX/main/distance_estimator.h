#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

float distance_estimator_estimate(int bbox_w_px, float focal_length_px, float known_width_m);
bool distance_estimator_approaching(float prev_distance_m, float curr_distance_m, float threshold);
float distance_estimator_ttc(float distance_m, float approach_speed_mps);

#ifdef __cplusplus
}
#endif
