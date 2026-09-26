param(
    [string]$Scenario = 'C03',
    [int]$DurationSeconds = 600
)

$ErrorActionPreference = 'Stop'
$Base = 'http://127.0.0.1:8080'

$scenarioData = Invoke-RestMethod -Uri "$Base/api/scenarios/$Scenario" -TimeoutSec 10
$body = @{
    scenario_id = $Scenario
    service = $scenarioData.service
    fault = $scenarioData.fault
    duration_seconds = $DurationSeconds
    auto_reset = $false
    metadata = @{ demo = 'competition'; requested_by = 'demo-run.ps1' }
} | ConvertTo-Json -Depth 8

Write-Host ('Injecting ' + $Scenario + ' :: ' + $scenarioData.name)
$result = Invoke-RestMethod -Method Post -Uri "$Base/api/faults/inject" -ContentType 'application/json' -Body $body -TimeoutSec 60
$result | ConvertTo-Json -Depth 20

$issue = $result.opsswarm.issue_number
if (-not $issue) { $issue = $result.github.issue_number }
if (-not $issue) { throw 'Fault was injected but no GitHub Issue number was returned.' }

Write-Host ''
Write-Host ('GitHub Issue #' + $issue)
$repo = (Invoke-RestMethod -Uri "$Base/api/integrations/github" -TimeoutSec 10).repo
Write-Host ('https://github.com/' + $repo + '/issues/' + $issue)
Write-Host ('IncidentLab run: ' + $result.run_id)
Write-Host 'OpsSwarm is processing the incident in the background.'