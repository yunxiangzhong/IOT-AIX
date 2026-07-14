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
#endif
