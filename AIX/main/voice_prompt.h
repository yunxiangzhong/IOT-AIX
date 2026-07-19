#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define VOICE_PROMPT_COMMAND_ID_CAPACITY 64U
#define VOICE_PROMPT_HISTORY_CAPACITY 8U

typedef enum {
    VOICE_PROMPT_NOT_REQUESTED = 0,
    VOICE_PROMPT_QUEUED,
    VOICE_PROMPT_DUPLICATE,
    VOICE_PROMPT_SUPPRESSED,
    VOICE_PROMPT_REJECTED,
    VOICE_PROMPT_UNAVAILABLE,
} voice_prompt_status_t;

typedef struct {
    const char *command_id;
    uint8_t track;
    uint32_t frame_seq;
} voice_prompt_request_t;

typedef struct {
    char command_id[VOICE_PROMPT_COMMAND_ID_CAPACITY];
    uint8_t track;
    uint32_t frame_seq;
} voice_prompt_queue_item_t;

typedef struct {
    bool requested;
    bool accepted;
    bool duplicate;
    uint8_t track;
    voice_prompt_status_t status;
} voice_prompt_result_t;

typedef struct {
    bool available;
    uint8_t playing_track;
    char command_history[VOICE_PROMPT_HISTORY_CAPACITY][VOICE_PROMPT_COMMAND_ID_CAPACITY];
    size_t command_history_count;
} voice_prompt_policy_t;

bool voice_prompt_track_for_band(const char *risk_band, uint8_t *out_track);
bool voice_prompt_request_is_valid(const char *risk_band, const voice_prompt_request_t *request);
bool voice_prompt_queue_item_init(voice_prompt_queue_item_t *out_item, const voice_prompt_request_t *request);
const char *voice_prompt_status_name(voice_prompt_status_t status);
const char *voice_prompt_error_name(voice_prompt_status_t status);
voice_prompt_result_t voice_prompt_result_not_requested(void);
voice_prompt_result_t voice_prompt_result_rejected(void);
voice_prompt_result_t voice_prompt_result_duplicate_ack(const voice_prompt_result_t *original);
void voice_prompt_policy_init(voice_prompt_policy_t *policy, bool available);
void voice_prompt_policy_set_available(voice_prompt_policy_t *policy, bool available);
void voice_prompt_policy_mark_finished(voice_prompt_policy_t *policy, uint8_t track);
void voice_prompt_policy_handle_player_error(voice_prompt_policy_t *policy);
voice_prompt_result_t voice_prompt_policy_submit(
    voice_prompt_policy_t *policy,
    const char *risk_band,
    const voice_prompt_request_t *request);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t voice_prompt_start(void);
voice_prompt_result_t voice_prompt_submit(const char *risk_band, const voice_prompt_request_t *request);
bool voice_prompt_is_ready(void);
#endif
