#include "voice_prompt.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include "dfplayer.h"

static bool command_id_is_valid(const char *command_id)
{
    if (command_id == NULL || command_id[0] == '\0') {
        return false;
    }
    for (size_t index = 0; command_id[index] != '\0'; index++) {
        const unsigned char character = (unsigned char)command_id[index];
        if (index + 1U >= VOICE_PROMPT_COMMAND_ID_CAPACITY ||
            !(isalnum(character) || character == ':' || character == '_' || character == '-')) {
            return false;
        }
    }
    return true;
}

bool voice_prompt_track_for_band(const char *risk_band, uint8_t *out_track)
{
    if (risk_band == NULL || out_track == NULL) {
        return false;
    }
    if (strcmp(risk_band, "attention") == 0) {
        *out_track = 1U;
    } else if (strcmp(risk_band, "high") == 0) {
        *out_track = 2U;
    } else if (strcmp(risk_band, "critical") == 0) {
        *out_track = 3U;
    } else {
        return false;
    }
    return true;
}

bool voice_prompt_track_for_scene(uint8_t scene_id, uint8_t *out_track)
{
    if (out_track == NULL) {
        return false;
    }
    if (scene_id == 4U || scene_id == 5U || scene_id == 6U) {
        *out_track = scene_id;
        return true;
    }
    return false;
}

bool voice_prompt_scene_is_valid(uint8_t scene_id)
{
    return scene_id == 4U || scene_id == 5U || scene_id == 6U;
}

bool voice_prompt_request_is_valid(const char *risk_band, const voice_prompt_request_t *request)
{
    uint8_t expected_track = 0;
    return request != NULL && voice_prompt_track_for_band(risk_band, &expected_track) &&
           request->track == expected_track && command_id_is_valid(request->command_id);
}

bool voice_prompt_queue_item_init(voice_prompt_queue_item_t *out_item, const voice_prompt_request_t *request)
{
    if (out_item == NULL || request == NULL || !command_id_is_valid(request->command_id)) {
        return false;
    }
    memset(out_item, 0, sizeof(*out_item));
    snprintf(out_item->command_id, sizeof(out_item->command_id), "%s", request->command_id);
    out_item->track = request->track;
    out_item->frame_seq = request->frame_seq;
    return true;
}

const char *voice_prompt_status_name(voice_prompt_status_t status)
{
    switch (status) {
    case VOICE_PROMPT_NOT_REQUESTED:
        return "not_requested";
    case VOICE_PROMPT_QUEUED:
        return "queued";
    case VOICE_PROMPT_DUPLICATE:
        return "duplicate";
    case VOICE_PROMPT_SUPPRESSED:
        return "suppressed";
    case VOICE_PROMPT_REJECTED:
        return "rejected";
    case VOICE_PROMPT_UNAVAILABLE:
        return "unavailable";
    default:
        return "rejected";
    }
}

const char *voice_prompt_error_name(voice_prompt_status_t status)
{
    switch (status) {
    case VOICE_PROMPT_SUPPRESSED:
        return "higher_priority_playing";
    case VOICE_PROMPT_REJECTED:
        return "invalid_voice_prompt";
    case VOICE_PROMPT_UNAVAILABLE:
        return "dfplayer_unavailable";
    default:
        return "";
    }
}

voice_prompt_result_t voice_prompt_result_not_requested(void)
{
    return (voice_prompt_result_t){
        .requested = false,
        .accepted = false,
        .duplicate = false,
        .track = 0,
        .status = VOICE_PROMPT_NOT_REQUESTED,
    };
}

voice_prompt_result_t voice_prompt_result_rejected(void)
{
    return (voice_prompt_result_t){
        .requested = true,
        .accepted = false,
        .duplicate = false,
        .track = 0,
        .status = VOICE_PROMPT_REJECTED,
    };
}

voice_prompt_result_t voice_prompt_result_duplicate_ack(const voice_prompt_result_t *original)
{
    if (original == NULL || !original->requested) {
        return voice_prompt_result_not_requested();
    }
    if (!original->accepted ||
        (original->status != VOICE_PROMPT_QUEUED && original->status != VOICE_PROMPT_DUPLICATE)) {
        return *original;
    }
    voice_prompt_result_t result = *original;
    result.accepted = true;
    result.duplicate = true;
    result.status = VOICE_PROMPT_DUPLICATE;
    return result;
}

void voice_prompt_policy_init(voice_prompt_policy_t *policy, bool available)
{
    if (policy == NULL) {
        return;
    }
    memset(policy, 0, sizeof(*policy));
    policy->available = available;
}

void voice_prompt_policy_set_available(voice_prompt_policy_t *policy, bool available)
{
    if (policy != NULL) {
        policy->available = available;
        if (!available) {
            policy->playing_track = 0;
        }
    }
}

void voice_prompt_policy_mark_finished(voice_prompt_policy_t *policy, uint8_t track)
{
    if (policy != NULL && policy->playing_track == track) {
        policy->playing_track = 0;
    }
}

void voice_prompt_policy_handle_player_error(voice_prompt_policy_t *policy)
{
    voice_prompt_policy_set_available(policy, false);
}

static bool command_was_seen(const voice_prompt_policy_t *policy, const char *command_id)
{
    for (size_t index = 0; index < policy->command_history_count; index++) {
        if (strcmp(policy->command_history[index], command_id) == 0) {
            return true;
        }
    }
    return false;
}

static void remember_command(voice_prompt_policy_t *policy, const char *command_id)
{
    size_t index = policy->command_history_count;
    if (index < VOICE_PROMPT_HISTORY_CAPACITY) {
        policy->command_history_count++;
    } else {
        memmove(policy->command_history, policy->command_history + 1U,
                (VOICE_PROMPT_HISTORY_CAPACITY - 1U) * VOICE_PROMPT_COMMAND_ID_CAPACITY);
        index = VOICE_PROMPT_HISTORY_CAPACITY - 1U;
    }
    snprintf(policy->command_history[index], VOICE_PROMPT_COMMAND_ID_CAPACITY, "%s", command_id);
}

voice_prompt_result_t voice_prompt_policy_submit(
    voice_prompt_policy_t *policy,
    const char *risk_band,
    const voice_prompt_request_t *request)
{
    voice_prompt_result_t result = voice_prompt_result_rejected();
    if (!voice_prompt_request_is_valid(risk_band, request) || policy == NULL) {
        return result;
    }
    result.track = request->track;
    if (command_was_seen(policy, request->command_id)) {
        result.accepted = true;
        result.duplicate = true;
        result.status = VOICE_PROMPT_DUPLICATE;
        return result;
    }
    if (!policy->available) {
        result.status = VOICE_PROMPT_UNAVAILABLE;
        return result;
    }
    if (policy->playing_track > request->track) {
        result.status = VOICE_PROMPT_SUPPRESSED;
        return result;
    }
    remember_command(policy, request->command_id);
    policy->playing_track = request->track;
    result.accepted = true;
    result.status = VOICE_PROMPT_QUEUED;
    return result;
}

voice_prompt_result_t voice_prompt_policy_submit_scene(
    voice_prompt_policy_t *policy,
    uint8_t scene_id,
    const voice_prompt_request_t *request)
{
    voice_prompt_result_t result = voice_prompt_result_rejected();
    uint8_t expected_track = 0U;
    if (policy == NULL || request == NULL || !voice_prompt_track_for_scene(scene_id, &expected_track) ||
        request->track != expected_track || !command_id_is_valid(request->command_id)) {
        return result;
    }
    result.track = request->track;
    if (command_was_seen(policy, request->command_id)) {
        result.accepted = true;
        result.duplicate = true;
        result.status = VOICE_PROMPT_DUPLICATE;
        return result;
    }
    if (!policy->available) {
        result.status = VOICE_PROMPT_UNAVAILABLE;
        return result;
    }
    if (policy->playing_track > request->track) {
        result.status = VOICE_PROMPT_SUPPRESSED;
        return result;
    }
    remember_command(policy, request->command_id);
    policy->playing_track = request->track;
    result.accepted = true;
    result.status = VOICE_PROMPT_QUEUED;
    return result;
}

#ifdef ESP_PLATFORM

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#ifndef CONFIG_AIX_ENABLE_VOICE_PROMPT
#define CONFIG_AIX_ENABLE_VOICE_PROMPT 0
#endif
#ifndef CONFIG_AIX_VOICE_VOLUME
#define CONFIG_AIX_VOICE_VOLUME 18
#endif

#define VOICE_TASK_STACK 4096U
#define VOICE_TASK_PRIORITY 4U
#define VOICE_CARD_WAIT_MS 3000U
#define VOICE_RETRY_DELAY_MS 3000U
#define DFPLAYER_SOURCE_TF 0x0002U

static const char *TAG = "AIX_VOICE";
static QueueHandle_t s_queue;
static SemaphoreHandle_t s_lock;
static voice_prompt_policy_t s_policy;
static bool s_started;
static char s_playing_command_id[VOICE_PROMPT_COMMAND_ID_CAPACITY];
static uint8_t s_playing_track;
static uint32_t s_playing_frame_seq;

static void policy_take(void)
{
    (void)xSemaphoreTake(s_lock, portMAX_DELAY);
}

static void policy_give(void)
{
    (void)xSemaphoreGive(s_lock);
}

static void emit_voice_status(const char *state, const voice_prompt_request_t *request, const char *error)
{
    const uint8_t track = request != NULL ? request->track : 0U;
    const uint32_t frame_seq = request != NULL ? request->frame_seq : 0U;
    const char *command_id = request != NULL && request->command_id != NULL ? request->command_id : "";
    printf("{\"type\":\"voice_status\",\"version\":1,\"state\":\"%s\","
           "\"track\":%u,\"frame_seq\":%lu,\"command_id\":\"%s\",\"error\":\"%s\"}\n",
           state,
           (unsigned int)track,
           (unsigned long)frame_seq,
           command_id,
           error != NULL ? error : "");
    fflush(stdout);
}

static bool configure_dfplayer_if_card_ready(void)
{
    if (dfplayer_uart_start() != ESP_OK) {
        return false;
    }
    (void)dfplayer_send_command(DFPLAYER_COMMAND_RESET, 0U, false);
    for (uint32_t elapsed = 0; elapsed < VOICE_CARD_WAIT_MS; elapsed += 100U) {
        dfplayer_message_t message = {0};
        const esp_err_t ret = dfplayer_read_message(&message, 100U);
        if (ret == ESP_OK && message.command == DFPLAYER_EVENT_CARD_ONLINE && message.parameter == DFPLAYER_SOURCE_TF) {
            if (dfplayer_send_command(DFPLAYER_COMMAND_SELECT_SOURCE, DFPLAYER_SOURCE_TF, false) == ESP_OK &&
                dfplayer_send_command(DFPLAYER_COMMAND_SET_VOLUME, CONFIG_AIX_VOICE_VOLUME, false) == ESP_OK) {
                return true;
            }
            return false;
        }
    }
    return false;
}

static void voice_task(void *arg)
{
    (void)arg;
    for (;;) {
        policy_take();
        const bool available = s_policy.available;
        policy_give();
        if (!available) {
            emit_voice_status("initializing", NULL, "");
            if (configure_dfplayer_if_card_ready()) {
                policy_take();
                voice_prompt_policy_set_available(&s_policy, true);
                policy_give();
                emit_voice_status("ready", NULL, "");
                continue;
            }
            emit_voice_status("error", NULL, "tf_card_not_ready");
            vTaskDelay(pdMS_TO_TICKS(VOICE_RETRY_DELAY_MS));
            continue;
        }

        voice_prompt_queue_item_t queued_request = {0};
        if (xQueueReceive(s_queue, &queued_request, pdMS_TO_TICKS(100U)) == pdTRUE) {
            voice_prompt_request_t request = {
                .command_id = queued_request.command_id,
                .track = queued_request.track,
                .frame_seq = queued_request.frame_seq,
            };
            const esp_err_t ret = dfplayer_send_command(DFPLAYER_COMMAND_PLAY_MP3_FOLDER, request.track, true);
            if (ret == ESP_OK) {
                snprintf(s_playing_command_id, sizeof(s_playing_command_id), "%s", request.command_id);
                s_playing_track = request.track;
                s_playing_frame_seq = request.frame_seq;
                emit_voice_status("playing", &request, "");
            } else {
                policy_take();
                voice_prompt_policy_mark_finished(&s_policy, request.track);
                voice_prompt_policy_set_available(&s_policy, false);
                policy_give();
                emit_voice_status("error", &request, "uart_write_failed");
                continue;
            }
        }

        dfplayer_message_t message = {0};
        while (dfplayer_read_message(&message, 0U) == ESP_OK) {
            if (message.command == DFPLAYER_EVENT_PLAY_FINISHED_TF) {
                voice_prompt_request_t finished = {
                    .command_id = s_playing_command_id,
                    .track = s_playing_track != 0U ? s_playing_track : (uint8_t)message.parameter,
                    .frame_seq = s_playing_frame_seq,
                };
                policy_take();
                voice_prompt_policy_mark_finished(&s_policy, finished.track);
                policy_give();
                emit_voice_status("finished", &finished, "");
                s_playing_command_id[0] = '\0';
                s_playing_track = 0U;
                s_playing_frame_seq = 0U;
            } else if (message.command == DFPLAYER_EVENT_ERROR) {
                voice_prompt_request_t failed = {
                    .command_id = s_playing_command_id,
                    .track = s_playing_track,
                    .frame_seq = s_playing_frame_seq,
                };
                policy_take();
                voice_prompt_policy_handle_player_error(&s_policy);
                policy_give();
                emit_voice_status("error", &failed, "dfplayer_reported_error");
                s_playing_command_id[0] = '\0';
                s_playing_track = 0U;
                s_playing_frame_seq = 0U;
            }
        }
    }
}

esp_err_t voice_prompt_start(void)
{
#if !CONFIG_AIX_ENABLE_VOICE_PROMPT
    return ESP_OK;
#else
    if (s_started) {
        return ESP_OK;
    }
    s_queue = xQueueCreate(1U, sizeof(voice_prompt_queue_item_t));
    s_lock = xSemaphoreCreateMutex();
    if (s_queue == NULL || s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    voice_prompt_policy_init(&s_policy, false);
    if (xTaskCreate(voice_task, "aix_voice", VOICE_TASK_STACK, NULL, VOICE_TASK_PRIORITY, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    ESP_LOGI(TAG, "DFPlayer voice task started: UART2 TX=GPIO47 RX=GPIO48 volume=%d", CONFIG_AIX_VOICE_VOLUME);
    return ESP_OK;
#endif
}

voice_prompt_result_t voice_prompt_submit(const char *risk_band, const voice_prompt_request_t *request)
{
    if (!s_started || s_lock == NULL || s_queue == NULL) {
        voice_prompt_result_t unavailable = voice_prompt_result_rejected();
        unavailable.track = request != NULL ? request->track : 0U;
        unavailable.status = VOICE_PROMPT_UNAVAILABLE;
        return unavailable;
    }
    policy_take();
    voice_prompt_result_t result = voice_prompt_policy_submit(&s_policy, risk_band, request);
    if (result.status == VOICE_PROMPT_QUEUED) {
        voice_prompt_queue_item_t queued_request = {0};
        if (!voice_prompt_queue_item_init(&queued_request, request) ||
            xQueueOverwrite(s_queue, &queued_request) != pdPASS) {
            voice_prompt_policy_mark_finished(&s_policy, request->track);
            result.accepted = false;
            result.status = VOICE_PROMPT_UNAVAILABLE;
        }
    }
    policy_give();
    return result;
}

voice_prompt_result_t voice_prompt_submit_scene(uint8_t scene_id, const voice_prompt_request_t *request)
{
    if (!s_started || s_lock == NULL || s_queue == NULL) {
        voice_prompt_result_t unavailable = voice_prompt_result_rejected();
        unavailable.track = request != NULL ? request->track : 0U;
        unavailable.status = VOICE_PROMPT_UNAVAILABLE;
        return unavailable;
    }
    policy_take();
    voice_prompt_result_t result = voice_prompt_policy_submit_scene(&s_policy, scene_id, request);
    if (result.status == VOICE_PROMPT_QUEUED) {
        voice_prompt_queue_item_t queued_request = {0};
        if (!voice_prompt_queue_item_init(&queued_request, request) ||
            xQueueOverwrite(s_queue, &queued_request) != pdPASS) {
            voice_prompt_policy_mark_finished(&s_policy, request->track);
            result.accepted = false;
            result.status = VOICE_PROMPT_UNAVAILABLE;
        }
    }
    policy_give();
    return result;
}

bool voice_prompt_is_ready(void)
{
    if (!s_started || s_lock == NULL) {
        return false;
    }
    policy_take();
    const bool ready = s_policy.available;
    policy_give();
    return ready;
}

#endif
