#pragma once

#include <stdatomic.h>

#include "action_policy.h"
#include "road_hazard_policy.h"

#define SEMANTIC_ANALYSIS_ID_CAPACITY 65

typedef enum {
    SEMANTIC_INDICATOR_ACCEPTED = 0,
    SEMANTIC_INDICATOR_DUPLICATE,
    SEMANTIC_INDICATOR_REJECT_SCHEMA,
} semantic_indicator_result_t;

typedef struct {
    bool flashed;
    bool suppressed;
    const char *reason;
} semantic_indicator_outcome_t;

typedef enum {
    COLLISION_INDICATOR_ACCEPTED = 0,
    COLLISION_INDICATOR_DUPLICATE,
    COLLISION_INDICATOR_REJECT_IDENTITY,
} collision_indicator_result_t;

typedef enum {
    COLLISION_ACK_ACCEPTED = 0,
    COLLISION_ACK_REJECT_IDENTITY,
} collision_ack_result_t;

typedef struct {
    action_state_t state;
    rgb_pattern_t pattern;
    bool remote;
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY];
    uint32_t expires_in_ms;
    bool semantic;
    bool collision;
} alert_effective_t;

typedef struct {
    atomic_flag lock;
    road_hazard_policy_t hazards;
    action_decision_t local;
    char boot_id[ACTION_POLICY_BOOT_ID_CAPACITY];
    char last_analysis_id[SEMANTIC_ANALYSIS_ID_CAPACITY];
    uint64_t semantic_until_ms;
    bool semantic_last_flashed;
    bool semantic_last_suppressed;
    bool collision_latched;
    bool collision_has_count;
    uint32_t collision_impact_count;
} alert_arbiter_t;

void alert_arbiter_init(
    alert_arbiter_t *arbiter,
    const char *device_id,
    const char *boot_id,
    const action_decision_t *initial_local);
void alert_arbiter_set_local(alert_arbiter_t *arbiter, const action_decision_t *decision, uint64_t now_ms);
road_hazard_result_t alert_arbiter_submit(
    alert_arbiter_t *arbiter,
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome);
bool alert_arbiter_tick(alert_arbiter_t *arbiter, uint64_t now_ms, road_hazard_expired_t *expired);
alert_effective_t alert_arbiter_get_effective(alert_arbiter_t *arbiter, uint64_t now_ms);
semantic_indicator_result_t alert_arbiter_submit_semantic(
    alert_arbiter_t *arbiter,
    const char *analysis_id,
    uint64_t now_ms,
    semantic_indicator_outcome_t *outcome);
collision_indicator_result_t alert_arbiter_submit_collision(
    alert_arbiter_t *arbiter, const char *boot_id, uint32_t impact_count);
collision_ack_result_t alert_arbiter_ack_collision(
    alert_arbiter_t *arbiter, const char *boot_id, uint32_t impact_count);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t alert_arbiter_runtime_start(
    const char *device_id,
    const char *boot_id,
    const action_decision_t *initial_local);
void alert_arbiter_runtime_set_local(const action_decision_t *decision, uint64_t now_ms);
road_hazard_result_t alert_arbiter_runtime_submit(
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome);
alert_effective_t alert_arbiter_runtime_get_effective(uint64_t now_ms);
const char *alert_arbiter_runtime_last_voice_state(void);
semantic_indicator_result_t alert_arbiter_runtime_submit_semantic(
    const char *analysis_id,
    uint64_t now_ms,
    semantic_indicator_outcome_t *outcome);
collision_indicator_result_t alert_arbiter_runtime_submit_collision(
    const char *boot_id, uint32_t impact_count);
collision_ack_result_t alert_arbiter_runtime_ack_collision(
    const char *boot_id, uint32_t impact_count);
#endif
