#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "../main/dfplayer.h"
#include "../main/voice_prompt.h"

static int failures;

static void expect(bool condition, const char *message)
{
    if (!condition) {
        printf("FAIL: %s\n", message);
        failures++;
    }
}

static voice_prompt_request_t request(const char *command_id, uint8_t track, uint32_t frame_seq)
{
    voice_prompt_request_t value = {
        .command_id = command_id,
        .track = track,
        .frame_seq = frame_seq,
    };
    return value;
}

int main(void)
{
    uint8_t frame[DFPLAYER_FRAME_SIZE];
    const uint8_t expected_play[] = {0x7E, 0xFF, 0x06, 0x12, 0x01, 0x00, 0x01, 0xFE, 0xE7, 0xEF};
    const uint8_t finished_frame[] = {0x7E, 0xFF, 0x06, 0x3D, 0x00, 0x00, 0x02, 0xFE, 0xBC, 0xEF};
    dfplayer_message_t message = {0};
    voice_prompt_policy_t policy;
    voice_prompt_result_t result;
    voice_prompt_request_t prompt;

    expect(dfplayer_build_command(DFPLAYER_COMMAND_PLAY_MP3_FOLDER, 1, true, frame),
           "DFPlayer play command was not built");
    expect(memcmp(frame, expected_play, sizeof(frame)) == 0,
           "DFPlayer 0x12 command or checksum mismatch");
    expect(dfplayer_parse_frame(finished_frame, &message), "DFPlayer finish event rejected");
    expect(message.command == DFPLAYER_EVENT_PLAY_FINISHED_TF && message.parameter == 2,
           "DFPlayer finish event decoded incorrectly");

    voice_prompt_policy_init(&policy, true);
    prompt = request("0123456789abcdef:10:1", 1, 10);
    result = voice_prompt_policy_submit(&policy, "attention", &prompt);
    expect(result.status == VOICE_PROMPT_QUEUED && result.accepted,
           "attention entry must queue track 1");

    result = voice_prompt_policy_submit(&policy, "attention", &prompt);
    expect(result.status == VOICE_PROMPT_DUPLICATE && result.accepted,
           "same command ID must be idempotent");

    prompt = request("0123456789abcdef:11:2", 2, 11);
    result = voice_prompt_policy_submit(&policy, "high", &prompt);
    expect(result.status == VOICE_PROMPT_QUEUED && result.accepted,
           "higher risk must queue and interrupt lower risk");

    prompt = request("0123456789abcdef:12:1", 1, 12);
    result = voice_prompt_policy_submit(&policy, "attention", &prompt);
    expect(result.status == VOICE_PROMPT_SUPPRESSED && !result.accepted,
           "lower risk must be suppressed while higher risk is playing");

    voice_prompt_policy_mark_finished(&policy, 2);
    prompt = request("0123456789abcdef:13:3", 3, 13);
    result = voice_prompt_policy_submit(&policy, "critical", &prompt);
    expect(result.status == VOICE_PROMPT_QUEUED && result.accepted,
           "critical track must queue after playback finishes");

    prompt = request("0123456789abcdef:14:2", 2, 14);
    result = voice_prompt_policy_submit(&policy, "critical", &prompt);
    expect(result.status == VOICE_PROMPT_REJECTED && !result.accepted,
           "risk band and track mismatch must be rejected");

    voice_prompt_policy_set_available(&policy, false);
    prompt = request("0123456789abcdef:15:3", 3, 15);
    result = voice_prompt_policy_submit(&policy, "critical", &prompt);
    expect(result.status == VOICE_PROMPT_UNAVAILABLE && !result.accepted,
           "offline player must report unavailable");

    if (failures == 0) {
        printf("voice_prompt_test: ALL PASSED\n");
    }
    return failures;
}
