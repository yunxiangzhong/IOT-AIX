#include "pneumatic_controller.h"

#ifdef ESP_PLATFORM

#include <stdio.h>
#include <string.h>

#include "action_controller.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mpu6050_sensor.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "pressure_sensor.h"

#ifndef CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC
#define CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC 0
#endif

#define PNEUMATIC_TASK_PERIOD_MS 20
#define PNEUMATIC_TASK_STACK 4096
#define PNEUMATIC_TASK_PRIORITY 7
#define PNEUMATIC_STATUS_PERIOD_MS 1000ULL
#define PNEUMATIC_NVS_NAMESPACE "pneumatic"
#define PNEUMATIC_NVS_KEY "cal_v1"
#define PNEUMATIC_CALIBRATION_VERSION 3U
#define PNEUMATIC_SELF_TEST_MIN_RISE_KPA 0.3f
#define PNEUMATIC_SELF_TEST_TIMEOUT_MS 6000ULL
#define PNEUMATIC_SELF_TEST_PUMP_MS 800U

static const char *TAG = "AIX_PNEUMATIC";

typedef struct {
    uint32_t version;
    float target_kpa;
    float max_kpa;
    uint32_t max_inflate_ms;
} saved_calibration_t;

typedef struct {
    bool inflate_pulse;
    bool vent;
    bool emergency_stop;
    bool reset_fault;
} pending_commands_t;

typedef enum {
    PNEUMATIC_SELF_TEST_IDLE = 0,
    PNEUMATIC_SELF_TEST_REQUESTED,
    PNEUMATIC_SELF_TEST_PUMPING,
    PNEUMATIC_SELF_TEST_VENTING,
} pneumatic_self_test_phase_t;

typedef struct {
    pneumatic_self_test_phase_t phase;
    uint64_t started_ms;
    float baseline_kpa;
    float peak_kpa;
} pneumatic_self_test_t;

static SemaphoreHandle_t s_lock;
static bool s_started;
static pneumatic_policy_t s_policy;
static pneumatic_status_t s_status;
static pending_commands_t s_pending;
static char s_last_command_id[PNEUMATIC_COMMAND_ID_CAPACITY];
static bool s_pump_verified;
static bool s_valve_verified;
static bool s_self_test_failed;
static pneumatic_self_test_t s_self_test;

static uint64_t now_ms(void)
{
    return (uint64_t)(esp_timer_get_time() / 1000ULL);
}

static void set_outputs(bool pump_on, bool valve_on)
{
    (void)gpio_set_level(PNEUMATIC_PUMP_GPIO, pump_on ? 1 : 0);
    (void)gpio_set_level(PNEUMATIC_VALVE_GPIO, valve_on ? 1 : 0);
}

static esp_err_t configure_outputs(void)
{
    gpio_config_t config = {
        .pin_bit_mask = (1ULL << PNEUMATIC_PUMP_GPIO) | (1ULL << PNEUMATIC_VALVE_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&config), TAG, "configure pneumatic GPIO failed");
    set_outputs(false, false);
    return ESP_OK;
}

static pneumatic_policy_config_t build_config(void)
{
    pneumatic_policy_config_t config = pneumatic_policy_default_config();
    config.calibration_enabled = true;
    config.automatic_enabled = CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC != 0;
    config.calibration_valid = true;

    nvs_handle_t handle;
    if (nvs_open(PNEUMATIC_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) {
        return config;
    }
    saved_calibration_t saved = {0};
    size_t size = sizeof(saved);
    const esp_err_t ret = nvs_get_blob(handle, PNEUMATIC_NVS_KEY, &saved, &size);
    nvs_close(handle);
    if (ret != ESP_OK || size != sizeof(saved) || saved.version != PNEUMATIC_CALIBRATION_VERSION) {
        return config;
    }
    pneumatic_policy_config_t candidate = config;
    candidate.target_kpa = saved.target_kpa;
    candidate.max_kpa = saved.max_kpa;
    candidate.max_inflate_ms = saved.max_inflate_ms;
    if (pneumatic_policy_config_is_valid(&candidate)) {
        candidate.calibration_valid = true;
        return candidate;
    }
    return config;
}

static esp_err_t persist_calibration(const pneumatic_policy_config_t *config)
{
    saved_calibration_t saved = {
        .version = PNEUMATIC_CALIBRATION_VERSION,
        .target_kpa = config->target_kpa,
        .max_kpa = config->max_kpa,
        .max_inflate_ms = config->max_inflate_ms,
    };
    nvs_handle_t handle;
    ESP_RETURN_ON_ERROR(nvs_open(PNEUMATIC_NVS_NAMESPACE, NVS_READWRITE, &handle), TAG, "open pneumatic NVS failed");
    esp_err_t ret = nvs_set_blob(handle, PNEUMATIC_NVS_KEY, &saved, sizeof(saved));
    if (ret == ESP_OK) {
        ret = nvs_commit(handle);
    }
    nvs_close(handle);
    return ret;
}

static bool status_changed(const pneumatic_status_t *before, const pneumatic_status_t *after)
{
    return before->output.state != after->output.state ||
           before->output.fault != after->output.fault ||
           before->output.trigger_source != after->output.trigger_source ||
           before->output.pump_on != after->output.pump_on ||
           before->output.valve_on != after->output.valve_on;
}

static void emit_status(const pneumatic_status_t *status)
{
    printf("{\"type\":\"pneumatic_status\",\"version\":1,\"ts_ms\":%llu,"
           "\"state\":\"%s\",\"fault\":\"%s\",\"trigger\":\"%s\","
           "\"operation\":%d,\"pump_on\":%s,\"valve_on\":%s,"
           "\"pressure_kpa\":%.2f,\"pressure_raw_valid\":%s,\"pressure_valid\":%s,\"pressure_age_ms\":%lu,"
           "\"pump_verified\":%s,\"valve_verified\":%s,\"self_test_failed\":%s,\"automatic_enabled\":%s,"
           "\"vision_state\":\"%s\",\"vision_fresh\":%s,\"mpu_available\":%s,"
           "\"mpu_calibrated\":%s,\"impact\":%s,\"rapid_tilt\":%s}\n",
           (unsigned long long)status->timestamp_ms,
           pneumatic_state_name(status->output.state),
           pneumatic_fault_name(status->output.fault),
           pneumatic_trigger_name(status->output.trigger_source),
           (int)status->output.operation,
           status->output.pump_on ? "true" : "false",
           status->output.valve_on ? "true" : "false",
           status->pressure_kpa,
           status->pressure_raw_valid ? "true" : "false",
           status->pressure_valid ? "true" : "false",
           (unsigned long)status->pressure_age_ms,
           status->pump_verified ? "true" : "false",
           status->valve_verified ? "true" : "false",
           status->self_test_failed ? "true" : "false",
           status->automatic_enabled ? "true" : "false",
           action_state_name(status->vision_state),
           status->vision_fresh ? "true" : "false",
           status->mpu_available ? "true" : "false",
           status->mpu_calibrated ? "true" : "false",
           status->mpu_impact ? "true" : "false",
           status->mpu_rapid_tilt ? "true" : "false");
    fflush(stdout);
}

static void update_self_test(
    const pneumatic_policy_output_t *output,
    bool pressure_fresh,
    float pressure_kpa,
    uint64_t timestamp_ms)
{
    if (s_self_test.phase == PNEUMATIC_SELF_TEST_IDLE) {
        return;
    }
    if (!pressure_fresh || timestamp_ms - s_self_test.started_ms > PNEUMATIC_SELF_TEST_TIMEOUT_MS) {
        s_pump_verified = false;
        s_valve_verified = false;
        s_self_test_failed = true;
        s_pending.vent = true;
        s_self_test.phase = PNEUMATIC_SELF_TEST_IDLE;
        ESP_LOGE(TAG, "pneumatic self-test failed: pressure feedback missing or timed out");
        return;
    }
    if (s_self_test.phase == PNEUMATIC_SELF_TEST_REQUESTED &&
        output->state == PNEUMATIC_STATE_INFLATING) {
        s_self_test.phase = PNEUMATIC_SELF_TEST_PUMPING;
        s_self_test.peak_kpa = pressure_kpa;
        return;
    }
    if (s_self_test.phase == PNEUMATIC_SELF_TEST_PUMPING) {
        if (pressure_kpa > s_self_test.peak_kpa) {
            s_self_test.peak_kpa = pressure_kpa;
        }
        if (output->state == PNEUMATIC_STATE_HOLDING) {
            s_pump_verified = (s_self_test.peak_kpa - s_self_test.baseline_kpa) >= PNEUMATIC_SELF_TEST_MIN_RISE_KPA;
            s_valve_verified = false;
            s_pending.vent = true;
            s_self_test_failed = !s_pump_verified;
            s_self_test.phase = s_pump_verified ? PNEUMATIC_SELF_TEST_VENTING : PNEUMATIC_SELF_TEST_IDLE;
            ESP_LOGI(TAG, "pneumatic self-test pump %s (rise %.2f kPa)",
                     s_pump_verified ? "verified" : "failed",
                     s_self_test.peak_kpa - s_self_test.baseline_kpa);
        }
        return;
    }
    if (s_self_test.phase == PNEUMATIC_SELF_TEST_VENTING &&
        (output->state == PNEUMATIC_STATE_VENTING || output->state == PNEUMATIC_STATE_COOLDOWN ||
         output->state == PNEUMATIC_STATE_VENTED) &&
        pressure_kpa <= s_self_test.peak_kpa - PNEUMATIC_SELF_TEST_MIN_RISE_KPA) {
        s_valve_verified = true;
        s_self_test.phase = PNEUMATIC_SELF_TEST_IDLE;
        ESP_LOGI(TAG, "pneumatic self-test valve verified");
    }
}

static void controller_task(void *arg)
{
    (void)arg;
    uint64_t last_emit_ms = 0;
    for (;;) {
        const uint64_t timestamp_ms = now_ms();
        const action_decision_t decision = action_controller_get_decision();
        pressure_sensor_sample_t pressure = {0};
        const bool has_pressure = pressure_sensor_get_latest(&pressure);
        mpu6050_status_t mpu = {0};
        const bool has_mpu = mpu6050_sensor_get_latest(&mpu);
        const bool pressure_fresh = has_pressure && pressure.valid &&
                                    timestamp_ms >= pressure.timestamp_ms &&
                                    timestamp_ms - pressure.timestamp_ms <= PNEUMATIC_PRESSURE_STALE_MS;

        xSemaphoreTake(s_lock, portMAX_DELAY);
        const bool pump_verified = s_pump_verified;
        const bool valve_verified = s_valve_verified;
        const bool self_test_failed = s_self_test_failed;
        const pneumatic_self_test_phase_t self_test_phase = s_self_test.phase;
        const pending_commands_t pending = s_pending;
        s_pending = (pending_commands_t){0};
        const bool common_automatic_ready = pressure_fresh && pump_verified &&
                                            valve_verified && !self_test_failed;
        const pneumatic_policy_input_t input = {
            .vision_state = decision.state,
            .vision_fresh = decision.valid && !decision.stale,
            .motion_impact = has_mpu && mpu.motion.impact,
            .motion_rapid_tilt = has_mpu && mpu.motion.rapid_tilt,
            .automatic_permitted = common_automatic_ready,
            .vision_trigger_permitted = true,
            .motion_trigger_permitted = has_mpu && mpu.motion.calibrated,
            .pressure_valid = has_pressure && pressure.valid,
            .pressure_kpa = pressure.filtered_kpa,
            .pressure_timestamp_ms = pressure.timestamp_ms,
            .manual_inflate_pulse = pending.inflate_pulse,
            .manual_inflate_duration_ms = self_test_phase != PNEUMATIC_SELF_TEST_IDLE
                                               ? PNEUMATIC_SELF_TEST_PUMP_MS
                                               : PNEUMATIC_CALIBRATION_PULSE_MS,
            .vent_request = pending.vent,
            .emergency_stop = pending.emergency_stop,
            .reset_fault = pending.reset_fault,
        };

        const pneumatic_status_t previous = s_status;
        const pneumatic_policy_output_t output = pneumatic_policy_step(&s_policy, &input, timestamp_ms);
        update_self_test(&output, pressure_fresh, pressure.filtered_kpa, timestamp_ms);
        s_status = (pneumatic_status_t){
            .config = s_policy.config,
            .output = output,
            .pressure_kpa = pressure.filtered_kpa,
            .pressure_raw_valid = has_pressure && pressure.raw_valid,
            .pressure_valid = has_pressure && pressure.valid,
            .pressure_age_ms = !has_pressure || timestamp_ms < pressure.timestamp_ms
                                ? UINT32_MAX
                                : (uint32_t)(timestamp_ms - pressure.timestamp_ms),
            .vision_state = decision.state,
            .vision_fresh = decision.valid && !decision.stale,
            .mpu_available = has_mpu,
            .mpu_calibrated = has_mpu && mpu.motion.calibrated,
            .mpu_impact = has_mpu && mpu.motion.impact,
            .mpu_rapid_tilt = has_mpu && mpu.motion.rapid_tilt,
            .pump_verified = s_pump_verified,
            .valve_verified = s_valve_verified,
            .self_test_failed = s_self_test_failed,
            .automatic_enabled = s_policy.config.automatic_enabled,
            .timestamp_ms = timestamp_ms,
        };
        const pneumatic_status_t current = s_status;
        xSemaphoreGive(s_lock);

        set_outputs(output.pump_on, output.valve_on);
        if (status_changed(&previous, &current) || timestamp_ms - last_emit_ms >= PNEUMATIC_STATUS_PERIOD_MS) {
            emit_status(&current);
            last_emit_ms = timestamp_ms;
        }
        vTaskDelay(pdMS_TO_TICKS(PNEUMATIC_TASK_PERIOD_MS));
    }
}

esp_err_t pneumatic_controller_start(void)
{
    if (s_started) {
        return ESP_OK;
    }
    ESP_RETURN_ON_ERROR(nvs_flash_init(), TAG, "initialize NVS failed");
    ESP_RETURN_ON_ERROR(configure_outputs(), TAG, "set pneumatic outputs safe failed");
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    const pneumatic_policy_config_t config = build_config();
    pneumatic_policy_init(&s_policy, &config, now_ms());
    s_status.config = config;
    s_status.automatic_enabled = config.automatic_enabled;
    s_status.output = (pneumatic_policy_output_t){
        .state = s_policy.state,
        .fault = s_policy.fault,
    };
    if (xTaskCreate(controller_task, "pneumatic", PNEUMATIC_TASK_STACK, NULL, PNEUMATIC_TASK_PRIORITY, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    ESP_LOGI(TAG,
             "pneumatic controller ready: pump GPIO%d, valve GPIO%d, automatic=%s, calibration=%s",
             PNEUMATIC_PUMP_GPIO,
             PNEUMATIC_VALVE_GPIO,
             config.automatic_enabled ? "enabled" : "disabled",
             config.calibration_valid ? "loaded" : "required");
    return ESP_OK;
}

bool pneumatic_controller_is_started(void)
{
    return s_started;
}

bool pneumatic_controller_get_status(pneumatic_status_t *out)
{
    if (!s_started || out == NULL) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_status;
    xSemaphoreGive(s_lock);
    return true;
}

bool pneumatic_controller_get_self_test(bool *pump_verified, bool *valve_verified, bool *self_test_failed)
{
    if (!s_started || pump_verified == NULL || valve_verified == NULL || self_test_failed == NULL) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *pump_verified = s_pump_verified;
    *valve_verified = s_valve_verified;
    *self_test_failed = s_self_test_failed;
    xSemaphoreGive(s_lock);
    return true;
}

static void set_result_error(pneumatic_command_result_t *result, const char *error)
{
    if (result == NULL) {
        return;
    }
    result->accepted = false;
    snprintf(result->error, sizeof(result->error), "%s", error);
    (void)pneumatic_controller_get_status(&result->status);
}

esp_err_t pneumatic_controller_execute(
    const pneumatic_command_t *command,
    pneumatic_command_result_t *result)
{
    if (result != NULL) {
        *result = (pneumatic_command_result_t){0};
    }
    if (!s_started || command == NULL || command->command_id[0] == '\0') {
        set_result_error(result, "controller_not_ready_or_command_id_missing");
        return ESP_ERR_INVALID_STATE;
    }

    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (strcmp(command->command_id, s_last_command_id) == 0) {
        if (result != NULL) {
            result->accepted = true;
            result->duplicate = true;
            result->status = s_status;
        }
        xSemaphoreGive(s_lock);
        return ESP_OK;
    }

    if (command->type == PNEUMATIC_COMMAND_SAVE_CALIBRATION) {
        pneumatic_policy_config_t candidate = s_policy.config;
        candidate.target_kpa = command->target_kpa;
        candidate.max_kpa = command->max_kpa;
        candidate.max_inflate_ms = command->max_inflate_ms;
        candidate.calibration_valid = true;
        if (s_policy.state != PNEUMATIC_STATE_VENTED || !pneumatic_policy_config_is_valid(&candidate)) {
            xSemaphoreGive(s_lock);
            set_result_error(result, "calibration_requires_vented_state_and_safe_limits");
            return ESP_ERR_INVALID_ARG;
        }
        const esp_err_t persist_ret = persist_calibration(&candidate);
        if (persist_ret != ESP_OK) {
            xSemaphoreGive(s_lock);
            set_result_error(result, "calibration_persist_failed");
            return persist_ret;
        }
        pneumatic_policy_init(&s_policy, &candidate, now_ms());
        s_status.config = candidate;
        s_status.output.state = s_policy.state;
        s_status.output.fault = s_policy.fault;
    } else {
        switch (command->type) {
            case PNEUMATIC_COMMAND_INFLATE_PULSE:
                s_pending.inflate_pulse = true;
                break;
            case PNEUMATIC_COMMAND_VENT:
                s_pending.vent = true;
                break;
            case PNEUMATIC_COMMAND_EMERGENCY_STOP:
                s_pending.emergency_stop = true;
                set_outputs(false, false);
                break;
            case PNEUMATIC_COMMAND_RESET_FAULT:
                s_pending.reset_fault = true;
                break;
            case PNEUMATIC_COMMAND_SELF_TEST:
                if (s_policy.state != PNEUMATIC_STATE_VENTED ||
                    s_status.pressure_age_ms > PNEUMATIC_PRESSURE_STALE_MS ||
                    !s_status.pressure_valid ||
                    s_self_test.phase != PNEUMATIC_SELF_TEST_IDLE) {
                    xSemaphoreGive(s_lock);
                    set_result_error(result, "self_test_requires_vented_fresh_low_pressure");
                    return ESP_ERR_INVALID_STATE;
                }
                s_pump_verified = false;
                s_valve_verified = false;
                s_self_test_failed = false;
                s_self_test = (pneumatic_self_test_t){
                    .phase = PNEUMATIC_SELF_TEST_REQUESTED,
                    .started_ms = now_ms(),
                    .baseline_kpa = s_status.pressure_kpa,
                    .peak_kpa = s_status.pressure_kpa,
                };
                s_pending.inflate_pulse = true;
                break;
            default:
                xSemaphoreGive(s_lock);
                set_result_error(result, "unsupported_command");
                return ESP_ERR_INVALID_ARG;
        }
    }

    snprintf(s_last_command_id, sizeof(s_last_command_id), "%s", command->command_id);
    if (result != NULL) {
        result->accepted = true;
        result->status = s_status;
    }
    xSemaphoreGive(s_lock);
    return ESP_OK;
}

#endif
