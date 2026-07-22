#include <assert.h>
#include <stdio.h>

#include "mpu6050_sensor.h"

int main(void)
{
    assert(MPU6050_SAMPLE_RATE_HZ == 100U);
    assert(MPU6050_GYRO_OUTPUT_RATE_HZ % MPU6050_SAMPLE_RATE_HZ == 0U);
    assert(MPU6050_SAMPLE_RATE_DIVIDER == 9U);
    assert(MPU6050_GYRO_OUTPUT_RATE_HZ / (MPU6050_SAMPLE_RATE_DIVIDER + 1U) ==
           MPU6050_SAMPLE_RATE_HZ);
    assert(MOTION_DETECTOR_IMPACT_DELTA_G == 1.2f);
    assert(MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS == 20ULL);
    assert(MOTION_DETECTOR_IMPACT_REFRACTORY_MS == 200ULL);
    puts("mpu6050_config_test: PASS");
    return 0;
}
