#include <stdio.h>
#include "../main/distance_estimator.h"

int main(void)
{
    int failures = 0;

    /* Test: normal estimation — a 1.8m wide truck at 50px bbox with 800px focal */
    float d = distance_estimator_estimate(50, 800.0f, 1.8f);
    if (d < 28.5f || d > 29.0f) {
        printf("FAIL: estimate=%.1f expected ~28.8\n", d); failures++;
    }

    /* Test: zero bbox returns -1 */
    d = distance_estimator_estimate(0, 800.0f, 1.8f);
    if (d >= 0.0f) {
        printf("FAIL: zero bbox should return negative, got %.1f\n", d); failures++;
    }

    /* Test: approaching detection */
    if (!distance_estimator_approaching(10.0f, 8.0f, 0.5f)) {
        printf("FAIL: should detect approaching 10->8\n"); failures++;
    }
    if (distance_estimator_approaching(10.0f, 9.8f, 0.5f)) {
        printf("FAIL: should not detect approaching 10->9.8 (threshold 0.5)\n"); failures++;
    }
    if (distance_estimator_approaching(-1.0f, 5.0f, 0.5f)) {
        printf("FAIL: negative prev should return false\n"); failures++;
    }

    /* Test: TTC */
    float ttc = distance_estimator_ttc(20.0f, 5.0f);
    if (ttc < 3.9f || ttc > 4.1f) {
        printf("FAIL: ttc=%.1f expected 4.0\n", ttc); failures++;
    }
    ttc = distance_estimator_ttc(0.0f, 5.0f);
    if (ttc >= 0.0f) {
        printf("FAIL: zero distance TTC should return negative\n"); failures++;
    }

    if (failures == 0) {
        printf("distance_estimator_test: ALL PASSED\n");
    }
    return failures;
}
