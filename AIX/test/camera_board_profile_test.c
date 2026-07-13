#include <stdio.h>

#include "../main/camera_board_devkitc1_ov5640.h"

#ifndef AIX_CAMERA_XCLK_FREQ_HZ
#define AIX_CAMERA_XCLK_FREQ_HZ 0
#endif

int main(void)
{
    int failures = 0;

    if (AIX_CAMERA_PIN_XCLK != -1) {
        printf("FAIL: onboard-oscillator OV5640 must not use an external XCLK GPIO\n");
        failures++;
    }
    if (AIX_CAMERA_XCLK_FREQ_HZ != 24000000) {
        printf("FAIL: onboard-oscillator OV5640 must report a 24 MHz sensor clock\n");
        failures++;
    }

    if (failures == 0) {
        printf("camera_board_profile_test: ALL PASSED\n");
    }
    return failures;
}
