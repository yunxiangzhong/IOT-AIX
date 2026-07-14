#include <stdio.h>
#include <string.h>

#include "../main/host_risk.h"

int main(void)
{
    host_risk_state_t state = {0};

    if (!host_risk_accept(&state, 12, 68, "high", "car", 2000)) {
        printf("valid risk was rejected\n");
        return 1;
    }
    if (state.risk_score != 68 || strcmp(state.risk_band, "high") != 0) {
        printf("risk state was not stored\n");
        return 1;
    }
    if (host_risk_accept(&state, 11, 20, "low", "", 2100)) {
        printf("older frame was accepted\n");
        return 1;
    }
    if (!host_risk_is_stale(&state, 5000, 3000) || host_risk_is_stale(&state, 4999, 3000)) {
        printf("stale calculation failed\n");
        return 1;
    }
    if (host_risk_accept(&state, 13, 101, "critical", "car", 5000)) {
        printf("out-of-range score was accepted\n");
        return 1;
    }
    return 0;
}
