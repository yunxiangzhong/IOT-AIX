#include "vision_input.h"

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

static float clamp01(float value)
{
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

static const char *find_field(const char *line, const char *key)
{
    const char *cursor = line;
    while ((cursor = strstr(cursor, key)) != NULL) {
        const char *colon = strchr(cursor + strlen(key), ':');
        if (colon != NULL) {
            return colon + 1;
        }
        cursor += strlen(key);
    }
    return NULL;
}

static bool parse_float_field(const char *line, const char *key, float *out)
{
    const char *value = find_field(line, key);
    if (value == NULL) {
        return false;
    }
    char *end = NULL;
    const float parsed = strtof(value, &end);
    if (end == value) {
        return false;
    }
    *out = clamp01(parsed);
    return true;
}

static bool parse_uint_field(const char *line, const char *key, uint32_t *out)
{
    const char *value = find_field(line, key);
    if (value == NULL) {
        return false;
    }
    char *end = NULL;
    const unsigned long parsed = strtoul(value, &end, 10);
    if (end == value) {
        return false;
    }
    *out = (uint32_t)parsed;
    return true;
}

static bool parse_bool_field(const char *line, const char *key, bool *out)
{
    const char *value = find_field(line, key);
    if (value == NULL) {
        return false;
    }
    while (*value == ' ') {
        value++;
    }
    if (strncmp(value, "true", 4) == 0 || *value == '1') {
        *out = true;
        return true;
    }
    if (strncmp(value, "false", 5) == 0 || *value == '0') {
        *out = false;
        return true;
    }
    return false;
}

bool vision_input_parse_line(const char *line, vision_input_snapshot_t *out)
{
    if (line == NULL || out == NULL) {
        return false;
    }
    if (strstr(line, "\"type\":\"vision\"") == NULL &&
        strstr(line, "\"type\": \"vision\"") == NULL) {
        return false;
    }

    vision_input_snapshot_t parsed = {0};
    if (!parse_uint_field(line, "\"seq\"", &parsed.seq) ||
        !parse_uint_field(line, "\"ts_ms\"", &parsed.ts_ms) ||
        !parse_float_field(line, "\"looming\"", &parsed.looming) ||
        !parse_float_field(line, "\"area_rate\"", &parsed.area_rate) ||
        !parse_float_field(line, "\"center_motion\"", &parsed.center_motion) ||
        !parse_float_field(line, "\"confidence\"", &parsed.confidence) ||
        !parse_bool_field(line, "\"valid\"", &parsed.valid)) {
        return false;
    }
    parsed.stale = false;
    *out = parsed;
    return true;
}

#ifdef ESP_PLATFORM
#include <stdio.h>

#include "config_input.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#define VISION_INPUT_TASK_STACK 4096
#define VISION_INPUT_TASK_PRIORITY 6
#define VISION_INPUT_LINE_MAX 256

static const char *TAG = "AIX_VISION_IN";
static portMUX_TYPE s_vision_lock = portMUX_INITIALIZER_UNLOCKED;
static vision_input_snapshot_t s_latest_vision;
static bool s_has_vision;
static bool s_task_started;

bool vision_input_get_snapshot(vision_input_snapshot_t *out)
{
    if (out == NULL) {
        return false;
    }
    taskENTER_CRITICAL(&s_vision_lock);
    const bool has_vision = s_has_vision;
    if (has_vision) {
        *out = s_latest_vision;
    }
    taskEXIT_CRITICAL(&s_vision_lock);
    return has_vision;
}

static void vision_input_task(void *arg)
{
    (void)arg;
    char line[VISION_INPUT_LINE_MAX];

    while (1) {
        if (fgets(line, sizeof(line), stdin) == NULL) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        config_input_state_t config = config_input_get_state();
        if (config_input_parse_line(line, &config)) {
            config_input_set_state(&config);
            ESP_LOGI(TAG, "pressure monitoring %s", config.pressure_enabled ? "enabled" : "disabled");
            continue;
        }

        vision_input_snapshot_t parsed = {0};
        if (!vision_input_parse_line(line, &parsed)) {
            continue;
        }
        parsed.received_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);

        taskENTER_CRITICAL(&s_vision_lock);
        s_latest_vision = parsed;
        s_has_vision = true;
        taskEXIT_CRITICAL(&s_vision_lock);

        ESP_LOGD(TAG, "vision seq=%lu looming=%.2f confidence=%.2f",
                 (unsigned long)parsed.seq,
                 parsed.looming,
                 parsed.confidence);
    }
}

esp_err_t vision_input_start_task(void)
{
    if (s_task_started) {
        return ESP_OK;
    }

    BaseType_t ok = xTaskCreate(vision_input_task,
                                "vision_input",
                                VISION_INPUT_TASK_STACK,
                                NULL,
                                VISION_INPUT_TASK_PRIORITY,
                                NULL);
    if (ok != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    s_task_started = true;
    return ESP_OK;
}
#endif

