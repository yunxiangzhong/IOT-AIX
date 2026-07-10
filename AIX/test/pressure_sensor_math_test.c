#include <math.h>
#include <stdio.h>

#include "../main/pressure_sensor.h"

static int expect_close(const char *name, float actual, float expected)
{
    const float diff = fabsf(actual - expected);
    if (diff > 0.01f) {
        printf("%s: expected %.2f, got %.2f\n", name, expected, actual);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;

    failures += expect_close("lower endpoint",
                             pressure_sensor_voltage_to_kpa(200),
                             0.0f);
    failures += expect_close("upper endpoint",
                             pressure_sensor_voltage_to_kpa(2700),
                             200.0f);
    failures += expect_close("midpoint",
                             pressure_sensor_voltage_to_kpa(1450),
                             100.0f);
    failures += expect_close("low clamp",
                             pressure_sensor_voltage_to_kpa(100),
                             0.0f);
    failures += expect_close("high clamp",
                             pressure_sensor_voltage_to_kpa(3000),
                             200.0f);

    if (pressure_sensor_is_over_pressure(179.9f)) {
        printf("over pressure threshold: 179.9 should be safe\n");
        failures++;
    }
    if (!pressure_sensor_is_over_pressure(180.0f)) {
        printf("over pressure threshold: 180.0 should warn\n");
        failures++;
    }

    return failures;
}
