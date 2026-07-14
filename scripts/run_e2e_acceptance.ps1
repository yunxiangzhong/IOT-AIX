[CmdletBinding()]
param(
    [string]$ServiceUrl = "http://127.0.0.1:8008",
    [string]$DeviceId = "aix-helmet-01",
    [int]$DurationSeconds = 600,
    [string]$SerialPort = "",
    [int]$Baudrate = 115200,
    [string]$OutputPath = "",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$root = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $root "e2e_report.json"
}
$ServiceUrl = $ServiceUrl.TrimEnd('/')

function Get-State {
    $encoded = [Uri]::EscapeDataString($DeviceId)
    Invoke-RestMethod -Uri "$ServiceUrl/v1/state/latest?device_id=$encoded" -TimeoutSec 2
}

function Get-P95([Collections.Generic.List[double]]$Values) {
    if ($Values.Count -eq 0) { return $null }
    $sorted = @($Values | Sort-Object)
    $index = [Math]::Min($sorted.Count - 1, [Math]::Ceiling($sorted.Count * 0.95) - 1)
    return [Math]::Round([double]$sorted[$index], 2)
}

$health = Invoke-RestMethod -Uri "$ServiceUrl/healthz" -TimeoutSec 2
if ($health.http_ready -ne $true) {
    throw "PC HTTP service is not ready at $ServiceUrl"
}
$initial = Get-State
$frames = [Collections.Generic.HashSet[string]]::new()
$inferenceLatencies = [Collections.Generic.List[double]]::new()
$callbackLatencies = [Collections.Generic.List[double]]::new()
$bandCounts = @{}
$rgbCounts = @{}
$serialActionCount = 0
$serialActionMismatches = 0
$uplinkAttempts = 0
$uplinkAccepted = 0
$serialBuffer = ""
$serial = $null

if (-not [string]::IsNullOrWhiteSpace($SerialPort)) {
    $serial = [IO.Ports.SerialPort]::new($SerialPort, $Baudrate)
    $serial.ReadTimeout = 50
    $serial.Open()
}

$startedAt = [DateTimeOffset]::Now
$deadline = [DateTime]::UtcNow.AddSeconds($DurationSeconds)
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $state = Get-State
            $seq = [int]$state.upload.last_frame_seq
            if ($seq -ge 0) {
                $null = $frames.Add("$($state.boot_id):$seq")
            }
            if ($null -ne $state.model.latency_ms) {
                $inferenceLatencies.Add([double]$state.model.latency_ms)
            }
            if ($null -ne $state.callback.latency_ms) {
                $callbackLatencies.Add([double]$state.callback.latency_ms)
            }
            $band = [string]$state.risk.band
            if (-not $bandCounts.ContainsKey($band)) { $bandCounts[$band] = 0 }
            $bandCounts[$band]++
            $rgb = [string]$state.action.rgb_pattern
            if (-not $rgbCounts.ContainsKey($rgb)) { $rgbCounts[$rgb] = 0 }
            $rgbCounts[$rgb]++
        } catch {
            # A transient state-read failure is retained in the final counters.
        }

        if ($null -ne $serial -and $serial.BytesToRead -gt 0) {
            $serialBuffer += $serial.ReadExisting()
            $lines = $serialBuffer -split "`r?`n"
            $serialBuffer = $lines[-1]
            foreach ($line in $lines[0..([Math]::Max(0, $lines.Count - 2))]) {
                if (-not $line.StartsWith('{')) { continue }
                try {
                    $event = $line | ConvertFrom-Json
                    if ($event.type -eq "action_status") {
                        $serialActionCount++
                        if ($null -ne $state -and [int]$event.frame_seq -ne [int]$state.action.frame_seq) {
                            $serialActionMismatches++
                        }
                    } elseif ($event.type -eq "uplink_status") {
                        $uplinkAttempts++
                        if ($event.valid -eq $true) { $uplinkAccepted++ }
                    }
                } catch { }
            }
        }
        Start-Sleep -Milliseconds 400
    }
} finally {
    if ($null -ne $serial) { $serial.Close() }
}

$final = Get-State
$acceptedFrames = [int64]$final.upload.accepted_frames - [int64]$initial.upload.accepted_frames
$validResults = [int64]$final.model.valid_results - [int64]$initial.model.valid_results
$confirmed = [int64]$final.callback.confirmed_count - [int64]$initial.callback.confirmed_count
$callbackFailed = [int64]$final.callback.failed_count - [int64]$initial.callback.failed_count
$acceptanceRate = if ($uplinkAttempts -gt 0) { [Math]::Round(100.0 * $uplinkAccepted / $uplinkAttempts, 2) } else { $null }
$callbackP95 = Get-P95 $callbackLatencies
$failures = [Collections.Generic.List[string]]::new()
if ($acceptedFrames -lt [Math]::Floor($DurationSeconds * 2.3)) { $failures.Add("accepted frame rate below 2.3 FPS") }
if ($validResults -lt [Math]::Floor($DurationSeconds * 0.4167)) { $failures.Add("valid model results below proportional 250/600 threshold") }
if ($confirmed -ne $validResults) { $failures.Add("confirmed action_ack count does not match valid results") }
if ($callbackFailed -gt 0) { $failures.Add("callback failures observed") }
if ($null -ne $callbackP95 -and $callbackP95 -ge 500) { $failures.Add("callback P95 is not below 500 ms") }
if ($null -ne $acceptanceRate -and $acceptanceRate -lt 95) { $failures.Add("ESP upload acceptance is below 95 percent") }
if ($serialActionMismatches -gt 0) { $failures.Add("serial action_status frame mismatch observed") }

$report = [ordered]@{
    type = "aix_e2e_report"
    version = 1
    started_at = $startedAt.ToString("o")
    ended_at = [DateTimeOffset]::Now.ToString("o")
    duration_seconds = $DurationSeconds
    device_id = $DeviceId
    boot_id = $final.boot_id
    frames_accepted = $acceptedFrames
    unique_frames_observed = $frames.Count
    upload_acceptance_percent = $acceptanceRate
    queue_replaced = [int64]$final.upload.queue_replaced - [int64]$initial.upload.queue_replaced
    valid_model_results = $validResults
    action_ack_confirmed = $confirmed
    callback_failed = $callbackFailed
    inference_p95_ms = Get-P95 $inferenceLatencies
    callback_p95_ms = $callbackP95
    serial_action_status = $serialActionCount
    serial_action_mismatches = $serialActionMismatches
    risk_band_samples = $bandCounts
    rgb_pattern_samples = $rgbCounts
    fault_recovery = [ordered]@{
        model_stop = "manual_not_run"
        wifi_disconnect = "manual_not_run"
        stale_frame_replay = "manual_not_run"
        wrong_token = "manual_not_run"
    }
    passed_automatic_window = $failures.Count -eq 0
    failures = $failures
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "E2E report: $OutputPath"
if ($Strict -and $failures.Count -gt 0) {
    exit 1
}
