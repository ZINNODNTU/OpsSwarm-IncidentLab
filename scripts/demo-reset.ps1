$ErrorActionPreference = 'Stop'
$Base = 'http://127.0.0.1:8080'
Write-Host '=== Resetting IncidentLab services to known-good baseline ==='
$result = Invoke-RestMethod -Method Post -Uri "$Base/api/reset" -TimeoutSec 45
$result | ConvertTo-Json -Depth 12
$services = @(Invoke-RestMethod -Uri "$Base/api/services" -TimeoutSec 15)
$bad = @($services | Where-Object { -not $_.healthy })
if ($bad.Count -gt 0) { throw ('Reset completed but unhealthy services remain: ' + (($bad.service) -join ', ')) }
Write-Host 'All IncidentLab services are healthy.'