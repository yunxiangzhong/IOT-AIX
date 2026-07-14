[CmdletBinding()]
param(
    [string]$Ssid,
    [string]$Password
)

$ErrorActionPreference = "Stop"
$configPath = Join-Path $PSScriptRoot "sdkconfig.preview"

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
    $Ssid = Read-Host "输入 Windows 移动热点 SSID"
}
if ([string]::IsNullOrWhiteSpace($Password)) {
    $Password = Read-SecretText "输入热点密码（不会回显）"
}
if ([string]::IsNullOrWhiteSpace($Ssid) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "SSID 和密码都不能为空。"
}

@"
# Generated locally by AIX/configure_preview.ps1; do not commit.
CONFIG_AIX_ENABLE_CAMERA_PREVIEW=y
CONFIG_AIX_ENABLE_VISION_UPLINK=n
CONFIG_AIX_WIFI_SSID="$(Escape-KconfigString $Ssid)"
CONFIG_AIX_WIFI_PASSWORD="$(Escape-KconfigString $Password)"
"@ | Set-Content -LiteralPath $configPath -Encoding ascii

Write-Host "已写入 $configPath"
Write-Host "SSID: $Ssid"
Write-Host "下一步：运行 scripts\verify.ps1 -BuildFirmware，或在 AIX 目录用相同 sdkconfig.defaults;sdkconfig.preview 配置编译。"
