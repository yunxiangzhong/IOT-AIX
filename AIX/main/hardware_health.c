#include "hardware_health.h"

#include <stddef.h>

hardware_health_snapshot_t hardware_health_evaluate(const hardware_health_input_t *input)
{
    if (input == NULL) {
        return (hardware_health_snapshot_t){
            .overall = HARDWARE_HEALTH_FAULT,
            .reason = "health_input_missing",
        };
    }
    const hardware_health_state_t pneumatic_state = input->pneumatic_started
                                                        ? HARDWARE_HEALTH_HEALTHY
                                                        : HARDWARE_HEALTH_DISABLED;
    hardware_health_snapshot_t snapshot = {
        .ov5640 = input->camera_healthy ? HARDWARE_HEALTH_HEALTHY : HARDWARE_HEALTH_FAULT,
        .mpu6050 = input->mpu_healthy ? HARDWARE_HEALTH_HEALTHY : HARDWARE_HEALTH_DEGRADED,
        .pressure = input->pressure_healthy ? HARDWARE_HEALTH_HEALTHY : HARDWARE_HEALTH_FAULT,
        .dfplayer = input->dfplayer_healthy ? HARDWARE_HEALTH_HEALTHY : HARDWARE_HEALTH_DEGRADED,
        .rgb = input->rgb_healthy ? HARDWARE_HEALTH_HEALTHY : HARDWARE_HEALTH_DEGRADED,
        .pump = !input->pneumatic_started ? HARDWARE_HEALTH_DISABLED
                                          : input->self_test_failed ? HARDWARE_HEALTH_FAULT
                                          : input->pump_verified ? HARDWARE_HEALTH_HEALTHY
                                                                 : HARDWARE_HEALTH_PENDING,
        .valve = !input->pneumatic_started ? HARDWARE_HEALTH_DISABLED
                                           : input->self_test_failed ? HARDWARE_HEALTH_FAULT
                                           : input->valve_verified ? HARDWARE_HEALTH_HEALTHY
                                                                  : HARDWARE_HEALTH_PENDING,
        .overall = pneumatic_state,
        .reason = "ready",
    };
    snapshot.automatic_ready = input->camera_healthy && input->network_healthy &&
                               input->pressure_healthy && input->pneumatic_started &&
                               input->pump_verified && input->valve_verified &&
                               !input->self_test_failed;
    if (!input->pressure_healthy) {
        snapshot.overall = HARDWARE_HEALTH_FAULT;
        snapshot.reason = "pressure_unhealthy";
    } else if (!input->pneumatic_started) {
        snapshot.overall = HARDWARE_HEALTH_DISABLED;
        snapshot.reason = "pneumatic_controller_disabled";
    } else if (input->self_test_failed) {
        snapshot.overall = HARDWARE_HEALTH_FAULT;
        snapshot.reason = "pneumatic_self_test_failed";
    } else if (!input->pump_verified || !input->valve_verified) {
        snapshot.overall = HARDWARE_HEALTH_DEGRADED;
        snapshot.reason = "pneumatic_self_test_pending_but_pressure_release_ready";
    } else if (!input->camera_healthy || !input->network_healthy || !input->mpu_healthy ||
               !input->dfplayer_healthy || !input->rgb_healthy) {
        snapshot.overall = HARDWARE_HEALTH_DEGRADED;
        snapshot.reason = "module_degraded";
    } else {
        snapshot.overall = HARDWARE_HEALTH_HEALTHY;
    }
    return snapshot;
}

const char *hardware_health_state_name(hardware_health_state_t state)
{
    switch (state) {
        case HARDWARE_HEALTH_INITIALIZING: return "initializing";
        case HARDWARE_HEALTH_HEALTHY: return "healthy";
        case HARDWARE_HEALTH_DEGRADED: return "degraded";
        case HARDWARE_HEALTH_FAULT: return "fault";
        case HARDWARE_HEALTH_STALE: return "stale";
        case HARDWARE_HEALTH_DISABLED: return "disabled";
        case HARDWARE_HEALTH_PENDING: return "pending";
        default: return "fault";
    }
}

#ifdef ESP_PLATFORM

#include <stdio.h>

#include "camera_local.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mpu6050_sensor.h"
#include "network_runtime.h"
#include "pneumatic_controller.h"
#include "pressure_sensor.h"
#include "rgb_status.h"
#include "voice_prompt.h"

#define HARDWARE_HEALTH_PERIOD_MS 1000U

static bool s_started;
static hardware_health_snapshot_t s_latest;

static bool is_fresh(uint64_t timestamp_ms, uint64_t current_ms, uint64_t maximum_age_ms)
{
    return current_ms >= timestamp_ms && current_ms - timestamp_ms <= maximum_age_ms;
}

static hardware_health_snapshot_t collect_health(void)
{
    const uint64_t current_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);
    camera_local_status_t camera = {0};
    camera_local_get_status(&camera);
    pressure_sensor_sample_t pressure = {0};
    const bool has_pressure = pressure_sensor_get_latest(&pressure);
    mpu6050_status_t mpu = {0};
    const bool has_mpu = mpu6050_sensor_get_latest(&mpu);
    bool pump_verified = false;
    bool valve_verified = false;
    bool self_test_failed = false;
    const bool pneumatic_started = pneumatic_controller_get_self_test(&pump_verified, &valve_verified, &self_test_failed);
    const hardware_health_input_t input = {
        .camera_healthy = camera.initialized && camera.valid && camera.frames_ok > 0U,
        .network_healthy = network_runtime_is_connected(),
        .mpu_healthy = has_mpu && mpu.motion.calibrated && is_fresh(mpu.timestamp_ms, current_ms, 250U),
        .pressure_healthy = has_pressure && pressure.valid && is_fresh(pressure.timestamp_ms, current_ms, 200U),
        .dfplayer_healthy = voice_prompt_is_ready(),
        .rgb_healthy = rgb_status_is_ready(),
        .pneumatic_started = pneumatic_started,
        .pump_verified = pump_verified,
        .valve_verified = valve_verified,
        .self_test_failed = self_test_failed,
    };
    return hardware_health_evaluate(&input);
}

static void emit_health(const hardware_health_snapshot_t *health)
{
    printf("{\"type\":\"hardware_health\",\"version\":1,\"ts_ms\":%llu,"
           "\"overall\":\"%s\",\"automatic_ready\":%s,"
           "\"ov5640\":\"%s\",\"mpu6050\":\"%s\",\"pressure\":\"%s\","
           "\"dfplayer\":\"%s\",\"rgb\":\"%s\",\"pump\":\"%s\",\"valve\":\"%s\","
           "\"reason\":\"%s\"}\n",
           (unsigned long long)(esp_timer_get_time() / 1000ULL),
           hardware_health_state_name(health->overall), health->automatic_ready ? "true" : "false",
           hardware_health_state_name(health->ov5640), hardware_health_state_name(health->mpu6050),
           hardware_health_state_name(health->pressure), hardware_health_state_name(health->dfplayer),
           hardware_health_state_name(health->rgb), hardware_health_state_name(health->pump),
           hardware_health_state_name(health->valve), health->reason);
    fflush(stdout);
}

static void hardware_health_task(void *arg)
{
    (void)arg;
    for (;;) {
        s_latest = collect_health();
        emit_health(&s_latest);
        vTaskDelay(pdMS_TO_TICKS(HARDWARE_HEALTH_PERIOD_MS));
    }
}

esp_err_t hardware_health_start(void)
{
    if (s_started) {
        return ESP_OK;
    }
    if (xTaskCreate(hardware_health_task, "hardware_health", 4096, NULL, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

bool hardware_health_automatic_ready(void)
{
    return s_latest.automatic_ready;
}

#endif
