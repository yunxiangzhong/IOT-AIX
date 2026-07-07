#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool pressure_enabled;
} config_input_state_t;

bool config_input_parse_line(const char *line, config_input_state_t *out);
void config_input_set_state(const config_input_state_t *state);
config_input_state_t config_input_get_state(void);
bool config_input_pressure_enabled(void);

#ifdef __cplusplus
}
#endif
