#include "host_risk.h"

#include <string.h>

static bool valid_band(const char *band)
{
    return band != NULL &&
           (strcmp(band, "low") == 0 || strcmp(band, "attention") == 0 ||
            strcmp(band, "high") == 0 || strcmp(band, "critical") == 0);
}

bool host_risk_accept(
    host_risk_state_t *state,
    uint32_t frame_seq,
    int risk_score,
    const char *risk_band,
    const char *dominant_class,
    uint64_t received_ts_ms)
{
    if (state == NULL || risk_score < 0 || risk_score > 100 || !valid_band(risk_band) ||
        dominant_class == NULL || (state->valid && frame_seq < state->frame_seq)) {
        return false;
    }
    state->valid = true;
    state->frame_seq = frame_seq;
    state->risk_score = (uint8_t)risk_score;
    state->capture_ts_ms = received_ts_ms;
    state->received_ts_ms = received_ts_ms;
    strncpy(state->risk_band, risk_band, sizeof(state->risk_band) - 1U);
    state->risk_band[sizeof(state->risk_band) - 1U] = '\0';
    strncpy(state->dominant_class, dominant_class, sizeof(state->dominant_class) - 1U);
    state->dominant_class[sizeof(state->dominant_class) - 1U] = '\0';
    return true;
}

bool host_risk_is_stale(const host_risk_state_t *state, uint64_t now_ms, uint64_t timeout_ms)
{
    return state == NULL || !state->valid || now_ms < state->received_ts_ms ||
           now_ms - state->received_ts_ms >= timeout_ms;
}
