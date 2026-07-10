#include "vision_detect_input.h"

#include <stdio.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#define VISION_DETECT_TASK_STACK 4096
#define VISION_DETECT_TASK_PRIORITY 5
#define VISION_DETECT_PERIOD_MS 200

static const char *TAG = "AIX_VISION_DET";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static vision_detect_result_t s_latest;
static bool s_has_data;
static bool s_task_started;

bool vision_detect_input_get_snapshot(vision_detect_result_t *out)
{
    if (!out) return false;
    taskENTER_CRITICAL(&s_lock);
    bool ok = s_has_data;
    if (ok) *out = s_latest;
    taskEXIT_CRITICAL(&s_lock);
    return ok;
}

static void vision_detect_sim_task(void *arg)
{
    (void)arg;
    uint32_t seq = 0;
    float distance = 25.0f;
    const float approach_speed = 0.8f;  /* m per cycle */
    const float cycle_period = VISION_DETECT_PERIOD_MS / 1000.0f;

    while (1) {
        const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);
        seq++;

        /* Simulate approach */
        distance -= approach_speed * cycle_period;
        if (distance < 1.0f) {
            distance = 25.0f;  /* reset */
        }

        const float ttc = (approach_speed > 0.0f) ? distance / approach_speed : -1.0f;

        printf("{\"type\":\"vision_detect\",\"version\":1,\"seq\":%lu,\"ts_ms\":%lu,"
               "\"source\":\"simulated\",\"objects\":[{\"class\":\"truck\","
               "\"confidence\":0.85,\"bbox\":[100,60,80,60],\"distance_m\":%.1f,"
               "\"approaching\":true}],\"nearest_distance_m\":%.1f,"
               "\"ttc_s\":%.1f,\"valid\":true}\n",
               (unsigned long)seq, (unsigned long)now_ms,
               distance, distance, ttc);
        fflush(stdout);

        vision_detect_result_t snap = {0};
        snap.seq = seq;
        snap.ts_ms = now_ms;
        snap.received_ms = now_ms;
        strncpy(snap.source, "simulated", 31);
        snap.valid = true;
        snap.nearest_distance_m = distance;
        snap.ttc_s = ttc;
        snap.object_count = 1;
        strncpy(snap.objects[0].class_name, "truck", 31);
        snap.objects[0].confidence = 0.85f;
        snap.objects[0].distance_m = distance;
        snap.objects[0].approaching = true;

        taskENTER_CRITICAL(&s_lock);
        s_latest = snap;
        s_has_data = true;
        taskEXIT_CRITICAL(&s_lock);

        vTaskDelay(pdMS_TO_TICKS(VISION_DETECT_PERIOD_MS));
    }
}

esp_err_t vision_detect_input_start_task(void)
{
    if (s_task_started) return ESP_OK;
    BaseType_t ok = xTaskCreate(vision_detect_sim_task, "vision_det",
                                VISION_DETECT_TASK_STACK, NULL,
                                VISION_DETECT_TASK_PRIORITY, NULL);
    if (ok != pdPASS) return ESP_ERR_NO_MEM;
    s_task_started = true;
    ESP_LOGI(TAG, "simulated vision_detect task started");
    return ESP_OK;
}
#else
/* Host stub: no snapshot available without ESP platform */
bool vision_detect_input_get_snapshot(vision_detect_result_t *out)
{
    (void)out;
    return false;
}
#endif
