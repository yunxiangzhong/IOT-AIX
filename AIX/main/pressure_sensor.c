#include "pressure_sensor.h"

#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#define PRESSURE_SENSOR_ADC_UNIT ADC_UNIT_1
#define PRESSURE_SENSOR_ADC_CHANNEL ADC_CHANNEL_0
#define PRESSURE_SENSOR_ADC_ATTEN ADC_ATTEN_DB_12
#define PRESSURE_SENSOR_SAMPLE_PERIOD_MS 20
#define PRESSURE_SENSOR_LOG_PERIOD_MS 1000
#define PRESSURE_SENSOR_FILTER_ALPHA 0.2f
#define PRESSURE_SENSOR_TASK_STACK 3072
#define PRESSURE_SENSOR_TASK_PRIORITY 5
#define PRESSURE_SENSOR_VALID_LOW_MV 100
#define PRESSURE_SENSOR_VALID_HIGH_MV 2900

static const char *TAG = "AIX_PRESSURE";

static adc_oneshot_unit_handle_t s_adc_handle;
static adc_cali_handle_t s_cali_handle;
static bool s_initialized;
static bool s_calibrated;
static bool s_filter_ready;
static bool s_task_started;
static float s_filtered_kpa;
static uint32_t s_sample_count;
static portMUX_TYPE s_latest_lock = portMUX_INITIALIZER_UNLOCKED;
static pressure_sensor_sample_t s_latest_sample;
static bool s_has_latest_sample;

static bool pressure_sensor_calibration_init(void)
{
    esp_err_t ret = ESP_FAIL;

#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t curve_config = {
        .unit_id = PRESSURE_SENSOR_ADC_UNIT,
        .chan = PRESSURE_SENSOR_ADC_CHANNEL,
        .atten = PRESSURE_SENSOR_ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ret = adc_cali_create_scheme_curve_fitting(&curve_config, &s_cali_handle);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "ADC calibration: curve fitting");
        return true;
    }
#endif

#if ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    adc_cali_line_fitting_config_t line_config = {
        .unit_id = PRESSURE_SENSOR_ADC_UNIT,
        .atten = PRESSURE_SENSOR_ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ret = adc_cali_create_scheme_line_fitting(&line_config, &s_cali_handle);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "ADC calibration: line fitting");
        return true;
    }
#endif

    if (ret == ESP_ERR_NOT_SUPPORTED) {
        ESP_LOGW(TAG, "ADC calibration not supported, using raw fallback");
    } else {
        ESP_LOGW(TAG, "ADC calibration unavailable: %s", esp_err_to_name(ret));
    }
    s_cali_handle = NULL;
    return false;
}

esp_err_t pressure_sensor_init(void)
{
    if (s_initialized) {
        return ESP_OK;
    }

    adc_oneshot_unit_init_cfg_t unit_config = {
        .unit_id = PRESSURE_SENSOR_ADC_UNIT,
    };
    esp_err_t ret = adc_oneshot_new_unit(&unit_config, &s_adc_handle);
    if (ret != ESP_OK) {
        return ret;
    }

    adc_oneshot_chan_cfg_t channel_config = {
        .atten = PRESSURE_SENSOR_ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ret = adc_oneshot_config_channel(s_adc_handle,
                                     PRESSURE_SENSOR_ADC_CHANNEL,
                                     &channel_config);
    if (ret != ESP_OK) {
        return ret;
    }

    s_calibrated = pressure_sensor_calibration_init();
    s_initialized = true;

    ESP_LOGI(TAG,
             "XGZP6847A pressure sensor ready: GPIO%d ADC1_CH0, 3.3V model, "
             "%dmV-%dmV => 0-%.0fkPa",
             PRESSURE_SENSOR_ADC_GPIO,
             PRESSURE_SENSOR_MIN_MV,
             PRESSURE_SENSOR_MAX_MV,
             PRESSURE_SENSOR_FULL_SCALE_KPA);
    return ESP_OK;
}

esp_err_t pressure_sensor_read(pressure_sensor_sample_t *out)
{
    if (out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    int raw = 0;
    esp_err_t ret = adc_oneshot_read(s_adc_handle,
                                     PRESSURE_SENSOR_ADC_CHANNEL,
                                     &raw);
    if (ret != ESP_OK) {
        return ret;
    }

    int voltage_mv = 0;
    if (s_calibrated) {
        ret = adc_cali_raw_to_voltage(s_cali_handle, raw, &voltage_mv);
        if (ret != ESP_OK) {
            return ret;
        }
    } else {
        voltage_mv = (raw * 3300) / 4095;
    }

    const float pressure_kpa = pressure_sensor_voltage_to_kpa(voltage_mv);
    const bool valid = (voltage_mv >= PRESSURE_SENSOR_VALID_LOW_MV) &&
                       (voltage_mv <= PRESSURE_SENSOR_VALID_HIGH_MV);
    if (!valid) {
        s_filter_ready = false;
        s_filtered_kpa = 0.0f;
    } else if (!s_filter_ready) {
        s_filtered_kpa = pressure_kpa;
        s_filter_ready = true;
    } else {
        s_filtered_kpa = (PRESSURE_SENSOR_FILTER_ALPHA * pressure_kpa) +
                         ((1.0f - PRESSURE_SENSOR_FILTER_ALPHA) * s_filtered_kpa);
    }

    s_sample_count++;
    out->raw = raw;
    out->voltage_mv = voltage_mv;
    out->pressure_kpa = pressure_kpa;
    out->filtered_kpa = s_filtered_kpa;
    out->over_pressure = valid && pressure_sensor_is_over_pressure(s_filtered_kpa);
    out->valid = valid;
    out->sample_count = s_sample_count;
    out->timestamp_ms = (uint64_t)(esp_timer_get_time() / 1000ULL);

    taskENTER_CRITICAL(&s_latest_lock);
    s_latest_sample = *out;
    s_has_latest_sample = true;
    taskEXIT_CRITICAL(&s_latest_lock);

    return ESP_OK;
}

bool pressure_sensor_get_latest(pressure_sensor_sample_t *out)
{
    if (out == NULL) {
        return false;
    }

    taskENTER_CRITICAL(&s_latest_lock);
    const bool has_sample = s_has_latest_sample;
    if (has_sample) {
        *out = s_latest_sample;
    }
    taskEXIT_CRITICAL(&s_latest_lock);

    return has_sample;
}

static void pressure_sensor_task(void *arg)
{
    (void)arg;

    TickType_t last_log_tick = xTaskGetTickCount();

    while (1) {
        pressure_sensor_sample_t sample = {0};
        const esp_err_t ret = pressure_sensor_read(&sample);
        if (ret == ESP_OK) {
            const TickType_t now = xTaskGetTickCount();
            if ((now - last_log_tick) >= pdMS_TO_TICKS(PRESSURE_SENSOR_LOG_PERIOD_MS)) {
                const uint32_t ts_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);
                printf("{\"type\":\"pressure\",\"version\":1,\"seq\":%lu,"
                       "\"ts_ms\":%lu,\"raw\":%d,\"mv\":%d,\"kpa\":%.2f,"
                       "\"filtered_kpa\":%.2f,\"over_pressure\":%s,"
                       "\"valid\":%s}\n",
                       (unsigned long)sample.sample_count,
                       (unsigned long)ts_ms,
                       sample.raw,
                       sample.voltage_mv,
                       sample.pressure_kpa,
                       sample.filtered_kpa,
                       sample.over_pressure ? "true" : "false",
                       sample.valid ? "true" : "false");
                fflush(stdout);
                last_log_tick = now;
            }

            if (sample.over_pressure) {
                ESP_LOGW(TAG,
                         "soft over-pressure warning: %.2fkPa >= %.2fkPa",
                         sample.filtered_kpa,
                         PRESSURE_SENSOR_OVER_PRESSURE_KPA);
            }
            if (!sample.valid) {
                ESP_LOGW(TAG,
                         "pressure sensor voltage outside expected range: %dmV",
                         sample.voltage_mv);
            }
        } else {
            ESP_LOGE(TAG, "pressure read failed: %s", esp_err_to_name(ret));
        }

        vTaskDelay(pdMS_TO_TICKS(PRESSURE_SENSOR_SAMPLE_PERIOD_MS));
    }
}

esp_err_t pressure_sensor_start_task(void)
{
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    if (s_task_started) {
        return ESP_OK;
    }

    BaseType_t ok = xTaskCreate(pressure_sensor_task,
                                "pressure_sensor",
                                PRESSURE_SENSOR_TASK_STACK,
                                NULL,
                                PRESSURE_SENSOR_TASK_PRIORITY,
                                NULL);
    if (ok != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    s_task_started = true;
    return ESP_OK;
}

