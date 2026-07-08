#include "vision_detect.h"

#include <stdlib.h>
#include <string.h>

static const char *find_key(const char *line, const char *key)
{
    const char *cursor = line;
    while ((cursor = strstr(cursor, key)) != NULL) {
        const char *after = cursor + strlen(key);
        if (*after == ':' || *after == ' ') {
            return after;
        }
        cursor = after;
    }
    return NULL;
}

static bool parse_u32(const char *line, const char *key, uint32_t *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    char *end = NULL;
    unsigned long v = strtoul(val, &end, 10);
    if (end == val) return false;
    *out = (uint32_t)v;
    return true;
}

static bool parse_float(const char *line, const char *key, float *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    char *end = NULL;
    float v = strtof(val, &end);
    if (end == val) return false;
    *out = v;
    return true;
}

static bool parse_bool(const char *line, const char *key, bool *out)
{
    const char *val = find_key(line, key);
    if (!val) return false;
    while (*val == ':' || *val == ' ') val++;
    if (strncmp(val, "true", 4) == 0) { *out = true; return true; }
    if (strncmp(val, "false", 5) == 0) { *out = false; return true; }
    if (*val == '1') { *out = true; return true; }
    if (*val == '0') { *out = false; return true; }
    return false;
}

bool vision_detect_parse_line(const char *line, vision_detect_result_t *out)
{
    if (!line || !out) return false;
    if (strstr(line, "\"vision_detect\"") == NULL) return false;

    memset(out, 0, sizeof(*out));
    if (!parse_u32(line, "\"seq\"", &out->seq)) return false;
    if (!parse_u32(line, "\"ts_ms\"", &out->ts_ms)) return false;
    if (!parse_float(line, "\"nearest_distance_m\"", &out->nearest_distance_m)) return false;
    if (!parse_float(line, "\"ttc_s\"", &out->ttc_s)) return false;
    if (!parse_bool(line, "\"valid\"", &out->valid)) return false;

    /* Parse source if present */
    const char *src = find_key(line, "\"source\"");
    if (src) {
        while (*src == ':' || *src == ' ') src++;
        if (*src == '"') {
            src++;
            int i = 0;
            while (*src && *src != '"' && i < 31) {
                out->source[i++] = *src++;
            }
            out->source[i] = '\0';
        }
    }

    /* Parse first object's class and distance if present */
    const char *cls = find_key(line, "\"class\"");
    if (cls) {
        while (*cls == ':' || *cls == ' ') cls++;
        if (*cls == '"') {
            cls++;
            int i = 0;
            while (*cls && *cls != '"' && i < 31) {
                out->objects[0].class_name[i++] = *cls++;
            }
            out->objects[0].class_name[i] = '\0';
            out->object_count = 1;
        }
        parse_float(line, "\"confidence\"", &out->objects[0].confidence);
        parse_float(line, "\"distance_m\"", &out->objects[0].distance_m);
        parse_bool(line, "\"approaching\"", &out->objects[0].approaching);
    }

    return true;
}
