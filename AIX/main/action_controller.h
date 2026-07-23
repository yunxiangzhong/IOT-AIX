#pragma once

#include "action_policy.h"

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t action_controller_start(const char *device_id, const char *boot_id);
risk_accept_result_t action_controller_apply_risk(
    const vision_risk_input_t *risk,
    uint64_t now_ms,
    action_decision_t *decision);
void action_controller_set_fault(action_fault_t fault, bool active);
action_decision_t action_controller_get_decision(void);
bool action_controller_apply_demo(uint8_t scene_id, uint32_t frame_seq, action_decision_t *decision);
void action_controller_enter_demo(void);
void action_controller_reset_demo(void);
void action_controller_clear_demo(void);
#endif
