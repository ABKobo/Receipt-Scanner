param(
  [string]$Url = 'http://127.0.0.1:8000/',
  [string]$Log = 'monitor.jsonl',
  [int]$Seconds = 30,
  [string]$Version = 'unknown'
)
$ErrorActionPreference = 'Continue'
$stop = (Get-Date).ToUniversalTime().AddSeconds($Seconds)
while ((Get-Date).ToUniversalTime() -lt $stop) {
  $started = (Get-Date).ToUniversalTime()
  $status = 0; $ok = $false; $errorText = ''
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
    $status = [int]$response.StatusCode
    $ok = $status -ge 200 -and $status -lt 500
  } catch { $errorText = $_.Exception.Message }
  $ended = (Get-Date).ToUniversalTime()
  $row = [ordered]@{
    start_utc=$started.ToString('o'); end_utc=$ended.ToString('o')
    elapsed_ms=[int](($ended-$started).TotalMilliseconds)
    status=$status; reachable=$ok; version=$Version; error=$errorText
  }
  ($row | ConvertTo-Json -Compress) | Add-Content -LiteralPath $Log -Encoding UTF8
  Start-Sleep -Seconds 1
}
