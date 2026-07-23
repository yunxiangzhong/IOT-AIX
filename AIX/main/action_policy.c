#include "action_policy.h"

#include <stddef.h>
#include <string.h>

static const char *expected_band(int score)
{
    if (score >= 80) {
        return "critical";
    }
    if (score >= 60) {
        return "high";
    }
    if (score >= 30) {
        return "attention";
    }
    return "low";
}

void action_policy_init(action_policy_t *policy, const char *device_id, const char *boot_id, uint64_t now_ms)
{
    if (policy == NULL) {
        return;
    }
    memset(policy, 0, sizeof(*policy));
    if (device_id != NULL) {
        strncpy(policy->device_id, device_id, sizeof(policy->device_id) - 1U);
    }
    if (boot_id != NULL) {
        strncpy(policy->boot_id, boot_id, sizeof(policy->boot_id) - 1U);
    }
    policy->boot_ts_ms = now_ms;
}

risk_accept_result_t action_policy_accept(action_policy_t *policy, const vision_risk_input_t *risk, uint64_t now_ms)
{
    if (policy == NULL || risk == NULL || !risk->valid || risk->device_id == NULL || risk->boot_id == NULL ||
        risk->risk_band == NULL || risk->dominant_class == NULL || risk->reason == NULL ||
        risk->risk_score < 0 || risk->risk_score > 100 || risk->capture_ts_ms > now_ms) {
        return RISK_REJECT_INVALID;
    }
    if (strcmp(policy->device_id, risk->device_id) != 0) {
        return RISK_REJECT_DEVICE;
    }
    if (strcmp(policy->boot_id, risk->boot_id) != 0) {
        return RISK_REJECT_BOOT;
    }
    if (!risk->scene_requested && policy->has_risk && risk->frame_seq <= policy->frame_seq) {
        return RISK_REJECT_SEQUENCE;
    }
    if (now_ms - risk->capture_ts_ms > ACTION_POLICY_RISK_TTL_MS) {
        return RISK_REJECT_STALE;
    }
    if (!risk->scene_requested && strcmp(expected_band(risk->risk_score), risk->risk_band) != 0) {
        return RISK_REJECT_BAND;
    }

    policy->has_risk = true;
    if (!risk->scene_requested) {
        policy->frame_seq = risk->frame_seq;
    }
    policy->capture_ts_ms = risk->capture_ts_ms;
    policy->received_ts_ms = now_ms;
    policy->risk_score = (uint8_t)risk->risk_score;
    strncpy(policy->risk_band, risk->risk_band, sizeof(policy->risk_band) - 1U);
    policy->risk_band[sizeof(policy->risk_band) - 1U] = '\0';
    policy->actuation_hazard_present = risk->actuation_hazard_present;
    policy->actuation_hazard_active = risk->actuation_hazard_active;
    return RISK_ACCEPTED;
}

void action_policy_set_fault(action_policy_t *policy, action_fault_t fault, bool active)
{
    if (policy == NULL || fault == ACTION_FAULT_NONE) {
        return;
    }
    if (active) {
        policy->faults = (uint8_t)(policy->faults | (uint8_t)fault);
    } else {
        policy->faults = (uint8_t)(policy->faults & (uint8_t)~fault);
    }
}

action_decision_t action_policy_decide(const action_policy_t *policy, uint64_t now_ms)
{
    action_decision_t result = {
        .state = ACTION_STATE_FAULT,
        .rgb_pattern = RGB_PURPLE_BLINK_1HZ,
        .stale = true,
        .valid = false,
    };
    if (policy == NULL) {
        return result;
    }
    result.source_frame_seq = policy->frame_seq;
    result.risk_score = policy->risk_score;
    result.actuation_hazard_present = policy->actuation_hazard_present;
    result.actuation_hazard_active = policy->actuation_hazard_active;
    if (policy->faults != 0U) {
        return result;
    }
    if (!policy->has_risk) {
        if (now_ms >= policy->boot_ts_ms && now_ms - policy->boot_ts_ms < ACTION_POLICY_BOOT_GRACE_MS) {
            result.state = ACTION_STATE_LOADING;
            result.rgb_pattern = RGB_BLUE_BLINK_1HZ;
            result.stale = false;
        }
        return result;
    }
    if (now_ms < policy->received_ts_ms || now_ms - policy->received_ts_ms >= ACTION_POLICY_RISK_TTL_MS) {
        return result;
    }
    result.valid = true;
    result.stale = false;
    if (policy->risk_score >= 80U) {
        result.state = ACTION_STATE_CRITICAL;
        result.rgb_pattern = RGB_RED_DOUBLE_PULSE;
    } else if (policy->risk_score >= 60U) {
        result.state = ACTION_STATE_HIGH;
        result.rgb_pattern = RGB_ORANGE_BLINK_2HZ;
    } else if (policy->risk_score >= 30U) {
        result.state = ACTION_STATE_ATTENTION;
        result.rgb_pattern = RGB_YELLOW_BLINK_1HZ;
    } else {
        result.state = ACTION_STATE_SAFE;
        result.rgb_pattern = RGB_GREEN_SOLID;
    }
    return result;
}

const char *action_state_name(action_state_t state)
{
    static const char *const names[] = {"loading", "safe", "attention", "high", "critical", "fault"};
    return state >= ACTION_STATE_LOADING && state <= ACTION_STATE_FAULT ? names[state] : "fault";
}

const char *rgb_pattern_name(rgb_pattern_t pattern)
{
    static const char *const names[] = {
        "blue_blink_1hz", "green_solid", "yellow_blink_1hz",
        "orange_blink_2hz", "red_double_pulse", "purple_blink_1hz",
        "cyan_result_pulse", "white_airbag_latched",
    };
    return pattern >= RGB_BLUE_BLINK_1HZ && pattern <= RGB_WHITE_AIRBAG_LATCHED ? names[pattern] : "purple_blink_1hz";
}

const char *risk_accept_result_name(risk_accept_result_t result)
{
    static const char *const names[] = {
        "accepted", "invalid", "device", "boot", "sequence", "stale", "band",
    };
    return result >= RISK_ACCEPTED && result <= RISK_REJECT_BAND ? names[result] : "invalid";
}
