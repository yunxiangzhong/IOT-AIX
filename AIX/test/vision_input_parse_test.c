#include <stdio.h>

#include "../main/vision_input.h"

int main(void)
{
    vision_input_snapshot_t snapshot = {0};
    const char *line = "{\"type\":\"vision\",\"version\":1,\"seq\":12,\"ts_ms\":43020,\"source\":\"pc_camera\",\"looming\":0.72,\"area_rate\":0.58,\"center_motion\":0.41,\"confidence\":0.80,\"valid\":true}";

    if (!vision_input_parse_line(line, &snapshot)) {
        printf("vision line should parse\n");
        return 1;
    }
    if (snapshot.seq != 12 || snapshot.ts_ms != 43020) {
        printf("bad seq or ts_ms: seq=%lu ts=%lu\n",
               (unsigned long)snapshot.seq,
               (unsigned long)snapshot.ts_ms);
        return 1;
    }
    if (snapshot.looming < 0.71f || snapshot.looming > 0.73f) {
        printf("bad looming %.3f\n", snapshot.looming);
        return 1;
    }
    if (snapshot.area_rate < 0.57f || snapshot.area_rate > 0.59f) {
        printf("bad area %.3f\n", snapshot.area_rate);
        return 1;
    }
    if (snapshot.center_motion < 0.40f || snapshot.center_motion > 0.42f) {
        printf("bad center %.3f\n", snapshot.center_motion);
        return 1;
    }
    if (snapshot.confidence < 0.79f || snapshot.confidence > 0.81f) {
        printf("bad confidence %.3f\n", snapshot.confidence);
        return 1;
    }
    if (!snapshot.valid || snapshot.stale) {
        printf("bad valid/stale flags\n");
        return 1;
    }

    if (vision_input_parse_line("{\"type\":\"pressure\"}", &snapshot)) {
        printf("non-vision line should be ignored\n");
        return 1;
    }

    return 0;
}
