#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms);

#ifdef __cplusplus
}
#endif
