[CmdletBinding()]
param(
    [ValidateSet("none", "demo", "hardware", "camera")]
    [string]$IdfProfile = "none"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$hostApp = Join-Path $projectRoot "host_app"
$aix = Join-Path $projectRoot "AIX"
$main = Join-Path $aix "main"
$testBin = Join-Path $projectRoot ".test-bin"

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

New-Item -ItemType Directory -Force -Path $testBin | Out-Null

Invoke-HostCTest "pressure_sensor_math_test" @(
    (Join-Path $aix "test\pressure_sensor_math_test.c")
) @("-lm")
Invoke-HostCTest "vision_input_parse_test" @(
    (Join-Path $main "vision_input.c"),
    (Join-Path $aix "test\vision_input_parse_test.c")
)
Invoke-HostCTest "config_input_parse_test" @(
    (Join-Path $main "config_input.c"),
    (Join-Path $aix "test\config_input_parse_test.c")
)
Invoke-HostCTest "vision_detect_parse_test" @(
    (Join-Path $main "vision_detect.c"),
    (Join-Path $aix "test\vision_detect_parse_test.c")
)
Invoke-HostCTest "distance_estimator_test" @(
    (Join-Path $main "distance_estimator.c"),
    (Join-Path $aix "test\distance_estimator_test.c")
) @("-lm")
Invoke-HostCTest "risk_fusion_test" @(
    (Join-Path $main "risk_fusion.c"),
    (Join-Path $main "vision_detect.c"),
    (Join-Path $aix "test\risk_fusion_test.c")
) @("-lm")
Invoke-HostCTest "voice_prompt_test" @(
    (Join-Path $main "voice_prompt.c"),
    (Join-Path $aix "test\voice_prompt_test.c")
)
Invoke-HostCTest "camera_local_test" @(
    (Join-Path $main "camera_local.c"),
    (Join-Path $aix "test\camera_local_test.c")
)

if ($IdfProfile -ne "none") {
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
    $useEspIdfPython = (Test-Path -LiteralPath $idfPython) -and (Test-Path -LiteralPath $idfScript)
    $idf = if ($useEspIdfPython) { $null } else { Get-Command idf.py -ErrorAction SilentlyContinue }
    if (-not $useEspIdfPython -and $null -eq $idf) {
        throw "ESP-IDF tools were not found. Run ESP-IDF export.ps1 before requesting an ESP-IDF build."
    }

    $buildDir = "build-$IdfProfile"
    $sdkconfig = "$buildDir/sdkconfig"
    $defaults = switch ($IdfProfile) {
        "demo" { "sdkconfig.defaults" }
        "hardware" { "sdkconfig.defaults;sdkconfig.hardware.defaults" }
        "camera" { "sdkconfig.defaults;sdkconfig.hardware.defaults;sdkconfig.camera.defaults" }
    }

    Invoke-Checked "ESP-IDF $IdfProfile build" {
        Push-Location $aix
        try {
            if ($useEspIdfPython) {
                & $idfPython $idfScript -B $buildDir "-DSDKCONFIG=$sdkconfig" "-DSDKCONFIG_DEFAULTS=$defaults" build
            } else {
                & $idf.Source -B $buildDir "-DSDKCONFIG=$sdkconfig" "-DSDKCONFIG_DEFAULTS=$defaults" build
            }
        } finally {
            Pop-Location
        }
    }
}

Write-Output "Verification passed: Python tests, compileall, and eight host-side C tests."
