# Collision Airbag Host Alert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the conflicting absolute-acceleration rule with collision-grade acceleration-delta detection, safely trigger protective inflation, and provide a persistent silent host SOS alert with auditable event records.

**Architecture:** The MPU detector owns collision classification and exposes both a latched protection state and loss-resistant event metadata. The pneumatic controller remains the sole actuator authority and enforces pressure, calibration, automatic-mode, and pump/valve self-test gates. The PySide6 host parses optional protocol extensions, deduplicates collision events in a pure state helper, presents a non-modal persistent alert, and records append-only lifecycle entries.

**Tech Stack:** C11 host tests, ESP-IDF 5.4.4/FreeRTOS, JSON serial telemetry, Python 3.11, PySide6, `unittest`, PowerShell verification scripts.

---

### Task 1: Replace absolute acceleration detection with collision delta events

**Files:**
- Modify: `AIX/test/motion_detector_test.c`
- Modify: `AIX/main/motion_detector.h`
- Modify: `AIX/main/motion_detector.c`

- [ ] **Step 1: Replace the old impact test with failing boundary, timing, refractory, and latch tests**

Keep the existing `calibrate()` helper, replace `test_two_high_acceleration_samples_latch_impact()`, and extend `main()` with these tests:

```c
static void test_collision_uses_adjacent_acceleration_delta(void)
{
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);

    motion_sample_t sample = stationary_sample();
    motion_output_t output = motion_detector_step(&detector, &sample, 2000);
    assert(!output.impact_event);

    sample.accel_z_g = 2.19f; /* delta 1.19 g */
    output = motion_detector_step(&detector, &sample, 2010);
    assert(!output.impact_event);
    assert(!output.impact);
    output = motion_detector_step(&detector, &sample, 2020);
    assert(!output.impact_event); /* stable high absolute value is not a collision */

    sample.accel_z_g = 0.99f; /* delta 1.20 g */
    output = motion_detector_step(&detector, &sample, 2030);
    assert(output.impact_event);
    assert(output.impact);
    assert(output.impact_count == 1U);
    assert(output.sample_interval_ms == 10U);
    assert(output.accel_delta_g >= 1.199f);
}

static void test_collision_rejects_invalid_interval_and_refreshes_baseline(void)
{
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);
    motion_sample_t sample = stationary_sample();
    motion_detector_step(&detector, &sample, 2000);
    sample.accel_z_g = 2.3f;
    motion_output_t output = motion_detector_step(&detector, &sample, 2021);
    assert(!output.impact_event);
    sample.accel_z_g = 2.4f;
    output = motion_detector_step(&detector, &sample, 2031);
    assert(!output.impact_event);
    sample.accel_z_g = 1.0f;
    output = motion_detector_step(&detector, &sample, 2031); /* dt == 0 */
    assert(!output.impact_event);
    sample.accel_z_g = 2.4f;
    output = motion_detector_step(&detector, &sample, 2020); /* rollback */
    assert(!output.impact_event);
}

static void test_collision_refractory_coalesces_sensor_ringing(void)
{
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);
    motion_sample_t sample = stationary_sample();
    motion_detector_step(&detector, &sample, 2000);
    sample.accel_z_g = 2.3f;
    assert(motion_detector_step(&detector, &sample, 2010).impact_event);
    sample.accel_z_g = 1.0f;
    assert(!motion_detector_step(&detector, &sample, 2020).impact_event);
    sample.accel_z_g = 2.3f;
    assert(motion_detector_step(&detector, &sample, 2220).impact_event);
    assert(detector.impact_count == 2U);
}

static void test_sideways_device_does_not_clear_danger_latch(void)
{
    motion_detector_t detector;
    motion_detector_init(&detector, 0);
    calibrate(&detector, 0);
    motion_sample_t sample = stationary_sample();
    motion_detector_step(&detector, &sample, 2000);
    sample.accel_z_g = 2.3f;
    assert(motion_detector_step(&detector, &sample, 2010).impact);
    motion_sample_t sideways = {.accel_x_g = 1.0f};
    assert(motion_detector_step(&detector, &sideways, 2020).danger_latched);
    assert(motion_detector_step(&detector, &sideways, 7020).danger_latched);
}
```

Keep the existing relative-mount test, but trigger it with one valid delta and verify that returning to the calibrated direction for five continuous seconds clears the latch.

- [ ] **Step 2: Run the focused C test and verify RED**

Run:

```powershell
New-Item -ItemType Directory -Force .test-bin | Out-Null
gcc AIX/main/motion_detector.c AIX/test/motion_detector_test.c -IAIX/main -Wall -Wextra -lm -o .test-bin/motion_detector_test.exe
```

Expected: compilation fails because `impact_event`, `impact_count`, `sample_interval_ms`, and `accel_delta_g` do not exist.

- [ ] **Step 3: Implement the delta detector and restore tilt-safe clearing**

In `motion_detector.h`, replace the old absolute-threshold constants and counter with:

```c
#define MOTION_DETECTOR_IMPACT_DELTA_G 1.2f
#define MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS 20ULL
#define MOTION_DETECTOR_IMPACT_REFRACTORY_MS 200ULL

/* motion_output_t additions */
float accel_delta_g;
uint32_t sample_interval_ms;
bool impact_event;
uint32_t impact_count;

/* motion_detector_t additions */
float previous_accel_norm_g;
uint64_t previous_sample_ms;
uint64_t last_impact_ms;
uint32_t impact_count;
bool has_previous_sample;
```

Delete `MOTION_DETECTOR_IMPACT_THRESHOLD_G`, `MOTION_DETECTOR_IMPACT_SAMPLES`, and `impact_consecutive_samples`. In `motion_detector_step()`:

```c
bool impact_event = false;
float accel_delta_g = 0.0f;
uint32_t sample_interval_ms = 0U;

if (detector->has_previous_sample && now_ms > detector->previous_sample_ms) {
    const uint64_t interval = now_ms - detector->previous_sample_ms;
    if (interval <= MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS) {
        accel_delta_g = fabsf(accel_norm_g - detector->previous_accel_norm_g);
        sample_interval_ms = (uint32_t)interval;
        const bool refractory_complete = detector->impact_count == 0U ||
            now_ms - detector->last_impact_ms >= MOTION_DETECTOR_IMPACT_REFRACTORY_MS;
        if (refractory_complete && accel_delta_g >= MOTION_DETECTOR_IMPACT_DELTA_G) {
            impact_event = true;
            detector->impact_latched = true;
            detector->impact_count++;
            detector->last_impact_ms = now_ms;
            detector->stable_started_ms = 0;
        }
    }
}
detector->previous_accel_norm_g = accel_norm_g;
detector->previous_sample_ms = now_ms;
detector->has_previous_sample = true;
```

Initialize the baseline on the calibration-completing sample, pass the new diagnostic values through `build_output()`, and require `tilt_deg < 30.0f` in the five-second stable-clear condition. Invalid/rollback/over-20-ms intervals refresh the baseline without generating an event.

- [ ] **Step 4: Run the focused C test and verify GREEN**

Run:

```powershell
gcc AIX/main/motion_detector.c AIX/test/motion_detector_test.c -IAIX/main -Wall -Wextra -lm -o .test-bin/motion_detector_test.exe
.\.test-bin\motion_detector_test.exe
```

Expected: `motion_detector_test: PASS` with no compiler warnings.

- [ ] **Step 5: Commit the detector change**

```powershell
git add AIX/main/motion_detector.h AIX/main/motion_detector.c AIX/test/motion_detector_test.c
git commit -m "fix: detect collision acceleration deltas"
```

### Task 2: Make collision telemetry immediate and loss-resistant

**Files:**
- Modify: `AIX/main/mpu6050_sensor.c`
- Modify: `AIX/main/risk_receiver.c`
- Modify: `AIX/test/mpu6050_config_test.c`
- Modify: `scripts/verify.ps1`

- [ ] **Step 1: Add failing source/protocol invariants**

Extend `AIX/test/mpu6050_config_test.c` with compile-time assertions for 100 Hz sampling and the new 20 ms maximum interval. Extend `scripts/verify.ps1` after the MPU C test with exact source invariants:

```powershell
$mpuSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "mpu6050_sensor.c")
if ($mpuSourceText -notmatch 'impact_event' -or
    $mpuSourceText -notmatch 'impact_count' -or
    $mpuSourceText -notmatch 'next\.motion\.impact_event\s*\|\|') {
    throw "MPU collision events must be emitted immediately with a persistent counter"
}
$riskReceiverSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "risk_receiver.c")
if ($riskReceiverSourceText -match 'impact_samples|MOTION_DETECTOR_IMPACT_THRESHOLD_G') {
    throw "pneumatic config endpoint must expose acceleration-delta collision semantics"
}
$pneumaticSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "pneumatic_controller.c")
$collisionFirmwareText = $mpuSourceText + "`n" + $pneumaticSourceText
if ($collisionFirmwareText -match 'voice_prompt|dfplayer') {
    throw "MPU collision and pneumatic paths must remain silent"
}
```

- [ ] **Step 2: Run verification and verify RED**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

Expected: failure containing `MPU collision events must be emitted immediately with a persistent counter` or the obsolete configuration-field error.

- [ ] **Step 3: Extend motion JSON and immediate emission**

In `emit_motion()` add these JSON properties without changing protocol version 2:

```c
"\"accel_norm_g\":%.3f,\"accel_delta_g\":%.3f,\"sample_interval_ms\":%lu,"
"\"impact_event\":%s,\"impact_count\":%lu,\"tilt_deg\":%.2f,\"impact\":%s,"
```

Pass values from `status->motion`. Change the periodic emission gate to:

```c
if (next.motion.impact_event || next.timestamp_ms - last_log_ms >= MPU6050_LOG_PERIOD_MS) {
    emit_motion(&next);
    last_log_ms = next.timestamp_ms;
}
```

In `/pneumatic/config`, replace `impact_g` and `impact_samples` with:

```json
"impact_delta_g": 1.2,
"impact_max_interval_ms": 20,
"impact_refractory_ms": 200
```

- [ ] **Step 4: Run verification and verify GREEN**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

Expected: all host Python and C tests pass, including `mpu6050_config_test`.

- [ ] **Step 5: Commit the telemetry change**

```powershell
git add AIX/main/mpu6050_sensor.c AIX/main/risk_receiver.c AIX/test/mpu6050_config_test.c scripts/verify.ps1
git commit -m "feat: emit reliable collision telemetry"
```

### Task 3: Restrict pneumatic automatic motion triggers to verified collisions

**Files:**
- Modify: `AIX/test/pneumatic_policy_test.c`
- Modify: `AIX/main/pneumatic_policy.h`
- Modify: `AIX/main/pneumatic_policy.c`
- Modify: `AIX/main/pneumatic_controller.h`
- Modify: `AIX/main/pneumatic_controller.c`
- Modify: `scripts/verify.ps1`

- [ ] **Step 1: Add failing pneumatic policy tests**

Add these cases and call them from `main()`:

```c
static void test_collision_inflates_without_fresh_vision(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.vision_fresh = false;
    input.motion_impact = true;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_PRIME_VALVE);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_MPU_IMPACT);
}

static void test_rapid_tilt_is_diagnostic_only(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.motion_rapid_tilt = true;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_VENTED);
    assert(output.trigger_source == PNEUMATIC_TRIGGER_NONE);
}

static void test_collision_respects_common_safety_gate(void)
{
    pneumatic_policy_t policy;
    pneumatic_policy_config_t config = automatic_config();
    pneumatic_policy_init(&policy, &config, 0);
    pneumatic_policy_input_t input = safe_input();
    input.motion_impact = true;
    input.automatic_permitted = false;
    pneumatic_policy_output_t output = pneumatic_policy_step(&policy, &input, 1);
    assert(output.state == PNEUMATIC_STATE_VENTED);
}
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
gcc AIX/main/action_policy.c AIX/main/pneumatic_policy.c AIX/test/pneumatic_policy_test.c -IAIX/main -Wall -Wextra -o .test-bin/pneumatic_policy_test.exe
.\.test-bin\pneumatic_policy_test.exe
```

Expected: `test_rapid_tilt_is_diagnostic_only` aborts because rapid tilt currently starts inflation.

- [ ] **Step 3: Remove rapid tilt from automatic actuation and align pressure limits**

Delete the `motion_rapid_tilt` branch from `current_automatic_trigger()`. Retain `motion_rapid_tilt` in status telemetry for diagnostics. Set `PNEUMATIC_CALIBRATION_CEILING_KPA` to `20.0f`, retain the sensor full-scale constant at 200 kPa, and change the `max_kpa` comment to state that control configuration is capped at 20 kPa.

- [ ] **Step 4: Snapshot readiness flags and commands under one mutex**

In `controller_task()`, move reads of `s_pump_verified`, `s_valve_verified`, `s_self_test_failed`, `s_pending`, and `s_self_test.phase` after `xSemaphoreTake(s_lock, portMAX_DELAY)`. Construct `automatic_permitted` while the lock is held:

```c
xSemaphoreTake(s_lock, portMAX_DELAY);
const bool pump_verified = s_pump_verified;
const bool valve_verified = s_valve_verified;
const bool self_test_failed = s_self_test_failed;
const pneumatic_self_test_phase_t self_test_phase = s_self_test.phase;
const pending_commands_t pending = s_pending;
s_pending = (pending_commands_t){0};

const bool common_automatic_ready = pressure_fresh && pump_verified &&
                                    valve_verified && !self_test_failed;
pneumatic_policy_input_t input = {
    .vision_state = decision.state,
    .vision_fresh = decision.valid && !decision.stale,
    .motion_impact = has_mpu && mpu.motion.impact,
    .motion_rapid_tilt = has_mpu && mpu.motion.rapid_tilt,
    .automatic_permitted = common_automatic_ready,
    .motion_trigger_permitted = has_mpu && mpu.motion.calibrated,
    .pressure_valid = has_pressure && pressure.valid,
    .pressure_kpa = pressure.filtered_kpa,
    .pressure_timestamp_ms = pressure.timestamp_ms,
    .manual_inflate_pulse = pending.inflate_pulse,
    .manual_inflate_duration_ms = self_test_phase != PNEUMATIC_SELF_TEST_IDLE
        ? PNEUMATIC_SELF_TEST_PUMP_MS : PNEUMATIC_CALIBRATION_PULSE_MS,
    .vent_request = pending.vent,
    .emergency_stop = pending.emergency_stop,
    .reset_fault = pending.reset_fault,
};
```

Keep the policy step, self-test update, and `s_status` assignment inside the same critical section. Add `automatic_enabled` to `pneumatic_status_t`, populate it from `s_policy.config.automatic_enabled`, and emit it in `pneumatic_status` JSON.

- [ ] **Step 5: Add a controller lock-order invariant and run tests**

Extend `scripts/verify.ps1` with this lock-order invariant, then run the suite:

```powershell
$controllerTask = [regex]::Match(
    $pneumaticSourceText,
    '(?s)static void controller_task\(.*?\n}\r?\n\r?\nesp_err_t pneumatic_controller_start').Value
$firstLock = $controllerTask.IndexOf('xSemaphoreTake(s_lock, portMAX_DELAY)')
if ([string]::IsNullOrWhiteSpace($controllerTask) -or $firstLock -lt 0) {
    throw "pneumatic controller task or safety mutex was not found"
}
$beforeLock = $controllerTask.Substring(0, $firstLock)
if ($beforeLock -match 's_pump_verified|s_valve_verified|s_self_test_failed|s_pending') {
    throw "pneumatic readiness flags and pending commands must be read under the safety mutex"
}
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

Expected: all tests and source invariants pass.

- [ ] **Step 6: Commit the pneumatic safety change**

```powershell
git add AIX/main/pneumatic_policy.h AIX/main/pneumatic_policy.c AIX/main/pneumatic_controller.h AIX/main/pneumatic_controller.c AIX/test/pneumatic_policy_test.c scripts/verify.ps1
git commit -m "fix: gate collision airbag actuation safely"
```

### Task 4: Parse collision metadata and centralize protection readiness

**Files:**
- Create: `host_app/aix_host_app/collision_state.py`
- Create: `host_app/tests/test_collision_state.py`
- Modify: `host_app/aix_host_app/models.py`
- Modify: `host_app/aix_host_app/parsers.py`
- Modify: `host_app/tests/test_parsers.py`

- [ ] **Step 1: Write failing parser and state tests**

Test both upgraded and old version-2 motion messages. The upgraded case must assert `accel_delta_g == 1.31`, `sample_interval_ms == 10`, `impact_event is True`, and `impact_count == 7`; the old case must assert `impact_event is False` and `impact_count is None`. Add a pneumatic parser assertion for `automatic_enabled`.

Create `test_collision_state.py` with:

```python
def test_counter_deduplicates_heartbeats_and_counts_new_events():
    tracker = CollisionEventTracker()
    assert tracker.observe(motion(seq=10, count=1, event=True)) == 1
    assert tracker.observe(motion(seq=11, count=1, event=False)) == 0
    assert tracker.observe(motion(seq=12, count=3, event=True)) == 2

def test_old_firmware_uses_impact_rising_edge():
    tracker = CollisionEventTracker()
    assert tracker.observe(motion(seq=1, count=None, event=False, impact=False)) == 0
    assert tracker.observe(motion(seq=2, count=None, event=False, impact=True)) == 1
    assert tracker.observe(motion(seq=3, count=None, event=False, impact=True)) == 0

def test_collision_readiness_does_not_require_vision():
    ready = protection_readiness(pneumatic(vision_fresh=False), require_vision=False)
    blocked = protection_readiness(pneumatic(pump_verified=False), require_vision=False)
    assert ready.allowed
    assert not blocked.allowed and "泵自检" in blocked.reason
```

Define the test factories in the same file so every argument is explicit:

```python
from dataclasses import replace

from aix_host_app.collision_state import CollisionEventTracker, protection_readiness
from aix_host_app.models import MotionEvent, PneumaticStatusEvent

def motion(*, seq: int, count: int | None, event: bool, impact: bool = True) -> MotionEvent:
    return MotionEvent(
        seq=seq, ts_ms=seq * 10, speed_mps=0.0, accel_mps2=9.80665,
        speed_valid=False, accel_valid=True, accel_norm_g=1.0,
        tilt_deg=0.0, impact=impact, calibrated=True,
        impact_event=event, impact_count=count,
    )

def pneumatic(**changes) -> PneumaticStatusEvent:
    base = PneumaticStatusEvent(
        ts_ms=1000, state="vented", fault="none", trigger="none", operation=0,
        pump_on=False, valve_on=False, pressure_kpa=5.0, pressure_valid=True,
        pressure_age_ms=20, vision_state="safe", vision_fresh=True,
        mpu_available=True, mpu_calibrated=True, impact=False, rapid_tilt=False,
        pump_verified=True, valve_verified=True, self_test_failed=False,
        automatic_enabled=True,
    )
    return replace(base, **changes)
```

- [ ] **Step 2: Run focused Python tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest host_app.tests.test_parsers host_app.tests.test_collision_state -v
```

Expected: import or attribute failures for the new fields and `collision_state` module.

- [ ] **Step 3: Extend immutable protocol models and optional parsing**

Add these defaults to `MotionEvent`:

```python
accel_delta_g: float | None = None
sample_interval_ms: int | None = None
impact_event: bool = False
impact_count: int | None = None
```

Add `automatic_enabled: bool = False` to `PneumaticStatusEvent`. Parse the new fields with `payload.get("field_name", default_value)` so old firmware remains readable; reject negative `sample_interval_ms` and `impact_count`.

- [ ] **Step 4: Implement the pure tracker and readiness helper**

Create `collision_state.py` with:

```python
from dataclasses import dataclass

from .models import MotionEvent, PneumaticStatusEvent

@dataclass(frozen=True)
class ProtectionReadiness:
    allowed: bool
    reason: str

def protection_readiness(event: PneumaticStatusEvent, *, require_vision: bool) -> ProtectionReadiness:
    failures = []
    if not event.automatic_enabled:
        failures.append("自动模式关闭")
    if not event.pressure_valid or event.pressure_age_ms > 200:
        failures.append("压力无效或过期")
    if not event.pump_verified:
        failures.append("泵自检未通过")
    if not event.valve_verified:
        failures.append("阀自检未通过")
    if event.self_test_failed:
        failures.append("气动自检失败")
    if require_vision and not event.vision_fresh:
        failures.append("视觉结果过期")
    return ProtectionReadiness(not failures, "；".join(failures) if failures else "安全条件有效")

class CollisionEventTracker:
    def __init__(self) -> None:
        self._last_seq: int | None = None
        self._last_count: int | None = None
        self._legacy_impact = False

    def observe(self, event: MotionEvent) -> int:
        rebooted = self._last_seq is not None and event.seq <= self._last_seq
        self._last_seq = event.seq
        if event.impact_count is not None:
            if rebooted or self._last_count is None:
                self._last_count = event.impact_count
                return 1 if event.impact_event else 0
            previous = self._last_count
            self._last_count = event.impact_count
            if event.impact_count == previous:
                return 0
            return max(1, (event.impact_count - previous) & 0xFFFFFFFF)
        detected = event.impact and not self._legacy_impact
        self._legacy_impact = event.impact
        return 1 if detected else 0
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m unittest host_app.tests.test_parsers host_app.tests.test_collision_state -v`

Expected: all focused tests pass.

- [ ] **Step 6: Commit protocol state handling**

```powershell
git add host_app/aix_host_app/models.py host_app/aix_host_app/parsers.py host_app/aix_host_app/collision_state.py host_app/tests/test_parsers.py host_app/tests/test_collision_state.py
git commit -m "feat: parse and deduplicate collision events"
```

### Task 5: Add append-only collision lifecycle recording

**Files:**
- Modify: `host_app/aix_host_app/session_recorder.py`
- Modify: `host_app/tests/test_session_recorder.py`

- [ ] **Step 1: Write the failing recorder test**

Extend the session test:

```python
recorder.record_collision({"event": "detected", "collision_id": "boot-7", "impact_count": 7})
recorder.record_collision({"event": "pneumatic_update", "collision_id": "boot-7", "state": "inflating"})
recorder.record_collision({"event": "acknowledged", "collision_id": "boot-7"})
```

After `close()`, parse `collision_events.jsonl`, assert the three event names are ordered, share one collision ID, and each line has `wall_time`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.\.venv\Scripts\python.exe -m unittest host_app.tests.test_session_recorder -v`

Expected: `AttributeError: 'SessionRecorder' object has no attribute 'record_collision'`.

- [ ] **Step 3: Add the lifecycle stream**

Add `_collisions`, open `collision_events.jsonl` in `start()`, close/reset it in `close()`, and implement:

```python
def record_collision(self, payload: dict[str, Any]) -> None:
    if self._collisions is None:
        return
    self._write_line(
        self._collisions,
        {"wall_time": datetime.now().astimezone().isoformat(), **payload},
    )
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m unittest host_app.tests.test_session_recorder -v`

Expected: all session recorder tests pass.

- [ ] **Step 5: Commit collision recording**

```powershell
git add host_app/aix_host_app/session_recorder.py host_app/tests/test_session_recorder.py
git commit -m "feat: record collision alert lifecycle"
```

### Task 6: Add the persistent silent collision alert and route live pneumatic feedback

**Files:**
- Create: `host_app/aix_host_app/widgets/collision_alert_dialog.py`
- Create: `host_app/tests/test_collision_alert.py`
- Modify: `host_app/aix_host_app/app.py`
- Modify: `host_app/tests/test_app_events.py`

- [ ] **Step 1: Write failing UI and routing tests**

The dialog test must construct the widget offscreen, call `show_collision(event, 1, readiness)`, assert it is visible/non-modal, verify the red collision title, verify a blocked pneumatic reason, call `close()`, and assert it remains visible until the acknowledge button is clicked. The app routing test must feed one upgraded collision line twice and assert one `detected` JSONL record, then feed `impact_count:2` and assert the same visible dialog count becomes two. Patch `chain_client.send_pneumatic_command` with a mock and assert acknowledgement sends no command; also assert the collision handler contains no call to a voice or DFPlayer API.

Use representative upgraded motion input:

```python
collision_line = (
    '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
    '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
    '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
    '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
    '"impact_event":true,"impact_count":1,"tilt_deg":3.0,"impact":true,'
    '"rapid_tilt":false,"danger_latched":true,"calibrated":true,'
    '"speed_mps":0.0,"speed_valid":false}'
)
```

- [ ] **Step 2: Run focused UI tests and verify RED**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m unittest host_app.tests.test_collision_alert host_app.tests.test_app_events -v
```

Expected: import failure for `collision_alert_dialog` or missing `MainWindow.collision_alert`.

- [ ] **Step 3: Implement the non-modal persistent alert dialog**

Create `CollisionAlertDialog(QDialog)` with this complete behavior and no audio API:

```python
from PySide6 import QtCore, QtGui, QtWidgets

from ..collision_state import ProtectionReadiness
from ..models import MotionEvent, PneumaticStatusEvent

class CollisionAlertDialog(QtWidgets.QDialog):
    acknowledged = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)
        self.setWindowTitle("碰撞告警")
        self.setMinimumWidth(520)
        self._allow_close = False
        layout = QtWidgets.QVBoxLayout(self)
        self.title = QtWidgets.QLabel("碰撞告警 · 正在求助")
        self.title.setStyleSheet("font-size: 26px; font-weight: 700; color: #ff4d4f;")
        self.count_label = QtWidgets.QLabel()
        self.collision_detail = QtWidgets.QLabel()
        self.collision_detail.setWordWrap(True)
        self.pneumatic_detail = QtWidgets.QLabel("等待气动状态回传")
        self.pneumatic_detail.setWordWrap(True)
        self.ack_button = QtWidgets.QPushButton("确认已知晓")
        self.ack_button.clicked.connect(self.acknowledge)
        for widget in (self.title, self.count_label, self.collision_detail, self.pneumatic_detail, self.ack_button):
            layout.addWidget(widget)

    def show_collision(
        self,
        event: MotionEvent,
        total_count: int,
        readiness: ProtectionReadiness | None,
    ) -> None:
        self.count_label.setText(f"本次求助期间检测到 {total_count} 次碰撞")
        delta = "--" if event.accel_delta_g is None else f"{event.accel_delta_g:.2f} g"
        interval = "--" if event.sample_interval_ms is None else f"{event.sample_interval_ms} ms"
        self.collision_detail.setText(
            f"设备时间 {event.ts_ms} ms · 加速度 {event.accel_norm_g or 0.0:.2f} g\n"
            f"变化量 {delta} · 样本间隔 {interval} · 倾角 {event.tilt_deg or 0.0:.1f}°"
        )
        if readiness is not None:
            state = "气囊允许执行" if readiness.allowed else "气囊未执行"
            self.pneumatic_detail.setText(f"{state} · {readiness.reason}")
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_pneumatic_status(
        self,
        event: PneumaticStatusEvent,
        readiness: ProtectionReadiness,
    ) -> None:
        state = "允许" if readiness.allowed else "阻塞"
        self.pneumatic_detail.setText(
            f"气动保护{state} · {readiness.reason}\n"
            f"状态 {event.state} · 触发源 {event.trigger} · 故障 {event.fault} · "
            f"压力 {event.pressure_kpa:.2f} kPa"
        )

    def acknowledge(self) -> None:
        self.acknowledged.emit()
        self._allow_close = True
        self.close()
        self._allow_close = False

    def shutdown(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
```

The title-bar close action is ignored until acknowledgement. `shutdown()` exists only so `MainWindow.closeEvent()` can terminate the application cleanly without pretending the user acknowledged the alert.

- [ ] **Step 4: Integrate collision tracking into `MainWindow`**

Initialize `CollisionEventTracker`, `CollisionAlertDialog`, `_active_collision_id`, `_collision_total`, `_latest_pneumatic_status`, and `_last_collision_pneumatic_identity`. On every `MotionEvent`, call `new_events = tracker.observe(event)`. If nonzero:

```python
self._collision_total += new_events
self._active_collision_id = f"motion-{event.ts_ms}-{event.impact_count or event.seq}"
readiness = (
    protection_readiness(self._latest_pneumatic_status, require_vision=False)
    if self._latest_pneumatic_status is not None else None
)
self.collision_alert.show_collision(event, self._collision_total, readiness)
self.session_recorder.record_collision({
    "event": "detected",
    "collision_id": self._active_collision_id,
    "device_ts_ms": event.ts_ms,
    "seq": event.seq,
    "impact_count": event.impact_count,
    "accel_norm_g": event.accel_norm_g,
    "accel_delta_g": event.accel_delta_g,
    "sample_interval_ms": event.sample_interval_ms,
    "tilt_deg": event.tilt_deg,
    "alert_count": self._collision_total,
})
```

On `PneumaticStatusEvent`, store the latest status, update the alert if active, and append `pneumatic_update` only when `(state, fault, trigger, pump_on, valve_on, readiness.allowed, readiness.reason)` changes. Record `automatic_enabled`, pressure validity/age, pump/valve verification, self-test failure, state, trigger, and fault. On acknowledge, append `acknowledged`, set `_active_collision_id = None`, reset `_collision_total = 0`, and clear only host presentation state; do not call any pneumatic or voice method. Call `self.collision_alert.shutdown()` at the start of `MainWindow.closeEvent()` so an unacknowledged tool window cannot keep the process alive.

- [ ] **Step 5: Run focused UI tests and verify GREEN**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m unittest host_app.tests.test_collision_alert host_app.tests.test_app_events -v
```

Expected: tests pass; no pneumatic-command or voice signal is emitted by acknowledgement.

- [ ] **Step 6: Commit the collision alert UI**

```powershell
git add host_app/aix_host_app/app.py host_app/aix_host_app/widgets/collision_alert_dialog.py host_app/tests/test_collision_alert.py host_app/tests/test_app_events.py
git commit -m "feat: show persistent collision help alert"
```

### Task 7: Align dashboard readiness, configuration defaults, and operator documentation

**Files:**
- Modify: `host_app/aix_host_app/widgets/active_dashboard.py`
- Modify: `host_app/aix_host_app/widgets/pneumatic_calibration_panel.py`
- Modify: `host_app/tests/test_active_dashboard.py`
- Modify: `README.md`
- Modify: `AIX/README.md`
- Modify: `host_app/README.md`
- Modify: `docs/hardware/pneumatic-mpu6050-wiring.md`

- [ ] **Step 1: Add failing UI readiness/default tests**

Assert `PneumaticCalibrationPanel().max_inflate_ms.value() == 5000`. Feed `ActiveVisionDashboard.apply_pneumatic_status()` these cases:

1. vision stale but automatic enabled, fresh pressure, and both self-tests verified: collision protection reads `允许`;
2. pump unverified: reads `禁止` and mentions pump self-test;
3. pressure age 201 ms: reads `禁止` and mentions pressure expiration.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m unittest host_app.tests.test_active_dashboard -v`

Expected: default duration assertion fails at 2000 ms and readiness assertions expose the old vision-only gate.

- [ ] **Step 3: Use the shared readiness helper and update displayed MPU configuration**

Set the calibration panel default to 5000 ms. Replace its old `impact_g × impact_samples` text with `impact_delta_g`, `impact_max_interval_ms`, and `impact_refractory_ms`. In `ActiveVisionDashboard.apply_pneumatic_status()`, call `protection_readiness(event, require_vision=False)` for the decision panel's automatic-protection status. Render the shared reason and never require `vision_fresh` for MPU collision readiness. Keep visual-path freshness messaging in the visual chain only.

- [ ] **Step 4: Correct safety documentation without overstating hardware verification**

Update all four documents to state:

- sensor measurement range remains 200 kPa, but software-configurable pneumatic hard cap is 20 kPa;
- defaults are target 8 kPa, max 12 kPa, max inflate 5000 ms;
- MPU automatic inflation is triggered only by `Δ|a| >= 1.2 g` within 20 ms, with 200 ms event coalescing;
- rapid tilt is diagnostic only;
- collision creates a persistent silent local host help alert and event log;
- source tests/build success do not prove the physical airbag works.

Remove claims that MPU `rapid_tilt` inflates and examples recommending a 200 kPa hard limit or 2000 ms maximum inflate setting.

- [ ] **Step 5: Run focused tests and documentation scans**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest host_app.tests.test_active_dashboard -v
rg -n "硬上限.*200 kPa|200\.0 kPa|impact/rapid_tilt|冲击.*×.*samples|max_inflate_ms.*2000" README.md AIX/README.md host_app/README.md docs/hardware/pneumatic-mpu6050-wiring.md
```

Expected: Python tests pass and `rg` returns no obsolete control-limit or trigger claims. Mentions of the XGZP6847A 200 kPa sensor measurement range are allowed only when explicitly contrasted with the 20 kPa software cap.

- [ ] **Step 6: Commit UI and documentation alignment**

```powershell
git add host_app/aix_host_app/widgets/active_dashboard.py host_app/aix_host_app/widgets/pneumatic_calibration_panel.py host_app/tests/test_active_dashboard.py README.md AIX/README.md host_app/README.md docs/hardware/pneumatic-mpu6050-wiring.md
git commit -m "fix: align collision protection status and limits"
```

### Task 8: Full regression and ESP-IDF build verification

**Files:**
- Modify only if verification reveals a task-scope defect in files already listed above.

- [ ] **Step 1: Run whitespace and obsolete-rule checks**

```powershell
git diff --check origin/main...HEAD
rg -n "MOTION_DETECTOR_IMPACT_THRESHOLD_G|MOTION_DETECTOR_IMPACT_SAMPLES|PNEUMATIC_TRIGGER_MPU_RAPID_TILT" AIX/main AIX/test
```

Expected: `git diff --check` is silent. The old motion constants have no matches; the rapid-tilt enum/name may remain for protocol compatibility, but `current_automatic_trigger()` must not return it.

- [ ] **Step 2: Run the complete host and firmware-host test suite**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

Expected: all Python suites, C safety tests, compile checks, and source ownership invariants pass.

- [ ] **Step 3: Run a clean ESP-IDF 5.4.4 runtime build without flashing**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File AIX/sync_runtime_config.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -BuildFirmware
```

Expected: configuration reports `CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL=y` and `CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC=y`; `AIX/build-verify/AIX.bin` and `AIX/build-verify/firmware-manifest.json` are produced. Do not run `idf.py flash` or open a serial port.

- [ ] **Step 4: Inspect final evidence and commit any verification-only adjustment**

```powershell
git status --short --branch
git log --oneline origin/main..HEAD
Get-FileHash AIX/build-verify/AIX.bin -Algorithm SHA256
```

Expected: only intentional source/docs commits are ahead of `origin/main`; generated build outputs remain ignored. If verification required an in-scope correction, rerun the affected focused test and commit only those intentional files with `git add -- <exact paths>`.

- [ ] **Step 5: Report the hardware verification boundary**

Report three distinct results: implemented in source, verified by automated tests/build, and not yet verified on the physical pump/valve/airbag. State explicitly that no board was flashed in this work.
