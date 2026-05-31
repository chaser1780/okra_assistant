$script:rebuildRequested = $false
$script:autoRebuildWhenChanged = $true
foreach ($arg in $args) {
    if ($arg -eq '-Rebuild' -or $arg -eq '--rebuild') {
        $script:rebuildRequested = $true
    }
    if ($arg -eq '-AutoRebuildWhenChanged' -or $arg -eq '--auto-rebuild-when-changed') {
        $script:autoRebuildWhenChanged = $true
    }
}
if ($env:OKRA_DESKTOP_REBUILD -in @('1', 'true', 'TRUE', 'yes', 'YES')) {
    $script:rebuildRequested = $true
}
if ($env:OKRA_DESKTOP_AUTO_REBUILD -in @('1', 'true', 'TRUE', 'yes', 'YES')) {
    $script:autoRebuildWhenChanged = $true
}

$agentHome = $PSScriptRoot
$webApiPath = Join-Path $agentHome 'app\web_api.py'
$frontendDir = Join-Path $agentHome 'frontend'
$tempDir = Join-Path $agentHome 'temp'
$cacheDir = Join-Path $agentHome 'cache\pycache'
$logDir = Join-Path $agentHome 'logs\desktop'
New-Item -ItemType Directory -Force -Path $tempDir, $cacheDir, $logDir | Out-Null
$env:FUND_AGENT_HOME = $agentHome
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = $cacheDir
$env:PYTHONIOENCODING = 'utf-8'
$projectCargoBin = Join-Path $agentHome 'tools\cargo\bin'
if ((Test-Path $projectCargoBin) -and ($env:Path -notlike "*$projectCargoBin*")) {
    $env:Path = "$projectCargoBin;$env:Path"
}

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
$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$logPath = Join-Path $logDir ("desktop_" + $timestamp + ".log")
$workbenchExe = Join-Path $frontendDir 'src-tauri\target\release\okra-workbench.exe'

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not (Test-Path $frontendDir)) {
    "Tauri/React frontend is unavailable. Install Node.js dependencies or restore the frontend directory." | Tee-Object -FilePath $logPath
    exit 1
}
if (-not $npmCommand) {
    if ((Test-Path $workbenchExe) -and -not $script:rebuildRequested -and -not $script:autoRebuildWhenChanged) {
        "Node/npm is unavailable; using existing OKRA Workbench executable: $workbenchExe" | Tee-Object -FilePath $logPath
    } else {
        "Node/npm is unavailable. Install Node.js or use an existing executable without -Rebuild." | Tee-Object -FilePath $logPath
        exit 1
    }
}

$apiLogPath = Join-Path $logDir ("web_api_" + $timestamp + ".log")
$apiErrPath = Join-Path $logDir ("web_api_" + $timestamp + ".err.log")
$frontendLogPath = Join-Path $logDir ("frontend_" + $timestamp + ".log")
$frontendErrPath = Join-Path $logDir ("frontend_" + $timestamp + ".err.log")

function Test-WorkbenchNeedsBuild {
    param(
        [string]$FrontendRoot,
        [string]$ExecutablePath
    )

    if (-not (Test-Path $ExecutablePath)) {
        return $true
    }

    $exeTime = (Get-Item $ExecutablePath).LastWriteTimeUtc
    $sourcePaths = @(
        (Join-Path $FrontendRoot 'src'),
        (Join-Path $FrontendRoot 'src-tauri\src'),
        (Join-Path $FrontendRoot 'src-tauri\icons'),
        (Join-Path $FrontendRoot 'src-tauri\Cargo.toml'),
        (Join-Path $FrontendRoot 'src-tauri\build.rs'),
        (Join-Path $FrontendRoot 'src-tauri\tauri.conf.json'),
        (Join-Path $FrontendRoot 'package.json'),
        (Join-Path $FrontendRoot 'package-lock.json'),
        (Join-Path $FrontendRoot 'index.html'),
        (Join-Path $FrontendRoot 'tsconfig.json'),
        (Join-Path $FrontendRoot 'vite.config.ts'),
        (Join-Path $FrontendRoot 'tailwind.config.js'),
        (Join-Path $FrontendRoot 'postcss.config.js')
    )

    foreach ($path in $sourcePaths) {
        if (-not (Test-Path $path)) {
            continue
        }
        $item = Get-Item $path
        if ($item.PSIsContainer) {
            $newer = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike '*\target\*' -and $_.LastWriteTimeUtc -gt $exeTime } |
                Select-Object -First 1
            if ($newer) {
                return $true
            }
        } elseif ($item.LastWriteTimeUtc -gt $exeTime) {
            return $true
        }
    }

    return $false
}

function Get-ProcessExitCode {
    param([System.Diagnostics.Process]$Process)

    Wait-Process -Id $Process.Id
    $Process.Refresh()
    if ($null -eq $Process.ExitCode) {
        return 0
    }
    return [int]$Process.ExitCode
}

function Get-ProcessUsingPath {
    param([string]$ExecutablePath)

    $resolved = $null
    try {
        $resolved = (Resolve-Path $ExecutablePath -ErrorAction Stop).Path
    } catch {
        return $null
    }
    return Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and ([string]::Equals($_.Path, $resolved, [System.StringComparison]::OrdinalIgnoreCase))
        } catch {
            $false
        }
    } | Select-Object -First 1
}

function Stop-ExistingDesktopHelpers {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*$webApiPath*" -or
        $_.CommandLine -like "*$frontendDir*node_modules*\\vite\\bin\\vite.js*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Test-OkraApi {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ne 200) {
            return $false
        }
        $payload = $response.Content | ConvertFrom-Json
        if ($payload.ok -and $payload.data.app -eq 'okra-assistant') {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Wait-OkraApi {
    param([int]$Attempts = 20)

    for ($i = 0; $i -lt $Attempts; $i++) {
        if (Test-OkraApi) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Start-ManagedOkraApi {
    Stop-ExistingDesktopHelpers
    $apiArgs = @($pythonCommand.Prefix) + @('-B', '-X', 'utf8', $webApiPath, '--home', $agentHome)
    $process = Start-Process -FilePath $pythonCommand.Exe -ArgumentList $apiArgs -WorkingDirectory $agentHome -WindowStyle Hidden -RedirectStandardOutput $apiLogPath -RedirectStandardError $apiErrPath -PassThru
    if (-not (Wait-OkraApi)) {
        "OKRA web API did not become healthy. See $apiErrPath" | Tee-Object -FilePath $logPath -Append
    }
    return $process
}

function Ensure-ApiForRunningWorkbench {
    if (Test-OkraApi) {
        "Existing OKRA web API is healthy; preserving it for the running Workbench." | Tee-Object -FilePath $logPath -Append
        return $null
    }
    "Running Workbench found but OKRA web API is unavailable; starting a replacement API." | Tee-Object -FilePath $logPath -Append
    return Start-ManagedOkraApi
}

$cargoCommand = Get-Command cargo -ErrorAction SilentlyContinue
$frontendExit = 1
$apiProcess = $null

if ($npmCommand -and -not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Push-Location $frontendDir
    & $npmCommand.Source install *> $frontendLogPath
    $installExit = $LASTEXITCODE
    Pop-Location
    if ($installExit -ne 0) {
        "npm install failed. See $frontendLogPath" | Tee-Object -FilePath $logPath
        exit $installExit
    }
}

try {
    Push-Location $frontendDir
    if ($cargoCommand -or (Test-Path $workbenchExe)) {
        $needsBuild = $script:rebuildRequested -or (-not (Test-Path $workbenchExe))
        $buildBlocked = $false
        if ($needsBuild -and -not $cargoCommand) {
            "Cargo is unavailable and OKRA Workbench needs a rebuild. Install Rust/Cargo or use an existing executable." | Tee-Object -FilePath $logPath
            $buildBlocked = $true
            $frontendExit = 1
        }
        if (-not $buildBlocked -and -not $needsBuild -and $script:autoRebuildWhenChanged) {
            if ($cargoCommand) {
                $needsBuild = Test-WorkbenchNeedsBuild -FrontendRoot $frontendDir -ExecutablePath $workbenchExe
            } else {
                "Cargo is unavailable; skipping source freshness scan and using existing executable." | Tee-Object -FilePath $logPath
            }
        }
        $runningWorkbench = if (Test-Path $workbenchExe) { Get-ProcessUsingPath -ExecutablePath $workbenchExe } else { $null }
        if (-not $buildBlocked -and $needsBuild -and $runningWorkbench -and -not $script:rebuildRequested) {
            "OKRA Workbench is already running (PID $($runningWorkbench.Id)); skipping rebuild of locked executable." | Tee-Object -FilePath $logPath
            "Close the running app and use .\run_desktop_app.ps1 -Rebuild to force a rebuild." | Tee-Object -FilePath $logPath -Append
            $needsBuild = $false
        }
        if ($buildBlocked) {
            $frontendExit = 1
        } elseif ($needsBuild -and $cargoCommand) {
            "Building OKRA Workbench..." | Tee-Object -FilePath $logPath
            $buildProcess = Start-Process -FilePath $npmCommand.Source -ArgumentList @('run', 'build') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput $frontendLogPath -RedirectStandardError $frontendErrPath -PassThru
            $buildExit = Get-ProcessExitCode -Process $buildProcess
            if ($buildExit -ne 0) {
                $frontendExit = $buildExit
            } else {
                $cargoLogPath = Join-Path $logDir ("tauri_" + $timestamp + ".log")
                $cargoErrPath = Join-Path $logDir ("tauri_" + $timestamp + ".err.log")
                $tauriProcess = Start-Process -FilePath $npmCommand.Source -ArgumentList @('run', 'tauri', '--', 'build', '--no-bundle') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput $cargoLogPath -RedirectStandardError $cargoErrPath -PassThru
                $frontendExit = Get-ProcessExitCode -Process $tauriProcess
            }
        } else {
            "Using existing OKRA Workbench executable: $workbenchExe" | Tee-Object -FilePath $logPath
            if (-not $script:autoRebuildWhenChanged) {
                "Fast startup mode: skipped source freshness scan. Use .\run_desktop_app.ps1 -Rebuild after frontend or Tauri changes." | Tee-Object -FilePath $logPath -Append
            } else {
                "Source freshness scan passed. Use .\run_desktop_app.ps1 -Rebuild to force a rebuild." | Tee-Object -FilePath $logPath -Append
            }
            $frontendExit = 0
        }

        if ($frontendExit -eq 0) {
            if ($runningWorkbench -and -not $script:rebuildRequested) {
                $apiProcess = Ensure-ApiForRunningWorkbench
                "OKRA Workbench is already running (PID $($runningWorkbench.Id)); leaving the current window in place." | Tee-Object -FilePath $logPath -Append
                Wait-Process -Id $runningWorkbench.Id
                $frontendExit = 0
            } elseif (Test-Path $workbenchExe) {
                $apiProcess = Start-ManagedOkraApi
                $appProcess = Start-Process -FilePath $workbenchExe -WorkingDirectory $agentHome -PassThru
                Wait-Process -Id $appProcess.Id
                $frontendExit = $appProcess.ExitCode
            } else {
                "Tauri executable not found: $workbenchExe" | Tee-Object -FilePath $logPath
                $frontendExit = 1
            }
        }
    } else {
        $apiProcess = Start-ManagedOkraApi
        $frontendProcess = Start-Process -FilePath $npmCommand.Source -ArgumentList @('run', 'dev') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput $frontendLogPath -RedirectStandardError $frontendErrPath -PassThru
        Start-Sleep -Seconds 3
        Start-Process 'http://127.0.0.1:5173'
        Wait-Process -Id $frontendProcess.Id
        $frontendExit = $frontendProcess.ExitCode
    }
} finally {
    Pop-Location
    if ($apiProcess) {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
exit $frontendExit
