[CmdletBinding()]
param(
    [switch]$BuildFirmware
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
$runtimeRoot = Split-Path -Parent $commonGitDir
$python = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
$hostApp = Join-Path $projectRoot "host_app"
$aix = Join-Path $projectRoot "AIX"
$main = Join-Path $aix "main"
$testBin = Join-Path $projectRoot ".test-bin"
$cameraKconfig = Join-Path $main "Kconfig.projbuild"
$cameraSource = Join-Path $main "camera_local.c"
$cameraPreview = Join-Path $main "camera_preview.c"
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
Invoke-HostCTest "host_risk_test" @(
    (Join-Path $main "host_risk.c"),
    (Join-Path $aix "test\host_risk_test.c")
)

if ($BuildFirmware) {
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
    $useEspIdfPython = $false
    if ($null -ne $idfPython -and $null -ne $idfScript) {
        $useEspIdfPython = (Test-Path -LiteralPath $idfPython) -and (Test-Path -LiteralPath $idfScript)
    }
    $idf = if ($useEspIdfPython) { $null } else { Get-Command idf.py -ErrorAction SilentlyContinue }
    if (-not $useEspIdfPython -and $null -eq $idf) {
        throw "ESP-IDF tools were not found. Run ESP-IDF export.ps1 before requesting an ESP-IDF build."
    }

    $buildDir = "build-verify"
    $sdkconfig = "$buildDir/sdkconfig"
    $sdkconfigDefaults = "sdkconfig.defaults"
    if (Test-Path -LiteralPath (Join-Path $aix "sdkconfig.preview")) {
        $sdkconfigDefaults = "sdkconfig.defaults;sdkconfig.preview"
    }

    Invoke-Checked "ESP-IDF firmware build" {
        Push-Location $aix
        try {
            if ($useEspIdfPython) {
                & $idfPython $idfScript -B $buildDir "-DSDKCONFIG=$sdkconfig" "-DSDKCONFIG_DEFAULTS=$sdkconfigDefaults" build
            } else {
                & $idf.Source -B $buildDir "-DSDKCONFIG=$sdkconfig" "-DSDKCONFIG_DEFAULTS=$sdkconfigDefaults" build
            }
        } finally {
            Pop-Location
        }
    }
}

Write-Output "Verification passed: host/service Python tests, compileall, and pressure/camera/risk host-side C tests."
