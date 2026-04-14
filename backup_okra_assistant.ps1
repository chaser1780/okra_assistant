param(
    [string]$ProjectRoot = "F:\okra_assistant",
    [switch]$ExcludeLogs
)

$ErrorActionPreference = "Stop"

$projectPath = [System.IO.Path]::GetFullPath($ProjectRoot)
$backupDir = Join-Path $projectPath "backups"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$stagingDir = Join-Path $backupDir ("staging_" + $timestamp)
$zipPath = Join-Path $backupDir ("okra_assistant_backup_" + $timestamp + ".zip")

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
if (Test-Path $stagingDir) {
    Remove-Item $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

$excludeTop = @("cache", "temp", "backups")
if ($ExcludeLogs) {
    $excludeTop += "logs"
}

Get-ChildItem -Force $projectPath | ForEach-Object {
    if ($excludeTop -contains $_.Name) {
        return
    }
    Copy-Item $_.FullName -Destination $stagingDir -Recurse -Force
}

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $stagingDir -Recurse -Force

Write-Output $zipPath
