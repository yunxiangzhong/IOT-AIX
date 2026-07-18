[CmdletBinding()]
param(
    [int]$Port = 8008
)

$ErrorActionPreference = "Stop"

$projectRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$runtimeRoot = Join-Path $projectRoot "Models\DepthAnything3"
$python = Join-Path $runtimeRoot "env\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "DA3 environment is missing: $python. Run install.ps1 first."
}

$env:DA3_ROOT = $runtimeRoot
$env:HF_HOME = Join-Path $runtimeRoot "cache\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $runtimeRoot "cache\torch"
$env:YOLO_CONFIG_DIR = Join-Path $runtimeRoot "cache\ultralytics"
$env:MPLCONFIGDIR = Join-Path $runtimeRoot "cache\matplotlib"

Push-Location $PSScriptRoot
try {
    & $python -m uvicorn server:create_runtime_app --factory --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
