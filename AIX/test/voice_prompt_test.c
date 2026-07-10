#include <stdio.h>
#include <string.h>

#include "../main/voice_prompt.h"

int main(void)
{
    char line[256];
    const bool ok = voice_prompt_format_event(
        line,
        sizeof(line),
        "target \"truck\" \\ close",
        7,
        1234);

    const char *expected =
        "{\"type\":\"voice\",\"version\":1,\"seq\":7,\"ts_ms\":1234,"
        "\"text\":\"target \\\"truck\\\" \\\\ close\",\"played\":true}";

    if (!ok) {
        printf("FAIL: format returned false\n");
        return 1;
    }
    if (strcmp(line, expected) != 0) {
        printf("FAIL: got '%s'\nexpected '%s'\n", line, expected);
        return 1;
    }

    if (voice_prompt_format_event(line, sizeof(line), NULL, 1, 1)) {
        printf("FAIL: null text formatted\n");
        return 1;
    }
    if (voice_prompt_format_event(line, 10, "this string is too long", 1, 1)) {
        printf("FAIL: oversized buffer formatted\n");
        return 1;
    }

    printf("voice_prompt_test: ALL PASSED\n");
    return 0;
}
