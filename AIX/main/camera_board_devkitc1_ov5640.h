#pragma once

/*
 * Fixed wiring for the 18-pin 3.3 V ALIENTEK DVP OV5640 breakout and
 * ESP32-S3-DevKitC-1. This camera board has its own 24 MHz oscillator, so
 * ESP32-S3 must not drive an external XCLK pin.
 * Do not reuse these pins for other peripherals while the camera profile is active.
 */
#define AIX_CAMERA_PIN_SIOD 4
#define AIX_CAMERA_PIN_SIOC 5
#define AIX_CAMERA_PIN_XCLK -1
#define AIX_CAMERA_XCLK_FREQ_HZ 24000000
#define AIX_CAMERA_PIN_PCLK 7
#define AIX_CAMERA_PIN_VSYNC 8
#define AIX_CAMERA_PIN_HREF 9
#define AIX_CAMERA_PIN_D0 10
#define AIX_CAMERA_PIN_D1 11
#define AIX_CAMERA_PIN_D2 12
#define AIX_CAMERA_PIN_D3 13
#define AIX_CAMERA_PIN_D4 14
#define AIX_CAMERA_PIN_D5 15
#define AIX_CAMERA_PIN_D6 16
#define AIX_CAMERA_PIN_D7 17
#define AIX_CAMERA_PIN_PWDN 18
#define AIX_CAMERA_PIN_RESET 21
