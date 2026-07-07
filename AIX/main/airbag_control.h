#pragma once

#include "risk_fusion.h"

#ifdef ESP_PLATFORM
void airbag_control_apply_simulated(const risk_fusion_result_t *result,
                                    uint32_t seq,
                                    uint32_t ts_ms);
#endif
