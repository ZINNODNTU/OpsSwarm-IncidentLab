$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent

Get-ChildItem $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('__pycache__','.pytest_cache','.mypy_cache','.ruff_cache') } |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem $Root -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.pyc','.pyo') -or $_.Name -like '*.log' -or $_.Name -like '*.pid' } |
    Remove-Item -Force -ErrorAction SilentlyContinue

$Runtime = Join-Path $Root 'runtime-data'
if (Test-Path $Runtime) {
    Get-ChildItem $Runtime -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'Repository runtime/cache artifacts cleaned. .env was preserved and remains git-ignored.'
