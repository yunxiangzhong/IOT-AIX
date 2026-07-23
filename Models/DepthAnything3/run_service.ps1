[CmdletBinding()]
param(
    [int]$Port = 8008
)

$ErrorActionPreference = "Stop"

$projectRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
. (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts\runtime_paths.ps1")
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
$sharedProjectRoot = Resolve-AixRuntimeRoot -ProjectRoot $projectRoot -GitCommonDir $commonGitDir
$runtimeRoot = Join-Path $sharedProjectRoot "Models\DepthAnything3"
$python = Join-Path $runtimeRoot "env\python.exe"
$localEnvPaths = @(
    (Join-Path $projectRoot ".env.local"),
    (Join-Path $sharedProjectRoot ".env.local")
) | Select-Object -Unique

if (-not $env:VEI_API_KEY) {
    foreach ($localEnvPath in $localEnvPaths) {
        if (Test-Path -LiteralPath $localEnvPath) {
            $keyLine = Get-Content -LiteralPath $localEnvPath |
                Where-Object { $_ -match '^\s*VEI_API_KEY\s*=' } |
                Select-Object -Last 1
            if ($keyLine) {
                $env:VEI_API_KEY = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
                break
            }
        }
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "DA3 environment is missing: $python. Run install.ps1 first."
}

$env:DA3_ROOT = $runtimeRoot
$env:HF_HOME = Join-Path $runtimeRoot "cache\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $runtimeRoot "cache\torch"
$env:YOLO_CONFIG_DIR = Join-Path $runtimeRoot "cache\ultralytics"
$env:MPLCONFIGDIR = Join-Path $runtimeRoot "cache\matplotlib"

Push-Location (Join-Path $PSScriptRoot "service")
try {
    & $python -m uvicorn server:create_runtime_app --factory --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
