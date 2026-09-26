$ErrorActionPreference='Stop'
$LabRoot = Split-Path $PSScriptRoot -Parent
Set-Location $LabRoot

docker compose down --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'docker compose down failed' }
Write-Host 'OpsSwarm Docker stack stopped. OpenClaw state volume was preserved.'
