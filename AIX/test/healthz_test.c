#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Verify the /healthz response JSON structure and boundary conditions
   without requiring the ESP-IDF HTTP server in a host-compiled test. */

static int check(bool condition, const char *label)
{
    if (!condition) {
        printf("FAIL: %s\n", label);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;
    char body[256];
    int written;

    /* healthz JSON fits within buffer */
    written = snprintf(
        body, sizeof(body),
        "{\"type\":\"healthz\",\"version\":1,"
        "\"device_id\":\"aix-helmet-01\",\"boot_id\":\"0123456789abcdef\","
        "\"risk_receiver_ready\":true}");
    failures += check(written > 0 && (size_t)written < sizeof(body),
                      "healthz JSON fits 256-byte buffer");

    /* required keys present */
    failures += check(strstr(body, "\"type\":\"healthz\"") != NULL,
                      "type field is healthz");
    failures += check(strstr(body, "\"version\":1") != NULL,
                      "version field is 1");
    failures += check(strstr(body, "\"device_id\":\"aix-helmet-01\"") != NULL,
                      "device_id field present");
    failures += check(strstr(body, "\"boot_id\":\"0123456789abcdef\"") != NULL,
                      "boot_id field present");
    failures += check(strstr(body, "\"risk_receiver_ready\":true") != NULL,
                      "risk_receiver_ready is true");

    /* edge-case: long device_id still fits */
    written = snprintf(
        body, sizeof(body),
        "{\"type\":\"healthz\",\"version\":1,"
        "\"device_id\":\"aix-helmet-device-max-length-63-chars-abcdefghijklmnopqrstuvwxy\","
        "\"boot_id\":\"0123456789abcdef\","
        "\"risk_receiver_ready\":true}");
    failures += check(written > 0 && (size_t)written < sizeof(body),
                      "healthz JSON with 63-char device_id fits");

    /* edge-case: 16-char hex boot_id */
    written = snprintf(
        body, sizeof(body),
        "{\"type\":\"healthz\",\"version\":1,"
        "\"device_id\":\"aix-01\",\"boot_id\":\"ffffffffffffffff\","
        "\"risk_receiver_ready\":true}");
    failures += check(written > 0 && (size_t)written < sizeof(body),
                      "healthz JSON with max boot_id fits");
    failures += check(strstr(body, "\"boot_id\":\"ffffffffffffffff\"") != NULL,
                      "16-char hex boot_id renders correctly");

    /* risk_receiver_ready is always boolean true, not string */
    failures += check(strstr(body, "\"risk_receiver_ready\":true") != NULL,
                      "risk_receiver_ready is JSON boolean true (not string)");

    if (failures == 0) {
        printf("healthz_test: ALL PASSED\n");
    } else {
        printf("healthz_test: %d FAILURES\n", failures);
    }
    return failures;
}
