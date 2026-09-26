param(
    [string]$Scenario = 'C03',
    [int]$WaitSeconds = 480,
    [switch]$Approve
)

$ErrorActionPreference = 'Stop'
$Lab = 'http://127.0.0.1:8080'
$Ops = 'http://127.0.0.1:8088'

function Get-RunState([int]$IssueNumber) {
    try { return Invoke-RestMethod -Uri "$Ops/runs/$IssueNumber" -TimeoutSec 10 } catch { return $null }
}

Write-Host '=== OpsSwarm Competition E2E Demo ==='
$scenarioData = Invoke-RestMethod -Uri "$Lab/api/scenarios/$Scenario" -TimeoutSec 10
Write-Host ('Scenario: ' + $Scenario + ' - ' + $scenarioData.name)
Write-Host ('Service: ' + $scenarioData.service + ' | Fault: ' + $scenarioData.fault)

$body = @{
    scenario_id = $Scenario
    service = $scenarioData.service
    fault = $scenarioData.fault
    duration_seconds = 900
    auto_reset = $false
    metadata = @{ demo = 'competition-e2e'; requested_by = 'demo-e2e.ps1' }
} | ConvertTo-Json -Depth 8

$start = Invoke-RestMethod -Method Post -Uri "$Lab/api/faults/inject" -ContentType 'application/json' -Body $body -TimeoutSec 90
if ($start.fault_verification.status -ne 'PASS') { throw 'IncidentLab did not verify a real runtime fault.' }
$issue = $start.opsswarm.issue_number
if (-not $issue) { $issue = $start.github.issue_number }
if (-not $issue) { throw 'No GitHub Issue was created.' }
$repo = (Invoke-RestMethod -Uri "$Lab/api/integrations/github" -TimeoutSec 10).repo

Write-Host ''
Write-Host ('Verified fault run: ' + $start.run_id)
Write-Host ('GitHub Issue #' + $issue)
Write-Host ('https://github.com/' + $repo + '/issues/' + $issue)

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$run = $null
$approved = $false
$lastState = ''

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $run = Get-RunState $issue
    if (-not $run) { continue }

    if ($run.state -ne $lastState) {
        $lastState = $run.state
        Write-Host ('[' + (Get-Date -Format 'HH:mm:ss') + '] state=' + $run.state + ' tasks=' + @($run.tasks).Count + ' findings=' + @($run.findings).Count + ' RCA=' + [bool]$run.root_cause + ' plan=' + [bool]$run.recovery_plan + ' verification=' + [bool]$run.verification)
    }

    if ($run.state -eq 'WAITING_APPROVAL') {
        $option = @($run.decision.options) | Select-Object -First 1
        if (-not $option) { throw 'WAITING_APPROVAL has no remediation option.' }
        $command = '/opsswarm approve ' + $option.id
        Write-Host ('Human approval required: ' + $command)
        if ($Approve -and -not $approved) {
            gh issue comment $issue --repo $repo --body $command | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not post GitHub approval comment.' }
            $approved = $true
            Write-Host 'Approval comment posted. Local GitHub polling fallback will process it.'
        } elseif (-not $Approve) {
            Write-Host 'Waiting for a human to post the command above on GitHub...'
        }
    }

    if ($run.state -eq 'WAITING_INPUT') {
        Write-Host ('Human input required: ' + $run.decision.question)
        if ($Approve) { throw 'Automated demo stopped at WAITING_INPUT; RCA confidence was insufficient.' }
    }

    if ($run.state -in @('RESOLVED','FAILED','ABORTED')) { break }
}

if (-not $run) { throw 'No OpsSwarm run was observed.' }
if ($run.state -notin @('RESOLVED','FAILED','ABORTED')) { throw ('Timed out in state ' + $run.state) }

$labEvidence = Invoke-RestMethod -Uri "$Lab/api/evidence/$($start.run_id)" -TimeoutSec 15
$issueState = gh issue view $issue --repo $repo --json state --jq '.state'

Write-Host ''
Write-Host '=== FINAL DEMO RESULT ==='
Write-Host ('OpsSwarm state: ' + $run.state)
Write-Host ('GitHub Issue state: ' + $issueState)
Write-Host ('Investigation tasks: ' + @($run.tasks).Count)
Write-Host ('Findings: ' + @($run.findings).Count)
if ($run.root_cause) { Write-Host ('RCA: ' + $run.root_cause.root_cause + ' | confidence=' + $run.root_cause.confidence) }
if ($run.execution) { Write-Host ('Recovery: success=' + $run.execution.success + ' | ' + $run.execution.summary) }
if ($run.verification) { Write-Host ('S7 verified=' + $run.verification.verified + ' | confidence=' + $run.verification.confidence) }
if ($labEvidence.verification) { Write-Host ('IncidentLab verification=' + $labEvidence.verification.status) }

if ($run.state -ne 'RESOLVED') { throw ('Demo failed with OpsSwarm state ' + $run.state) }
if ($run.verification -and -not $run.verification.verified) { throw 'OpsSwarm reached RESOLVED without S7 verification.' }
Write-Host 'DEMO PASS: fault -> GitHub -> parallel investigation -> RCA -> human gate -> recovery -> independent verification -> resolved.'