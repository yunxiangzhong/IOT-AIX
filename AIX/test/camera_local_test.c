#include <stdio.h>
#include <stdint.h>

#include "../main/camera_local.h"

int main(void)
{
    int failures = 0;
    const uint8_t valid_jpeg[] = {0xff, 0xd8, 0x01, 0x02, 0xff, 0xd9};
    const uint8_t bad_header[] = {0x00, 0xd8, 0x01, 0x02, 0xff, 0xd9};
    const uint8_t bad_tail[] = {0xff, 0xd8, 0x01, 0x02, 0x00, 0xd9};

    if (!camera_local_frame_is_valid_jpeg(valid_jpeg, sizeof(valid_jpeg))) {
        printf("FAIL: valid JPEG rejected\n");
        failures++;
    }
    if (camera_local_frame_is_valid_jpeg(NULL, 0)) {
        printf("FAIL: null frame accepted\n");
        failures++;
    }
    if (camera_local_frame_is_valid_jpeg(valid_jpeg, 3)) {
        printf("FAIL: short frame accepted\n");
        failures++;
    }
    if (camera_local_frame_is_valid_jpeg(bad_header, sizeof(bad_header))) {
        printf("FAIL: bad JPEG header accepted\n");
        failures++;
    }
    if (camera_local_frame_is_valid_jpeg(bad_tail, sizeof(bad_tail))) {
        printf("FAIL: bad JPEG tail accepted\n");
        failures++;
    }

    if (failures == 0) {
        printf("camera_local_test: ALL PASSED\n");
    }
    return failures;
}
