param(
    [switch]$FullTests
)

$ErrorActionPreference = 'Stop'
$LabRoot = Split-Path $PSScriptRoot -Parent
$failures = @()
Set-Location $LabRoot

function Check([string]$Name, [scriptblock]$Action) {
    try {
        & $Action
        Write-Host ("[PASS] " + $Name)
    } catch {
        $script:failures += "$Name :: $($_.Exception.Message)"
        Write-Host ("[FAIL] " + $Name + " :: " + $_.Exception.Message)
    }
}

Write-Host '=== OpsSwarm Competition Demo Preflight ==='

Check 'IncidentLab HTTP health' {
    $h = Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 8
    if (-not $h.ok) { throw 'IncidentLab health returned ok=false' }
}

Check 'OpsSwarm HTTP health' {
    $h = Invoke-RestMethod 'http://127.0.0.1:8088/health' -TimeoutSec 8
    if (-not $h.ok) { throw 'OpsSwarm health returned ok=false' }
}

Check 'IncidentLab services baseline healthy' {
    $services = @(Invoke-RestMethod 'http://127.0.0.1:8080/api/services' -TimeoutSec 15)
    $bad = @($services | Where-Object { -not $_.healthy })
    if ($bad.Count -gt 0) { throw ('Unhealthy services: ' + (($bad.service) -join ', ')) }
}

Check 'GitHub issue integration' {
    $g = Invoke-RestMethod 'http://127.0.0.1:8080/api/integrations/github' -TimeoutSec 8
    if (-not $g.enabled -or $g.issue_creation -ne 'ready') { throw 'GitHub integration is not ready' }
}

Check 'IncidentLab -> OpsSwarm integration' {
    $o = Invoke-RestMethod 'http://127.0.0.1:8080/api/integrations/opsswarm' -TimeoutSec 8
    if (-not $o.enabled -or $o.http_status -ge 400) { throw 'OpsSwarm integration is not reachable' }
}

Check 'Containerized OpenClaw Gateway' {
    docker compose exec -T openclaw curl -fsS http://127.0.0.1:18789/healthz *> $null
    if ($LASTEXITCODE -ne 0) { throw 'OpenClaw container health probe failed' }
}

Check 'OpenClaw recovery workspace permissions' {
    docker compose exec -T openclaw sh -lc 'test ! -w /opt/opsswarm/workspaces/opsswarm-application-investigator/project/incidentlab/api.py && test -w /opt/opsswarm/workspaces/opsswarm-recovery-responder/project/incidentlab/api.py && test ! -w /opt/opsswarm/workspaces/opsswarm-recovery-responder/project/runtime-data'
    if ($LASTEXITCODE -ne 0) { throw 'OpenClaw RO/RW workspace policy is not enforced' }
}

Check 'S1-S8 packaged skills' {
    $expected = @(
        's1-intent-guard','s2-task-graph','s3-horizon-plan','s4-role-dispatch',
        's5-collab-exec','s6-resilience-guard','s7-observe-verify','s8-orchestration-hub'
    )
    foreach ($skill in $expected) {
        $path = Join-Path $LabRoot "platform\openclaw\skills\$skill\SKILL.md"
        if (-not (Test-Path $path)) { throw "Missing $skill/SKILL.md" }
        $text = Get-Content $path -Raw
        if ($text -notmatch '(?m)^name:\s*' -or $text -notmatch '(?m)^description:\s*') {
            throw "$skill has invalid frontmatter"
        }
    }
}

Check 'OpenClaw specialist model call' {
    $raw = docker compose exec -T openclaw openclaw agent --agent opsswarm-observability-investigator -m 'Reply with the single word READY' --json --timeout 60
    if ($LASTEXITCODE -ne 0) { throw 'OpenClaw agent call failed' }
    $joined = ($raw -join [Environment]::NewLine)
    $data = $joined | ConvertFrom-Json
    if ($data.status -ne 'ok') { throw 'OpenClaw agent status is not ok' }
}

if ($FullTests) {
    Check 'IncidentLab pytest' {
        python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'IncidentLab pytest failed' }
    }

    Check 'Packaged OpsSwarm compile' {
        python -m compileall -q platform\opsswarm\opsswarm
        if ($LASTEXITCODE -ne 0) { throw 'Packaged OpsSwarm compile failed' }
    }
}

Write-Host ''
if ($failures.Count -gt 0) {
    Write-Host '=== PREFLIGHT FAILED ==='
    $failures | ForEach-Object { Write-Host ('- ' + $_) }
    exit 1
}

Write-Host '=== PREFLIGHT PASS ==='
Write-Host 'Unified Docker environment is ready for the OpsSwarm competition demo.'
