$agentHome = 'F:\okra_assistant'
$tempDir = Join-Path $agentHome 'temp'
$logDir = Join-Path $agentHome 'logs\tasks'
New-Item -ItemType Directory -Force -Path $tempDir, $logDir | Out-Null
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = (Join-Path $agentHome 'cache\pycache')
$env:PYTHONIOENCODING = 'utf-8'

function Resolve-PythonCommand {
    param([string]$ProjectRoot)

    $projectToml = Join-Path $ProjectRoot 'project.toml'
    $configured = ''
    if (Test-Path $projectToml) {
        $match = Select-String -Path $projectToml -Pattern '^\s*python_executable\s*=\s*"(.+)"\s*$' | Select-Object -First 1
        if ($match -and $match.Matches.Count -gt 0) {
            $configured = $match.Matches[0].Groups[1].Value.Trim()
        }
    }

    $candidates = @()
    if ($env:OKRA_PYTHON_EXE) {
        $candidates += [pscustomobject]@{ Exe = $env:OKRA_PYTHON_EXE; Prefix = @() }
    }
    if ($configured) {
        $candidates += [pscustomobject]@{ Exe = $configured; Prefix = @() }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += [pscustomobject]@{ Exe = $pythonCommand.Source; Prefix = @() }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $candidates += [pscustomobject]@{ Exe = $pyCommand.Source; Prefix = @('-3') }
    }

    foreach ($candidate in $candidates) {
        if (-not $candidate.Exe) {
            continue
        }
        if (Test-Path $candidate.Exe) {
            return $candidate
        }
        $resolved = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if ($resolved) {
            return [pscustomobject]@{ Exe = $resolved.Source; Prefix = $candidate.Prefix }
        }
    }

    throw "Unable to locate a usable Python interpreter. Set OKRA_PYTHON_EXE or project.toml [runtime].python_executable."
}

$pythonCommand = Resolve-PythonCommand -ProjectRoot $agentHome
$env:OKRA_PYTHON_EXE = $pythonCommand.Exe
$runner = 'F:\okra_assistant\scripts\run_report_window.py'
$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$logPath = Join-Path $logDir ("intraday_" + $timestamp + ".log")
& $pythonCommand.Exe @($pythonCommand.Prefix) -B -X utf8 $runner --agent-home $agentHome --mode intraday *> $logPath
exit $LASTEXITCODE
