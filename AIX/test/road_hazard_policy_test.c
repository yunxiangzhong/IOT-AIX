#include <stdio.h>
#include <string.h>

#include "../main/road_hazard_policy.h"

static road_hazard_request_t valid_request(const char *event_id)
{
    road_hazard_request_t request = {
        .type = "road_hazard",
        .version = 1.0,
        .device_id = "helmet-01",
        .boot_id = "boot-01",
        .event_id = event_id,
        .camera_id = "roadside-cam-3",
        .intersection_id = "intersection-7",
        .message_code = "TRUCK_APPROACH",
        .direction = "left",
        .object_type = "truck",
        .eta_ms = 1800.0,
        .severity = "high",
        .ttl_ms = 5000.0,
        .simulated = false,
        .simulated_is_bool = true,
    };
    return request;
}

static int expect_rejected(road_hazard_policy_t *policy, road_hazard_request_t request,
                           uint64_t now_ms, road_hazard_result_t expected)
{
    road_hazard_outcome_t outcome = {0};
    const road_hazard_result_t result = road_hazard_policy_submit(policy, &request, now_ms, &outcome);
    if (result != expected || outcome.accepted || outcome.duplicate) {
        printf("expected rejection %d, got %d accepted=%d duplicate=%d\n",
               (int)expected, (int)result, outcome.accepted, outcome.duplicate);
        return 1;
    }
    return 0;
}

int main(void)
{
    road_hazard_policy_t policy;
    road_hazard_policy_init(&policy, "helmet-01", "boot-01");

    road_hazard_request_t request = valid_request("evt_A-9.~");
    road_hazard_outcome_t outcome = {0};
    if (road_hazard_policy_submit(&policy, &request, 1000U, &outcome) != ROAD_HAZARD_ACCEPTED ||
        !outcome.accepted || outcome.duplicate || outcome.expires_in_ms != 5000U ||
        outcome.severity != ROAD_HAZARD_SEVERITY_HIGH) {
        printf("first valid hazard was not accepted\n");
        return 1;
    }

    road_hazard_request_t retry = request;
    retry.ttl_ms = 3800.0; /* Sender transmits monotonic remaining TTL on retry. */
    if (road_hazard_policy_submit(&policy, &retry, 2200U, &outcome) != ROAD_HAZARD_DUPLICATE ||
        !outcome.accepted || !outcome.duplicate || outcome.expires_in_ms != 3800U) {
        printf("exact duplicate did not preserve original expiry\n");
        return 1;
    }
    retry.ttl_ms = 100.0;
    if (road_hazard_policy_submit(&policy, &retry, 5900U, &outcome) != ROAD_HAZARD_DUPLICATE ||
        outcome.expires_in_ms != 100U) {
        printf("duplicate extended the original TTL\n");
        return 1;
    }

    road_hazard_request_t increasing_ttl = request;
    increasing_ttl.ttl_ms = 6000.0;
    if (expect_rejected(&policy, increasing_ttl, 3000U, ROAD_HAZARD_REJECT_EVENT_CONFLICT)) return 1;

    road_hazard_request_t conflict = request;
    conflict.eta_ms = 1700.0;
    if (expect_rejected(&policy, conflict, 3000U, ROAD_HAZARD_REJECT_EVENT_CONFLICT)) {
        return 1;
    }
    if (expect_rejected(&policy, request, 6000U, ROAD_HAZARD_REJECT_EXPIRED)) {
        return 1;
    }

    road_hazard_request_t invalid = valid_request("evt-schema");
    invalid.version = 1.5;
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.simulated_is_bool = false; /* JSON number 0/1 must not pass as a boolean. */
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.eta_ms = 0.0;
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.ttl_ms = 30001.0;
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_TTL)) return 1;
    invalid = valid_request("evt-schema");
    invalid.event_id = "bad/event";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.direction = "up";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.object_type = "car";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-schema");
    invalid.severity = "low";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_SCHEMA)) return 1;
    invalid = valid_request("evt-device");
    invalid.device_id = "other";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_DEVICE)) return 1;
    invalid = valid_request("evt-boot");
    invalid.boot_id = "other";
    if (expect_rejected(&policy, invalid, 1000U, ROAD_HAZARD_REJECT_BOOT)) return 1;

    road_hazard_expired_t expired = {0};
    if (!road_hazard_policy_expire_next(&policy, 6000U, &expired) ||
        strcmp(expired.event_id, "evt_A-9.~") != 0 ||
        road_hazard_policy_expire_next(&policy, 6001U, &expired)) {
        printf("expiry event was not emitted exactly once\n");
        return 1;
    }

    printf("road_hazard_policy_test: ALL PASSED\n");
    return 0;
}
