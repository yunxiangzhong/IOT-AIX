#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char class_name[32];
    float confidence;
    int16_t bbox_x;
    int16_t bbox_y;
    int16_t bbox_w;
    int16_t bbox_h;
    float distance_m;
    bool approaching;
} vision_detect_object_t;

typedef struct {
    uint32_t seq;
    uint32_t ts_ms;
    char source[32];
    vision_detect_object_t objects[8];
    int object_count;
    float nearest_distance_m;
    float ttc_s;
    bool valid;
} vision_detect_result_t;

bool vision_detect_parse_line(const char *line, vision_detect_result_t *out);

#ifdef __cplusplus
}
#endif
