#include "config_input.h"

#include <stddef.h>
#include <string.h>

static config_input_state_t s_config_state = {
    .pressure_enabled = true,
};

static const char *find_field(const char *line, const char *key)
{
    const char *cursor = line;
    while ((cursor = strstr(cursor, key)) != NULL) {
        const char *colon = strchr(cursor + strlen(key), ':');
        if (colon != NULL) {
            return colon + 1;
        }
        cursor += strlen(key);
    }
    return NULL;
}

static bool parse_bool_field(const char *line, const char *key, bool *out)
{
    const char *value = find_field(line, key);
    if (value == NULL) {
        return false;
    }
    while (*value == ' ') {
        value++;
    }
    if (strncmp(value, "true", 4) == 0 || *value == '1') {
        *out = true;
        return true;
    }
    if (strncmp(value, "false", 5) == 0 || *value == '0') {
        *out = false;
        return true;
    }
    return false;
}

bool config_input_parse_line(const char *line, config_input_state_t *out)
{
    if (line == NULL || out == NULL) {
        return false;
    }
    if (strstr(line, "\"type\":\"config\"") == NULL &&
        strstr(line, "\"type\": \"config\"") == NULL) {
        return false;
    }

    config_input_state_t parsed = *out;
    if (!parse_bool_field(line, "\"pressure_enabled\"", &parsed.pressure_enabled)) {
        return false;
    }
    *out = parsed;
    return true;
}

void config_input_set_state(const config_input_state_t *state)
{
    if (state == NULL) {
        return;
    }
    s_config_state = *state;
}

config_input_state_t config_input_get_state(void)
{
    return s_config_state;
}

bool config_input_pressure_enabled(void)
{
    return s_config_state.pressure_enabled;
}
