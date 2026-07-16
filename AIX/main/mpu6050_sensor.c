#include "mpu6050_sensor.h"

#ifdef ESP_PLATFORM

#include <stdio.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_check.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define MPU6050_I2C_PORT I2C_NUM_0
#define MPU6050_I2C_CLOCK_HZ 400000U
#define MPU6050_READ_TIMEOUT_MS 20
#define MPU6050_SAMPLE_TIMEOUT_MS 20
#define MPU6050_TASK_STACK 4096
#define MPU6050_TASK_PRIORITY 6
#define MPU6050_LOG_PERIOD_MS 100

#define MPU6050_REG_ACCEL_XOUT_H 0x3B
#define MPU6050_REG_CONFIG 0x1A
#define MPU6050_REG_GYRO_CONFIG 0x1B
#define MPU6050_REG_ACCEL_CONFIG 0x1C
#define MPU6050_REG_INT_PIN_CFG 0x37
#define MPU6050_REG_INT_ENABLE 0x38
#define MPU6050_REG_PWR_MGMT_1 0x6B
#define MPU6050_REG_WHO_AM_I 0x75

static const char *TAG = "AIX_MPU6050";
static i2c_master_bus_handle_t s_i2c_bus;
static i2c_master_dev_handle_t s_i2c_device;
static TaskHandle_t s_task_handle;
static bool s_started;
static bool s_has_latest;
static portMUX_TYPE s_latest_lock = portMUX_INITIALIZER_UNLOCKED;
static mpu6050_status_t s_latest;

static uint64_t now_ms(void)
{
    return (uint64_t)(esp_timer_get_time() / 1000ULL);
}

static esp_err_t write_register(uint8_t reg, uint8_t value)
{
    const uint8_t bytes[] = {reg, value};
    return i2c_master_transmit(s_i2c_device, bytes, sizeof(bytes), MPU6050_READ_TIMEOUT_MS);
}

static esp_err_t read_registers(uint8_t reg, uint8_t *bytes, size_t length)
{
    return i2c_master_transmit_receive(
        s_i2c_device, &reg, sizeof(reg), bytes, length, MPU6050_READ_TIMEOUT_MS);
}

static int16_t read_i16(const uint8_t *bytes)
{
    return (int16_t)(((uint16_t)bytes[0] << 8U) | bytes[1]);
}

static void IRAM_ATTR data_ready_isr(void *arg)
{
    BaseType_t higher_priority_task_woken = pdFALSE;
    vTaskNotifyGiveFromISR((TaskHandle_t)arg, &higher_priority_task_woken);
    if (higher_priority_task_woken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static void emit_motion(const mpu6050_status_t *status)
{
    printf("{\"type\":\"motion\",\"version\":2,\"seq\":%lu,\"ts_ms\":%llu,"
           "\"accel_g\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
           "\"gyro_dps\":{\"x\":%.2f,\"y\":%.2f,\"z\":%.2f},"
           "\"accel_norm_g\":%.3f,\"tilt_deg\":%.2f,\"impact\":%s,"
           "\"rapid_tilt\":%s,\"danger_latched\":%s,\"calibrated\":%s,"
           "\"speed_mps\":0.0,\"speed_valid\":false}\n",
           (unsigned long)status->sequence,
           (unsigned long long)status->timestamp_ms,
           status->sample.accel_x_g,
           status->sample.accel_y_g,
           status->sample.accel_z_g,
           status->sample.gyro_x_dps,
           status->sample.gyro_y_dps,
           status->sample.gyro_z_dps,
           status->motion.accel_norm_g,
           status->motion.tilt_deg,
           status->motion.impact ? "true" : "false",
           status->motion.rapid_tilt ? "true" : "false",
           status->motion.danger_latched ? "true" : "false",
           status->motion.calibrated ? "true" : "false");
    fflush(stdout);
}

static esp_err_t read_sample(motion_sample_t *sample)
{
    uint8_t bytes[14];
    esp_err_t ret = read_registers(MPU6050_REG_ACCEL_XOUT_H, bytes, sizeof(bytes));
    if (ret != ESP_OK) {
        return ret;
    }
    sample->accel_x_g = (float)read_i16(&bytes[0]) / 2048.0f;
    sample->accel_y_g = (float)read_i16(&bytes[2]) / 2048.0f;
    sample->accel_z_g = (float)read_i16(&bytes[4]) / 2048.0f;
    sample->gyro_x_dps = (float)read_i16(&bytes[8]) / 16.4f;
    sample->gyro_y_dps = (float)read_i16(&bytes[10]) / 16.4f;
    sample->gyro_z_dps = (float)read_i16(&bytes[12]) / 16.4f;
    return ESP_OK;
}

static void mpu6050_task(void *arg)
{
    (void)arg;
    motion_detector_t detector;
    motion_detector_init(&detector, now_ms());
    uint64_t last_log_ms = 0;

    for (;;) {
        (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(MPU6050_SAMPLE_TIMEOUT_MS));
        motion_sample_t sample = {0};
        esp_err_t ret = read_sample(&sample);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "sample read failed: %s", esp_err_to_name(ret));
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        mpu6050_status_t next = {
            .sample = sample,
            .timestamp_ms = now_ms(),
        };
        next.motion = motion_detector_step(&detector, &sample, next.timestamp_ms);
        taskENTER_CRITICAL(&s_latest_lock);
        next.sequence = s_latest.sequence + 1U;
        s_latest = next;
        s_has_latest = true;
        taskEXIT_CRITICAL(&s_latest_lock);

        if (next.timestamp_ms - last_log_ms >= MPU6050_LOG_PERIOD_MS) {
            emit_motion(&next);
            last_log_ms = next.timestamp_ms;
        }
    }
}

static esp_err_t configure_mpu6050(void)
{
    uint8_t who_am_i = 0;
    esp_err_t ret = read_registers(MPU6050_REG_WHO_AM_I, &who_am_i, sizeof(who_am_i));
    if (ret != ESP_OK) {
        return ret;
    }
    if (who_am_i != 0x68U && who_am_i != 0x69U) {
        ESP_LOGE(TAG, "unexpected WHO_AM_I=0x%02x", who_am_i);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_RETURN_ON_ERROR(write_register(MPU6050_REG_PWR_MGMT_1, 0x00), TAG, "wake MPU6050 failed");
    ESP_RETURN_ON_ERROR(write_register(MPU6050_REG_CONFIG, 0x03), TAG, "set DLPF failed");
    ESP_RETURN_ON_ERROR(write_register(MPU6050_REG_GYRO_CONFIG, 0x18), TAG, "set gyro range failed");
    ESP_RETURN_ON_ERROR(write_register(MPU6050_REG_ACCEL_CONFIG, 0x18), TAG, "set accel range failed");
    ESP_RETURN_ON_ERROR(write_register(MPU6050_REG_INT_PIN_CFG, 0x00), TAG, "set interrupt pin failed");
    return write_register(MPU6050_REG_INT_ENABLE, 0x01);
}

esp_err_t mpu6050_sensor_start(void)
{
    if (s_started) {
        return ESP_OK;
    }
    i2c_master_bus_config_t bus_config = {
        .i2c_port = MPU6050_I2C_PORT,
        .sda_io_num = MPU6050_I2C_SDA_GPIO,
        .scl_io_num = MPU6050_I2C_SCL_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false,
    };
    ESP_RETURN_ON_ERROR(i2c_new_master_bus(&bus_config, &s_i2c_bus), TAG, "create I2C bus failed");
    i2c_device_config_t device_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = MPU6050_I2C_ADDRESS,
        .scl_speed_hz = MPU6050_I2C_CLOCK_HZ,
    };
    ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(s_i2c_bus, &device_config, &s_i2c_device), TAG, "add MPU6050 failed");
    ESP_RETURN_ON_ERROR(configure_mpu6050(), TAG, "configure MPU6050 failed");

    gpio_config_t int_config = {
        .pin_bit_mask = 1ULL << MPU6050_INT_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&int_config), TAG, "configure MPU6050 INT failed");
    esp_err_t isr_ret = gpio_install_isr_service(0);
    if (isr_ret != ESP_OK && isr_ret != ESP_ERR_INVALID_STATE) {
        return isr_ret;
    }
    if (xTaskCreate(mpu6050_task, "mpu6050", MPU6050_TASK_STACK, NULL, MPU6050_TASK_PRIORITY, &s_task_handle) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    ESP_RETURN_ON_ERROR(gpio_isr_handler_add(MPU6050_INT_GPIO, data_ready_isr, s_task_handle), TAG, "add MPU6050 ISR failed");
    s_started = true;
    ESP_LOGI(TAG, "MPU6050 ready: I2C SDA=GPIO%d SCL=GPIO%d INT=GPIO%d, 100Hz ±16g ±2000dps", MPU6050_I2C_SDA_GPIO, MPU6050_I2C_SCL_GPIO, MPU6050_INT_GPIO);
    return ESP_OK;
}

bool mpu6050_sensor_get_latest(mpu6050_status_t *out)
{
    if (out == NULL) {
        return false;
    }
    taskENTER_CRITICAL(&s_latest_lock);
    const bool has_latest = s_has_latest;
    if (has_latest) {
        *out = s_latest;
    }
    taskEXIT_CRITICAL(&s_latest_lock);
    return has_latest;
}

#endif
