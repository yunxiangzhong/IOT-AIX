#include <stdio.h>
#include <string.h>

#include "../main/action_policy.h"

static int failures;

static void expect(bool condition, const char *message)
{
    if (!condition) {
        printf("FAIL: %s\n", message);
        failures++;
    }
}

static vision_risk_input_t risk(uint32_t seq, uint64_t capture_ms, int score, const char *band)
{
    vision_risk_input_t value = {
        .device_id = "aix-helmet-01",
        .boot_id = "0123456789abcdef",
        .frame_seq = seq,
        .capture_ts_ms = capture_ms,
        .risk_score = score,
        .risk_band = band,
        .dominant_class = "",
        .reason = "scene_proximity",
        .valid = true,
    };
    return value;
}

int main(void)
{
    action_policy_t policy;
    action_decision_t decision;
    vision_risk_input_t input;

    action_policy_init(&policy, "aix-helmet-01", "0123456789abcdef", 1000);
    decision = action_policy_decide(&policy, 2000);
    expect(decision.state == ACTION_STATE_LOADING && decision.rgb_pattern == RGB_BLUE_BLINK_1HZ,
           "boot grace must be blue loading");

    input = risk(1, 2000, 8, "low");
    expect(action_policy_accept(&policy, &input, 2200) == RISK_ACCEPTED, "fresh low risk rejected");
    decision = action_policy_decide(&policy, 2200);
    expect(decision.state == ACTION_STATE_SAFE && decision.rgb_pattern == RGB_GREEN_SOLID,
           "low risk must be solid green");

    input = risk(2, 2300, 30, "attention");
    expect(action_policy_accept(&policy, &input, 2400) == RISK_ACCEPTED, "attention rejected");
    expect(action_policy_decide(&policy, 2400).rgb_pattern == RGB_YELLOW_BLINK_1HZ,
           "attention must blink yellow");

    input = risk(3, 2500, 60, "high");
    expect(action_policy_accept(&policy, &input, 2600) == RISK_ACCEPTED, "high rejected");
    expect(action_policy_decide(&policy, 2600).rgb_pattern == RGB_ORANGE_BLINK_2HZ,
           "high must blink orange");

    input = risk(4, 2700, 80, "critical");
    expect(action_policy_accept(&policy, &input, 2800) == RISK_ACCEPTED, "critical rejected");
    expect(action_policy_decide(&policy, 2800).rgb_pattern == RGB_RED_DOUBLE_PULSE,
           "critical must use red double pulse");

    expect(action_policy_accept(&policy, &input, 2900) == RISK_REJECT_SEQUENCE,
           "duplicate frame accepted");
    input = risk(3, 2800, 70, "high");
    expect(action_policy_accept(&policy, &input, 2900) == RISK_REJECT_SEQUENCE,
           "out-of-order frame accepted");

    input = risk(4, 2900, 85, "critical");
    input.scene_requested = true;
    input.scene_id = 4;
    expect(action_policy_accept(&policy, &input, 3000) == RISK_ACCEPTED,
           "scene must be accepted without advancing the real frame sequence");
    input = risk(5, 3000, 20, "low");
    expect(action_policy_accept(&policy, &input, 3100) == RISK_ACCEPTED,
           "next real frame must remain acceptable after a scene");

    input = risk(6, 3200, 29, "attention");
    expect(action_policy_accept(&policy, &input, 3300) == RISK_REJECT_BAND,
           "score/band mismatch accepted");
    input = risk(6, 100, 20, "low");
    expect(action_policy_accept(&policy, &input, 3301) == RISK_REJECT_STALE,
           "stale callback accepted");
    input = risk(6, 3300, 20, "low");
    input.boot_id = "fedcba9876543210";
    expect(action_policy_accept(&policy, &input, 3400) == RISK_REJECT_BOOT,
           "wrong boot id accepted");

    expect(action_policy_decide(&policy, 6101).state == ACTION_STATE_FAULT,
           "risk older than three seconds must fail safe");
    expect(action_policy_decide(&policy, 6101).rgb_pattern == RGB_PURPLE_BLINK_1HZ,
           "stale risk must blink purple");

    action_policy_set_fault(&policy, ACTION_FAULT_NETWORK, true);
    expect(action_policy_decide(&policy, 3000).state == ACTION_STATE_FAULT,
           "network fault must override a fresh risk");
    action_policy_set_fault(&policy, ACTION_FAULT_NETWORK, false);

    action_policy_init(&policy, "aix-helmet-01", "fedcba9876543210", 6000);
    input = risk(0, 6100, 20, "low");
    input.boot_id = "fedcba9876543210";
    expect(action_policy_accept(&policy, &input, 6200) == RISK_ACCEPTED,
           "new boot cycle must accept a reset frame sequence");

    expect(strcmp(action_state_name(ACTION_STATE_CRITICAL), "critical") == 0,
           "action state name mismatch");
    expect(strcmp(rgb_pattern_name(RGB_RED_DOUBLE_PULSE), "red_double_pulse") == 0,
           "RGB pattern name mismatch");

    if (failures == 0) {
        printf("action_policy_test: ALL PASSED\n");
    }
    return failures;
}
