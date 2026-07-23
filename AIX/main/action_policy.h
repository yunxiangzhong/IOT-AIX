#pragma once

#include <stdbool.h>
#include <stdint.h>

#define ACTION_POLICY_DEVICE_ID_CAPACITY 64
#define ACTION_POLICY_BOOT_ID_CAPACITY 17
#define ACTION_POLICY_RISK_TTL_MS 3000ULL
#define ACTION_POLICY_BOOT_GRACE_MS 45000ULL

typedef enum {
    ACTION_STATE_LOADING = 0,
    ACTION_STATE_SAFE,
    ACTION_STATE_ATTENTION,
    ACTION_STATE_HIGH,
    ACTION_STATE_CRITICAL,
    ACTION_STATE_FAULT,
} action_state_t;

typedef enum {
    RGB_BLUE_BLINK_1HZ = 0,
    RGB_GREEN_SOLID,
    RGB_YELLOW_BLINK_1HZ,
    RGB_ORANGE_BLINK_2HZ,
    RGB_RED_DOUBLE_PULSE,
    RGB_PURPLE_BLINK_1HZ,
} rgb_pattern_t;

typedef enum {
    ACTION_FAULT_NONE = 0,
    ACTION_FAULT_CAMERA = 1 << 0,
    ACTION_FAULT_NETWORK = 1 << 1,
    ACTION_FAULT_MODEL = 1 << 2,
} action_fault_t;

typedef enum {
    RISK_ACCEPTED = 0,
    RISK_REJECT_INVALID,
    RISK_REJECT_DEVICE,
    RISK_REJECT_BOOT,
    RISK_REJECT_SEQUENCE,
    RISK_REJECT_STALE,
    RISK_REJECT_BAND,
} risk_accept_result_t;

typedef struct {
    const char *device_id;
    const char *boot_id;
    uint32_t frame_seq;
    uint64_t capture_ts_ms;
    int risk_score;
    const char *risk_band;
    const char *dominant_class;
    const char *reason;
    bool valid;
    bool actuation_hazard_present;
    bool actuation_hazard_active;
} vision_risk_input_t;

typedef struct {
    char device_id[ACTION_POLICY_DEVICE_ID_CAPACITY];
    char boot_id[ACTION_POLICY_BOOT_ID_CAPACITY];
    uint64_t boot_ts_ms;
    uint64_t received_ts_ms;
    uint64_t capture_ts_ms;
    uint32_t frame_seq;
    uint8_t risk_score;
    char risk_band[12];
    uint8_t faults;
    bool has_risk;
    bool actuation_hazard_present;
    bool actuation_hazard_active;
} action_policy_t;

typedef struct {
    action_state_t state;
    rgb_pattern_t rgb_pattern;
    uint32_t source_frame_seq;
    uint8_t risk_score;
    bool stale;
    bool valid;
    bool actuation_hazard_present;
    bool actuation_hazard_active;
} action_decision_t;

void action_policy_init(action_policy_t *policy, const char *device_id, const char *boot_id, uint64_t now_ms);
risk_accept_result_t action_policy_accept(action_policy_t *policy, const vision_risk_input_t *risk, uint64_t now_ms);
void action_policy_set_fault(action_policy_t *policy, action_fault_t fault, bool active);
action_decision_t action_policy_decide(const action_policy_t *policy, uint64_t now_ms);
const char *action_state_name(action_state_t state);
const char *rgb_pattern_name(rgb_pattern_t pattern);
const char *risk_accept_result_name(risk_accept_result_t result);
