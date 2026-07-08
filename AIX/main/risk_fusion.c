#include "risk_fusion.h"

#include <stddef.h>

static const char *pressure_state_name(bool pressure_enabled, bool pressure_safe)
{
    if (!pressure_enabled) {
        return "disabled";
    }
    return pressure_safe ? "safe" : "unsafe";
}

static risk_fusion_result_t make_result(int level,
                                        int target_pct,
                                        const char *reason,
                                        bool vision_stale,
                                        bool pressure_enabled,
                                        bool pressure_safe)
{
    const bool effective_pressure_safe = !pressure_enabled || pressure_safe;
    risk_fusion_result_t result = {
        .level = level,
        .target_pct = effective_pressure_safe ? target_pct : 0,
        .reason = reason,
        .vision_stale = vision_stale,
        .pressure_safe = effective_pressure_safe,
        .pressure_state = pressure_state_name(pressure_enabled, pressure_safe),
    };
    return result;
}

risk_fusion_result_t risk_fusion_evaluate(const vision_input_snapshot_t *vision,
                                          bool pressure_safe)
{
    return risk_fusion_evaluate_with_pressure(vision, true, pressure_safe);
}

risk_fusion_result_t risk_fusion_evaluate_with_pressure(const vision_input_snapshot_t *vision,
                                                        bool pressure_enabled,
                                                        bool pressure_safe)
{
    if (vision == NULL) {
        return make_result(0, 0, "vision_missing", true, pressure_enabled, pressure_safe);
    }
    if (vision->stale) {
        return make_result(0, 0, "vision_stale", true, pressure_enabled, pressure_safe);
    }
    if (!vision->valid) {
        return make_result(0, 0, "vision_invalid", false, pressure_enabled, pressure_safe);
    }

    const float looming = vision->looming;
    const float area_rate = vision->area_rate;
    const float confidence = vision->confidence;

    if (looming >= 0.90f && area_rate >= 0.60f && confidence >= 0.80f) {
        return make_result(100, 100, "vision_critical", false, pressure_enabled, pressure_safe);
    }
    if (looming >= 0.70f && area_rate >= 0.35f && confidence >= 0.70f) {
        return make_result(80, 80, "vision_looming", false, pressure_enabled, pressure_safe);
    }
    if (looming >= 0.45f && area_rate >= 0.20f && confidence >= 0.60f) {
        return make_result(50, 50, "vision_approach", false, pressure_enabled, pressure_safe);
    }
    if (looming >= 0.25f && confidence >= 0.50f) {
        return make_result(20, 20, "vision_weak", false, pressure_enabled, pressure_safe);
    }
    return make_result(0, 0, "vision_clear", false, pressure_enabled, pressure_safe);
}

risk_fusion_result_v2_t risk_fusion_evaluate_v2(const vision_detect_result_t *detect,
                                                  bool pressure_enabled,
                                                  bool pressure_safe)
{
    risk_fusion_result_v2_t result = {0};
    result.pressure_state = pressure_state_name(pressure_enabled, pressure_safe);

    const bool effective_safe = !pressure_enabled || pressure_safe;
    result.pressure_safe = effective_safe;

    if (!effective_safe) {
        result.level = 100;
        result.target_pct = 0;
        result.reason = "pressure_unsafe";
        result.category = "safety_stop";
        return result;
    }

    if (detect == NULL || !detect->valid || detect->object_count == 0) {
        result.level = 10;
        result.target_pct = 10;
        result.reason = "no_target";
        result.category = "normal";
        result.nearest_distance_m = -1.0f;
        result.ttc_s = -1.0f;
        return result;
    }

    result.nearest_distance_m = detect->nearest_distance_m;
    result.ttc_s = detect->ttc_s;
    if (detect->object_count > 0) {
        result.nearest_class = detect->objects[0].class_name;
    }

    if (detect->ttc_s >= 0.0f && detect->ttc_s < 3.0f) {
        result.level = 100;
        result.target_pct = 100;
        result.category = "critical";
        result.reason = "ttc_critical";
    } else if (detect->nearest_distance_m >= 0.0f && detect->nearest_distance_m < 5.0f) {
        result.level = 40;
        result.target_pct = 40;
        result.category = "vision_warning";
        result.reason = "target_close";
    } else if (detect->nearest_distance_m >= 0.0f && detect->nearest_distance_m < 15.0f) {
        result.level = 20;
        result.target_pct = 20;
        result.category = "vision_caution";
        result.reason = "target_approaching";
    } else {
        result.level = 10;
        result.target_pct = 10;
        result.category = "normal";
        result.reason = "target_far";
    }

    return result;
}

#ifdef ESP_PLATFORM
#include <stdio.h>
#include <string.h>

#include "airbag_control.h"
#include "config_input.h"
#include "pressure_sensor.h"
#include "vision_detect_input.h"
#include "voice_prompt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_timer.h"

#define RISK_FUSION_TASK_STACK 4096
#define RISK_FUSION_TASK_PRIORITY 7
#define RISK_FUSION_PERIOD_MS 50
#define RISK_FUSION_VISION_STALE_MS 500
#define RISK_FUSION_LOG_PERIOD_MS 500

static bool s_task_started;
static uint32_t s_risk_seq;

static void risk_fusion_task(void *arg)
{
    (void)arg;
    TickType_t last_log_tick = 0;

    while (1) {
        const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);

        /* v1: looming/area_rate snapshot */
        vision_input_snapshot_t vision = {
            .valid = true,
            .stale = true,
        };
        if (vision_input_get_snapshot(&vision)) {
            vision.stale = (now_ms - vision.received_ms) > RISK_FUSION_VISION_STALE_MS;
        }

        /* v2: object detection snapshot */
        vision_detect_result_t detect = {0};
        const bool has_detect = vision_detect_input_get_snapshot(&detect);

        /* pressure */
        const config_input_state_t config = config_input_get_state();
        bool pressure_safe = false;
        if (!config.pressure_enabled) {
            pressure_safe = true;
        } else {
            pressure_sensor_sample_t pressure = {0};
            if (pressure_sensor_get_latest(&pressure)) {
                pressure_safe = pressure.valid && !pressure.over_pressure;
            }
        }

        const TickType_t tick_now = xTaskGetTickCount();
        if ((tick_now - last_log_tick) >= pdMS_TO_TICKS(RISK_FUSION_LOG_PERIOD_MS)) {
            s_risk_seq++;

            if (has_detect && detect.valid) {
                /* v2 path: object-detection-based evaluation */
                risk_fusion_result_v2_t v2 = risk_fusion_evaluate_v2(
                    &detect, config.pressure_enabled, pressure_safe);
                printf("{\"type\":\"risk\",\"version\":2,\"seq\":%lu,"
                       "\"ts_ms\":%lu,\"level\":%d,\"target_pct\":%d,"
                       "\"reason\":\"%s\",\"category\":\"%s\","
                       "\"nearest_class\":\"%s\",\"nearest_distance_m\":%.2f,"
                       "\"ttc_s\":%.2f,"
                       "\"pressure_safe\":%s,\"pressure_state\":\"%s\"}\n",
                       (unsigned long)s_risk_seq,
                       (unsigned long)now_ms,
                       v2.level,
                       v2.target_pct,
                       v2.reason,
                       v2.category,
                       v2.nearest_class ? v2.nearest_class : "",
                       (double)v2.nearest_distance_m,
                       (double)v2.ttc_s,
                       v2.pressure_safe ? "true" : "false",
                       v2.pressure_state);

                /* voice prompt for level >= 20 */
                if (v2.level >= 20) {
                    const char *voice = NULL;
                    if (strcmp(v2.category, "critical") == 0) {
                        voice = "\xe7\xb4\xa7\xe6\x80\xa5\xe5\x8d\xb1\xe9\x99\xa9\xef\xbc\x8c\xe7\x9b\xae\xe6\xa0\x87\xe8\xbf\x87\xe8\xbf\x91";
                    } else if (strcmp(v2.category, "vision_warning") == 0) {
                        /* "注意，{nearest_class}接近" - build dynamically */
                        char buf[64];
                        snprintf(buf, sizeof(buf), "\xe6\xb3\xa8\xe6\x84\x8f\xef\xbc\x8c%s\xe6\x8e\xa5\xe8\xbf\x91",
                                 v2.nearest_class ? v2.nearest_class : "\xe7\x9b\xae\xe6\xa0\x87");
                        voice = buf;
                    } else if (strcmp(v2.category, "vision_caution") == 0) {
                        char buf[64];
                        snprintf(buf, sizeof(buf), "\xe5\x89\x8d\xe6\x96\xb9%s\xef\xbc\x8c\xe8\xaf\xb7\xe6\xb3\xa8\xe6\x84\x8f",
                                 v2.nearest_class ? v2.nearest_class : "\xe7\x9b\xae\xe6\xa0\x87");
                        voice = buf;
                    }
                    if (voice) {
                        voice_prompt_say(voice, s_risk_seq, now_ms);
                    }
                }
            } else {
                /* v1 fallback: looming/area_rate evaluation */
                risk_fusion_result_t v1 = risk_fusion_evaluate_with_pressure(
                    &vision, config.pressure_enabled, pressure_safe);
                printf("{\"type\":\"risk\",\"version\":1,\"seq\":%lu,"
                       "\"ts_ms\":%lu,\"level\":%d,\"target_pct\":%d,"
                       "\"reason\":\"%s\",\"vision_stale\":%s,"
                       "\"pressure_safe\":%s,\"pressure_state\":\"%s\"}\n",
                       (unsigned long)s_risk_seq,
                       (unsigned long)now_ms,
                       v1.level,
                       v1.target_pct,
                       v1.reason,
                       v1.vision_stale ? "true" : "false",
                       v1.pressure_safe ? "true" : "false",
                       v1.pressure_state);
                airbag_control_apply_simulated(&v1, s_risk_seq, now_ms);
            }

            fflush(stdout);
            last_log_tick = tick_now;
        }

        vTaskDelay(pdMS_TO_TICKS(RISK_FUSION_PERIOD_MS));
    }
}

esp_err_t risk_fusion_start_task(void)
{
    if (s_task_started) {
        return ESP_OK;
    }

    BaseType_t ok = xTaskCreate(risk_fusion_task,
                                "risk_fusion",
                                RISK_FUSION_TASK_STACK,
                                NULL,
                                RISK_FUSION_TASK_PRIORITY,
                                NULL);
    if (ok != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    s_task_started = true;
    return ESP_OK;
}
#endif
