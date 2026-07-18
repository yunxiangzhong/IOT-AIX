#include "dfplayer.h"

#include <stddef.h>

static uint16_t dfplayer_checksum(const uint8_t frame[DFPLAYER_FRAME_SIZE])
{
    uint16_t sum = 0;
    for (size_t index = 1; index <= 6; index++) {
        sum = (uint16_t)(sum + frame[index]);
    }
    return (uint16_t)(0U - sum);
}

bool dfplayer_build_command(uint8_t command, uint16_t parameter, bool request_feedback,
                            uint8_t out_frame[DFPLAYER_FRAME_SIZE])
{
    if (out_frame == NULL) {
        return false;
    }
    out_frame[0] = 0x7EU;
    out_frame[1] = 0xFFU;
    out_frame[2] = 0x06U;
    out_frame[3] = command;
    out_frame[4] = request_feedback ? 0x01U : 0x00U;
    out_frame[5] = (uint8_t)(parameter >> 8U);
    out_frame[6] = (uint8_t)(parameter & 0xFFU);
    const uint16_t checksum = dfplayer_checksum(out_frame);
    out_frame[7] = (uint8_t)(checksum >> 8U);
    out_frame[8] = (uint8_t)(checksum & 0xFFU);
    out_frame[9] = 0xEFU;
    return true;
}

bool dfplayer_parse_frame(const uint8_t frame[DFPLAYER_FRAME_SIZE], dfplayer_message_t *out_message)
{
    if (frame == NULL || out_message == NULL || frame[0] != 0x7EU || frame[1] != 0xFFU ||
        frame[2] != 0x06U || frame[9] != 0xEFU) {
        return false;
    }
    const uint16_t actual = (uint16_t)(((uint16_t)frame[7] << 8U) | frame[8]);
    if (actual != dfplayer_checksum(frame)) {
        return false;
    }
    out_message->command = frame[3];
    out_message->parameter = (uint16_t)(((uint16_t)frame[5] << 8U) | frame[6]);
    return true;
}

#ifdef ESP_PLATFORM

#include "driver/uart.h"
#include "freertos/FreeRTOS.h"

#define DFPLAYER_UART UART_NUM_2
#define DFPLAYER_TX_GPIO 47
#define DFPLAYER_RX_GPIO 48
#define DFPLAYER_BAUD_RATE 9600

static bool s_uart_started;

esp_err_t dfplayer_uart_start(void)
{
    if (s_uart_started) {
        return ESP_OK;
    }
    const uart_config_t config = {
        .baud_rate = DFPLAYER_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t ret = uart_param_config(DFPLAYER_UART, &config);
    if (ret != ESP_OK) {
        return ret;
    }
    ret = uart_set_pin(DFPLAYER_UART, DFPLAYER_TX_GPIO, DFPLAYER_RX_GPIO, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (ret != ESP_OK) {
        return ret;
    }
    ret = uart_driver_install(DFPLAYER_UART, 256, 0, 0, NULL, 0);
    if (ret != ESP_OK) {
        return ret;
    }
    s_uart_started = true;
    return ESP_OK;
}

esp_err_t dfplayer_send_command(uint8_t command, uint16_t parameter, bool request_feedback)
{
    uint8_t frame[DFPLAYER_FRAME_SIZE];
    if (!s_uart_started || !dfplayer_build_command(command, parameter, request_feedback, frame)) {
        return ESP_ERR_INVALID_STATE;
    }
    const int written = uart_write_bytes(DFPLAYER_UART, frame, sizeof(frame));
    return written == (int)sizeof(frame) ? ESP_OK : ESP_FAIL;
}

esp_err_t dfplayer_read_message(dfplayer_message_t *out_message, uint32_t timeout_ms)
{
    if (!s_uart_started || out_message == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    uint8_t frame[DFPLAYER_FRAME_SIZE];
    const TickType_t timeout = pdMS_TO_TICKS(timeout_ms);
    uint8_t byte = 0;
    do {
        if (uart_read_bytes(DFPLAYER_UART, &byte, 1, timeout) != 1) {
            return ESP_ERR_TIMEOUT;
        }
    } while (byte != 0x7EU);
    frame[0] = byte;
    if (uart_read_bytes(DFPLAYER_UART, &frame[1], DFPLAYER_FRAME_SIZE - 1U, timeout) !=
        (int)(DFPLAYER_FRAME_SIZE - 1U)) {
        return ESP_ERR_TIMEOUT;
    }
    return dfplayer_parse_frame(frame, out_message) ? ESP_OK : ESP_ERR_INVALID_RESPONSE;
}

#endif
