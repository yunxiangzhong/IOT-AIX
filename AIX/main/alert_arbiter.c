#include "alert_arbiter.h"

#include <stdio.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

static void lock_arbiter(alert_arbiter_t *arbiter)
{
    while (atomic_flag_test_and_set_explicit(&arbiter->lock, memory_order_acquire)) {
#ifdef ESP_PLATFORM
        vTaskDelay(1);
#endif
    }
}

static void unlock_arbiter(alert_arbiter_t *arbiter)
{
    atomic_flag_clear_explicit(&arbiter->lock, memory_order_release);
}

static unsigned local_priority(action_state_t state)
{
    switch (state) {
        case ACTION_STATE_CRITICAL: return 5U;
        case ACTION_STATE_HIGH: return 4U;
        case ACTION_STATE_FAULT: return 3U;
        case ACTION_STATE_ATTENTION: return 2U;
        case ACTION_STATE_SAFE:
        case ACTION_STATE_LOADING:
        default: return 1U;
    }
}

static unsigned remote_priority(road_hazard_severity_t severity)
{
    return severity == ROAD_HAZARD_SEVERITY_CRITICAL ? 5U
           : severity == ROAD_HAZARD_SEVERITY_HIGH ? 4U
                                                   : 2U;
}

static action_state_t remote_state(road_hazard_severity_t severity)
{
    return severity == ROAD_HAZARD_SEVERITY_CRITICAL ? ACTION_STATE_CRITICAL
           : severity == ROAD_HAZARD_SEVERITY_HIGH ? ACTION_STATE_HIGH
                                                   : ACTION_STATE_ATTENTION;
}

static rgb_pattern_t remote_pattern(road_hazard_severity_t severity)
{
    return severity == ROAD_HAZARD_SEVERITY_CRITICAL ? RGB_RED_DOUBLE_PULSE
           : severity == ROAD_HAZARD_SEVERITY_HIGH ? RGB_ORANGE_BLINK_2HZ
                                                   : RGB_YELLOW_BLINK_1HZ;
}

static alert_effective_t effective_locked(alert_arbiter_t *arbiter, uint64_t now_ms)
{
    alert_effective_t effective = {
        .state = arbiter->local.state,
        .pattern = arbiter->local.rgb_pattern,
    };
    road_hazard_severity_t severity;
    const char *event_id = NULL;
    uint32_t remaining = 0U;
    if (road_hazard_policy_highest_active(&arbiter->hazards, now_ms, &severity, &event_id, &remaining) &&
        remote_priority(severity) > local_priority(arbiter->local.state)) {
        effective.state = remote_state(severity);
        effective.pattern = remote_pattern(severity);
        effective.remote = true;
        effective.expires_in_ms = remaining;
        snprintf(effective.event_id, sizeof(effective.event_id), "%s", event_id);
    }
    return effective;
}

void alert_arbiter_init(
    alert_arbiter_t *arbiter,
    const char *device_id,
    const char *boot_id,
    const action_decision_t *initial_local)
{
    if (arbiter == NULL) return;
    memset(arbiter, 0, sizeof(*arbiter));
    atomic_flag_clear(&arbiter->lock);
    road_hazard_policy_init(&arbiter->hazards, device_id, boot_id);
    if (initial_local != NULL) arbiter->local = *initial_local;
}

void alert_arbiter_set_local(alert_arbiter_t *arbiter, const action_decision_t *decision, uint64_t now_ms)
{
    (void)now_ms;
    if (arbiter == NULL || decision == NULL) return;
    lock_arbiter(arbiter);
    arbiter->local = *decision;
    unlock_arbiter(arbiter);
}

road_hazard_result_t alert_arbiter_submit(
    alert_arbiter_t *arbiter,
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome)
{
    if (arbiter == NULL) return ROAD_HAZARD_REJECT_SCHEMA;
    lock_arbiter(arbiter);
    const road_hazard_result_t result = road_hazard_policy_submit(&arbiter->hazards, request, now_ms, outcome);
    unlock_arbiter(arbiter);
    return result;
}

bool alert_arbiter_tick(alert_arbiter_t *arbiter, uint64_t now_ms, road_hazard_expired_t *expired)
{
    if (arbiter == NULL) return false;
    lock_arbiter(arbiter);
    const bool result = road_hazard_policy_expire_next(&arbiter->hazards, now_ms, expired);
    unlock_arbiter(arbiter);
    return result;
}

alert_effective_t alert_arbiter_get_effective(alert_arbiter_t *arbiter, uint64_t now_ms)
{
    alert_effective_t result = {0};
    if (arbiter == NULL) return result;
    lock_arbiter(arbiter);
    result = effective_locked(arbiter, now_ms);
    unlock_arbiter(arbiter);
    return result;
}

#ifdef ESP_PLATFORM

#include "esp_timer.h"
#include "rgb_status.h"
#include "risk_receiver.h"

static alert_arbiter_t s_runtime;
static bool s_runtime_started;

static uint64_t runtime_now_ms(void)
{
    return (uint64_t)(esp_timer_get_time() / 1000ULL);
}

static void emit_expired(const road_hazard_expired_t *expired, const alert_effective_t *effective)
{
    char status[384];
    if (risk_receiver_format_road_hazard_status(
            status, sizeof(status), "expired", expired->event_id, "ttl_expired", 0U,
            rgb_pattern_name(effective->pattern)) >= 0) {
        printf("%s\n", status);
        fflush(stdout);
    }
}

static void arbiter_task(void *arg)
{
    (void)arg;
    rgb_pattern_t applied = (rgb_pattern_t)-1;
    for (;;) {
        const uint64_t now = runtime_now_ms();
        road_hazard_expired_t expired;
        while (alert_arbiter_tick(&s_runtime, now, &expired)) {
            const alert_effective_t current = alert_arbiter_get_effective(&s_runtime, now);
            emit_expired(&expired, &current);
        }
        const alert_effective_t effective = alert_arbiter_get_effective(&s_runtime, now);
        if (effective.pattern != applied) {
            rgb_status_set_pattern(effective.pattern);
            applied = effective.pattern;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

esp_err_t alert_arbiter_runtime_start(
    const char *device_id,
    const char *boot_id,
    const action_decision_t *initial_local)
{
    if (s_runtime_started) return ESP_OK;
    alert_arbiter_init(&s_runtime, device_id, boot_id, initial_local);
    esp_err_t ret = rgb_status_start();
    if (ret != ESP_OK) return ret;
    const alert_effective_t effective = alert_arbiter_get_effective(&s_runtime, runtime_now_ms());
    rgb_status_set_pattern(effective.pattern);
    if (xTaskCreate(arbiter_task, "alert_arbiter", 4096, NULL, 5, NULL) != pdPASS) return ESP_ERR_NO_MEM;
    s_runtime_started = true;
    return ESP_OK;
}

void alert_arbiter_runtime_set_local(const action_decision_t *decision, uint64_t now_ms)
{
    if (s_runtime_started) alert_arbiter_set_local(&s_runtime, decision, now_ms);
}

road_hazard_result_t alert_arbiter_runtime_submit(
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome)
{
    if (!s_runtime_started) return ROAD_HAZARD_REJECT_SCHEMA;
    return alert_arbiter_submit(&s_runtime, request, now_ms, outcome);
}

alert_effective_t alert_arbiter_runtime_get_effective(uint64_t now_ms)
{
    return alert_arbiter_get_effective(&s_runtime, now_ms);
}

#endif
