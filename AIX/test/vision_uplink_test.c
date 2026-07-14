#include <stdio.h>
#include <string.h>

#include "../main/vision_uplink.h"

int main(void)
{
    int failures = 0;
    const char valid[] = "{\"type\":\"frame_ack\",\"version\":1,\"device_id\":\"aix-helmet-01\",\"boot_id\":\"0123456789abcdef\",\"frame_seq\":7,\"accepted\":true}";
    const char bad_seq[] = "{\"type\":\"frame_ack\",\"version\":1,\"device_id\":\"aix-helmet-01\",\"boot_id\":\"0123456789abcdef\",\"frame_seq\":8,\"accepted\":true}";
    const char prefixed_seq[] = "{\"type\":\"frame_ack\",\"version\":1,\"device_id\":\"aix-helmet-01\",\"boot_id\":\"0123456789abcdef\",\"frame_seq\":70,\"accepted\":true}";
    const char bad_valid[] = "{\"type\":\"frame_ack\",\"version\":1,\"device_id\":\"aix-helmet-01\",\"boot_id\":\"0123456789abcdef\",\"frame_seq\":7,\"accepted\":false}";
    const char bad_boot[] = "{\"type\":\"frame_ack\",\"version\":1,\"device_id\":\"aix-helmet-01\",\"boot_id\":\"fedcba9876543210\",\"frame_seq\":7,\"accepted\":true}";
    const char model_error[] = "{\"type\":\"frame_ack\",\"version\":1,\"model_state\":\"error\"}";

    if (!vision_uplink_response_matches_frame(valid, strlen(valid), "aix-helmet-01", "0123456789abcdef", 7)) {
        printf("FAIL: valid vision response rejected\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(bad_seq, strlen(bad_seq), "aix-helmet-01", "0123456789abcdef", 7)) {
        printf("FAIL: mismatched frame sequence accepted\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(prefixed_seq, strlen(prefixed_seq), "aix-helmet-01", "0123456789abcdef", 7)) {
        printf("FAIL: prefixed frame sequence accepted\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(bad_valid, strlen(bad_valid), "aix-helmet-01", "0123456789abcdef", 7)) {
        printf("FAIL: invalid vision response accepted\n");
        failures++;
    }
    if (vision_uplink_response_matches_frame(bad_boot, strlen(bad_boot), "aix-helmet-01", "0123456789abcdef", 7)) {
        printf("FAIL: wrong boot id accepted\n");
        failures++;
    }
    if (!vision_uplink_response_model_failed(model_error, strlen(model_error)) ||
        vision_uplink_response_model_failed(valid, strlen(valid))) {
        printf("FAIL: model error state detection failed\n");
        failures++;
    }

    if (failures == 0) {
        printf("vision_uplink_test: ALL PASSED\n");
    }
    return failures;
}
