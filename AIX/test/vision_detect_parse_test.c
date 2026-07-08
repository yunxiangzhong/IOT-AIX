#include <stdio.h>
#include <string.h>
#include "../main/vision_detect.h"

int main(void)
{
    int failures = 0;

    /* Test: valid vision_detect line */
    const char *line1 =
        "{\"type\":\"vision_detect\",\"version\":1,\"seq\":42,\"ts_ms\":50000,"
        "\"source\":\"ov5640\",\"objects\":[{\"class\":\"truck\",\"confidence\":0.82,"
        "\"bbox\":[78,42,65,48],\"distance_m\":5.2,\"approaching\":true}],"
        "\"nearest_distance_m\":5.2,\"ttc_s\":4.1,\"valid\":true}";

    vision_detect_result_t r1 = {0};
    if (!vision_detect_parse_line(line1, &r1)) {
        printf("FAIL: parse valid line returned false\n");
        failures++;
    } else {
        if (r1.seq != 42) { printf("FAIL: seq=%lu expected 42\n", (unsigned long)r1.seq); failures++; }
        if (r1.ts_ms != 50000) { printf("FAIL: ts_ms=%lu expected 50000\n", (unsigned long)r1.ts_ms); failures++; }
        if (r1.nearest_distance_m < 5.1f || r1.nearest_distance_m > 5.3f) {
            printf("FAIL: nearest_distance_m=%.1f expected 5.2\n", r1.nearest_distance_m); failures++;
        }
        if (r1.ttc_s < 4.0f || r1.ttc_s > 4.2f) {
            printf("FAIL: ttc_s=%.1f expected 4.1\n", r1.ttc_s); failures++;
        }
        if (!r1.valid) { printf("FAIL: valid=false expected true\n"); failures++; }
        if (r1.object_count != 1) { printf("FAIL: object_count=%d expected 1\n", r1.object_count); failures++; }
        if (strcmp(r1.objects[0].class_name, "truck") != 0) {
            printf("FAIL: class='%s' expected 'truck'\n", r1.objects[0].class_name); failures++;
        }
    }

    /* Test: non-vision_detect line returns false */
    const char *line2 = "{\"type\":\"pressure\",\"version\":1,\"seq\":1}";
    vision_detect_result_t r2 = {0};
    if (vision_detect_parse_line(line2, &r2)) {
        printf("FAIL: non-vision_detect line parsed as vision_detect\n");
        failures++;
    }

    /* Test: missing valid field returns false */
    const char *line3 =
        "{\"type\":\"vision_detect\",\"version\":1,\"seq\":1,\"ts_ms\":1000,"
        "\"nearest_distance_m\":3.0,\"ttc_s\":2.0}";
    vision_detect_result_t r3 = {0};
    if (vision_detect_parse_line(line3, &r3)) {
        printf("FAIL: missing valid parsed successfully\n");
        failures++;
    }

    /* Test: NULL inputs return false */
    if (vision_detect_parse_line(NULL, &r1)) {
        printf("FAIL: NULL line parsed\n");
        failures++;
    }
    if (vision_detect_parse_line(line1, NULL)) {
        printf("FAIL: NULL out parsed\n");
        failures++;
    }

    if (failures == 0) {
        printf("vision_detect_parse_test: ALL PASSED\n");
    }
    return failures;
}
