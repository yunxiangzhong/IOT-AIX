[CmdletBinding()]
param(
    [string]$PreviewConfig,
    [string]$Sdkconfig
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($PreviewConfig)) {
    $PreviewConfig = Join-Path $PSScriptRoot "sdkconfig.preview"
}
if ([string]::IsNullOrWhiteSpace($Sdkconfig)) {
    $Sdkconfig = Join-Path $PSScriptRoot "sdkconfig"
}

if (-not (Test-Path -LiteralPath $PreviewConfig)) {
    throw "Missing preview configuration: $PreviewConfig"
}
if (-not (Test-Path -LiteralPath $Sdkconfig)) {
    Write-Output "active_sdkconfig_missing path=$Sdkconfig"
    exit 0
}

$keys = @(
    "CONFIG_AIX_ENABLE_CAMERA_PREVIEW",
    "CONFIG_AIX_WIFI_SSID",
    "CONFIG_AIX_WIFI_PASSWORD"
)
$previewLines = Get-Content -LiteralPath $PreviewConfig
$replacements = @{}
foreach ($key in $keys) {
    $line = $previewLines | Where-Object { $_ -match ("^{0}=" -f [regex]::Escape($key)) } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($line)) {
        throw "Missing $key in $PreviewConfig"
    }
    $replacements[$key] = $line
}

$lines = New-Object 'System.Collections.Generic.List[string]'
Get-Content -LiteralPath $Sdkconfig | ForEach-Object { $lines.Add($_) }
foreach ($key in $keys) {
    $matched = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match ("^(?:{0}=|# {0} is not set)" -f [regex]::Escape($key))) {
            $lines[$index] = $replacements[$key]
            $matched = $true
            break
        }
    }
    if (-not $matched) {
        $lines.Add($replacements[$key])
    }
}

[IO.File]::WriteAllLines($Sdkconfig, $lines, [Text.Encoding]::ASCII)
$ssidLine = $replacements["CONFIG_AIX_WIFI_SSID"]
Write-Output "active_sdkconfig_synced $ssidLine"
