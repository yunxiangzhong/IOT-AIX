#include "rgb_status.h"

#ifdef ESP_PLATFORM

#include "esp_check.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led_strip.h"

#define AIX_RGB_GPIO 38
#define AIX_RGB_MAX 51U

static led_strip_handle_t s_strip;
static rgb_pattern_t s_pattern = RGB_BLUE_BLINK_1HZ;
static bool s_started;
static portMUX_TYPE s_pattern_lock = portMUX_INITIALIZER_UNLOCKED;

static void set_color(uint8_t red, uint8_t green, uint8_t blue, bool on)
{
    if (!on) {
        red = green = blue = 0U;
    }
    led_strip_set_pixel(s_strip, 0, red, green, blue);
    led_strip_refresh(s_strip);
}

static void rgb_task(void *arg)
{
    (void)arg;
    for (;;) {
        rgb_pattern_t pattern;
        uint32_t phase = (uint32_t)((esp_timer_get_time() / 1000ULL) % 1000ULL);
        taskENTER_CRITICAL(&s_pattern_lock);
        pattern = s_pattern;
        taskEXIT_CRITICAL(&s_pattern_lock);
        switch (pattern) {
        case RGB_BLUE_BLINK_1HZ:
            set_color(0, 12, AIX_RGB_MAX, phase < 500U);
            break;
        case RGB_GREEN_SOLID:
            set_color(0, AIX_RGB_MAX, 8, true);
            break;
        case RGB_YELLOW_BLINK_1HZ:
            set_color(AIX_RGB_MAX, 36, 0, phase < 500U);
            break;
        case RGB_ORANGE_BLINK_2HZ:
            set_color(AIX_RGB_MAX, 18, 0, (phase % 500U) < 250U);
            break;
        case RGB_RED_DOUBLE_PULSE:
            set_color(AIX_RGB_MAX, 0, 0, phase < 120U || (phase >= 220U && phase < 340U));
            break;
        case RGB_PURPLE_BLINK_1HZ:
            set_color(32, 0, AIX_RGB_MAX, phase < 500U);
            break;
        case RGB_CYAN_RESULT_PULSE:
            set_color(0, AIX_RGB_MAX, AIX_RGB_MAX, true);
            break;
        case RGB_WHITE_AIRBAG_LATCHED:
            set_color(AIX_RGB_MAX, AIX_RGB_MAX, AIX_RGB_MAX, true);
            break;
        default:
            set_color(32, 0, AIX_RGB_MAX, phase < 500U);
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(40));
    }
}

esp_err_t rgb_status_start(void)
{
    led_strip_config_t strip_config = {
        .strip_gpio_num = AIX_RGB_GPIO,
        .max_leds = 1,
        .led_model = LED_MODEL_WS2812,
        .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB,
        .flags.invert_out = false,
    };
    led_strip_rmt_config_t rmt_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .mem_block_symbols = 0,
        .flags.with_dma = false,
    };
    ESP_RETURN_ON_ERROR(led_strip_new_rmt_device(&strip_config, &rmt_config, &s_strip), "AIX_RGB", "strip init failed");
    if (xTaskCreate(rgb_task, "rgb_status", 3072, NULL, 3, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

void rgb_status_set_pattern(rgb_pattern_t pattern)
{
    taskENTER_CRITICAL(&s_pattern_lock);
    s_pattern = pattern;
    taskEXIT_CRITICAL(&s_pattern_lock);
}

bool rgb_status_is_ready(void)
{
    return s_started && s_strip != NULL;
}

rgb_pattern_t rgb_status_get_pattern(void)
{
    rgb_pattern_t pattern;
    taskENTER_CRITICAL(&s_pattern_lock);
    pattern = s_pattern;
    taskEXIT_CRITICAL(&s_pattern_lock);
    return pattern;
}

#endif
