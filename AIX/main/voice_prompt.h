#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

bool voice_prompt_format_event(char *out, size_t out_size, const char *text, uint32_t seq, uint32_t ts_ms);
bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms);

#ifdef __cplusplus
}
#endif
