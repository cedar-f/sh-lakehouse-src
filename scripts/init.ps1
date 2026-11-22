#requires -Version 5.1
param([string]$TimeZone = 'Asia/Ho_Chi_Minh')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$envPath = Join-Path $projectRoot '.env'
if ($TimeZone -notmatch '^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$') {
    throw 'Use an IANA timezone, for example Asia/Ho_Chi_Minh or Etc/UTC.'
}
if (-not (Test-Path -LiteralPath $envPath)) {
    $template = [IO.File]::ReadAllText((Join-Path $projectRoot '.env.example'))
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        foreach ($key in @('JUPYTER_TOKEN', 'RUNNER_TOKEN', 'POSTGRES_PASSWORD', 'KESTRA_PASSWORD')) {
            $bytes = New-Object byte[] 24
            $random.GetBytes($bytes)
            $value = 'V3a' + [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
            $template = $template.Replace($key + '=GENERATE', $key + '=' + $value)
        }
    } finally { $random.Dispose() }
    $template = $template.Replace('TZ=Asia/Ho_Chi_Minh', 'TZ=' + $TimeZone)
    [IO.File]::WriteAllText($envPath, $template, (New-Object Text.UTF8Encoding($false)))
    Write-Host 'Created .env. Fill the four R2_ fields before starting.'
} else {
    Write-Host '.env already exists; kept existing values.'
}
$workspaceSetting = './workspace'
foreach ($line in [IO.File]::ReadAllLines($envPath)) {
    if ($line -match '^\s*WORKSPACE_DIR\s*=(.*)$') { $workspaceSetting = $Matches[1].Trim().Trim('"').Trim("'") }
}
if (-not $workspaceSetting) { $workspaceSetting = './workspace' }
$workspacePath = if ([IO.Path]::IsPathRooted($workspaceSetting)) {
    [IO.Path]::GetFullPath($workspaceSetting)
} else { [IO.Path]::GetFullPath((Join-Path $projectRoot $workspaceSetting)) }
[IO.Directory]::CreateDirectory($workspacePath) | Out-Null
[IO.Directory]::CreateDirectory((Join-Path $workspacePath '.lakehouse')) | Out-Null
Write-Host ('Workspace data directory: ' + $workspacePath)
