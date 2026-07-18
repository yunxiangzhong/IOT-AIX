from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Render deterministic offscreen dashboard acceptance images")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    window.chain_client.stop()
    window._watchdog_timer.stop()
    try:
        window.scenario_panel.start_requested.disconnect(window.chain_client.send_road_hazard)
    except RuntimeError:
        pass
    app.processEvents()
    state = {
        "type": "chain_state",
        "version": 1,
        "revision": 12,
        "device_id": "aix-helmet-01",
        "boot_id": "0123456789abcdef",
        "upload": {
            "state": "healthy", "last_frame_seq": 128, "fps": 1.0,
            "frame_age_ms": 86, "accepted_frames": 128, "queue_replaced": 0,
        },
        "model": {
            "state": "ready", "name": "DA3-SMALL", "detector": "YOLO26m-COCO",
            "backend": "pytorch-cuda-fp16", "latency_ms": 265.2, "gpu": "cuda",
            "error": "", "valid_results": 127,
        },
        "callback": {
            "state": "confirmed", "latency_ms": 58.0, "attempts": 1,
            "confirmed_count": 127, "failed_count": 0,
        },
        "risk": {
            "valid": True, "score": 68, "band": "high", "reason": "bus_proximity",
            "dominant_class": "bus", "frame_seq": 128,
        },
        "action": {
            "confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz",
            "frame_seq": 128, "stale": False, "e2e_latency_ms": 512,
        },
        "display": {
            "ready": True, "boot_id": "0123456789abcdef", "frame_seq": 128,
            "capture_ts_ms": 128000,
            "detections": [
                {"class_name": "bus", "score": 0.937, "bbox_norm": [0.0, 0.212, 0.998, 0.679], "risk_score": 68},
                {"class_name": "person", "score": 0.955, "bbox_norm": [0.061, 0.370, 0.305, 0.837], "risk_score": 45},
                {"class_name": "person", "score": 0.953, "bbox_norm": [0.826, 0.365, 0.999, 0.816], "risk_score": 42},
            ],
        },
        "last_error": "",
    }
    if not window.dashboard.apply_snapshot(args.image.read_bytes(), 128, 128000, state):
        raise RuntimeError("acceptance snapshot was rejected")
    window.statusBar().showMessage("验收数据 · 本地上位机链路")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for width, height in ((1280, 720), (1440, 900)):
        window.resize(width, height)
        window.show()
        app.processEvents()
        output = args.output_dir / f"dashboard-{width}x{height}.png"
        if not window.grab().save(str(output), "PNG"):
            raise RuntimeError(f"failed to save {output}")

    window.resize(1440, 900)
    window.device_button.setChecked(True)
    app.processEvents()
    device_output = args.output_dir / "device-access-1440x900.png"
    if not window.device_window.grab().save(str(device_output), "PNG"):
        raise RuntimeError(f"failed to save {device_output}")
    window.device_button.setChecked(False)

    window.diagnostics_button.setChecked(True)
    app.processEvents()
    window.dashboard.diagnostics.setCurrentIndex(3)
    diagnostics_output = args.output_dir / "pneumatic-calibration-980x650.png"
    if not window.diagnostics_window.grab().save(str(diagnostics_output), "PNG"):
        raise RuntimeError(f"failed to save {diagnostics_output}")
    window.diagnostics_button.setChecked(False)

    window._show_scenario()
    window.scenario_panel.begin_demo()
    window.scenario_panel._timer.stop()
    window.scenario_panel._update_from_elapsed(1850)
    app.processEvents()
    for width, height in ((1280, 720), (1440, 900)):
        window.resize(width, height)
        app.processEvents()
        output = args.output_dir / f"scenario-progress-{width}x{height}.png"
        if not window.grab().save(str(output), "PNG"):
            raise RuntimeError(f"failed to save {output}")

    event_id = window.scenario_panel.current_event_id
    window.scenario_panel.apply_chain_state({"road_hazard": {
        "event_id": event_id,
        "delivery": {"state": "completed"},
        "ack": {"state": "completed", "payload": {
            "type": "road_hazard_ack", "accepted": True, "event_id": event_id,
        }},
        "network_latency_ms": 42,
        "effective_rgb_pattern": "orange_blink_2hz",
    }})
    # 让验收图展示 ACK 后的语音、气动演示与骑行者减速结果。
    window.scenario_panel._update_from_elapsed(2850)
    window.resize(1440, 900)
    app.processEvents()
    ack_output = args.output_dir / "scenario-ack-1440x900.png"
    if not window.grab().save(str(ack_output), "PNG"):
        raise RuntimeError(f"failed to save {ack_output}")
    window.scenario_panel._update_from_elapsed(window.scenario_panel.EVENT_DURATION_MS)
    app.processEvents()
    arrival_output = args.output_dir / "scenario-arrival-1440x900.png"
    if not window.grab().save(str(arrival_output), "PNG"):
        raise RuntimeError(f"failed to save {arrival_output}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
