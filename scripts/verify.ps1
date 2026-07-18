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
