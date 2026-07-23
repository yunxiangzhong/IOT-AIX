[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$hostRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $hostRoot
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
if (-not [IO.Path]::IsPathRooted($commonGitDir)) {
    $commonGitDir = Join-Path $projectRoot $commonGitDir
}
$runtimeRoot = Split-Path -Parent $commonGitDir
$hostPython = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
$modelRoot = Join-Path $runtimeRoot "Models\DepthAnything3"
$modelPython = Join-Path $modelRoot "env\python.exe"
$serviceRoot = Join-Path $projectRoot "Models\DepthAnything3\service"
$syncScript = Join-Path $projectRoot "AIX\sync_runtime_config.ps1"
$hotspotScript = Join-Path $hostRoot "ensure_mobile_hotspot.ps1"
$localEnvPaths = @(
    (Join-Path $projectRoot ".env.local"),
    (Join-Path $runtimeRoot ".env.local")
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

function Test-RealModelHealth {
    param([Parameter(Mandatory = $true)][object]$Health)

    $gpu = [string]$Health.gpu
    if ([string]::IsNullOrWhiteSpace($gpu)) {
        $gpu = [string]$Health.device
    }
    $backend = [string]$Health.backend
    return (
        $Health.http_ready -eq $true -and
        $Health.model_ready -eq $true -and
        [string]$Health.model_state -eq "ready" -and
        [string]$Health.model -eq "DA3-SMALL" -and
        [string]$Health.detector -eq "YOLO26m-COCO" -and
        $gpu.ToLowerInvariant() -eq "cuda" -and
        $backend -in @("tensorrt-fp16", "pytorch-cuda-fp16")
    )
}

foreach ($required in @($hostPython, $modelPython, $syncScript, $hotspotScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required runtime file: $required"
    }
}
if ($DryRun) {
    Write-Output "aix_stack_ready host_python=$hostPython model_python=$modelPython"
    exit 0
}

Write-Output "[1/5] Synchronizing ignored runtime configuration..."
$runtime = & $syncScript -PassThru
if (-not $runtime.WifiConfigured) {
    throw "Wi-Fi credentials are empty in $($runtime.RuntimePath)"
}

Write-Output "[2/5] Verifying 2.4 GHz Windows Mobile Hotspot..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hotspotScript
if ($LASTEXITCODE -ne 0) {
    throw "Windows Mobile Hotspot setup failed with code $LASTEXITCODE"
}

$logRoot = Join-Path $hostRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutPath = Join-Path $logRoot "model-service-$stamp.stdout.log"
$stderrPath = Join-Path $logRoot "model-service-$stamp.stderr.log"

$env:DA3_ROOT = $modelRoot
$env:HF_HOME = Join-Path $modelRoot "cache\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $modelRoot "cache\torch"
$env:YOLO_CONFIG_DIR = Join-Path $modelRoot "cache\ultralytics"
$env:MPLCONFIGDIR = Join-Path $modelRoot "cache\matplotlib"
$env:AIX_LINK_TOKEN = $runtime.Token
$env:AIX_SERVICE_URL = "http://127.0.0.1:8008"
$env:AIX_DEVICE_ID = $runtime.DeviceId
$env:AIX_MODEL_STDOUT_PATH = $stdoutPath
$env:AIX_MODEL_STDERR_PATH = $stderrPath

$service = $null
$startedModelService = $false
$reuseHealthyService = $false
$existingServiceResponded = $false
try {
    $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8008/healthz" -TimeoutSec 1
    $existingServiceResponded = $true
    $reuseHealthyService = Test-RealModelHealth -Health $existingHealth
} catch {
    $reuseHealthyService = $false
}

if ($reuseHealthyService) {
    Write-Output "[3/5] Reusing verified DA3-SMALL + YOLO26m CUDA service on 127.0.0.1:8008..."
} elseif ($existingServiceResponded) {
    throw "Port 8008 is occupied by a service that is not the ready DA3-SMALL + YOLO26m CUDA runtime. Stop it explicitly and retry."
} else {
    Write-Output "[3/5] Starting asynchronous model service..."
    $modelArgs = @("-m", "uvicorn", "server:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8008")
    $service = Start-Process -FilePath $modelPython -ArgumentList $modelArgs -WorkingDirectory $serviceRoot `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
    $startedModelService = $true
}

try {
    Write-Output "[4/5] Waiting for real model and CUDA backend readiness..."
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    $healthy = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($startedModelService -and $service.HasExited) {
            throw "Model service exited early with code $($service.ExitCode). See $stderrPath"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8008/healthz" -TimeoutSec 1
            if (Test-RealModelHealth -Health $health) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $healthy) {
        throw "DA3-SMALL + YOLO26m CUDA model service did not become ready within 180 seconds. See $stderrPath"
    }

    Write-Output "[5/5] Starting PySide6 industrial dashboard..."
    Push-Location $hostRoot
    try {
        $hostArgs = @("-m", "aix_host_app")
        & $hostPython @hostArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Host app exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($startedModelService -and $null -ne $service -and -not $service.HasExited) {
        Stop-Process -Id $service.Id -Force
        $service.WaitForExit(5000)
    }
}
