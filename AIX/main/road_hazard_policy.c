#include "road_hazard_policy.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static bool nonempty_bounded(const char *value, size_t capacity)
{
    return value != NULL && value[0] != '\0' && strlen(value) < capacity;
}

static bool event_id_valid(const char *value)
{
    if (!nonempty_bounded(value, ROAD_HAZARD_EVENT_ID_CAPACITY)) {
        return false;
    }
    for (const unsigned char *p = (const unsigned char *)value; *p != '\0'; ++p) {
        const bool valid = (*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
                           (*p >= '0' && *p <= '9') || *p == '-' || *p == '_' || *p == '.' || *p == '~';
        if (!valid) {
            return false;
        }
    }
    return true;
}

static bool identifier_valid(const char *value)
{
    return event_id_valid(value);
}

static bool integer_in_range(double value, double minimum, double maximum)
{
    return isfinite(value) && value >= minimum && value <= maximum && floor(value) == value;
}

static bool parse_severity(const char *value, road_hazard_severity_t *severity)
{
    if (value != NULL && strcmp(value, "attention") == 0) {
        *severity = ROAD_HAZARD_SEVERITY_ATTENTION;
    } else if (value != NULL && strcmp(value, "high") == 0) {
        *severity = ROAD_HAZARD_SEVERITY_HIGH;
    } else if (value != NULL && strcmp(value, "critical") == 0) {
        *severity = ROAD_HAZARD_SEVERITY_CRITICAL;
    } else {
        return false;
    }
    return true;
}

static road_hazard_result_t validate(
    const road_hazard_policy_t *policy,
    const road_hazard_request_t *request,
    road_hazard_severity_t *severity)
{
    if (policy == NULL || request == NULL || request->type == NULL || strcmp(request->type, "road_hazard") != 0 ||
        !integer_in_range(request->version, 1.0, 1.0) ||
        !nonempty_bounded(request->device_id, ROAD_HAZARD_DEVICE_ID_CAPACITY) ||
        !nonempty_bounded(request->boot_id, ROAD_HAZARD_BOOT_ID_CAPACITY) || !event_id_valid(request->event_id) ||
        !identifier_valid(request->camera_id) || !identifier_valid(request->intersection_id) ||
        !identifier_valid(request->message_code) ||
        (strcmp(request->direction != NULL ? request->direction : "", "left") != 0 &&
         strcmp(request->direction != NULL ? request->direction : "", "right") != 0 &&
         strcmp(request->direction != NULL ? request->direction : "", "front") != 0 &&
         strcmp(request->direction != NULL ? request->direction : "", "rear") != 0) ||
        request->object_type == NULL || strcmp(request->object_type, "truck") != 0 ||
        !integer_in_range(request->eta_ms, 1.0, 4294967295.0) || !request->simulated_is_bool ||
        !parse_severity(request->severity, severity)) {
        return ROAD_HAZARD_REJECT_SCHEMA;
    }
    if (strcmp(policy->device_id, request->device_id) != 0) {
        return ROAD_HAZARD_REJECT_DEVICE;
    }
    if (strcmp(policy->boot_id, request->boot_id) != 0) {
        return ROAD_HAZARD_REJECT_BOOT;
    }
    if (!integer_in_range(request->ttl_ms, 1.0, 30000.0)) {
        return ROAD_HAZARD_REJECT_TTL;
    }
    return ROAD_HAZARD_ACCEPTED;
}

static uint64_t hash_bytes(uint64_t hash, const void *data, size_t size)
{
    const unsigned char *bytes = (const unsigned char *)data;
    for (size_t i = 0; i < size; ++i) {
        hash ^= bytes[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}

static uint64_t hash_string(uint64_t hash, const char *value)
{
    hash = hash_bytes(hash, value, strlen(value));
    const unsigned char separator = 0xffU;
    return hash_bytes(hash, &separator, sizeof(separator));
}

static uint64_t fingerprint(const road_hazard_request_t *request)
{
    uint64_t hash = 1469598103934665603ULL;
    hash = hash_string(hash, request->type);
    hash = hash_string(hash, request->device_id);
    hash = hash_string(hash, request->boot_id);
    hash = hash_string(hash, request->event_id);
    hash = hash_string(hash, request->camera_id);
    hash = hash_string(hash, request->intersection_id);
    hash = hash_string(hash, request->message_code);
    hash = hash_string(hash, request->direction);
    hash = hash_string(hash, request->object_type);
    hash = hash_string(hash, request->severity);
    const uint32_t eta = (uint32_t)request->eta_ms;
    hash = hash_bytes(hash, &eta, sizeof(eta));
    return hash_bytes(hash, &request->simulated, sizeof(request->simulated));
}

void road_hazard_policy_init(road_hazard_policy_t *policy, const char *device_id, const char *boot_id)
{
    if (policy == NULL) return;
    memset(policy, 0, sizeof(*policy));
    if (device_id != NULL) snprintf(policy->device_id, sizeof(policy->device_id), "%s", device_id);
    if (boot_id != NULL) snprintf(policy->boot_id, sizeof(policy->boot_id), "%s", boot_id);
}

static void set_outcome(
    road_hazard_outcome_t *outcome,
    const road_hazard_request_t *request,
    road_hazard_result_t result,
    road_hazard_severity_t severity,
    uint32_t remaining)
{
    if (outcome == NULL) return;
    memset(outcome, 0, sizeof(*outcome));
    outcome->accepted = result == ROAD_HAZARD_ACCEPTED || result == ROAD_HAZARD_DUPLICATE;
    outcome->duplicate = result == ROAD_HAZARD_DUPLICATE;
    outcome->expires_in_ms = remaining;
    outcome->severity = severity;
    outcome->error = result;
    if (request != NULL && request->event_id != NULL && strlen(request->event_id) < sizeof(outcome->event_id)) {
        snprintf(outcome->event_id, sizeof(outcome->event_id), "%s", request->event_id);
    }
}

road_hazard_result_t road_hazard_policy_submit(
    road_hazard_policy_t *policy,
    const road_hazard_request_t *request,
    uint64_t now_ms,
    road_hazard_outcome_t *outcome)
{
    road_hazard_severity_t severity = ROAD_HAZARD_SEVERITY_ATTENTION;
    const road_hazard_result_t validation = validate(policy, request, &severity);
    if (validation != ROAD_HAZARD_ACCEPTED) {
        set_outcome(outcome, request, validation, severity, 0U);
        return validation;
    }
    const uint64_t content_fingerprint = fingerprint(request);
    road_hazard_record_t *free_record = NULL;
    for (size_t i = 0; i < ROAD_HAZARD_RECORD_CAPACITY; ++i) {
        road_hazard_record_t *record = &policy->records[i];
        if (!record->used) {
            if (free_record == NULL) free_record = record;
            continue;
        }
        if (strcmp(record->event_id, request->event_id) != 0) continue;
        if (record->fingerprint != content_fingerprint) {
            set_outcome(outcome, request, ROAD_HAZARD_REJECT_EVENT_CONFLICT, severity, 0U);
            return ROAD_HAZARD_REJECT_EVENT_CONFLICT;
        }
        if ((uint32_t)request->ttl_ms > record->initial_ttl_ms) {
            set_outcome(outcome, request, ROAD_HAZARD_REJECT_EVENT_CONFLICT, severity, 0U);
            return ROAD_HAZARD_REJECT_EVENT_CONFLICT;
        }
        if (now_ms >= record->expires_at_ms) {
            set_outcome(outcome, request, ROAD_HAZARD_REJECT_EXPIRED, severity, 0U);
            return ROAD_HAZARD_REJECT_EXPIRED;
        }
        const uint32_t remaining = (uint32_t)(record->expires_at_ms - now_ms);
        set_outcome(outcome, request, ROAD_HAZARD_DUPLICATE, record->severity, remaining);
        return ROAD_HAZARD_DUPLICATE;
    }
    if (free_record == NULL) {
        for (size_t i = 0; i < ROAD_HAZARD_RECORD_CAPACITY; ++i) {
            if (policy->records[i].expiry_emitted) {
                free_record = &policy->records[i];
                break;
            }
        }
    }
    if (free_record == NULL || now_ms > UINT64_MAX - (uint64_t)request->ttl_ms) {
        set_outcome(outcome, request, ROAD_HAZARD_REJECT_CAPACITY, severity, 0U);
        return ROAD_HAZARD_REJECT_CAPACITY;
    }
    *free_record = (road_hazard_record_t){
        .used = true,
        .fingerprint = content_fingerprint,
        .expires_at_ms = now_ms + (uint64_t)request->ttl_ms,
        .initial_ttl_ms = (uint32_t)request->ttl_ms,
        .severity = severity,
    };
    snprintf(free_record->event_id, sizeof(free_record->event_id), "%s", request->event_id);
    set_outcome(outcome, request, ROAD_HAZARD_ACCEPTED, severity, (uint32_t)request->ttl_ms);
    return ROAD_HAZARD_ACCEPTED;
}

bool road_hazard_policy_expire_next(
    road_hazard_policy_t *policy,
    uint64_t now_ms,
    road_hazard_expired_t *expired)
{
    if (policy == NULL || expired == NULL) return false;
    for (size_t i = 0; i < ROAD_HAZARD_RECORD_CAPACITY; ++i) {
        road_hazard_record_t *record = &policy->records[i];
        if (record->used && !record->expiry_emitted && now_ms >= record->expires_at_ms) {
            record->expiry_emitted = true;
            snprintf(expired->event_id, sizeof(expired->event_id), "%s", record->event_id);
            expired->severity = record->severity;
            return true;
        }
    }
    return false;
}

bool road_hazard_policy_highest_active(
    const road_hazard_policy_t *policy,
    uint64_t now_ms,
    road_hazard_severity_t *severity,
    const char **event_id,
    uint32_t *expires_in_ms)
{
    const road_hazard_record_t *best = NULL;
    if (policy == NULL) return false;
    for (size_t i = 0; i < ROAD_HAZARD_RECORD_CAPACITY; ++i) {
        const road_hazard_record_t *record = &policy->records[i];
        if (record->used && now_ms < record->expires_at_ms &&
            (best == NULL || record->severity > best->severity)) {
            best = record;
        }
    }
    if (best == NULL) return false;
    if (severity != NULL) *severity = best->severity;
    if (event_id != NULL) *event_id = best->event_id;
    if (expires_in_ms != NULL) *expires_in_ms = (uint32_t)(best->expires_at_ms - now_ms);
    return true;
}

const char *road_hazard_result_name(road_hazard_result_t result)
{
    static const char *const names[] = {
        "", "", "schema", "device", "boot", "ttl", "event_id_conflict", "expired", "capacity",
    };
    return result >= ROAD_HAZARD_ACCEPTED && result <= ROAD_HAZARD_REJECT_CAPACITY ? names[result] : "schema";
}

const char *road_hazard_severity_name(road_hazard_severity_t severity)
{
    static const char *const names[] = {"attention", "high", "critical"};
    return severity >= ROAD_HAZARD_SEVERITY_ATTENTION && severity <= ROAD_HAZARD_SEVERITY_CRITICAL
               ? names[severity]
               : "attention";
}
