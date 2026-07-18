#include <stdio.h>
#include <string.h>

#include "../main/risk_receiver.h"

int main(void)
{
    uint64_t latency_ms = 0;
    char ack[384];
    if (!risk_receiver_token_matches("local-secret", "local-secret")) {
        printf("matching token rejected\n");
        return 1;
    }
    if (risk_receiver_format_action_ack(
            ack, sizeof(ack), 7U, true, false, 788U, "high", "orange_blink_2hz", "") < 0 ||
        strstr(ack, "\"e2e_latency_ms\":788") == NULL ||
        strstr(ack, "\"frame_seq\":7") == NULL) {
        printf("action ack does not expose e2e latency\n");
        return 1;
    }
    if (!risk_receiver_e2e_latency_ms(1200U, 1988U, &latency_ms) || latency_ms != 788U) {
        printf("valid e2e latency rejected\n");
        return 1;
    }
    if (!risk_receiver_e2e_latency_at_ack(1200U, 1500U, 1988U, &latency_ms) || latency_ms != 788U) {
        printf("e2e latency did not use the final ACK timestamp\n");
        return 1;
    }
    if (risk_receiver_e2e_latency_at_ack(1200U, 1988U, 1500U, &latency_ms)) {
        printf("e2e latency accepted an ACK timestamp before risk decision\n");
        return 1;
    }
    if (!risk_receiver_e2e_latency_ms(2000U, 2000U, &latency_ms) || latency_ms != 0U ||
        risk_receiver_e2e_latency_ms(2001U, 2000U, &latency_ms) ||
        risk_receiver_e2e_latency_ms(1000U, 2000U, NULL)) {
        printf("invalid e2e latency boundary accepted\n");
        return 1;
    }
    if (risk_receiver_token_matches("local-secret", "wrong-secret") ||
        risk_receiver_token_matches("local-secret", "local-secret-long") ||
        risk_receiver_token_matches("", "") ||
        risk_receiver_token_matches(NULL, "local-secret")) {
        printf("invalid token accepted\n");
        return 1;
    }
    printf("risk_receiver_test: ALL PASSED\n");
    return 0;
}
