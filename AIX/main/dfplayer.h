#pragma once

#include <stdbool.h>
#include <stdint.h>

#define DFPLAYER_FRAME_SIZE 10U
#define DFPLAYER_COMMAND_SET_VOLUME 0x06U
#define DFPLAYER_COMMAND_SELECT_SOURCE 0x09U
#define DFPLAYER_COMMAND_RESET 0x0CU
#define DFPLAYER_COMMAND_PLAY_MP3_FOLDER 0x12U
#define DFPLAYER_EVENT_PLAY_FINISHED_TF 0x3DU
#define DFPLAYER_EVENT_CARD_ONLINE 0x3FU
#define DFPLAYER_EVENT_ERROR 0x40U

typedef struct {
    uint8_t command;
    uint16_t parameter;
} dfplayer_message_t;

bool dfplayer_build_command(uint8_t command, uint16_t parameter, bool request_feedback,
                            uint8_t out_frame[DFPLAYER_FRAME_SIZE]);
bool dfplayer_parse_frame(const uint8_t frame[DFPLAYER_FRAME_SIZE], dfplayer_message_t *out_message);

#ifdef ESP_PLATFORM
#include "esp_err.h"

esp_err_t dfplayer_uart_start(void);
esp_err_t dfplayer_send_command(uint8_t command, uint16_t parameter, bool request_feedback);
esp_err_t dfplayer_read_message(dfplayer_message_t *out_message, uint32_t timeout_ms);
#endif
