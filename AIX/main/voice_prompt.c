#include "voice_prompt.h"

#include <stdio.h>

static bool append_char(char *out, size_t out_size, size_t *used, char ch)
{
    if (*used + 1 >= out_size) {
        return false;
    }
    out[*used] = ch;
    *used += 1;
    out[*used] = '\0';
    return true;
}

static bool append_text(char *out, size_t out_size, size_t *used, const char *text)
{
    while (*text) {
        if (!append_char(out, out_size, used, *text++)) {
            return false;
        }
    }
    return true;
}

static bool append_json_string(char *out, size_t out_size, size_t *used, const char *text)
{
    if (!append_char(out, out_size, used, '"')) {
        return false;
    }
    for (const unsigned char *cursor = (const unsigned char *)text; *cursor; cursor++) {
        const unsigned char ch = *cursor;
        if (ch == '"' || ch == '\\') {
            if (!append_char(out, out_size, used, '\\') ||
                !append_char(out, out_size, used, (char)ch)) {
                return false;
            }
        } else if (ch == '\n') {
            if (!append_text(out, out_size, used, "\\n")) {
                return false;
            }
        } else if (ch == '\r') {
            if (!append_text(out, out_size, used, "\\r")) {
                return false;
            }
        } else if (ch == '\t') {
            if (!append_text(out, out_size, used, "\\t")) {
                return false;
            }
        } else if (ch < 0x20) {
            return false;
        } else if (!append_char(out, out_size, used, (char)ch)) {
            return false;
        }
    }
    return append_char(out, out_size, used, '"');
}

bool voice_prompt_format_event(char *out, size_t out_size, const char *text, uint32_t seq, uint32_t ts_ms)
{
    if (out == NULL || out_size == 0 || text == NULL || text[0] == '\0') {
        return false;
    }

    int prefix = snprintf(out,
                          out_size,
                          "{\"type\":\"voice\",\"version\":1,\"seq\":%lu,\"ts_ms\":%lu,\"text\":",
                          (unsigned long)seq,
                          (unsigned long)ts_ms);
    if (prefix < 0 || (size_t)prefix >= out_size) {
        out[0] = '\0';
        return false;
    }

    size_t used = (size_t)prefix;
    if (!append_json_string(out, out_size, &used, text) ||
        !append_text(out, out_size, &used, ",\"played\":true}")) {
        out[0] = '\0';
        return false;
    }
    return true;
}

bool voice_prompt_say(const char *text, uint32_t seq, uint32_t ts_ms)
{
    char line[256];
    if (!voice_prompt_format_event(line, sizeof(line), text, seq, ts_ms)) {
        return false;
    }
    printf("%s\n", line);
    fflush(stdout);
    return true;
}
