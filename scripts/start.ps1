#requires -Version 5.1
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop first.' }
$engine = & docker info --format '{{.OSType}}' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop, then try again.' }
if (('' + $engine).Trim() -ne 'linux') { throw 'Switch Docker Desktop to Linux containers.' }
if (-not (Test-Path -LiteralPath '.env')) { throw 'Run scripts/init.ps1 first.' }
$values = @{}
foreach ($line in [IO.File]::ReadAllLines((Join-Path $projectRoot '.env'))) {
    if ($line.Trim().StartsWith('#') -or $line -notmatch '=') { continue }
    $parts = $line -split '=', 2
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
}
foreach ($key in @('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')) {
    if (-not $values[$key] -or $values[$key] -in @('CHANGE_ME', 'GENERATE')) { throw ('Fill ' + $key + ' in .env first.') }
}
if ($values['KESTRA_USER'] -notmatch '@') { throw 'KESTRA_USER must be an email address.' }
function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw ('Docker Compose failed: ' + ($ComposeArgs -join ' ')) }
}
Invoke-Compose -ComposeArgs @('version')
Invoke-Compose -ComposeArgs @('config', '--quiet')
if (-not $SkipBuild) { Invoke-Compose -ComposeArgs @('build') }
Invoke-Compose -ComposeArgs @('run', '--rm', '--no-deps', '--user', 'root', 'notebook', 'bash', '-c',
    'chown -R 1000:1000 /workspace /home/analyst/.ivy2 /home/analyst/.ssh; chmod 700 /home/analyst/.ssh')
Invoke-Compose -ComposeArgs @('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '900', 'bootstrap')
Invoke-Compose -ComposeArgs @('up', '-d', '--wait', '--wait-timeout', '900')
Write-Host 'Lakehouse started. Open http://localhost:8888/lab (or NOTEBOOK_PORT from .env).'
Write-Host 'Use JUPYTER_TOKEN from .env. Kestra uses KESTRA_USER / KESTRA_PASSWORD.'
