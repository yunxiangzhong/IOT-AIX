# OV5640 Wi-Fi Preview Design

## Goal

Keep the existing COM21 serial telemetry path, let the ESP32-S3 join the Windows mobile hotspot, and show the latest OV5640 JPEG frame in the desktop host application.

## Confirmed constraints

- ESP32-S3 connects only to a 2.4 GHz Wi-Fi network.
- Hotspot credentials are local-only in ignored `AIX/sdkconfig.preview`; source, docs, and tracked configs contain no credentials.
- Camera capture stays QVGA JPEG at 5 FPS. The host polls only the newest frame every 400 ms, with one request in flight.
- Firmware serves `GET /capture.jpg` on port 8080 and emits an additive `camera_preview` NDJSON event after it receives an IP address.
- Preview and the existing Depth Anything Wi-Fi uplink are mutually exclusive: both own Wi-Fi initialization and camera currently has one frame consumer.
- Invalid pressure (`valid:false`) is diagnostic-only: raw and mV remain visible, but no filtered kPa is displayed, plotted, or used for over-pressure.

## Firmware design

`camera_preview.c` owns Wi-Fi station setup, a mutex-protected copy of the newest JPEG, and the HTTP server. Its frame consumer copies the JPEG before the camera buffer is released. The handler copies the saved JPEG while holding the mutex, so it never accesses a released camera framebuffer. Empty SSID leaves preview unavailable without preventing normal local capture.

## Desktop design

`CameraPreviewEvent` carries the dynamic endpoint URL. `VisionPanel` owns a `QNetworkAccessManager` and 400 ms timer, decodes JPEG replies with `QImage.fromData`, and letterboxes them in a warm off-white preview card. HTTP failures change preview copy only, never the OV5640 serial-health state.

## Verification

- Parser and offscreen widget tests cover URL routing, invalid pressure display, and absent invalid plot history.
- A firmware host-side C test covers URL formatting.
- `scripts/verify.ps1` and an ESP-IDF build verify integration before flashing.
