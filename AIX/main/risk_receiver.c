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
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"

#ifndef CONFIG_AIX_LINK_TOKEN
#define CONFIG_AIX_LINK_TOKEN ""
#endif
#ifndef CONFIG_AIX_RISK_RECEIVER_PORT
#define CONFIG_AIX_RISK_RECEIVER_PORT 8080
#endif

#define RISK_BODY_MAX 2048U

static const char *TAG = "AIX_RISK_RX";
static httpd_handle_t s_server;

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

static esp_err_t send_ack(
    httpd_req_t *request,
    uint32_t frame_seq,
    bool accepted,
    bool stale,
    const action_decision_t *decision,
    const char *error)
{
    char body[320];
    snprintf(
        body,
        sizeof(body),
        "{\"type\":\"action_ack\",\"version\":1,\"frame_seq\":%lu,\"accepted\":%s,"
        "\"stale\":%s,\"action_state\":\"%s\",\"rgb_pattern\":\"%s\",\"error\":\"%s\"}",
        (unsigned long)frame_seq,
        accepted ? "true" : "false",
        stale ? "true" : "false",
        action_state_name(decision->state),
        rgb_pattern_name(decision->rgb_pattern),
        error != NULL ? error : "");
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
    bool schema_ok = cJSON_IsString(type) && strcmp(type->valuestring, "vision_risk") == 0 &&
                     cJSON_IsNumber(version) && version->valueint == 1 &&
                     cJSON_IsString(device) && cJSON_IsString(boot) &&
                     cJSON_IsNumber(seq) && seq->valuedouble >= 0 && seq->valuedouble <= UINT32_MAX &&
                     cJSON_IsNumber(capture) && capture->valuedouble >= 0 &&
                     cJSON_IsNumber(score) && cJSON_IsString(band) && cJSON_IsString(dominant) &&
                     cJSON_IsString(reason) && cJSON_IsNumber(latency) && latency->valuedouble >= 0 &&
                     isfinite(latency->valuedouble) && cJSON_IsTrue(valid);
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
    result = action_controller_apply_risk(&risk, current_ms, &decision);
    cJSON_Delete(root);

    if (result != RISK_ACCEPTED) {
        httpd_resp_set_status(request, "409 Conflict");
        return send_ack(
            request,
            risk.frame_seq,
            false,
            result == RISK_REJECT_STALE,
            &decision,
            risk_accept_result_name(result));
    }
    return send_ack(request, risk.frame_seq, true, false, &decision, "");
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
    config.server_port = CONFIG_AIX_RISK_RECEIVER_PORT;
    esp_err_t ret = httpd_start(&s_server, &config);
    if (ret != ESP_OK) {
        return ret;
    }
    ret = httpd_register_uri_handler(s_server, &uri);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "vision risk receiver listening on port %d", CONFIG_AIX_RISK_RECEIVER_PORT);
    }
    return ret;
}

#endif
