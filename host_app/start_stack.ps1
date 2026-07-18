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

Write-Output "[3/5] Starting asynchronous model service..."
$modelArgs = @("-m", "uvicorn", "server:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8008")
$service = Start-Process -FilePath $modelPython -ArgumentList $modelArgs -WorkingDirectory $serviceRoot `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru

try {
    Write-Output "[4/5] Waiting for HTTP health endpoint..."
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $healthy = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($service.HasExited) {
            throw "Model service exited early with code $($service.ExitCode). See $stderrPath"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8008/healthz" -TimeoutSec 1
            if ($health.http_ready -eq $true) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $healthy) {
        throw "Model service HTTP endpoint did not become ready within 30 seconds. See $stderrPath"
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
    if ($null -ne $service -and -not $service.HasExited) {
        Stop-Process -Id $service.Id -Force
        $service.WaitForExit(5000)
    }
}
