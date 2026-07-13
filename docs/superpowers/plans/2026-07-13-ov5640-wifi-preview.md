# OV5640 Wi-Fi Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the ESP32-S3 OV5640's latest JPEG in the host app over a Windows 2.4 GHz hotspot and prevent invalid pressure telemetry from appearing as a measurement.

**Architecture:** Firmware copies each completed JPEG into preview-owned memory and serves it after Wi-Fi receives an address. It announces the dynamic URL over serial. The PySide6 host polls at 400 ms and renders the JPEG; pressure widgets gate values/history on `valid`.

**Tech Stack:** ESP-IDF 5.4 (`esp_wifi`, `esp_http_server`, FreeRTOS), PySide6 QtNetwork/QImage, `unittest`, existing PowerShell verification.

## Global Constraints

- Use a 2.4 GHz hotspot; ESP32-S3 cannot use 5 GHz Wi-Fi.
- Keep credentials only in ignored `AIX/sdkconfig.preview`.
- Keep serial telemetry active; request preview only every 400 ms with one request in flight.
- Preview and Depth Anything Wi-Fi uplink are mutually exclusive.
- Do not display, plot, or record a `valid:false` pressure measurement.

---

### Task 1: Gate invalid pressure

**Files:** `AIX/main/pressure_sensor.c`, `host_app/aix_host_app/widgets/pressure_panel.py`, `host_app/aix_host_app/widgets/sensor_overview_panel.py`, `host_app/tests/test_pressure_widgets.py`

**Interfaces:** `PressureSample.valid` produces zero firmware filtered pressure for invalid input, `— kPa` UI text, and no graph-history addition.

- [x] Write a failing widget test: `panel.update_sample(PressureSample(1,1,0,0,0.0,0.4,False,False)); assert panel.value_label.text() == "— kPa"; assert panel.history.latest() is None`.
- [x] Run `python -m unittest host_app.tests.test_pressure_widgets -v`; expect fail because the old panel shows `0.4 kPa` and adds history.
- [x] Calculate voltage validity before the firmware filter; invalid input clears filter readiness, publishes zero filtered pressure, and disables over-pressure. Gate widget graph/history and overview metric on `valid`.
- [x] Run `python -m unittest host_app.tests.test_pressure_widgets -v`; expect pass.

### Task 2: Add firmware Wi-Fi JPEG preview

**Files:** `AIX/main/camera_preview.h`, `AIX/main/camera_preview.c`, `AIX/main/Kconfig.projbuild`, `AIX/main/CMakeLists.txt`, `AIX/main/main.c`, `.gitignore`, `AIX/test/camera_preview_test.c`

**Interfaces:** consume `camera_local_set_frame_consumer(camera_preview_submit_frame, NULL)`; produce `esp_err_t camera_preview_start(void)`, `bool camera_preview_submit_frame(...)`, and `camera_preview` NDJSON with `url`, `ip`, `port`, `valid`, and `reason`.

- [x] Write a failing C test for `camera_preview_make_url(url, sizeof(url), "192.168.137.23", 8080)` yielding `http://192.168.137.23:8080/capture.jpg`.
- [x] Compile it with `gcc AIX/test/camera_preview_test.c AIX/main/camera_preview.c -o .test-bin/camera_preview_test`; expect failure because preview source is absent.
- [x] Add the mutex-protected latest-frame copy, `GET /capture.jpg`, Wi-Fi/IP event, Kconfig, and `esp_http_server` dependency. Make uplink depend on `!AIX_ENABLE_CAMERA_PREVIEW` and attach preview consumer before camera start.
- [x] Run C test and `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`; expect zero exit code.

### Task 3: Route and render Wi-Fi frames in the host

**Files:** `host_app/aix_host_app/models.py`, `host_app/aix_host_app/parsers.py`, `host_app/aix_host_app/app.py`, `host_app/aix_host_app/widgets/vision_panel.py`, `host_app/tests/test_parsers.py`, `host_app/tests/test_app_events.py`

**Interfaces:** parser produces `CameraPreviewEvent`; application calls `VisionPanel.update_camera_preview(event)`; panel owns 400 ms single-flight `QNetworkAccessManager` polling.

- [x] Write failing parser/routing tests using a valid `camera_preview` JSON event with `/capture.jpg` URL.
- [x] Run `python -m unittest host_app.tests.test_parsers host_app.tests.test_app_events -v`; expect fail because the type is unsupported.
- [x] Parse/rout the event, add preview card with waiting/error states, decode `QImage.fromData`, and scale with `KeepAspectRatio`. Do not change serial-health state for HTTP errors.
- [x] Run `python -m unittest discover -s host_app/tests -v`; expect pass.

### Task 4: Configure, build, flash, and verify

**Files:** ignored `AIX/sdkconfig.preview`, `README.md`

- [x] Add local-only `CONFIG_AIX_ENABLE_CAMERA_PREVIEW=y`, SSID, and password to ignored `AIX/sdkconfig.preview`.
- [x] Build/flash `idf.py -B build-wifi-preview build flash -p COM21`; expect a verified flash.
- [x] Confirm serial emits a `camera_preview` URL and the host right panel renders current OV5640 images while disconnected pressure shows `— kPa` and raw/mV diagnostics.
