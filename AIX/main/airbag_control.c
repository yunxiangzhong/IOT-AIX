#include "airbag_control.h"

#ifdef ESP_PLATFORM
#include <stdio.h>

static int s_last_target_pct;

void airbag_control_apply_simulated(const risk_fusion_result_t *result,
                                    uint32_t seq,
                                    uint32_t ts_ms)
{
    if (result == NULL) {
        return;
    }

    const char *pump = "off";
    const char *valve = "closed";
    if (result->target_pct > s_last_target_pct) {
        pump = "inflate";
    } else if (result->target_pct < s_last_target_pct) {
        pump = "off";
        valve = "open";
    } else if (result->target_pct > 0) {
        pump = "hold";
    }

    printf("{\"type\":\"actuator\",\"version\":1,\"seq\":%lu,"
           "\"ts_ms\":%lu,\"mode\":\"sim\",\"target_pct\":%d,"
           "\"pump\":\"%s\",\"valve\":\"%s\"}\n",
           (unsigned long)seq,
           (unsigned long)ts_ms,
           result->target_pct,
           pump,
           valve);
    s_last_target_pct = result->target_pct;
}
#endif
