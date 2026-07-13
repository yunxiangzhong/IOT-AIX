#include <stdio.h>
#include <string.h>

#include "../main/vision_uplink.h"

int main(void)
{
    int failures = 0;
    const char valid[] = "{\"type\":\"vision_depth\",\"version\":1,\"frame_seq\":7,\"valid\":true}";
    const char bad_seq[] = "{\"type\":\"vision_depth\",\"version\":1,\"frame_seq\":8,\"valid\":true}";
    const char prefixed_seq[] = "{\"type\":\"vision_depth\",\"version\":1,\"frame_seq\":70,\"valid\":true}";
    const char bad_valid[] = "{\"type\":\"vision_depth\",\"version\":1,\"frame_seq\":7,\"valid\":false}";

    if (!vision_uplink_response_matches_frame(valid, strlen(valid), 7)) {
        printf("FAIL: valid vision response rejected\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(bad_seq, strlen(bad_seq), 7)) {
        printf("FAIL: mismatched frame sequence accepted\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(prefixed_seq, strlen(prefixed_seq), 7)) {
        printf("FAIL: prefixed frame sequence accepted\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(bad_valid, strlen(bad_valid), 7)) {
        printf("FAIL: invalid vision response accepted\n");
        failures++;
    }

    if (failures == 0) {
        printf("vision_uplink_test: ALL PASSED\n");
    }
    return failures;
}
