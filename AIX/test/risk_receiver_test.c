#include <stdio.h>

#include "../main/risk_receiver.h"

int main(void)
{
    if (!risk_receiver_token_matches("local-secret", "local-secret")) {
        printf("matching token rejected\n");
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
