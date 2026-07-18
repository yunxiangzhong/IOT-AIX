#pragma once

#include <stdatomic.h>

#include "action_policy.h"
#include "road_hazard_policy.h"

typedef struct {
    action_state_t state;
    rgb_pattern_t pattern;
    bool remote;
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY];
    uint32_t expires_in_ms;
} alert_effective_t;

typedef struct {
    atomic_flag lock;
    road_hazard_policy_t hazards;
    action_decision_t local;
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
#endif
