#include <stdio.h>

#include "../main/config_input.h"

int main(void)
{
    if (!config_input_pressure_enabled()) {
        printf("pressure should default to enabled\n");
        return 1;
    }

    config_input_state_t state = {
        .pressure_enabled = true,
    };

    if (!config_input_parse_line("{\"type\":\"config\",\"version\":1,\"pressure_enabled\":false}", &state)) {
        printf("config line should parse\n");
        return 1;
    }
    if (state.pressure_enabled) {
        printf("pressure should be disabled\n");
        return 1;
    }

    if (!config_input_parse_line("{\"type\":\"config\",\"version\":1,\"pressure_enabled\":true}", &state)) {
        printf("enabled config line should parse\n");
        return 1;
    }
    if (!state.pressure_enabled) {
        printf("pressure should be enabled\n");
        return 1;
    }

    if (config_input_parse_line("{\"type\":\"vision\"}", &state)) {
        printf("non-config line should be ignored\n");
        return 1;
    }

    return 0;
}
