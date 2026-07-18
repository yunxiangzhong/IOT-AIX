#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ROAD_HAZARD_EVENT_ID_CAPACITY 65U
#define ROAD_HAZARD_DEVICE_ID_CAPACITY 64U
#define ROAD_HAZARD_BOOT_ID_CAPACITY 32U
#define ROAD_HAZARD_RECORD_CAPACITY 16U

typedef enum {
    ROAD_HAZARD_SEVERITY_ATTENTION = 0,
    ROAD_HAZARD_SEVERITY_HIGH,
    ROAD_HAZARD_SEVERITY_CRITICAL,
} road_hazard_severity_t;

typedef enum {
    ROAD_HAZARD_ACCEPTED = 0,
    ROAD_HAZARD_DUPLICATE,
    ROAD_HAZARD_REJECT_SCHEMA,
    ROAD_HAZARD_REJECT_DEVICE,
    ROAD_HAZARD_REJECT_BOOT,
    ROAD_HAZARD_REJECT_TTL,
    ROAD_HAZARD_REJECT_EVENT_CONFLICT,
    ROAD_HAZARD_REJECT_EXPIRED,
    ROAD_HAZARD_REJECT_CAPACITY,
} road_hazard_result_t;

typedef struct {
    const char *type;
    double version;
    const char *device_id;
    const char *boot_id;
    const char *event_id;
    const char *camera_id;
    const char *intersection_id;
    const char *message_code;
    const char *direction;
    const char *object_type;
    double eta_ms;
    const char *severity;
    double ttl_ms;
    bool simulated;
    bool simulated_is_bool;
} road_hazard_request_t;

typedef struct {
    bool used;
    bool expiry_emitted;
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY];
    uint64_t fingerprint;
    uint64_t expires_at_ms;
    uint32_t initial_ttl_ms;
    road_hazard_severity_t severity;
} road_hazard_record_t;

typedef struct {
    char device_id[ROAD_HAZARD_DEVICE_ID_CAPACITY];
    char boot_id[ROAD_HAZARD_BOOT_ID_CAPACITY];
    road_hazard_record_t records[ROAD_HAZARD_RECORD_CAPACITY];
} road_hazard_policy_t;

typedef struct {
    bool accepted;
    bool duplicate;
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY];
    uint32_t expires_in_ms;
    road_hazard_severity_t severity;
    road_hazard_result_t error;
} road_hazard_outcome_t;

typedef struct {
    char event_id[ROAD_HAZARD_EVENT_ID_CAPACITY];
    road_hazard_severity_t severity;
} road_hazard_expired_t;

void road_hazard_policy_init(road_hazard_policy_t *policy, const char *device_id, const char *boot_id);
road_hazard_result_t road_hazard_policy_submit(
    road_hazard_policy_t *policy,
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome);
bool road_hazard_policy_expire_next(
    road_hazard_policy_t *policy,
    uint64_t now_ms,
    road_hazard_expired_t *expired);
bool road_hazard_policy_highest_active(
    const road_hazard_policy_t *policy,
    uint64_t now_ms,
    road_hazard_severity_t *severity,
    const char **event_id,
    uint32_t *expires_in_ms);
const char *road_hazard_result_name(road_hazard_result_t result);
const char *road_hazard_severity_name(road_hazard_severity_t severity);
