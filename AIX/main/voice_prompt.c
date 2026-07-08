#include "voice_prompt.h"

#include <stdio.h>
#include <string.h>

bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms)
{
    if (text == NULL || text[0] == '\0') {
        return false;
    }
    printf("{\"type\":\"voice\",\"version\":1,\"seq\":%lu,\"ts_ms\":%lu,"
           "\"text\":\"%s\",\"played\":true}\n",
           (unsigned long)seq, (unsigned long)ts_ms, text);
    fflush(stdout);
    return true;
}
