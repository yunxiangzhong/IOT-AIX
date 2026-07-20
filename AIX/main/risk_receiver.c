#include "risk_receiver.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

bool risk_receiver_token_matches(const char *expected, const char *provided)
{
    if (expected == NULL || provided == NULL || expected[0] == '\0') {
        return false;
    }
    size_t expected_length = strlen(expected);
    size_t provided_length = strlen(provided);
    if (expected_length != provided_length) {
        return false;
    }
    unsigned char difference = 0U;
    for (size_t index = 0; index < expected_length; index++) {
        difference |= (unsigned char)(expected[index] ^ provided[index]);
    }
    return difference == 0U;
}

bool risk_receiver_e2e_latency_ms(uint64_t capture_ts_ms, uint64_t now_ms, uint64_t *latency_ms)
{
    if (latency_ms == NULL || capture_ts_ms > now_ms) {
        return false;
    }
    *latency_ms = now_ms - capture_ts_ms;
    return true;
}

bool risk_receiver_e2e_latency_at_ack(
    uint64_t capture_ts_ms,
    uint64_t decision_ms,
    uint64_t ack_now_ms,
    uint64_t *latency_ms)
{
    if (ack_now_ms < decision_ms) {
        return false;
    }
    return risk_receiver_e2e_latency_ms(capture_ts_ms, ack_now_ms, latency_ms);
}

int risk_receiver_format_action_ack(
    char *buffer,
    size_t capacity,
    uint32_t frame_seq,
    bool accepted,
    bool stale,
    uint64_t e2e_latency_ms,
    const char *action_state,
    const char *rgb_pattern,
    const char *error)
{
    if (buffer == NULL || capacity == 0U || action_state == NULL || rgb_pattern == NULL) {
        return -1;
    }
    int written = snprintf(
        buffer,
        capacity,
        "{\"type\":\"action_ack\",\"version\":1,\"frame_seq\":%lu,\"accepted\":%s,"
        "\"stale\":%s,\"action_state\":\"%s\",\"rgb_pattern\":\"%s\","
        "\"e2e_latency_ms\":%llu,\"error\":\"%s\"}",
        (unsigned long)frame_seq,
        accepted ? "true" : "false",
        stale ? "true" : "false",
        action_state,
        rgb_pattern,
        (unsigned long long)e2e_latency_ms,
        error != NULL ? error : "");
    return written >= 0 && (size_t)written < capacity ? written : -1;
}

bool risk_receiver_copy_safe_road_hazard_event_id(char *output, size_t capacity, const char *input)
{
    if (output == NULL || capacity == 0U) {
        return false;
    }
    output[0] = '\0';
    if (input == NULL) {
        return false;
    }
    const size_t length = strlen(input);
    if (length == 0U || length > 64U || length >= capacity) {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        const unsigned char value = (unsigned char)input[index];
        const bool valid = (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z') ||
                           (value >= '0' && value <= '9') || value == '-' || value == '_' ||
                           value == '.' || value == '~';
        if (!valid) {
            return false;
        }
    }
    memcpy(output, input, length + 1U);
    return true;
}

bool risk_receiver_copy_safe_road_hazard_severity(char *output, size_t capacity, const char *input)
{
    if (output == NULL || capacity == 0U) {
        return false;
    }
    output[0] = '\0';
    if (input == NULL ||
        (strcmp(input, "attention") != 0 && strcmp(input, "high") != 0 && strcmp(input, "critical") != 0)) {
        return false;
    }
    const size_t length = strlen(input);
    if (length >= capacity) {
        return false;
    }
    memcpy(output, input, length + 1U);
    return true;
}

int risk_receiver_format_road_hazard_ack(
    char *buffer,
    size_t capacity,
    const char *device_id,
    const char *boot_id,
    bool accepted,
    bool duplicate,
    const char *event_id,
    uint32_t expires_in_ms,
    const char *severity,
    const char *effective_rgb_pattern,
    const char *voice_state,
    const char *error)
{
    if (buffer == NULL || capacity == 0U || device_id == NULL || boot_id == NULL ||
        event_id == NULL || severity == NULL || effective_rgb_pattern == NULL || voice_state == NULL) {
        return -1;
    }
    const int written = snprintf(
        buffer, capacity,
        "{\"type\":\"road_hazard_ack\",\"version\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"accepted\":%s,\"duplicate\":%s,\"event_id\":\"%s\",\"expires_in_ms\":%lu,"
        "\"severity\":\"%s\",\"effective_rgb_pattern\":\"%s\","
        "\"voice_state\":\"%s\",\"error\":\"%s\"}",
        device_id, boot_id, accepted ? "true" : "false", duplicate ? "true" : "false",
        event_id, (unsigned long)expires_in_ms, severity, effective_rgb_pattern,
        voice_state, error != NULL ? error : "");
    return written >= 0 && (size_t)written < capacity ? written : -1;
}

int risk_receiver_format_road_hazard_status(
    char *buffer,
    size_t capacity,
    const char *state,
    const char *event_id,
    const char *reason,
    uint32_t expires_in_ms,
    const char *effective_rgb_pattern)
{
    if (buffer == NULL || capacity == 0U || state == NULL || event_id == NULL ||
        reason == NULL || effective_rgb_pattern == NULL) {
        return -1;
    }
    const int written = snprintf(
        buffer, capacity,
        "{\"type\":\"road_hazard_status\",\"version\":1,\"state\":\"%s\","
        "\"event_id\":\"%s\",\"reason\":\"%s\",\"expires_in_ms\":%lu,"
        "\"effective_rgb_pattern\":\"%s\"}",
        state, event_id, reason, (unsigned long)expires_in_ms, effective_rgb_pattern);
    return written >= 0 && (size_t)written < capacity ? written : -1;
}

#ifdef ESP_PLATFORM

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "alert_arbiter.h"
#include "action_controller.h"
#include "cJSON.h"
#include "device_identity.h"
#include "esp_check.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "mpu6050_sensor.h"
#include "pneumatic_controller.h"
#include "voice_prompt.h"

#ifndef CONFIG_AIX_LINK_TOKEN
#define CONFIG_AIX_LINK_TOKEN ""
#endif
#ifndef CONFIG_AIX_RISK_RECEIVER_PORT
#define CONFIG_AIX_RISK_RECEIVER_PORT 8080
#endif

#define RISK_BODY_MAX 2048U
#define ROAD_HAZARD_BODY_MAX 2048U
#define PNEUMATIC_BODY_MAX 1024U
#define RISK_CACHE_DEVICE_ID_CAPACITY 64U
#define RISK_CACHE_BOOT_ID_CAPACITY 32U

static const char *TAG = "AIX_RISK_RX";
static httpd_handle_t s_server;

typedef struct {
    bool valid;
    bool voice_requested;
    char device_id[RISK_CACHE_DEVICE_ID_CAPACITY];
    char boot_id[RISK_CACHE_BOOT_ID_CAPACITY];
    char command_id[VOICE_PROMPT_COMMAND_ID_CAPACITY];
    uint32_t frame_seq;
    action_decision_t decision;
    voice_prompt_result_t voice_result;
} risk_ack_cache_t;

static risk_ack_cache_t s_risk_ack_cache;

static bool token_matches(httpd_req_t *request)
{
    size_t length = httpd_req_get_hdr_value_len(request, "X-AIX-Token");
    if (length == 0 || length >= 128U || CONFIG_AIX_LINK_TOKEN[0] == '\0') {
        return false;
    }
    char value[128];
    if (httpd_req_get_hdr_value_str(request, "X-AIX-Token", value, sizeof(value)) != ESP_OK) {
        return false;
    }
    return risk_receiver_token_matches(CONFIG_AIX_LINK_TOKEN, value);
}

static bool device_and_boot_match(const cJSON *device, const cJSON *boot)
{
    return cJSON_IsString(device) && cJSON_IsString(boot) &&
           strcmp(device->valuestring, device_identity_device_id()) == 0 &&
           strcmp(boot->valuestring, device_identity_boot_id()) == 0;
}

static bool cached_ack_matches(
    const vision_risk_input_t *risk,
    bool voice_requested,
    const char *command_id,
    action_decision_t *out_decision,
    voice_prompt_result_t *out_voice_result)
{
    if (!s_risk_ack_cache.valid || s_risk_ack_cache.frame_seq != risk->frame_seq ||
        s_risk_ack_cache.voice_requested != voice_requested ||
        strcmp(s_risk_ack_cache.device_id, risk->device_id) != 0 ||
        strcmp(s_risk_ack_cache.boot_id, risk->boot_id) != 0 ||
        (voice_requested && strcmp(s_risk_ack_cache.command_id, command_id) != 0)) {
        return false;
    }
    *out_decision = s_risk_ack_cache.decision;
    *out_voice_result = s_risk_ack_cache.voice_result;
    return true;
}

static void cache_ack(
    const vision_risk_input_t *risk,
    bool voice_requested,
    const char *command_id,
    const action_decision_t *decision,
    const voice_prompt_result_t *voice_result)
{
    s_risk_ack_cache.valid = true;
    s_risk_ack_cache.voice_requested = voice_requested;
    s_risk_ack_cache.frame_seq = risk->frame_seq;
    s_risk_ack_cache.decision = *decision;
    s_risk_ack_cache.voice_result = *voice_result;
    snprintf(s_risk_ack_cache.device_id, sizeof(s_risk_ack_cache.device_id), "%s", risk->device_id);
    snprintf(s_risk_ack_cache.boot_id, sizeof(s_risk_ack_cache.boot_id), "%s", risk->boot_id);
    snprintf(s_risk_ack_cache.command_id, sizeof(s_risk_ack_cache.command_id), "%s",
             voice_requested ? command_id : "");
}

static esp_err_t send_ack(
    httpd_req_t *request,
    uint32_t frame_seq,
    uint64_t capture_ts_ms,
    bool accepted,
    bool stale,
    uint64_t decision_ms,
    const action_decision_t *decision,
    const voice_prompt_result_t *voice_result,
    const char *command_id,
    const char *error)
{
    uint64_t e2e_latency_ms = 0;
    uint64_t ack_now_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
    if (!risk_receiver_e2e_latency_at_ack(capture_ts_ms, decision_ms, ack_now_ms, &e2e_latency_ms)) {
        e2e_latency_ms = 0;
    }
    char body[768];
    int written = snprintf(
        body,
        sizeof(body),
        "{\"type\":\"action_ack\",\"version\":1,\"frame_seq\":%lu,\"accepted\":%s,"
        "\"stale\":%s,\"action_state\":\"%s\",\"rgb_pattern\":\"%s\",\"e2e_latency_ms\":%llu,\"error\":\"%s\","
        "\"voice_ack\":{\"requested\":%s,\"command_id\":\"%s\",\"track\":%u,"
        "\"accepted\":%s,\"duplicate\":%s,\"status\":\"%s\",\"error\":\"%s\"}}",
        (unsigned long)frame_seq,
        accepted ? "true" : "false",
        stale ? "true" : "false",
        action_state_name(decision->state),
        rgb_pattern_name(decision->rgb_pattern),
        (unsigned long long)e2e_latency_ms,
        error != NULL ? error : "",
        voice_result->requested ? "true" : "false",
        command_id != NULL ? command_id : "",
        (unsigned int)voice_result->track,
        voice_result->accepted ? "true" : "false",
        voice_result->duplicate ? "true" : "false",
        voice_prompt_status_name(voice_result->status),
        voice_prompt_error_name(voice_result->status));
    if (written < 0 || (size_t)written >= sizeof(body)) {
        return ESP_ERR_INVALID_SIZE;
    }
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, body);
}

static void emit_road_hazard_status(
    const char *state,
    const char *event_id,
    const char *reason,
    uint32_t expires_in_ms,
    const char *pattern)
{
    char status[512];
    if (risk_receiver_format_road_hazard_status(
            status, sizeof(status), state, event_id, reason, expires_in_ms, pattern) >= 0) {
        printf("%s\n", status);
        fflush(stdout);
    }
}

static esp_err_t send_road_hazard_ack(
    httpd_req_t *request,
    const char *http_status,
    bool accepted,
    bool duplicate,
    const char *event_id,
    uint32_t expires_in_ms,
    const char *severity,
    const char *voice_state,
    const char *error,
    uint64_t now_ms)
{
    const alert_effective_t effective = alert_arbiter_runtime_get_effective(now_ms);
    char body[768];
    if (risk_receiver_format_road_hazard_ack(
            body, sizeof(body), device_identity_device_id(), device_identity_boot_id(),
            accepted, duplicate, event_id, expires_in_ms, severity,
            rgb_pattern_name(effective.pattern), voice_state, error) < 0) {
        return ESP_ERR_INVALID_SIZE;
    }
    if (http_status != NULL) httpd_resp_set_status(request, http_status);
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, body);
}

static esp_err_t reject_road_hazard(
    httpd_req_t *request,
    const char *http_status,
    const char *event_id,
    const char *severity,
    const char *reason,
    uint64_t now_ms)
{
    const alert_effective_t effective = alert_arbiter_runtime_get_effective(now_ms);
    emit_road_hazard_status("rejected", event_id, reason, 0U, rgb_pattern_name(effective.pattern));
    return send_road_hazard_ack(
        request, http_status, false, false, event_id, 0U, severity,
        "not_requested", reason, now_ms);
}

static const char *json_string(const cJSON *item)
{
    return cJSON_IsString(item) ? item->valuestring : NULL;
}

static double json_number(const cJSON *item)
{
    return cJSON_IsNumber(item) ? item->valuedouble : NAN;
}

static esp_err_t road_hazard_handler(httpd_req_t *request)
{
    uint64_t current_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
    if (!token_matches(request)) {
        return reject_road_hazard(request, "401 Unauthorized", "", "", "token", current_ms);
    }
    if (request->content_len <= 0 || request->content_len > (int)ROAD_HAZARD_BODY_MAX) {
        return reject_road_hazard(request, "413 Payload Too Large", "", "", "payload_size", current_ms);
    }
    char *body = calloc(1U, (size_t)request->content_len + 1U);
    if (body == NULL) return ESP_ERR_NO_MEM;
    int received = 0;
    while (received < request->content_len) {
        const int chunk = httpd_req_recv(request, body + received, request->content_len - received);
        if (chunk <= 0) {
            free(body);
            return reject_road_hazard(request, "400 Bad Request", "", "", "payload_read", current_ms);
        }
        received += chunk;
    }
    cJSON *root = cJSON_Parse(body);
    free(body);
    if (root == NULL) {
        return reject_road_hazard(request, "400 Bad Request", "", "", "json", current_ms);
    }

    const cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    const cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "version");
    const cJSON *device = cJSON_GetObjectItemCaseSensitive(root, "device_id");
    const cJSON *boot = cJSON_GetObjectItemCaseSensitive(root, "boot_id");
    const cJSON *event = cJSON_GetObjectItemCaseSensitive(root, "event_id");
    const cJSON *camera = cJSON_GetObjectItemCaseSensitive(root, "camera_id");
    const cJSON *intersection = cJSON_GetObjectItemCaseSensitive(root, "intersection_id");
    const cJSON *message_code = cJSON_GetObjectItemCaseSensitive(root, "message_code");
    const cJSON *direction = cJSON_GetObjectItemCaseSensitive(root, "direction");
    const cJSON *object_type = cJSON_GetObjectItemCaseSensitive(root, "object_type");
    const cJSON *eta = cJSON_GetObjectItemCaseSensitive(root, "eta_ms");
    const cJSON *severity = cJSON_GetObjectItemCaseSensitive(root, "severity");
    const cJSON *ttl = cJSON_GetObjectItemCaseSensitive(root, "ttl_ms");
    const cJSON *simulated = cJSON_GetObjectItemCaseSensitive(root, "simulated");
    road_hazard_request_t hazard = {
        .type = json_string(type),
        .version = json_number(version),
        .device_id = json_string(device),
        .boot_id = json_string(boot),
        .event_id = json_string(event),
        .camera_id = json_string(camera),
        .intersection_id = json_string(intersection),
        .message_code = json_string(message_code),
        .direction = json_string(direction),
        .object_type = json_string(object_type),
        .eta_ms = json_number(eta),
        .severity = json_string(severity),
        .ttl_ms = json_number(ttl),
        .simulated = cJSON_IsTrue(simulated),
        .simulated_is_bool = cJSON_IsBool(simulated),
    };
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY] = "";
    char severity_name[16] = "";
    (void)risk_receiver_copy_safe_road_hazard_event_id(event_id, sizeof(event_id), hazard.event_id);
    (void)risk_receiver_copy_safe_road_hazard_severity(severity_name, sizeof(severity_name), hazard.severity);
    if (!cJSON_IsObject(root) || cJSON_GetArraySize(root) != 14) {
        cJSON_Delete(root);
        return reject_road_hazard(request, "400 Bad Request", event_id, severity_name, "schema", current_ms);
    }

    current_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
    road_hazard_outcome_t outcome = {0};
    const road_hazard_result_t result =
        alert_arbiter_runtime_submit(&hazard, current_ms, &outcome);
    cJSON_Delete(root);

    if (result != ROAD_HAZARD_ACCEPTED && result != ROAD_HAZARD_DUPLICATE) {
        const char *status = result == ROAD_HAZARD_REJECT_SCHEMA || result == ROAD_HAZARD_REJECT_TTL
                                 ? "400 Bad Request"
                                 : result == ROAD_HAZARD_REJECT_CAPACITY ? "503 Service Unavailable"
                                                                        : "409 Conflict";
        return reject_road_hazard(
            request, status, event_id, severity_name, road_hazard_result_name(result), current_ms);
    }

    const alert_effective_t effective = alert_arbiter_runtime_get_effective(current_ms);
    const char *accepted_severity = road_hazard_severity_name(outcome.severity);
    if (result == ROAD_HAZARD_ACCEPTED) {
        emit_road_hazard_status(
            "active", outcome.event_id, "accepted", outcome.expires_in_ms,
            rgb_pattern_name(effective.pattern));
    }
    return send_road_hazard_ack(
        request, NULL, true, result == ROAD_HAZARD_DUPLICATE, outcome.event_id,
        outcome.expires_in_ms, accepted_severity,
        alert_arbiter_runtime_last_voice_state(), "", current_ms);
}

static esp_err_t risk_handler(httpd_req_t *request)
{
    char *body = NULL;
    cJSON *root = NULL;
    int received = 0;
    int chunk;
    action_decision_t decision = action_controller_get_decision();
    vision_risk_input_t risk = {0};
    risk_accept_result_t result;
    voice_prompt_result_t voice_result = voice_prompt_result_not_requested();
    voice_prompt_request_t voice_request = {0};
    char voice_command_id[VOICE_PROMPT_COMMAND_ID_CAPACITY] = "";
    bool voice_requested = false;
    uint64_t current_ms = 0;
    uint64_t decision_ms = 0;

    if (!token_matches(request)) {
        httpd_resp_set_status(request, "401 Unauthorized");
        return httpd_resp_sendstr(request, "invalid link token");
    }
    if (request->content_len <= 0 || request->content_len > (int)RISK_BODY_MAX) {
        httpd_resp_set_status(request, "413 Payload Too Large");
        return httpd_resp_sendstr(request, "risk payload too large");
    }
    body = calloc(1U, (size_t)request->content_len + 1U);
    if (body == NULL) {
        return ESP_ERR_NO_MEM;
    }
    while (received < request->content_len) {
        chunk = httpd_req_recv(request, body + received, request->content_len - received);
        if (chunk <= 0) {
            free(body);
            httpd_resp_set_status(request, "400 Bad Request");
            return httpd_resp_sendstr(request, "risk payload read failed");
        }
        received += chunk;
    }
    root = cJSON_Parse(body);
    free(body);
    if (root == NULL) {
        httpd_resp_set_status(request, "400 Bad Request");
        return httpd_resp_sendstr(request, "invalid JSON");
    }

    cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "version");
    cJSON *device = cJSON_GetObjectItemCaseSensitive(root, "device_id");
    cJSON *boot = cJSON_GetObjectItemCaseSensitive(root, "boot_id");
    cJSON *seq = cJSON_GetObjectItemCaseSensitive(root, "frame_seq");
    cJSON *capture = cJSON_GetObjectItemCaseSensitive(root, "capture_ts_ms");
    cJSON *score = cJSON_GetObjectItemCaseSensitive(root, "risk_score");
    cJSON *band = cJSON_GetObjectItemCaseSensitive(root, "risk_band");
    cJSON *dominant = cJSON_GetObjectItemCaseSensitive(root, "dominant_class");
    cJSON *reason = cJSON_GetObjectItemCaseSensitive(root, "reason");
    cJSON *latency = cJSON_GetObjectItemCaseSensitive(root, "latency_ms");
    cJSON *valid = cJSON_GetObjectItemCaseSensitive(root, "valid");
    cJSON *voice_prompt = cJSON_GetObjectItemCaseSensitive(root, "voice_prompt");
    bool schema_ok = cJSON_IsString(type) && strcmp(type->valuestring, "vision_risk") == 0 &&
                     cJSON_IsNumber(version) && version->valueint == 1 &&
                     cJSON_IsString(device) && cJSON_IsString(boot) &&
                     cJSON_IsNumber(seq) && seq->valuedouble >= 0 && seq->valuedouble <= UINT32_MAX &&
                     cJSON_IsNumber(capture) && capture->valuedouble >= 0 &&
                     cJSON_IsNumber(score) && cJSON_IsString(band) && cJSON_IsString(dominant) &&
                     cJSON_IsString(reason) && cJSON_IsNumber(latency) && latency->valuedouble >= 0 &&
                     isfinite(latency->valuedouble) && cJSON_IsTrue(valid);
    if (schema_ok && voice_prompt != NULL) {
        cJSON *command_id = cJSON_GetObjectItemCaseSensitive(voice_prompt, "command_id");
        cJSON *track = cJSON_GetObjectItemCaseSensitive(voice_prompt, "track");
        voice_requested = true;
        voice_request.command_id = cJSON_IsString(command_id) ? command_id->valuestring : NULL;
        voice_request.track = cJSON_IsNumber(track) && track->valueint >= 0 && track->valueint <= UINT8_MAX
                                  ? (uint8_t)track->valueint
                                  : 0U;
        voice_request.frame_seq = (uint32_t)seq->valuedouble;
        schema_ok = cJSON_IsObject(voice_prompt) && voice_prompt_request_is_valid(band->valuestring, &voice_request);
        if (schema_ok) {
            snprintf(voice_command_id, sizeof(voice_command_id), "%s", voice_request.command_id);
            voice_request.command_id = voice_command_id;
        }
    }
    if (!schema_ok) {
        cJSON_Delete(root);
        httpd_resp_set_status(request, "400 Bad Request");
        return httpd_resp_sendstr(request, "invalid vision_risk schema");
    }
    risk.device_id = device->valuestring;
    risk.boot_id = boot->valuestring;
    risk.frame_seq = (uint32_t)seq->valuedouble;
    risk.capture_ts_ms = (uint64_t)capture->valuedouble;
    risk.risk_score = score->valueint;
    risk.risk_band = band->valuestring;
    risk.dominant_class = dominant->valuestring;
    risk.reason = reason->valuestring;
    risk.valid = true;

    if (device_and_boot_match(device, boot) &&
        cached_ack_matches(&risk, voice_requested, voice_request.command_id, &decision, &voice_result)) {
        if (voice_requested) {
            voice_result = voice_prompt_result_duplicate_ack(&voice_result);
        }
        decision_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
        cJSON_Delete(root);
        return send_ack(request, risk.frame_seq, risk.capture_ts_ms, true, false, decision_ms, &decision, &voice_result,
                        voice_requested ? voice_command_id : "", "");
    }

    current_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
    result = action_controller_apply_risk(&risk, current_ms, &decision);
    decision_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);

    if (result != RISK_ACCEPTED) {
        if (voice_requested) {
            voice_result = voice_prompt_result_rejected();
            voice_result.track = voice_request.track;
        }
        cJSON_Delete(root);
        httpd_resp_set_status(request, "409 Conflict");
        return send_ack(
            request,
            risk.frame_seq,
            risk.capture_ts_ms,
            false,
            result == RISK_REJECT_STALE,
            decision_ms,
            &decision,
            &voice_result,
            voice_requested ? voice_command_id : "",
            risk_accept_result_name(result));
    }
    if (voice_requested) {
        voice_result = voice_prompt_submit(risk.risk_band, &voice_request);
    }
    cache_ack(&risk, voice_requested, voice_requested ? voice_command_id : "", &decision, &voice_result);
    cJSON_Delete(root);
    return send_ack(request, risk.frame_seq, risk.capture_ts_ms, true, false, decision_ms, &decision, &voice_result,
                    voice_requested ? voice_command_id : "", "");
}

static esp_err_t send_pneumatic_ack(
    httpd_req_t *request,
    const char *command_id,
    const pneumatic_command_result_t *result)
{
    const pneumatic_status_t *status = &result->status;
    char body[640];
    snprintf(
        body,
        sizeof(body),
        "{\"type\":\"pneumatic_ack\",\"version\":1,\"boot_id\":\"%s\",\"command_id\":\"%s\","
        "\"accepted\":%s,\"duplicate\":%s,\"error\":\"%s\","
        "\"state\":\"%s\",\"fault\":\"%s\",\"pump_on\":%s,\"valve_on\":%s}",
        device_identity_boot_id(),
        command_id,
        result->accepted ? "true" : "false",
        result->duplicate ? "true" : "false",
        result->error,
        pneumatic_state_name(status->output.state),
        pneumatic_fault_name(status->output.fault),
        status->output.pump_on ? "true" : "false",
        status->output.valve_on ? "true" : "false");
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, body);
}

static bool parse_pneumatic_command_type(const char *value, pneumatic_command_type_t *out)
{
    if (strcmp(value, "inflate_pulse") == 0) {
        *out = PNEUMATIC_COMMAND_INFLATE_PULSE;
    } else if (strcmp(value, "vent") == 0) {
        *out = PNEUMATIC_COMMAND_VENT;
    } else if (strcmp(value, "emergency_stop") == 0) {
        *out = PNEUMATIC_COMMAND_EMERGENCY_STOP;
    } else if (strcmp(value, "reset_fault") == 0) {
        *out = PNEUMATIC_COMMAND_RESET_FAULT;
    } else if (strcmp(value, "save_calibration") == 0) {
        *out = PNEUMATIC_COMMAND_SAVE_CALIBRATION;
    } else if (strcmp(value, "self_test") == 0) {
        *out = PNEUMATIC_COMMAND_SELF_TEST;
    } else {
        return false;
    }
    return true;
}

static esp_err_t pneumatic_command_handler(httpd_req_t *request)
{
    if (!token_matches(request)) {
        httpd_resp_set_status(request, "401 Unauthorized");
        return httpd_resp_sendstr(request, "invalid link token");
    }
    if (!pneumatic_controller_is_started()) {
        httpd_resp_set_status(request, "503 Service Unavailable");
        return httpd_resp_sendstr(request, "pneumatic controller disabled");
    }
    if (request->content_len <= 0 || request->content_len > (int)PNEUMATIC_BODY_MAX) {
        httpd_resp_set_status(request, "413 Payload Too Large");
        return httpd_resp_sendstr(request, "pneumatic payload too large");
    }

    char *body = calloc(1U, (size_t)request->content_len + 1U);
    if (body == NULL) {
        return ESP_ERR_NO_MEM;
    }
    int received = 0;
    while (received < request->content_len) {
        const int chunk = httpd_req_recv(request, body + received, request->content_len - received);
        if (chunk <= 0) {
            free(body);
            httpd_resp_set_status(request, "400 Bad Request");
            return httpd_resp_sendstr(request, "pneumatic payload read failed");
        }
        received += chunk;
    }
    cJSON *root = cJSON_Parse(body);
    free(body);
    if (root == NULL) {
        httpd_resp_set_status(request, "400 Bad Request");
        return httpd_resp_sendstr(request, "invalid JSON");
    }

    cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "version");
    cJSON *device = cJSON_GetObjectItemCaseSensitive(root, "device_id");
    cJSON *boot = cJSON_GetObjectItemCaseSensitive(root, "boot_id");
    cJSON *command_id = cJSON_GetObjectItemCaseSensitive(root, "command_id");
    cJSON *command_name = cJSON_GetObjectItemCaseSensitive(root, "command");
    const bool basic_schema_ok = cJSON_IsString(type) && strcmp(type->valuestring, "pneumatic_command") == 0 &&
                                 cJSON_IsNumber(version) && version->valueint == 1 &&
                                 device_and_boot_match(device, boot) && cJSON_IsString(command_id) &&
                                 command_id->valuestring[0] != '\0' &&
                                 strlen(command_id->valuestring) < PNEUMATIC_COMMAND_ID_CAPACITY &&
                                 cJSON_IsString(command_name);
    if (!basic_schema_ok) {
        cJSON_Delete(root);
        httpd_resp_set_status(request, "400 Bad Request");
        return httpd_resp_sendstr(request, "invalid pneumatic command schema or device identity");
    }

    pneumatic_command_t command = {0};
    if (!parse_pneumatic_command_type(command_name->valuestring, &command.type)) {
        cJSON_Delete(root);
        httpd_resp_set_status(request, "400 Bad Request");
        return httpd_resp_sendstr(request, "unsupported pneumatic command");
    }
    snprintf(command.command_id, sizeof(command.command_id), "%s", command_id->valuestring);
    if (command.type == PNEUMATIC_COMMAND_SAVE_CALIBRATION) {
        cJSON *target = cJSON_GetObjectItemCaseSensitive(root, "target_kpa");
        cJSON *maximum = cJSON_GetObjectItemCaseSensitive(root, "max_kpa");
        cJSON *inflate = cJSON_GetObjectItemCaseSensitive(root, "max_inflate_ms");
        if (!cJSON_IsNumber(target) || !isfinite(target->valuedouble) ||
            !cJSON_IsNumber(maximum) || !isfinite(maximum->valuedouble) ||
            !cJSON_IsNumber(inflate) || inflate->valuedouble < 0 || inflate->valuedouble > UINT32_MAX) {
            cJSON_Delete(root);
            httpd_resp_set_status(request, "400 Bad Request");
            return httpd_resp_sendstr(request, "invalid calibration values");
        }
        command.target_kpa = (float)target->valuedouble;
        command.max_kpa = (float)maximum->valuedouble;
        command.max_inflate_ms = (uint32_t)inflate->valuedouble;
    }
    cJSON_Delete(root);

    pneumatic_command_result_t result = {0};
    const esp_err_t ret = pneumatic_controller_execute(&command, &result);
    if (ret != ESP_OK && !result.accepted) {
        httpd_resp_set_status(request, "409 Conflict");
    }
    return send_pneumatic_ack(request, command.command_id, &result);
}

static esp_err_t pneumatic_config_handler(httpd_req_t *request)
{
    if (!token_matches(request)) {
        httpd_resp_set_status(request, "401 Unauthorized");
        return httpd_resp_sendstr(request, "invalid link token");
    }
    pneumatic_status_t status = {0};
    if (!pneumatic_controller_get_status(&status)) {
        httpd_resp_set_status(request, "503 Service Unavailable");
        return httpd_resp_sendstr(request, "pneumatic controller disabled");
    }
    char body[1024];
    snprintf(
        body,
        sizeof(body),
        "{\"type\":\"pneumatic_config\",\"version\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"automatic_enabled\":%s,\"calibration_valid\":%s,\"target_kpa\":%.2f,"
        "\"max_kpa\":%.2f,\"max_inflate_ms\":%lu,\"pressure_stale_ms\":%llu,"
        "\"calibration_pulse_ms\":%llu,\"calibration_ceiling_kpa\":%.1f,"
        "\"hold_max_ms\":%llu,\"clear_confirm_ms\":%llu,\"vent_timeout_ms\":%llu,"
        "\"cooldown_ms\":%llu,\"pump_gpio\":%d,\"valve_gpio\":%d,"
        "\"mpu\":{\"sda_gpio\":%d,\"scl_gpio\":%d,\"int_gpio\":%d,"
        "\"sample_hz\":100,\"impact_g\":%.1f,\"impact_samples\":%u,"
        "\"rapid_tilt_deg\":%.1f,\"rapid_tilt_dps\":%.1f,\"rapid_tilt_ms\":%llu,\"clear_ms\":%llu}}",
        device_identity_device_id(),
        device_identity_boot_id(),
        status.config.automatic_enabled ? "true" : "false",
        status.config.calibration_valid ? "true" : "false",
        status.config.target_kpa,
        status.config.max_kpa,
        (unsigned long)status.config.max_inflate_ms,
        (unsigned long long)PNEUMATIC_PRESSURE_STALE_MS,
        (unsigned long long)PNEUMATIC_CALIBRATION_PULSE_MS,
        PNEUMATIC_CALIBRATION_CEILING_KPA,
        (unsigned long long)PNEUMATIC_HOLD_MAX_MS,
        (unsigned long long)PNEUMATIC_CLEAR_CONFIRM_MS,
        (unsigned long long)PNEUMATIC_VENT_TIMEOUT_MS,
        (unsigned long long)PNEUMATIC_COOLDOWN_MS,
        PNEUMATIC_PUMP_GPIO,
        PNEUMATIC_VALVE_GPIO,
        MPU6050_I2C_SDA_GPIO,
        MPU6050_I2C_SCL_GPIO,
        MPU6050_INT_GPIO,
        MOTION_DETECTOR_IMPACT_THRESHOLD_G,
        MOTION_DETECTOR_IMPACT_SAMPLES,
        MOTION_DETECTOR_RAPID_TILT_DEG,
        MOTION_DETECTOR_RAPID_TILT_DPS,
        (unsigned long long)MOTION_DETECTOR_RAPID_TILT_MS,
        (unsigned long long)MOTION_DETECTOR_CLEAR_MS);
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, body);
}

esp_err_t risk_receiver_start(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    httpd_uri_t uri = {
        .uri = "/risk",
        .method = HTTP_POST,
        .handler = risk_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t pneumatic_command_uri = {
        .uri = "/pneumatic/command",
        .method = HTTP_POST,
        .handler = pneumatic_command_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t road_hazard_uri = {
        .uri = "/road-hazard",
        .method = HTTP_POST,
        .handler = road_hazard_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t pneumatic_config_uri = {
        .uri = "/pneumatic/config",
        .method = HTTP_GET,
        .handler = pneumatic_config_handler,
        .user_ctx = NULL,
    };
    config.server_port = CONFIG_AIX_RISK_RECEIVER_PORT;
    esp_err_t ret = httpd_start(&s_server, &config);
    if (ret != ESP_OK) {
        return ret;
    }
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &road_hazard_uri), TAG, "register road hazard failed");
    ret = httpd_register_uri_handler(s_server, &uri);
    if (ret != ESP_OK) {
        return ret;
    }
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &pneumatic_command_uri), TAG, "register pneumatic command failed");
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &pneumatic_config_uri), TAG, "register pneumatic config failed");
    ESP_LOGI(TAG, "vision, road hazard and pneumatic receiver listening on port %d", CONFIG_AIX_RISK_RECEIVER_PORT);
    return ESP_OK;
}

#endif
