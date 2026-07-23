#include <stdio.h>

#include "../main/alert_arbiter.h"

static road_hazard_request_t hazard(const char *event_id, const char *severity, double ttl_ms)
{
    road_hazard_request_t request = {
        .type = "road_hazard", .version = 1.0,
        .device_id = "helmet-01", .boot_id = "boot-01", .event_id = event_id,
        .camera_id = "cam", .intersection_id = "crossing", .message_code = "TRUCK_APPROACH",
        .direction = "front", .object_type = "truck", .eta_ms = 900.0,
        .severity = severity, .ttl_ms = ttl_ms, .simulated = false, .simulated_is_bool = true,
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

    action_decision_t local_safe = local(ACTION_STATE_SAFE, RGB_GREEN_SOLID);
    alert_arbiter_set_local(&arbiter, &local_safe, 5200U);
    semantic_indicator_outcome_t semantic = {0};
    if (alert_arbiter_submit_semantic(&arbiter, "analysis-1", 5200U, &semantic) !=
            SEMANTIC_INDICATOR_ACCEPTED ||
        !semantic.flashed || semantic.suppressed) {
        printf("semantic pulse was not accepted\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 5699U);
    if (!effective.semantic || effective.pattern != RGB_CYAN_RESULT_PULSE) {
        printf("semantic pulse did not remain active for 500ms\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 5700U);
    if (effective.semantic || effective.pattern != RGB_GREEN_SOLID) {
        printf("semantic pulse did not restore local pattern at 500ms\n");
        return 1;
    }
    if (alert_arbiter_submit_semantic(&arbiter, "analysis-1", 6000U, &semantic) !=
            SEMANTIC_INDICATOR_DUPLICATE ||
        !semantic.flashed ||
        alert_arbiter_get_effective(&arbiter, 6000U).pattern != RGB_GREEN_SOLID) {
        printf("duplicate semantic result did not return original ACK safely\n");
        return 1;
    }

    alert_arbiter_set_local(&arbiter, &local_critical, 6100U);
    if (alert_arbiter_submit_semantic(&arbiter, "analysis-2", 6100U, &semantic) !=
            SEMANTIC_INDICATOR_ACCEPTED ||
        !semantic.suppressed || semantic.flashed) {
        printf("critical state did not suppress semantic pulse\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 6100U);
    if (effective.pattern != RGB_RED_DOUBLE_PULSE) return 1;

    if (alert_arbiter_submit_collision(&arbiter, "boot-01", 3U) !=
        COLLISION_INDICATOR_ACCEPTED) {
        printf("new MPU collision was not latched\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 6200U);
    if (!effective.collision || effective.pattern != RGB_WHITE_AIRBAG_LATCHED) {
        printf("collision white did not override critical\n");
        return 1;
    }
    if (alert_arbiter_ack_collision(&arbiter, "old-boot", 3U) !=
            COLLISION_ACK_REJECT_IDENTITY ||
        alert_arbiter_ack_collision(&arbiter, "boot-01", 2U) !=
            COLLISION_ACK_REJECT_IDENTITY) {
        printf("stale collision acknowledgement was accepted\n");
        return 1;
    }
    if (alert_arbiter_ack_collision(&arbiter, "boot-01", 3U) !=
        COLLISION_ACK_ACCEPTED) {
        printf("matching collision acknowledgement was rejected\n");
        return 1;
    }
    effective = alert_arbiter_get_effective(&arbiter, 6201U);
    if (effective.collision || effective.pattern != RGB_RED_DOUBLE_PULSE) {
        printf("collision acknowledgement did not restore prior pattern\n");
        return 1;
    }

    printf("alert_arbiter_test: ALL PASSED\n");
    return 0;
}
