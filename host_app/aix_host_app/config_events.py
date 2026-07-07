from __future__ import annotations

import json


def make_pressure_config_line(enabled: bool) -> str:
    payload = {
        "type": "config",
        "version": 1,
        "pressure_enabled": bool(enabled),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
