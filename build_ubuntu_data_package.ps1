param(
    [string]$OutputDir = "dist",
    [string]$DatabasePath = "instance\\bitcrm.db"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
$dbSource = Join-Path $root $DatabasePath

if (-not (Test-Path $dbSource)) {
    throw "Database file not found: $dbSource"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRoot = Join-Path $root $OutputDir
$releaseName = "BITCRM-ubuntu-with-data-$timestamp"
$stagingDir = Join-Path $outputRoot $releaseName
$zipPath = Join-Path $outputRoot "$releaseName.zip"

$excludePatterns = @(
    '(^|\\)\.git($|\\)',
    '(^|\\)\.playwright-cli($|\\)',
    '(^|\\)venv($|\\)',
    '(^|\\)__pycache__($|\\)',
    '(^|\\)dist($|\\)',
    '(^|\\)instance($|\\)',
    '(^|\\)logs($|\\)',
    '(^|\\)gcm-diagnose\.log$',
    '\.db$',
    '\.log$'
)

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

if (Test-Path $stagingDir) {
    Remove-Item -Recurse -Force $stagingDir
}

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

Get-ChildItem -Path $root -Recurse -Force -File | ForEach-Object {
    $relativePath = $_.FullName.Substring($root.Length).TrimStart('\')
    foreach ($pattern in $excludePatterns) {
        if ($relativePath -match $pattern) {
            return
        }
    }

    $targetPath = Join-Path $stagingDir $relativePath
    $targetDir = Split-Path -Parent $targetPath
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }
    Copy-Item -Path $_.FullName -Destination $targetPath -Force
}

$migrationDir = Join-Path $stagingDir "migration-data"
New-Item -ItemType Directory -Force -Path $migrationDir | Out-Null
Copy-Item -Path $dbSource -Destination (Join-Path $migrationDir "bitcrm.db") -Force

Compress-Archive -Path $stagingDir -DestinationPath $zipPath -Force

Write-Host "Ubuntu data package created:"
Write-Host $zipPath
