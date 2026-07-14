[CmdletBinding()]
param(
    [string]$Ssid,
    [string]$Password,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$configPath = if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Join-Path $PSScriptRoot "sdkconfig.preview"
} else {
    $OutputPath
}

function Read-SecretText {
    param([string]$Prompt)

    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Escape-KconfigString {
    param([string]$Value)

    return $Value.Replace('\', '\\').Replace('"', '\"')
}

if ([string]::IsNullOrWhiteSpace($Ssid)) {
    $Ssid = Read-Host "Windows mobile hotspot SSID"
}
if ([string]::IsNullOrWhiteSpace($Password)) {
    $Password = Read-SecretText "Hotspot password (hidden)"
}
if ([string]::IsNullOrWhiteSpace($Ssid) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "SSID and password must not be empty."
}

$content = @(
    '# Generated locally by AIX/configure_preview.ps1; do not commit.'
    'CONFIG_AIX_ENABLE_CAMERA_PREVIEW=y'
    'CONFIG_AIX_ENABLE_VISION_UPLINK=n'
    ('CONFIG_AIX_WIFI_SSID="{0}"' -f (Escape-KconfigString $Ssid))
    ('CONFIG_AIX_WIFI_PASSWORD="{0}"' -f (Escape-KconfigString $Password))
)
$content | Set-Content -LiteralPath $configPath -Encoding ascii

Write-Host "Preview configuration written: $configPath"
Write-Host "SSID: $Ssid"
Write-Host "Next: run scripts\verify.ps1 -BuildFirmware, then flash the new firmware."
