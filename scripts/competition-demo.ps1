param(
    [string]$Scenario = 'C03',
    [switch]$Approve,
    [switch]$FullPreflight
)

$ErrorActionPreference = 'Stop'
$Scripts = $PSScriptRoot

Write-Host '=== 1/3 START DEMO STACK ==='
& (Join-Path $Scripts 'demo-start.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host '=== 2/3 PREFLIGHT ==='
if ($FullPreflight) {
    & (Join-Path $Scripts 'competition-preflight.ps1') -FullTests
} else {
    & (Join-Path $Scripts 'competition-preflight.ps1')
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host '=== 3/3 RUN E2E ==='
if ($Approve) {
    & (Join-Path $Scripts 'demo-e2e.ps1') -Scenario $Scenario -Approve
} else {
    & (Join-Path $Scripts 'demo-e2e.ps1') -Scenario $Scenario
}