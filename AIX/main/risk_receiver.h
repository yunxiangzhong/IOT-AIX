#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool risk_receiver_token_matches(const char *expected, const char *provided);
bool risk_receiver_e2e_latency_ms(uint64_t capture_ts_ms, uint64_t now_ms, uint64_t *latency_ms);
bool risk_receiver_e2e_latency_at_ack(
    uint64_t capture_ts_ms,
    uint64_t decision_ms,
    uint64_t ack_now_ms,
    uint64_t *latency_ms);
int risk_receiver_format_action_ack(
    char *buffer,
    size_t capacity,
    uint32_t frame_seq,
    bool accepted,
    bool stale,
    uint64_t e2e_latency_ms,
    const char *action_state,
    const char *rgb_pattern,
    const char *error);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t risk_receiver_start(void);
#endif
