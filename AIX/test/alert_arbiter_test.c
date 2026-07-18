#include <stdio.h>

#include "../main/alert_arbiter.h"

static road_hazard_request_t hazard(const char *event_id, const char *severity, double ttl_ms)
{
    road_hazard_request_t request = {
        .type = "road_hazard", .version = 1.0,
        .device_id = "helmet-01", .boot_id = "boot-01", .event_id = event_id,
        .camera_id = "cam", .intersection_id = "crossing", .message_code = "TRUCK_APPROACH",
        .direction = "front", .object_type = "truck", .eta_ms = 900.0,
        .severity = severity, .ttl_ms = ttl_ms, .simulated = true, .simulated_is_bool = true,
    };
    return request;
}

static action_decision_t local(action_state_t state, rgb_pattern_t pattern)
{
    action_decision_t decision = {.state = state, .rgb_pattern = pattern, .valid = true};
    return decision;
}

int main(void)
{
    alert_arbiter_t arbiter;
    action_decision_t local_fault = local(ACTION_STATE_FAULT, RGB_PURPLE_BLINK_1HZ);
    alert_arbiter_init(&arbiter, "helmet-01", "boot-01", &local_fault);

    alert_effective_t effective = alert_arbiter_get_effective(&arbiter, 1000U);
    if (effective.state != ACTION_STATE_FAULT || effective.remote) {
        printf("local fault baseline lost\n");
        return 1;
    }

    road_hazard_outcome_t outcome = {0};
    road_hazard_request_t high = hazard("high-1", "high", 1000.0);
    if (alert_arbiter_submit(&arbiter, &high, 1000U, &outcome) != ROAD_HAZARD_ACCEPTED) return 1;
    effective = alert_arbiter_get_effective(&arbiter, 1000U);
    if (!effective.remote || effective.state != ACTION_STATE_HIGH || effective.pattern != RGB_ORANGE_BLINK_2HZ) {
        printf("remote high did not override local fault\n");
        return 1;
    }

    action_decision_t local_critical = local(ACTION_STATE_CRITICAL, RGB_RED_DOUBLE_PULSE);
    alert_arbiter_set_local(&arbiter, &local_critical, 1200U);
    effective = alert_arbiter_get_effective(&arbiter, 1200U);
    if (effective.remote || effective.state != ACTION_STATE_CRITICAL) {
        printf("local critical did not override remote high\n");
        return 1;
    }

    action_decision_t local_attention = local(ACTION_STATE_ATTENTION, RGB_YELLOW_BLINK_1HZ);
    alert_arbiter_set_local(&arbiter, &local_attention, 1500U);
    effective = alert_arbiter_get_effective(&arbiter, 1500U);
    if (!effective.remote || effective.state != ACTION_STATE_HIGH) {
        printf("latest local update incorrectly displaced active remote high\n");
        return 1;
    }

    road_hazard_expired_t expired = {0};
    if (!alert_arbiter_tick(&arbiter, 2000U, &expired)) {
        printf("expiry heartbeat missed\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 2000U);
    if (effective.remote || effective.state != ACTION_STATE_ATTENTION ||
        effective.pattern != RGB_YELLOW_BLINK_1HZ) {
        printf("TTL expiry did not restore latest local state\n");
        return 1;
    }

    road_hazard_request_t critical = hazard("critical-1", "critical", 3000.0);
    if (alert_arbiter_submit(&arbiter, &critical, 2100U, &outcome) != ROAD_HAZARD_ACCEPTED) return 1;
    effective = alert_arbiter_get_effective(&arbiter, 2100U);
    if (!effective.remote || effective.state != ACTION_STATE_CRITICAL) {
        printf("remote critical priority failed\n");
        return 1;
    }

    /* Deterministic interleaving regression: duplicate, expiry and local updates cannot extend TTL
       or restore an older local snapshot even when calls arrive on the same boundary. */
    if (alert_arbiter_submit(&arbiter, &critical, 3000U, &outcome) != ROAD_HAZARD_DUPLICATE ||
        outcome.expires_in_ms != 2100U) return 1;
    alert_arbiter_set_local(&arbiter, &local_fault, 5099U);
    if (!alert_arbiter_tick(&arbiter, 5100U, &expired)) return 1;
    effective = alert_arbiter_get_effective(&arbiter, 5100U);
    if (effective.remote || effective.state != ACTION_STATE_FAULT) {
        printf("boundary race did not restore current local state\n");
        return 1;
    }

    printf("alert_arbiter_test: ALL PASSED\n");
    return 0;
}
