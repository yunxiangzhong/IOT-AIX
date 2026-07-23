#include <stdbool.h>
#include <stdio.h>

#include "risk_receiver.h"

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
    failures += check(risk_receiver_demo_lease_valid(100, 200), "lease is valid before expiry");
    failures += check(!risk_receiver_demo_lease_valid(200, 200), "lease expires at deadline");
    failures += check(!risk_receiver_demo_lease_valid(201, 200), "lease is invalid after deadline");
    printf("demo_mode_test: %s\n", failures == 0 ? "ALL PASSED" : "FAILURES");
    return failures;
}
