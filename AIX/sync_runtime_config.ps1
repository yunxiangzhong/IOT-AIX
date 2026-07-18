[CmdletBinding()]
param(
    [string]$DeviceId = "aix-helmet-01",
    [string]$ServiceUrl = "http://192.168.137.1:8008/v1/frames",
    [switch]$PassThru
)

$ErrorActionPreference = "Stop"
$aixRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $aixRoot
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
if (-not [IO.Path]::IsPathRooted($commonGitDir)) {
    $commonGitDir = Join-Path $projectRoot $commonGitDir
}
$sharedRoot = Split-Path -Parent $commonGitDir
$runtimePath = Join-Path $aixRoot "sdkconfig.runtime"
$sharedRuntimePath = Join-Path $sharedRoot "AIX\sdkconfig.runtime"
$previewPath = Join-Path $sharedRoot "AIX\sdkconfig.preview"

if (-not (Test-Path -LiteralPath $runtimePath)) {
    if (Test-Path -LiteralPath $sharedRuntimePath) {
        Copy-Item -LiteralPath $sharedRuntimePath -Destination $runtimePath
    } elseif (Test-Path -LiteralPath $previewPath) {
        Copy-Item -LiteralPath $previewPath -Destination $runtimePath
    } else {
        Set-Content -LiteralPath $runtimePath -Value @(
            'CONFIG_AIX_WIFI_SSID=""',
            'CONFIG_AIX_WIFI_PASSWORD=""'
        ) -Encoding utf8
    }
}

$settings = [ordered]@{
    CONFIG_AIX_ENABLE_CAMERA_PREVIEW = "n"
    CONFIG_AIX_ENABLE_VISION_UPLINK = "y"
    CONFIG_AIX_ENABLE_RISK_RECEIVER = "y"
    CONFIG_AIX_ENABLE_ONBOARD_RGB = "y"
    CONFIG_AIX_DEVICE_ID = '"' + $DeviceId + '"'
    CONFIG_AIX_VISION_SERVICE_URL = '"' + $ServiceUrl + '"'
    CONFIG_AIX_VISION_UPLOAD_PERIOD_MS = "1000"
    CONFIG_AIX_VISION_HTTP_TIMEOUT_MS = "1500"
    CONFIG_AIX_RISK_RECEIVER_PORT = "8080"
}

$lines = [Collections.Generic.List[string]]::new()
foreach ($line in Get-Content -LiteralPath $runtimePath) {
    $lines.Add($line)
}

$tokenLine = $lines | Where-Object { $_ -match '^CONFIG_AIX_LINK_TOKEN=' } | Select-Object -Last 1
if ($tokenLine) {
    $token = ($tokenLine -split '=', 2)[1].Trim('"')
} else {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $token = [Convert]::ToHexString($bytes).ToLowerInvariant()
}
$settings.CONFIG_AIX_LINK_TOKEN = '"' + $token + '"'

foreach ($key in $settings.Keys) {
    for ($index = $lines.Count - 1; $index -ge 0; $index--) {
        if ($lines[$index] -match ('^' + [regex]::Escape($key) + '=')) {
            $lines.RemoveAt($index)
        }
    }
    $lines.Add("$key=$($settings[$key])")
}
Set-Content -LiteralPath $runtimePath -Value $lines -Encoding utf8

$ssid = (($lines | Where-Object { $_ -match '^CONFIG_AIX_WIFI_SSID=' } | Select-Object -Last 1) -split '=', 2)[1].Trim('"')
$result = [pscustomobject]@{
    RuntimePath = $runtimePath
    DeviceId = $DeviceId
    ServiceUrl = $ServiceUrl
    Token = $token
    WifiConfigured = -not [string]::IsNullOrWhiteSpace($ssid)
    MigratedFromPreview = (Test-Path -LiteralPath $previewPath)
}
if ($PassThru) {
    $result
} else {
    Write-Output "Runtime config ready: $runtimePath"
    Write-Output "Device: $DeviceId | service: $ServiceUrl | Wi-Fi configured: $($result.WifiConfigured)"
}
