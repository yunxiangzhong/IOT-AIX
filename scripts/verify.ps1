[CmdletBinding()]
param(
    [switch]$BuildFirmware
)

$ErrorActionPreference = "Stop"

$projectRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
if (-not [System.IO.Path]::IsPathRooted($commonGitDir)) {
    $commonGitDir = Join-Path $projectRoot $commonGitDir
}
$runtimeRoot = Split-Path -Parent $commonGitDir
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
Invoke-HostCTest "vision_uplink_test" @(
    (Join-Path $main "vision_uplink.c"),
    (Join-Path $aix "test\vision_uplink_test.c")
)
Invoke-HostCTest "risk_receiver_test" @(
    (Join-Path $main "risk_receiver.c"),
    (Join-Path $aix "test\risk_receiver_test.c")
)
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
