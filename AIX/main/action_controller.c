#include "action_controller.h"

#ifdef ESP_PLATFORM

#include <stdio.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "rgb_status.h"

static action_policy_t s_policy;
static action_decision_t s_decision;
static SemaphoreHandle_t s_lock;
static bool s_started;

static uint64_t now_ms(void)
{
    return (uint64_t)(esp_timer_get_time() / 1000ULL);
}

static bool decision_changed(const action_decision_t *left, const action_decision_t *right)
{
    return left->state != right->state || left->rgb_pattern != right->rgb_pattern ||
           left->source_frame_seq != right->source_frame_seq || left->stale != right->stale ||
           left->valid != right->valid;
}

static void emit_status(const action_decision_t *decision, uint64_t timestamp_ms)
{
    printf("{\"type\":\"action_status\",\"version\":1,\"ts_ms\":%llu,"
           "\"frame_seq\":%lu,\"risk_score\":%u,\"valid\":%s,\"stale\":%s,"
           "\"action_state\":\"%s\",\"rgb_pattern\":\"%s\"}\n",
           (unsigned long long)timestamp_ms,
           (unsigned long)decision->source_frame_seq,
           (unsigned int)decision->risk_score,
           decision->valid ? "true" : "false",
           decision->stale ? "true" : "false",
           action_state_name(decision->state),
           rgb_pattern_name(decision->rgb_pattern));
    fflush(stdout);
}

static void controller_task(void *arg)
{
    (void)arg;
    uint64_t last_heartbeat_ms = 0;
    for (;;) {
        uint64_t current_ms = now_ms();
        action_decision_t next;
        bool changed;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        next = action_policy_decide(&s_policy, current_ms);
        changed = decision_changed(&next, &s_decision);
        s_decision = next;
        xSemaphoreGive(s_lock);
        if (changed) {
            rgb_status_set_pattern(next.rgb_pattern);
        }
        if (changed || current_ms - last_heartbeat_ms >= 1000ULL) {
            emit_status(&next, current_ms);
            last_heartbeat_ms = current_ms;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

esp_err_t action_controller_start(const char *device_id, const char *boot_id)
{
    if (s_started) {
        return ESP_OK;
    }
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    action_policy_init(&s_policy, device_id, boot_id, now_ms());
    s_decision = action_policy_decide(&s_policy, now_ms());
    esp_err_t rgb_ret = rgb_status_start();
    if (rgb_ret != ESP_OK) {
        return rgb_ret;
    }
    rgb_status_set_pattern(s_decision.rgb_pattern);
    if (xTaskCreate(controller_task, "action_policy", 4096, NULL, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

risk_accept_result_t action_controller_apply_risk(
    const vision_risk_input_t *risk,
    uint64_t timestamp_ms,
    action_decision_t *decision)
{
    risk_accept_result_t result;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    result = action_policy_accept(&s_policy, risk, timestamp_ms);
    s_decision = action_policy_decide(&s_policy, timestamp_ms);
    if (decision != NULL) {
        *decision = s_decision;
    }
    xSemaphoreGive(s_lock);
    if (result == RISK_ACCEPTED) {
        rgb_status_set_pattern(s_decision.rgb_pattern);
        emit_status(&s_decision, timestamp_ms);
    }
    return result;
}

void action_controller_set_fault(action_fault_t fault, bool active)
{
    if (!s_started) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    action_policy_set_fault(&s_policy, fault, active);
    xSemaphoreGive(s_lock);
}

action_decision_t action_controller_get_decision(void)
{
    action_decision_t result = {0};
    if (!s_started) {
        return result;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    result = action_policy_decide(&s_policy, now_ms());
    xSemaphoreGive(s_lock);
    return result;
}

#endif
