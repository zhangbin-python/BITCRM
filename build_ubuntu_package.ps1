param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRoot = Join-Path $root $OutputDir
$releaseName = "BITCRM-ubuntu-$timestamp"
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

Compress-Archive -Path $stagingDir -DestinationPath $zipPath -Force

Write-Host "Ubuntu package created:"
Write-Host $zipPath
