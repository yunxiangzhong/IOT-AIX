# Real Feedback Cleanup Implementation Plan

> **For agentic workers:** Execute each task with tests first and verify every claimed result. Do not flash hardware in this plan.

**Goal:** Remove runtime simulation and fabricated feedback from the production path while retaining regression tests and real hardware diagnostics.

**Architecture:** Formal-mode inputs reject simulated road-hazard events at both the PC service and firmware boundaries. The host application exposes only the real dashboard and only renders action results after authoritative ESP32 telemetry. Startup reuses a vision service only when its health response proves the expected real model and GPU backend are ready.

**Tech Stack:** Python 3, PySide6, FastAPI, ESP-IDF C, PowerShell, unittest, native C test executables.

**Constraints:** Do not flash a board. Do not modify the collision-airbag design or plan. Keep source tests and the physical pneumatic self-test. Delete only demo runtime paths and generated/stale artifacts.

---

### Task 1: Reject simulated road-hazard events

**Files:**

- Modify: `Models/DepthAnything3/service/tests/test_road_hazard.py`
- Modify: `Models/DepthAnything3/service/road_hazard.py`
- Modify: `AIX/test/road_hazard_policy_test.c`
- Modify: `AIX/test/alert_arbiter_test.c`
- Modify: `AIX/main/road_hazard_policy.c`

1. Add tests proving `simulated=true` is rejected and real payloads remain accepted.
2. Run the focused Python and C tests and record the expected failures.
3. Add boundary validation in both implementations.
4. Rerun the focused tests and confirm they pass.

### Task 2: Remove host runtime simulation and fabricated feedback

**Files:**

- Modify: `host_app/tests/test_cooperative_warning_ui.py`
- Modify: `host_app/tests/test_active_dashboard.py`
- Modify: `host_app/aix_host_app/app.py`
- Modify: `host_app/aix_host_app/widgets/active_dashboard.py`
- Modify: `host_app/aix_host_app/chain_client.py`
- Modify: `Models/DepthAnything3/service/frame_pipeline.py`
- Delete: `host_app/aix_host_app/widgets/cooperative_scenario.py`
- Delete: `host_app/render_acceptance.py`

1. Add tests for a single real dashboard page, no demo scene, and no unconfirmed pneumatic/RGB result.
2. Run the focused tests and record the expected failures.
3. Remove the cooperative demo sender/page and update dashboard wording to explicit waiting/threshold states.
4. Keep real road-hazard status recording and real voice/pneumatic telemetry handling.
5. Rerun the focused tests.

### Task 3: Require real vision readiness at startup

**Files:**

- Modify: `host_app/tests/test_launcher_scripts.py`
- Modify: `host_app/start_stack.ps1`

1. Add launcher assertions for model readiness, GPU, backend, and expected model identity.
2. Run the focused test and record the expected failure.
3. Tighten the health check so stale/test services are not reused.
4. Rerun the focused test.

### Task 4: Clean artifacts and verify without flashing

**Generated targets:**

- Remove stale `AIX/build*` directories identified by the audit.
- Remove `.test-bin` and `vision_detect_test.exe` after verification.

1. Resolve every deletion target to an absolute path under the repository.
2. Delete only the audited generated targets.
3. Run `scripts/verify.ps1` for the complete source test suite.
4. Run `scripts/verify.ps1 -BuildFirmware` to produce a fresh, attributable firmware candidate from the current HEAD and actual runtime configuration.
5. Inspect the generated manifest and `sdkconfig`; do not flash.
6. Remove transient test executables and report source-tested, build-verified, and hardware-unverified states separately.
