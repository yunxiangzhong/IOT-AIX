[CmdletBinding()]
param(
    [int]$Port = 8008
)

$ErrorActionPreference = "Stop"

$commonGitDir = (& git -C $PSScriptRoot rev-parse --git-common-dir).Trim()
$projectRoot = Split-Path -Parent $commonGitDir
$runtimeRoot = Join-Path $projectRoot "Models\DepthAnything3"
$python = Join-Path $runtimeRoot "env\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "DA3 environment is missing: $python. Run install.ps1 first."
}

$env:DA3_ROOT = $runtimeRoot
$env:HF_HOME = Join-Path $runtimeRoot "cache\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $runtimeRoot "cache\torch"

Push-Location $PSScriptRoot
try {
    & $python -m uvicorn server:create_runtime_app --factory --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
