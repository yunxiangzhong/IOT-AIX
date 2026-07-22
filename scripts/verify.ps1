[CmdletBinding()]
param(
    [switch]$BuildFirmware
)

$ErrorActionPreference = "Stop"

$projectRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
. (Join-Path $PSScriptRoot "runtime_paths.ps1")
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
$runtimeRoot = Resolve-AixRuntimeRoot -ProjectRoot $projectRoot -GitCommonDir $commonGitDir
$python = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
$hostApp = Join-Path $projectRoot "host_app"
$aix = Join-Path $projectRoot "AIX"
$main = Join-Path $aix "main"
$testBin = Join-Path $projectRoot ".test-bin"
$cameraKconfig = Join-Path $main "Kconfig.projbuild"
$cameraSource = Join-Path $main "camera_local.c"
$cameraPreview = Join-Path $main "camera_preview.c"
$runtimeSync = Join-Path $aix "sync_runtime_config.ps1"
$modelRoot = Join-Path $runtimeRoot "Models\DepthAnything3"
$modelService = Join-Path $projectRoot "Models\DepthAnything3\service"
$modelPython = Join-Path $modelRoot "env\python.exe"

if (-not (Test-Path -LiteralPath $cameraKconfig)) {
    throw "Missing ESP-IDF component configuration: $cameraKconfig"
}

$cameraSourceText = Get-Content -Raw -LiteralPath $cameraSource
if ($cameraSourceText -notmatch '(?s)#if CONFIG_SPIRAM.*esp_psram_is_initialized.*#else.*psram_enabled = false.*#endif') {
    throw "camera_local.c must not reference esp_psram_is_initialized when CONFIG_SPIRAM is disabled"
}
if (-not (Test-Path -LiteralPath $cameraPreview)) {
    throw "Missing camera preview source: $cameraPreview"
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing project virtual environment: $python"
}

$gcc = Get-Command gcc -ErrorAction SilentlyContinue
if ($null -eq $gcc) {
    throw "gcc was not found in PATH. Install MinGW-w64 or run from a configured development shell."
}

function Invoke-Checked {
    param([string]$Description, [scriptblock]$Command)

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Invoke-HostCTest {
    param(
        [string]$Name,
        [string[]]$Sources,
        [string[]]$Libraries = @()
    )

    $output = Join-Path $testBin "$Name.exe"
    Invoke-Checked "Compile $Name" {
        & $gcc.Source @Sources "-I$main" -Wall -Wextra @Libraries -o $output
    }
    Invoke-Checked "Run $Name" {
        & $output
    }
}

Invoke-Checked "Python unit tests" {
    Push-Location $hostApp
    try {
        & $python -m unittest discover -s tests -v
    } finally {
        Pop-Location
    }
}

Invoke-Checked "Python compileall" {
    Push-Location $hostApp
    try {
        & $python -m compileall -q aix_host_app tests
    } finally {
        Pop-Location
    }
}

if (Test-Path -LiteralPath $modelPython) {
    Invoke-Checked "Depth Anything service tests" {
        Push-Location $modelService
        try {
            & $modelPython -m unittest discover -s tests -v
        } finally {
            Pop-Location
        }
    }
} else {
    Write-Warning "Skipping DA3 service tests because the local model environment is missing: $modelPython"
}

New-Item -ItemType Directory -Force -Path $testBin | Out-Null

Invoke-HostCTest "pressure_sensor_math_test" @(
    (Join-Path $aix "test\pressure_sensor_math_test.c")
) @("-lm")
Invoke-HostCTest "camera_local_test" @(
    (Join-Path $main "camera_local.c"),
    (Join-Path $aix "test\camera_local_test.c")
)
Invoke-HostCTest "camera_preview_test" @(
    (Join-Path $main "camera_preview.c"),
    (Join-Path $aix "test\camera_preview_test.c")
)
Invoke-HostCTest "camera_board_profile_test" @(
    (Join-Path $aix "test\camera_board_profile_test.c")
)
Invoke-HostCTest "action_policy_test" @(
    (Join-Path $main "action_policy.c"),
    (Join-Path $aix "test\action_policy_test.c")
)
Invoke-HostCTest "voice_prompt_test" @(
    (Join-Path $main "dfplayer.c"),
    (Join-Path $main "voice_prompt.c"),
    (Join-Path $aix "test\voice_prompt_test.c")
)
Invoke-HostCTest "vision_uplink_test" @(
    (Join-Path $main "vision_uplink.c"),
    (Join-Path $aix "test\vision_uplink_test.c")
)
Invoke-HostCTest "risk_receiver_test" @(
    (Join-Path $main "risk_receiver.c"),
    (Join-Path $aix "test\risk_receiver_test.c")
)
Invoke-HostCTest "road_hazard_policy_test" @(
    (Join-Path $main "road_hazard_policy.c"),
    (Join-Path $aix "test\road_hazard_policy_test.c")
) @("-lm")
Invoke-HostCTest "alert_arbiter_test" @(
    (Join-Path $main "action_policy.c"),
    (Join-Path $main "road_hazard_policy.c"),
    (Join-Path $main "alert_arbiter.c"),
    (Join-Path $aix "test\alert_arbiter_test.c")
) @("-lm")
Invoke-HostCTest "pneumatic_policy_test" @(
    (Join-Path $main "action_policy.c"),
    (Join-Path $main "pneumatic_policy.c"),
    (Join-Path $aix "test\pneumatic_policy_test.c")
)
Invoke-HostCTest "motion_detector_test" @(
    (Join-Path $main "motion_detector.c"),
    (Join-Path $aix "test\motion_detector_test.c")
) @("-lm")
Invoke-HostCTest "mpu6050_config_test" @(
    (Join-Path $aix "test\mpu6050_config_test.c")
)

function Remove-CComments {
    param([string]$Text)

    $withoutBlockComments = [regex]::Replace($Text, '(?s)/\*.*?\*/', '')
    return [regex]::Replace($withoutBlockComments, '(?m)//.*$', '')
}

$mpuSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "mpu6050_sensor.c")
$mpuCodeText = Remove-CComments $mpuSourceText
$emitMotionMatch = [regex]::Match(
    $mpuCodeText,
    '(?s)static void emit_motion\([^)]*\)\s*(\{.*?\})\s*static esp_err_t read_sample')
$emitMotionBody = $emitMotionMatch.Groups[1].Value
$motionTelemetryMappingPattern = '(?s)printf\s*\(.*?' +
    '\\?"accel_delta_g\\?"\s*:\s*%\.3f.*?' +
    '\\?"sample_interval_ms\\?"\s*:\s*%lu.*?' +
    '\\?"impact_event\\?"\s*:\s*%s.*?' +
    '\\?"impact_count\\?"\s*:\s*%lu.*?' +
    'status->motion\.accel_delta_g\s*,\s*' +
    '\(unsigned long\)\s*status->motion\.sample_interval_ms\s*,\s*' +
    'status->motion\.impact_event\s*\?\s*"true"\s*:\s*"false"\s*,\s*' +
    '\(unsigned long\)\s*status->motion\.impact_count\b'
if ([string]::IsNullOrWhiteSpace($emitMotionBody) -or
    $emitMotionBody -notmatch $motionTelemetryMappingPattern) {
    throw "emit_motion must preserve collision JSON field-to-argument ordering"
}

$mpuTaskMatch = [regex]::Match(
    $mpuCodeText,
    '(?s)static void mpu6050_task\([^)]*\)\s*(\{.*?\})\s*static esp_err_t configure_mpu6050')
$mpuTaskBody = $mpuTaskMatch.Groups[1].Value
$impactEmitBlockMatch = [regex]::Match(
    $mpuTaskBody,
    '(?s)if\s*\(\s*next\.motion\.impact_event\s*\|\|.*?\)\s*(\{.*?\})')
$impactEmitBlock = $impactEmitBlockMatch.Groups[1].Value
if ([string]::IsNullOrWhiteSpace($mpuTaskBody) -or
    [string]::IsNullOrWhiteSpace($impactEmitBlock) -or
    $impactEmitBlock -notmatch 'emit_motion\s*\(\s*&next\s*\)\s*;' -or
    $impactEmitBlock -notmatch 'last_log_ms\s*=\s*next\.timestamp_ms\s*;') {
    throw "MPU collision events must be emitted immediately with a persistent counter"
}

$riskReceiverSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "risk_receiver.c")
$riskReceiverCodeText = Remove-CComments $riskReceiverSourceText
$pneumaticConfigMatch = [regex]::Match(
    $riskReceiverCodeText,
    '(?s)static esp_err_t pneumatic_config_handler\([^)]*\)\s*(\{.*?\})\s*esp_err_t risk_receiver_start')
$pneumaticConfigBody = $pneumaticConfigMatch.Groups[1].Value
$collisionConfigJsonPattern = '(?s)\\?"impact_delta_g\\?"\s*:\s*%\.1f.*?' +
    '\\?"impact_max_interval_ms\\?"\s*:\s*%llu.*?' +
    '\\?"impact_refractory_ms\\?"\s*:\s*%llu'
$collisionConfigConstantsPattern = '(?s)\bMOTION_DETECTOR_IMPACT_DELTA_G\b\s*,\s*' +
    '\(unsigned long long\)\s*MOTION_DETECTOR_IMPACT_MAX_INTERVAL_MS\b\s*,\s*' +
    '\(unsigned long long\)\s*MOTION_DETECTOR_IMPACT_REFRACTORY_MS\b'
$legacyCollisionConfigPattern = '\\?"impact_g\\?"\s*:|\\?"impact_samples\\?"\s*:|' +
    '\bMOTION_DETECTOR_IMPACT_THRESHOLD_G\b'
if ([string]::IsNullOrWhiteSpace($pneumaticConfigBody) -or
    $pneumaticConfigBody -notmatch $collisionConfigJsonPattern -or
    $pneumaticConfigBody -notmatch $collisionConfigConstantsPattern -or
    $pneumaticConfigBody -match $legacyCollisionConfigPattern) {
    throw "pneumatic config endpoint must expose acceleration-delta collision semantics"
}
$pneumaticSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "pneumatic_controller.c")
$collisionFirmwareText = $mpuSourceText + "`n" + $pneumaticSourceText
if ($collisionFirmwareText -match 'voice_prompt|dfplayer') {
    throw "MPU collision and pneumatic paths must remain silent"
}
$pneumaticCodeText = Remove-CComments $pneumaticSourceText
function Get-CFunctionRange {
    param(
        [string]$CodeText,
        [string]$StartPattern,
        [string]$FollowingPattern,
        [string]$Description
    )

    $match = [regex]::Match($CodeText, "(?s)$StartPattern.*?(?=\s*$FollowingPattern)")
    if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Value)) {
        throw "Unable to extract $Description from comment-free C source"
    }
    return $match.Value
}

function Assert-PatternsInOrder {
    param(
        [string]$Text,
        [string[]]$Patterns,
        [string]$Description
    )

    $cursor = 0
    foreach ($pattern in $Patterns) {
        $match = [regex]::Match($Text.Substring($cursor), $pattern)
        if (-not $match.Success) {
            throw "$Description is missing or out of order: $pattern"
        }
        $cursor += $match.Index + $match.Length
    }
}

function Assert-PneumaticControllerInvariants {
    param([string]$SourceText)

    $codeText = Remove-CComments $SourceText
    $controllerTaskBody = Get-CFunctionRange `
        -CodeText $codeText `
        -StartPattern 'static void controller_task\([^)]*\)\s*\{' `
        -FollowingPattern 'esp_err_t pneumatic_controller_start\s*\(' `
        -Description 'controller_task'
    $firstLock = [regex]::Match($controllerTaskBody, 'xSemaphoreTake\s*\(\s*s_lock\s*,[^;]*;')
    if (-not $firstLock.Success) {
        throw "controller_task must take s_lock"
    }
    $beforeFirstLock = $controllerTaskBody.Substring(0, $firstLock.Index)
    $unsafeSharedReadPattern = '\bs_(?:pump_verified|valve_verified|self_test_failed|pending)\b|' +
                               '\bs_self_test\s*\.\s*phase\b'
    if ($beforeFirstLock -match $unsafeSharedReadPattern) {
        throw "controller_task must not read shared pneumatic safety state before taking s_lock"
    }
    $afterFirstLock = $controllerTaskBody.Substring($firstLock.Index)
    $firstUnlock = [regex]::Match($afterFirstLock, 'xSemaphoreGive\s*\(\s*s_lock\s*\)\s*;')
    if (-not $firstUnlock.Success) {
        throw "controller_task must release its first s_lock region"
    }
    $lockedBody = $afterFirstLock.Substring(0, $firstUnlock.Index + $firstUnlock.Length)

    $commonReadyPattern = '\bconst\s+bool\s+common_automatic_ready\s*=\s*pressure_fresh\s*;'
    $statusAssignmentPattern = '(?s)\bs_status\s*=\s*\(\s*pneumatic_status_t\s*\)\s*\{' +
        '.*?\.config\s*=.*?\.output\s*=.*?\.pressure_kpa\s*=.*?\.pressure_raw_valid\s*=' +
        '.*?\.pressure_valid\s*=.*?\.pressure_age_ms\s*=.*?\.vision_state\s*=' +
        '.*?\.vision_fresh\s*=.*?\.mpu_available\s*=.*?\.mpu_calibrated\s*=' +
        '.*?\.mpu_impact\s*=.*?\.mpu_rapid_tilt\s*=.*?\.pump_verified\s*=' +
        '.*?\.valve_verified\s*=.*?\.self_test_failed\s*=.*?\.automatic_enabled\s*=' +
        '.*?\.timestamp_ms\s*=.*?\}\s*;'
    Assert-PatternsInOrder -Text $lockedBody -Description 'controller_task first s_lock region' -Patterns @(
        'xSemaphoreTake\s*\(\s*s_lock\s*,[^;]*;',
        '\bconst\s+pneumatic_self_test_phase_t\s+self_test_phase\s*=\s*s_self_test\s*\.\s*phase\s*;',
        '\bconst\s+pending_commands_t\s+pending\s*=\s*s_pending\s*;',
        '\bs_pending\s*=\s*\(\s*pending_commands_t\s*\)\s*\{\s*0\s*\}\s*;',
        $commonReadyPattern,
        '\bpneumatic_policy_step\s*\(',
        '\bupdate_self_test\s*\(',
        $statusAssignmentPattern,
        '\bconst\s+pneumatic_status_t\s+current\s*=\s*s_status\s*;',
        '\bset_outputs\s*\(\s*output\.pump_on\s*,\s*output\.valve_on\s*\)\s*;',
        'xSemaphoreGive\s*\(\s*s_lock\s*\)\s*;'
    )

    $emitStatusBody = Get-CFunctionRange `
        -CodeText $codeText `
        -StartPattern 'static void emit_status\([^)]*\)\s*\{' `
        -FollowingPattern 'static void update_self_test\s*\(' `
        -Description 'emit_status'
    $automaticEnabledMappingPattern = '(?s)\\?"self_test_failed\\?"\s*:\s*%s\s*,\s*' +
        '\\?"automatic_enabled\\?"\s*:\s*%s\s*,.*?' +
        '\\?"vision_state\\?"\s*:\s*\\?"%s\\?".*?' +
        'status->self_test_failed\s*\?\s*"true"\s*:\s*"false"\s*,\s*' +
        'status->automatic_enabled\s*\?\s*"true"\s*:\s*"false"\s*,\s*' +
        'action_state_name\s*\(\s*status->vision_state\s*\)'
    if ($emitStatusBody -notmatch $automaticEnabledMappingPattern) {
        throw "pneumatic_status automatic_enabled JSON placeholder must map to its matching printf argument"
    }

    $executeBody = Get-CFunctionRange `
        -CodeText $codeText `
        -StartPattern 'esp_err_t pneumatic_controller_execute\s*\([^)]*\)\s*\{' `
        -FollowingPattern '#endif' `
        -Description 'pneumatic_controller_execute'
    $executeLock = [regex]::Match($executeBody, 'xSemaphoreTake\s*\(\s*s_lock\s*,[^;]*;')
    $emergencyCase = [regex]::Match(
        $executeBody,
        '(?s)case\s+PNEUMATIC_COMMAND_EMERGENCY_STOP\s*:(.*?\bbreak\s*;)')
    if (-not $executeLock.Success -or -not $emergencyCase.Success -or
        $executeLock.Index -ge $emergencyCase.Index) {
        throw "emergency-stop command must execute after pneumatic_controller_execute takes s_lock"
    }
    $emergencyBody = $emergencyCase.Groups[1].Value
    $emergencyBarrierFirstPattern = '^\s*\{\s*s_pending\s*=\s*\(\s*pending_commands_t\s*\)\s*\{\s*0\s*\}\s*;'
    if ($emergencyBody -notmatch $emergencyBarrierFirstPattern -or
        $emergencyBody -match 'xSemaphoreGive\s*\(' -or
        $emergencyBody -match '\bs_pending\s*\.\s*emergency_stop\b' -or
        $emergencyBody -match '\bs_status\s*\.\s*output\s*\.\s*(?:state|fault|pump_on|valve_on)\s*=') {
        throw "emergency-stop command must use real policy output under the existing lock"
    }
    Assert-PatternsInOrder -Text $emergencyBody -Description 'emergency-stop command lock region' -Patterns @(
        '\bs_pending\s*=\s*\(\s*pending_commands_t\s*\)\s*\{\s*0\s*\}\s*;',
        '\bconst\s+uint64_t\s+emergency_timestamp_ms\s*=\s*now_ms\s*\(\s*\)\s*;',
        '(?s)\bconst\s+pneumatic_policy_input_t\s+emergency_input\s*=\s*\{\s*\.emergency_stop\s*=\s*true\s*,?\s*\}\s*;',
        '\bconst\s+pneumatic_policy_output_t\s+emergency_output\s*=\s*pneumatic_policy_step\s*\(\s*&s_policy\s*,\s*&emergency_input\s*,\s*emergency_timestamp_ms\s*\)\s*;',
        '\bs_status\s*\.\s*output\s*=\s*emergency_output\s*;',
        '\bs_status\s*\.\s*timestamp_ms\s*=\s*emergency_timestamp_ms\s*;',
        '\bset_outputs\s*\(\s*emergency_output\.pump_on\s*,\s*emergency_output\.valve_on\s*\)\s*;',
        '\bbreak\s*;'
    )
    $afterEmergencyCase = $executeBody.Substring($emergencyCase.Index + $emergencyCase.Length)
    Assert-PatternsInOrder -Text $afterEmergencyCase -Description 'emergency-stop acknowledged status' -Patterns @(
        '\bresult->status\s*=\s*s_status\s*;',
        'xSemaphoreGive\s*\(\s*s_lock\s*\)\s*;'
    )
}

function Assert-RejectedPneumaticMutation {
    param([string]$Name, [string]$MutatedSource)

    $rejected = $false
    try {
        Assert-PneumaticControllerInvariants $MutatedSource
    } catch {
        $rejected = $true
    }
    if (-not $rejected) {
        throw "Pneumatic verifier accepted mutation: $Name"
    }
}

function Replace-RequiredMutation {
    param([string]$SourceText, [string]$Pattern, [string]$Replacement, [string]$Name)

    $regex = [regex]::new($Pattern)
    $mutated = $regex.Replace($SourceText, $Replacement, 1)
    if ($mutated -eq $SourceText) {
        throw "Unable to construct pneumatic verifier mutation: $Name"
    }
    return $mutated
}

function Move-RequiredMutationAfterUnlock {
    param([string]$SourceText, [string]$StatementPattern, [string]$Name)

    $statementRegex = [regex]::new($StatementPattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $statement = $statementRegex.Match($SourceText)
    if (-not $statement.Success) {
        throw "Unable to locate pneumatic statement mutation: $Name"
    }
    $withoutStatement = $SourceText.Remove($statement.Index, $statement.Length)
    $unlock = [regex]::Match($withoutStatement, 'xSemaphoreGive\s*\(\s*s_lock\s*\)\s*;')
    if (-not $unlock.Success) {
        throw "Unable to locate pneumatic unlock mutation: $Name"
    }
    return $withoutStatement.Insert($unlock.Index + $unlock.Length, "`n" + $statement.Value)
}

Assert-PneumaticControllerInvariants $pneumaticCodeText
$snapshotOrderMutation = Replace-RequiredMutation $pneumaticCodeText `
    '(?<selftest>const\s+pneumatic_self_test_phase_t\s+self_test_phase\s*=\s*s_self_test\s*\.\s*phase\s*;\s*)(?<pending>const\s+pending_commands_t\s+pending\s*=\s*s_pending\s*;)' `
    "`${pending}`n        `${selftest}" 'snapshot order'
Assert-RejectedPneumaticMutation 'snapshot order' $snapshotOrderMutation
$commonGateMutation = Replace-RequiredMutation $pneumaticCodeText `
    'const\s+bool\s+common_automatic_ready\s*=\s*pressure_fresh\s*;' `
    'const bool common_automatic_ready = pressure_fresh && s_pump_verified;' 'pressure-only automatic gate'
Assert-RejectedPneumaticMutation 'pressure-only automatic gate' $commonGateMutation
$policyAfterUnlockMutation = Move-RequiredMutationAfterUnlock $pneumaticCodeText `
    'const\s+pneumatic_policy_output_t\s+output\s*=\s*pneumatic_policy_step\s*\([^;]+;' 'policy step after unlock'
Assert-RejectedPneumaticMutation 'policy step after unlock' $policyAfterUnlockMutation
$selfTestAfterUnlockMutation = Move-RequiredMutationAfterUnlock $pneumaticCodeText `
    'update_self_test\s*\([^;]+;' 'self-test update after unlock'
Assert-RejectedPneumaticMutation 'self-test update after unlock' $selfTestAfterUnlockMutation
$statusAfterUnlockMutation = Move-RequiredMutationAfterUnlock $pneumaticCodeText `
    's_status\s*=\s*\(\s*pneumatic_status_t\s*\)\s*\{.*?\}\s*;' 'status assignment after unlock'
Assert-RejectedPneumaticMutation 'status assignment after unlock' $statusAfterUnlockMutation
$currentAfterUnlockMutation = Move-RequiredMutationAfterUnlock $pneumaticCodeText `
    'const\s+pneumatic_status_t\s+current\s*=\s*s_status\s*;' 'current snapshot after unlock'
Assert-RejectedPneumaticMutation 'current snapshot after unlock' $currentAfterUnlockMutation
$outputAfterUnlockMutation = Move-RequiredMutationAfterUnlock $pneumaticCodeText `
    'set_outputs\s*\(\s*output\.pump_on\s*,\s*output\.valve_on\s*\)\s*;' 'output write after unlock'
Assert-RejectedPneumaticMutation 'output write after unlock' $outputAfterUnlockMutation
$emitArgumentSwapMutation = Replace-RequiredMutation $pneumaticCodeText `
    '(?<automatic>status->automatic_enabled\s*\?\s*"true"\s*:\s*"false"\s*,\s*)(?<vision>action_state_name\s*\(\s*status->vision_state\s*\))' `
    "`${vision},`n           `${automatic}" 'automatic_enabled printf argument order'
Assert-RejectedPneumaticMutation 'automatic_enabled printf argument order' $emitArgumentSwapMutation
$emergencyPolicyMutation = Replace-RequiredMutation $pneumaticCodeText `
    'const\s+pneumatic_policy_output_t\s+emergency_output\s*=\s*pneumatic_policy_step\s*\(\s*&s_policy\s*,\s*&emergency_input\s*,\s*emergency_timestamp_ms\s*\)\s*;' `
    '' 'emergency policy step removed'
Assert-RejectedPneumaticMutation 'emergency policy step removed' $emergencyPolicyMutation
$emergencyStatusMutation = Replace-RequiredMutation $pneumaticCodeText `
    's_status\s*\.\s*output\s*=\s*emergency_output\s*;' '' 'emergency status assignment removed'
Assert-RejectedPneumaticMutation 'emergency status assignment removed' $emergencyStatusMutation
$emergencyBarrierRemovedMutation = Replace-RequiredMutation $pneumaticCodeText `
    's_pending\s*=\s*\(\s*pending_commands_t\s*\)\s*\{\s*0\s*\}\s*;\s*(?=const\s+uint64_t\s+emergency_timestamp_ms)' `
    '' 'emergency pending barrier removed'
Assert-RejectedPneumaticMutation 'emergency pending barrier removed' $emergencyBarrierRemovedMutation
$emergencyBarrierLateMutation = Replace-RequiredMutation $pneumaticCodeText `
    ('(?s)(?<barrier>s_pending\s*=\s*\(\s*pending_commands_t\s*\)\s*\{\s*0\s*\}\s*;\s*)' +
     '(?<policy>const\s+uint64_t\s+emergency_timestamp_ms.*?const\s+pneumatic_policy_output_t\s+emergency_output\s*=\s*pneumatic_policy_step\s*\([^;]+;)') `
    "`${policy}`n                `${barrier}" 'emergency pending barrier after policy'
Assert-RejectedPneumaticMutation 'emergency pending barrier after policy' $emergencyBarrierLateMutation
Write-Output "Pneumatic verifier mutation checks passed: source accepted, 12 unsafe mutations rejected."
Invoke-HostCTest "hardware_health_test" @(
    (Join-Path $main "hardware_health.c"),
    (Join-Path $aix "test\hardware_health_test.c")
)

$pneumaticSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "pneumatic_controller.c")
if ($pneumaticSourceText -notmatch 'action_controller_get_decision\s*\(' -or
    $pneumaticSourceText -match 'road_hazard|alert_arbiter') {
    throw "pneumatic_controller must depend only on action_controller decision, MPU and pressure inputs"
}
$businessRgbCallers = @(rg -l 'rgb_status_set_pattern\s*\(' $main -g '*.c' |
    Where-Object { (Split-Path -Leaf $_) -ne 'rgb_status.c' })
if (@($businessRgbCallers).Count -ne 1 -or (Split-Path -Leaf $businessRgbCallers[0]) -ne 'alert_arbiter.c') {
    throw "alert_arbiter.c must be the only business caller of rgb_status_set_pattern"
}
$riskReceiverSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "risk_receiver.c")
if ($riskReceiverSourceText -notmatch '\.uri\s*=\s*"/road-hazard"') {
    throw "risk_receiver must register POST /road-hazard"
}
$roadHazardHandler = [regex]::Match(
    $riskReceiverSourceText,
    '(?s)static esp_err_t road_hazard_handler\(.*?\n}\r?\n\r?\nstatic esp_err_t risk_handler').Value
if ([string]::IsNullOrWhiteSpace($roadHazardHandler) -or
    $roadHazardHandler -match 'voice_prompt|dfplayer|pneumatic_controller') {
    throw "road-hazard handler must remain isolated from voice and pneumatic control"
}
$actionControllerSourceText = Get-Content -Raw -LiteralPath (Join-Path $main "action_controller.c")
$applyRiskBody = [regex]::Match(
    $actionControllerSourceText,
    '(?s)risk_accept_result_t action_controller_apply_risk\(.*?\n}\r?\n\r?\nvoid action_controller_set_fault').Value
if ([string]::IsNullOrWhiteSpace($applyRiskBody) -or
    $applyRiskBody -notmatch '(?s)action_decision_t\s+local_snapshot\s*;.*?local_snapshot\s*=\s*s_decision\s*;.*?xSemaphoreGive\s*\(s_lock\).*?alert_arbiter_runtime_set_local\s*\(&local_snapshot' -or
    [regex]::Match($applyRiskBody, '(?s)xSemaphoreGive\s*\(s_lock\)(.*)$').Groups[1].Value -match '\bs_decision\b') {
    throw "action_controller_apply_risk must copy s_decision under lock and use only the local snapshot after unlock"
}

if ($BuildFirmware) {
    if (-not $env:IDF_PATH) {
        $exportScript = "D:\APP\ESPIDF\export.ps1"
        if (-not (Test-Path -LiteralPath $exportScript)) {
            throw "ESP-IDF environment is not active and $exportScript was not found."
        }
        & $exportScript
    }
    $idfPython = if ($env:IDF_PYTHON_ENV_PATH) {
        Join-Path $env:IDF_PYTHON_ENV_PATH "Scripts\python.exe"
    } else {
        $null
    }
    $idfScript = if ($env:IDF_PATH) {
        Join-Path $env:IDF_PATH "tools\idf.py"
    } else {
        $null
    }
    if (-not (Test-Path -LiteralPath $idfPython) -or -not (Test-Path -LiteralPath $idfScript)) {
        throw "ESP-IDF Python or idf.py is missing after environment activation."
    }

    $buildDir = "build-verify"
    $sdkconfig = "$buildDir/sdkconfig"
    $sdkconfigDefaults = "sdkconfig.defaults;sdkconfig.runtime"
    if (-not (Test-Path -LiteralPath $runtimeSync)) {
        throw "Missing runtime configuration helper: $runtimeSync"
    }
    & $runtimeSync
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime configuration synchronization failed with exit code $LASTEXITCODE"
    }

    $requiredTools = @("cmake", "ninja", "xtensa-esp32s3-elf-gcc")
    $toolPaths = @{}
    foreach ($tool in $requiredTools) {
        $command = Get-Command $tool -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            throw "ESP-IDF tool is missing from the parent environment: $tool"
        }
        $toolPaths[$tool] = $command.Source
    }
    $toolDirectories = ($toolPaths.Values | ForEach-Object { Split-Path -Parent $_ } | Select-Object -Unique) -join ";"
    $idfShim = "import os,runpy,sys; os.environ['PATH']=sys.argv[1]+';'+os.environ.get('PATH',''); script=sys.argv[2]; sys.path.insert(0,os.path.dirname(script)); sys.argv=[script]+sys.argv[3:]; runpy.run_path(script,run_name='__main__')"
    $preflight = "import os,shutil,sys; os.environ['PATH']=sys.argv[1]+';'+os.environ.get('PATH',''); missing=[x for x in ('cmake','ninja','xtensa-esp32s3-elf-gcc') if not shutil.which(x)]; print('child_tools_ready' if not missing else 'child_tools_missing='+','.join(missing)); raise SystemExit(1 if missing else 0)"
    Invoke-Checked "ESP-IDF child tool preflight" {
        & $idfPython -c $preflight $toolDirectories
    }
    $env:IDF_CCACHE_ENABLE = "0"

    if (Test-Path -LiteralPath (Join-Path $aix $buildDir)) {
        Invoke-Checked "ESP-IDF fullclean" {
            Push-Location $aix
            try {
                & $idfPython -c $idfShim $toolDirectories $idfScript -B $buildDir fullclean
            } finally {
                Pop-Location
            }
        }
    }

    Invoke-Checked "ESP-IDF firmware build" {
        Push-Location $aix
        try {
            & $idfPython -c $idfShim $toolDirectories $idfScript -B $buildDir "-DSDKCONFIG=$sdkconfig" "-DSDKCONFIG_DEFAULTS=$sdkconfigDefaults" build
        } finally {
            Pop-Location
        }
    }

    $binary = Join-Path $aix "$buildDir\AIX.bin"
    $builtSdkconfig = Join-Path $aix $sdkconfig
    if (-not (Test-Path -LiteralPath $binary) -or -not (Test-Path -LiteralPath $builtSdkconfig)) {
        throw "Firmware build completed without AIX.bin or generated sdkconfig."
    }
    $commit = (& git -C $projectRoot rev-parse HEAD).Trim()
    $dirty = [bool]((& git -C $projectRoot status --porcelain).Count)
    $manifest = [ordered]@{
        generated_at = [DateTime]::Now.ToString("o")
        git_commit = $commit
        git_dirty = $dirty
        sdkconfig_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $builtSdkconfig).Hash.ToLowerInvariant()
        aix_bin_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $binary).Hash.ToLowerInvariant()
        aix_bin_bytes = (Get-Item -LiteralPath $binary).Length
    }
    $manifestPath = Join-Path $aix "$buildDir\firmware-manifest.json"
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
    Write-Output "Firmware manifest: $manifestPath"
}

Write-Output "Verification passed: host/service Python tests, compileall, and host-side C safety tests."
