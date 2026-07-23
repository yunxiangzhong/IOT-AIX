#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../main/voice_prompt.h"

static int check(bool condition, const char *label)
{
    if (!condition) {
        printf("FAIL: %s\n", label);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;
    uint8_t track = 0;

    /* Scene → track mapping */
    failures += check(voice_prompt_track_for_scene(4, &track) && track == 4,
                      "scene 4 → track 4");
    failures += check(voice_prompt_track_for_scene(5, &track) && track == 5,
                      "scene 5 → track 5");
    failures += check(voice_prompt_track_for_scene(6, &track) && track == 6,
                      "scene 6 → track 6");

    /* Invalid scenes */
    failures += check(!voice_prompt_track_for_scene(0, &track),
                      "scene 0 rejected");
    failures += check(!voice_prompt_track_for_scene(1, &track),
                      "scene 1 rejected (normal band track, not scene)");
    failures += check(!voice_prompt_track_for_scene(2, &track),
                      "scene 2 rejected");
    failures += check(!voice_prompt_track_for_scene(3, &track),
                      "scene 3 rejected");
    failures += check(!voice_prompt_track_for_scene(7, &track),
                      "scene 7 rejected (out of range)");
    failures += check(!voice_prompt_track_for_scene(255, &track),
                      "scene 255 rejected");

    /* NULL pointer safety */
    failures += check(!voice_prompt_track_for_scene(4, NULL),
                      "NULL out_track rejected");

    /* scene_is_valid */
    failures += check(voice_prompt_scene_is_valid(4), "scene 4 is valid");
    failures += check(voice_prompt_scene_is_valid(5), "scene 5 is valid");
    failures += check(voice_prompt_scene_is_valid(6), "scene 6 is valid");
    voice_prompt_policy_t policy;
    voice_prompt_policy_init(&policy, true);
    voice_prompt_request_t scene_request = {"demo_scene_5", 5U, 12U};
    voice_prompt_result_t scene_result = voice_prompt_policy_submit_scene(&policy, 5U, &scene_request);
    failures += check(scene_result.accepted && scene_result.track == 5U,
                      "scene 5 accepts its dedicated track");
    failures += check(!voice_prompt_scene_is_valid(0), "scene 0 is invalid");
    failures += check(!voice_prompt_scene_is_valid(3), "scene 3 is invalid");
    failures += check(!voice_prompt_scene_is_valid(7), "scene 7 is invalid");

    /* Normal band mapping unchanged */
    failures += check(voice_prompt_track_for_band("attention", &track) && track == 1,
                      "attention → track 1 (unchanged)");
    failures += check(voice_prompt_track_for_band("high", &track) && track == 2,
                      "high → track 2 (unchanged)");
    failures += check(voice_prompt_track_for_band("critical", &track) && track == 3,
                      "critical → track 3 (unchanged)");
    failures += check(!voice_prompt_track_for_band("low", &track),
                      "low → rejected (unchanged)");

    if (failures == 0) {
        printf("voice_prompt_scene_test: ALL PASSED\n");
    } else {
        printf("voice_prompt_scene_test: %d FAILURES\n", failures);
    }
    return failures;
}
