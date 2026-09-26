param(
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'
$LabRoot = Split-Path $PSScriptRoot -Parent
Set-Location $LabRoot

if (-not (Test-Path '.env')) {
    throw 'Missing .env. Copy .env.example to .env and configure GITHUB_TOKEN, OPENCLAW_GATEWAY_TOKEN and MINIMAX_API_KEY.'
}
$envMap = @{}
Get-Content '.env' | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object {
    $key,$value = $_.Split('=',2)
    $envMap[$key] = $value.Trim()
}
foreach ($required in @('GITHUB_TOKEN','OPENCLAW_GATEWAY_TOKEN','MINIMAX_API_KEY')) {
    if (-not $envMap.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($envMap[$required])) {
        throw "$required is empty in .env"
    }
}

Write-Host '=== Starting unified OpsSwarm Docker stack ==='
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

$deadline = (Get-Date).AddSeconds($WaitSeconds)
foreach ($service in @('openclaw','opsswarm','incidentlab')) {
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $cid = (docker compose ps -q $service).Trim()
        if ($cid) {
            $status = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $cid).Trim()
            if ($status -in @('healthy','running')) { $ready = $true; break }
            if ($status -in @('unhealthy','exited','dead')) {
                docker compose logs --tail=120 $service | Out-Host
                throw "$service entered state $status"
            }
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "Timed out waiting for $service" }
}

Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/reset' -TimeoutSec 45 | Out-Null
$lab = Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 10
$ops = Invoke-RestMethod 'http://127.0.0.1:8088/health' -TimeoutSec 10
$github = Invoke-RestMethod 'http://127.0.0.1:8080/api/integrations/github' -TimeoutSec 10

Write-Host ''
Write-Host '=== DEMO STACK READY ==='
Write-Host ('IncidentLab: ' + $lab.ok)
Write-Host ('OpsSwarm: ' + $ops.ok)
Write-Host ('GitHub: ' + $github.issue_creation + ' | ' + $github.repo)
Write-Host 'OpenClaw: containerized, MiniMax-M2.7-highspeed'
Write-Host 'Web demo: http://localhost:8080/'
Write-Host 'OpsSwarm API: http://localhost:8088/health'
