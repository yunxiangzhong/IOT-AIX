[CmdletBinding()]
param(
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$previewConfig = Join-Path $projectRoot "AIX\sdkconfig.preview"

function Read-KconfigString {
    param(
        [string]$Path,
        [string]$Name
    )

    $line = Select-String -LiteralPath $Path -Pattern ('^{0}="(.*)"$' -f [regex]::Escape($Name)) |
        Select-Object -First 1
    if ($null -eq $line) {
        throw "Missing $Name in $Path"
    }
    return $line.Matches[0].Groups[1].Value.Replace('\"', '"').Replace('\\', '\')
}

function Wait-WinRtOperation {
    param(
        $Operation,
        [Type]$ResultType,
        [int]$TimeoutSeconds = 30
    )

    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and $_.IsGenericMethod -and
            $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
            $_.ReturnType.IsGenericType
        } |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait($TimeoutSeconds * 1000)) {
        throw "Windows hotspot operation timed out."
    }
    return $task.Result
}

function Wait-WinRtAction {
    param(
        $Operation,
        [int]$TimeoutSeconds = 30
    )

    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and -not $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $task = $method.Invoke($null, @($Operation))
    if (-not $task.Wait($TimeoutSeconds * 1000)) {
        throw "Windows hotspot configuration timed out."
    }
}

if (-not (Test-Path -LiteralPath $previewConfig)) {
    throw "Missing $previewConfig. Run AIX\configure_preview.ps1 first."
}

$ssid = Read-KconfigString -Path $previewConfig -Name "CONFIG_AIX_WIFI_SSID"
$password = Read-KconfigString -Path $previewConfig -Name "CONFIG_AIX_WIFI_PASSWORD"
if ([string]::IsNullOrWhiteSpace($ssid) -or [string]::IsNullOrWhiteSpace($password)) {
    throw "The preview SSID and password must not be empty."
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null

$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) {
    throw "Windows has no active internet connection profile for Mobile Hotspot."
}
$manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$configuration = $manager.GetCurrentAccessPointConfiguration()

if ($StatusOnly) {
    Write-Output "wifi_hotspot_state=$($manager.TetheringOperationalState) ssid=$($configuration.Ssid) clients=$($manager.ClientCount)"
    exit 0
}

if ($configuration.Ssid -ne $ssid -or $configuration.Passphrase -ne $password) {
    if ([string]$manager.TetheringOperationalState -eq "On") {
        $stopResult = Wait-WinRtOperation ($manager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        if ([string]$stopResult.Status -ne "Success") {
            throw "Unable to stop Mobile Hotspot before updating its configuration: $($stopResult.Status)"
        }
    }
    $configuration.Ssid = $ssid
    $configuration.Passphrase = $password
    Wait-WinRtAction ($manager.ConfigureAccessPointAsync($configuration))
}

if ([string]$manager.TetheringOperationalState -ne "On") {
    $startResult = Wait-WinRtOperation ($manager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    if ([string]$startResult.Status -ne "Success") {
        throw "Unable to start Mobile Hotspot: $($startResult.Status) $($startResult.AdditionalErrorMessage)"
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds(15)
while ([string]$manager.TetheringOperationalState -ne "On" -and [DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Milliseconds 250
}
if ([string]$manager.TetheringOperationalState -ne "On") {
    throw "Mobile Hotspot did not reach the On state."
}

$activeConfiguration = $manager.GetCurrentAccessPointConfiguration()
if ($activeConfiguration.Ssid -ne $ssid) {
    throw "Mobile Hotspot SSID mismatch: expected $ssid, got $($activeConfiguration.Ssid)"
}
Write-Output "wifi_hotspot_ready state=On ssid=$ssid clients=$($manager.ClientCount)"
