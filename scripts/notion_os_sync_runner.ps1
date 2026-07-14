param(
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Mode = if ($Apply) { "apply" } else { "dry_run" }
Write-Host "MECORIA_NOTION_SYNC_MODE: $Mode"

if ($Apply) {
  python agents\notion_os_sync_runner\run.py --apply
} else {
  python agents\notion_os_sync_runner\run.py
}

if ($LASTEXITCODE -ne 0) {
  Write-Error "Notion OS sync runner command failed."
  exit $LASTEXITCODE
}

$RecordPath = "records\system\notion_os_sync_runner_latest.json"

if (!(Test-Path $RecordPath)) {
  Write-Error "Record path missing: $RecordPath"
  exit 1
}

$Record = Get-Content $RecordPath -Raw | ConvertFrom-Json
$ExpectedStatus = if ($Apply) { "os_sync_passed" } else { "os_sync_dry_run_ready" }

Write-Host "MECORIA_NOTION_SYNC_STATUS: $($Record.status)"
Write-Host "MECORIA_NOTION_SYNC_FAILED_STEPS: $($Record.summary.failed_step_count)"

if ($Record.status -ne $ExpectedStatus) {
  Write-Error "Unexpected sync status. Expected $ExpectedStatus but got $($Record.status)"
  exit 1
}

if ($Record.summary.failed_step_count -ne 0) {
  Write-Error "Sync runner failed step count is not zero."
  exit 1
}

Write-Host "MECORIA_NOTION_SYNC_RESULT: ok"
exit 0
