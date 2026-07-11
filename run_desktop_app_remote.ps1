$remoteApiBase = $env:OKRA_REMOTE_API_BASE
if (-not $remoteApiBase) {
    $remoteApiBase = $env:VITE_OKRA_API_BASE
}
if (-not $remoteApiBase) {
    throw 'Set OKRA_REMOTE_API_BASE or VITE_OKRA_API_BASE before starting remote mode.'
}

$env:OKRA_DESKTOP_MODE = 'remote'
$env:OKRA_REMOTE_API_BASE = $remoteApiBase
$env:VITE_OKRA_API_BASE = $remoteApiBase

& (Join-Path $PSScriptRoot 'run_desktop_app.ps1') @args
exit $LASTEXITCODE
