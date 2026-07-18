# Traffic Vision Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy YOLO26m on the local RTX 4060 and make the one-frame-per-second OV5640/ESP32/PC loop and PySide dashboard stable and frame-consistent.

**Architecture:** DA3-SMALL supplies coarse relative depth while YOLO26m supplies traffic semantics. The service commits an analyzed snapshot only after inference, the host renders that snapshot and its state atomically, and the ESP32 reports capture-to-ACK latency.

**Tech Stack:** Python 3.10, PyTorch CUDA 12.6, Ultralytics YOLO26, TensorRT FP16, FastAPI, PySide6, ESP-IDF C.

## Global Constraints

- Keep every model asset under `Models/DepthAnything3`.
- Runtime upload interval is 1000ms and processed-frame identity is authoritative for display.
- Use test-first red/green cycles for every behavior change.
- Do not claim the real ESP32 latency target without a real board measurement.

---

### Task 1: Stable detector and risk algorithm

**Files:**
- Modify: `Models/DepthAnything3/service/inference.py`
- Modify: `Models/DepthAnything3/service/server.py`
- Test: `Models/DepthAnything3/service/tests/test_risk.py`
- Test: `Models/DepthAnything3/service/tests/test_yolo_detector.py`

**Interfaces:**
- Produces `Yolo26Detector.detect_jpeg(bytes) -> list[DetectionSummary]`.
- Produces `RiskTracker.update(raw_score, emergency=False) -> tuple[int, str]` with two-frame escalation and three-frame de-escalation.
- `VisionAnalyzer.warmup()` completes before model readiness.

- [x] Add failing detector parsing/filter tests and temporal-risk regression tests; run each focused test and confirm the missing behavior fails.
- [x] Implement YOLO26m CUDA/TensorRT loading, DA3 process resolution 280, warmup, traffic-only risk scoring, EMA/hysteresis/confirmation, and model metadata.
- [x] Run all service unit tests and keep response score/band consistency.

### Task 2: Processed snapshot and latency protocol

**Files:**
- Modify: `Models/DepthAnything3/service/frame_pipeline.py`
- Modify: `Models/DepthAnything3/service/app.py`
- Modify: `Models/DepthAnything3/service/schemas.py`
- Test: `Models/DepthAnything3/service/tests/test_frame_pipeline.py`
- Test: `Models/DepthAnything3/service/tests/test_app.py`

**Interfaces:**
- Adds `LatestFrameStore.commit_processed(frame)` and `latest_processed(device_id)`.
- Adds `GET /v1/frame/processed.jpg` and `chain_state.display` containing boot/frame/capture identity plus detections.
- Accepts `action_ack.e2e_latency_ms` and exposes it in callback state.

- [x] Add failing tests proving uploaded frames are not displayed before analysis and processed headers match risk identity.
- [x] Implement processed snapshot commit before state publication, state revisions, detection payload storage, and E2E ACK validation.
- [x] Run focused API/pipeline tests, then the whole service suite.

### Task 3: Atomic stable PySide display

**Files:**
- Create: `host_app/aix_host_app/widgets/vision_canvas.py`
- Modify: `host_app/aix_host_app/chain_client.py`
- Modify: `host_app/aix_host_app/widgets/active_dashboard.py`
- Modify: `host_app/aix_host_app/app.py`
- Test: `host_app/tests/test_vision_canvas.py`
- Test: `host_app/tests/test_active_dashboard.py`
- Test: `host_app/tests/test_chain_client.py`

**Interfaces:**
- `VisionCanvas.set_snapshot(jpeg: bytes, detections: list[dict]) -> bool` paints a stable letterboxed image and Chinese overlays.
- `PcChainClient.snapshot_received(bytes, int, int, dict)` carries one immutable state snapshot with its processed JPEG.
- `ActiveVisionDashboard.apply_snapshot(...)` is the only method that updates the main risk card.

- [x] Add failing tests for constant size hints, processed identity selection, stale serial action rejection, and action events not changing risk UI.
- [x] Implement the paint widget, atomic state/frame routing, revision coalescing, and diagnostic log throttling.
- [x] Run all host tests and render 1280x720 plus 1440x900 screenshots for inspection.

### Task 4: ESP32 1Hz loop and full latency

**Files:**
- Modify: `AIX/sdkconfig.defaults`
- Modify: `AIX/main/Kconfig.projbuild`
- Modify: `AIX/main/vision_uplink.c`
- Modify: `AIX/main/risk_receiver.c`
- Test: `AIX/test/vision_uplink_test.c`
- Test: `AIX/test/risk_receiver_test.c`

**Interfaces:**
- Default `CONFIG_AIX_VISION_UPLOAD_PERIOD_MS=1000`.
- `action_ack` includes non-negative `e2e_latency_ms` computed as `now_ms - capture_ts_ms`.

- [x] Add host-compiled failing tests for 1000ms configuration and E2E latency boundary handling.
- [x] Implement the configuration and ACK field without changing the 3000ms safety TTL.
- [x] Run host C tests and an ESP-IDF build in the native toolchain environment if available.

### Task 5: Local deployment and acceptance

**Files:**
- Modify: `Models/DepthAnything3/install.ps1`
- Modify: `Models/DepthAnything3/run_service.ps1`
- Modify: `Models/DepthAnything3/install_manifest.json` generation
- Modify: `Models/DepthAnything3/README.md`
- Modify: `host_app/README.md`
- Modify: `README.md`

**Interfaces:**
- `install.ps1` installs/pins Ultralytics dependencies, downloads official `yolo26m.pt`, exports `yolo26m.engine` for the local GPU, and records hashes/backend.
- Service prefers `.engine`, falls back only to CUDA FP16 `.pt`, and reports both model names/backend in `/healthz`.

- [x] Add script/content tests before changing installer and launcher behavior.
- [x] Install under `Models/DepthAnything3/weights/YOLO26m`, attempt TensorRT export, retain the verified CUDA FP16 `.pt` fallback, and run a 30-frame warmed benchmark with mean/P95/max and VRAM output.
- [x] Run `scripts/verify.ps1`, focused real-model tests, `git diff --check`, and inspect final screenshots and repository status.
