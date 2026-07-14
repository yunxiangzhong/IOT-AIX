#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool valid;
    uint32_t frame_seq;
    uint64_t capture_ts_ms;
    uint8_t risk_score;
    char risk_band[12];
    char dominant_class[24];
    uint64_t received_ts_ms;
} host_risk_state_t;

bool host_risk_accept(
    host_risk_state_t *state,
    uint32_t frame_seq,
    int risk_score,
    const char *risk_band,
    const char *dominant_class,
    uint64_t received_ts_ms);
bool host_risk_is_stale(const host_risk_state_t *state, uint64_t now_ms, uint64_t timeout_ms);
