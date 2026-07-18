#include "risk_receiver.h"

#include <stddef.h>
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

#ifdef ESP_PLATFORM

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
    bool accepted,
    bool stale,
    const action_decision_t *decision,
    const voice_prompt_result_t *voice_result,
    const char *command_id,
    const char *error)
{
    char body[640];
    snprintf(
        body,
        sizeof(body),
        "{\"type\":\"action_ack\",\"version\":1,\"frame_seq\":%lu,\"accepted\":%s,"
        "\"stale\":%s,\"action_state\":\"%s\",\"rgb_pattern\":\"%s\",\"error\":\"%s\","
        "\"voice_ack\":{\"requested\":%s,\"command_id\":\"%s\",\"track\":%u,"
        "\"accepted\":%s,\"duplicate\":%s,\"status\":\"%s\",\"error\":\"%s\"}}",
        (unsigned long)frame_seq,
        accepted ? "true" : "false",
        stale ? "true" : "false",
        action_state_name(decision->state),
        rgb_pattern_name(decision->rgb_pattern),
        error != NULL ? error : "",
        voice_result->requested ? "true" : "false",
        command_id != NULL ? command_id : "",
        (unsigned int)voice_result->track,
        voice_result->accepted ? "true" : "false",
        voice_result->duplicate ? "true" : "false",
        voice_prompt_status_name(voice_result->status),
        voice_prompt_error_name(voice_result->status));
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, body);
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
    uint64_t current_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);

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
        cJSON_Delete(root);
        return send_ack(request, risk.frame_seq, true, false, &decision, &voice_result,
                        voice_requested ? voice_command_id : "", "");
    }

    result = action_controller_apply_risk(&risk, current_ms, &decision);

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
            false,
            result == RISK_REJECT_STALE,
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
    return send_ack(request, risk.frame_seq, true, false, &decision, &voice_result,
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
    ret = httpd_register_uri_handler(s_server, &uri);
    if (ret != ESP_OK) {
        return ret;
    }
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &pneumatic_command_uri), TAG, "register pneumatic command failed");
    ESP_RETURN_ON_ERROR(httpd_register_uri_handler(s_server, &pneumatic_config_uri), TAG, "register pneumatic config failed");
    ESP_LOGI(TAG, "vision and pneumatic receiver listening on port %d", CONFIG_AIX_RISK_RECEIVER_PORT);
    return ESP_OK;
}

#endif
