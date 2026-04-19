param(
    [string]$EngineRoot = ""
)

$ErrorActionPreference = "Stop"

$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PluginDir)
$PythonDir = Join-Path $PluginDir "Content\Python"
$VenvDir = Join-Path $PythonDir ".venv"
$ReqFile = Join-Path $PythonDir "requirements_streamlit.txt"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " MaterialAnalyzer - Python Environment Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$ueRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'UnrealEditor.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($ProjectRoot) }
if ($ueRunning) {
    Write-Host "ERROR: Unreal Editor is running for this project. Please close UE before setup." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ReqFile)) {
    Write-Host "ERROR: requirements file not found: $ReqFile" -ForegroundColor Red
    exit 1
}

$UEPython = $null

if ($EngineRoot -ne "") {
    $candidate = Join-Path $EngineRoot "Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
    if (Test-Path $candidate) {
        $UEPython = $candidate
        Write-Host "[engine param] $UEPython" -ForegroundColor DarkGray
    }
}

if (-not $UEPython) {
    $uproject = Get-ChildItem -Path $ProjectRoot -Filter "*.uproject" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($uproject) {
        try {
            $obj = Get-Content $uproject.FullName -Raw | ConvertFrom-Json
            $engineVer = $obj.EngineAssociation
            if ($engineVer) {
                $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineVer"
                try {
                    $reg = Get-ItemProperty $regPath -ErrorAction Stop
                    if ($reg.InstalledDirectory) {
                        $candidate = Join-Path $reg.InstalledDirectory "Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
                        if (Test-Path $candidate) {
                            $UEPython = $candidate
                            Write-Host "[registry HKLM] $UEPython" -ForegroundColor DarkGray
                        }
                    }
                } catch {}

                if (-not $UEPython) {
                    try {
                        $builds = Get-ItemProperty "HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds" -ErrorAction Stop
                        $builds.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object {
                            if (-not $UEPython) {
                                $buildPath = $_.Value
                                if ($_.Name -eq $engineVer -or $buildPath -match [regex]::Escape($engineVer)) {
                                    $candidate = Join-Path $buildPath "Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
                                    if (Test-Path $candidate) {
                                        $UEPython = $candidate
                                        Write-Host "[registry HKCU] $UEPython" -ForegroundColor DarkGray
                                    }
                                }
                            }
                        }
                    } catch {}
                }
            }
        } catch {}
    }
}

if (-not $UEPython -and $env:UE_ENGINE_DIR) {
    $candidate = Join-Path $env:UE_ENGINE_DIR "Binaries\ThirdParty\Python3\Win64\python.exe"
    if (Test-Path $candidate) {
        $UEPython = $candidate
        Write-Host "[env UE_ENGINE_DIR] $UEPython" -ForegroundColor DarkGray
    }
}

if (-not $UEPython) {
    $drives = @("C:", "D:", "E:", "F:")
    $patterns = @(
        "{0}\EpicGame\UE_*",
        "{0}\Program Files\Epic Games\UE_*",
        "{0}\UnrealEngine\UE_*"
    )
    foreach ($drive in $drives) {
        if (-not (Test-Path "$drive\")) { continue }
        foreach ($pattern in $patterns) {
            $glob = $pattern -f $drive
            $dirs = Get-ChildItem -Path $glob -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            foreach ($dir in $dirs) {
                $candidate = Join-Path $dir.FullName "Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
                if (Test-Path $candidate) {
                    $UEPython = $candidate
                    Write-Host "[disk scan] $UEPython" -ForegroundColor DarkGray
                    break
                }
            }
            if ($UEPython) { break }
        }
        if ($UEPython) { break }
    }
}

if (-not $UEPython) {
    Write-Host "ERROR: Could not locate Unreal Engine python.exe" -ForegroundColor Red
    Write-Host "Try: .\setup_python_env.ps1 -EngineRoot '<UE_ROOT_PATH>'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found UE Python: $UEPython" -ForegroundColor Green
$version = & $UEPython --version 2>&1
Write-Host "Version: $version" -ForegroundColor Green
Write-Host ""

Write-Host "[1/3] Creating virtual environment..." -ForegroundColor Yellow

function Stop-VenvProcesses {
    param([string]$VenvPath)

    $needle = $VenvPath.Replace('\\', '/').ToLowerInvariant()
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match 'python|pip|streamlit' -and
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Replace('\\', '/') -like "*$needle*"
        }

    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped process using venv: PID $($p.ProcessId)" -ForegroundColor DarkGray
        } catch {}
    }
}

if (Test-Path $VenvDir) {
    Write-Host "Removing existing venv..." -ForegroundColor DarkGray
    Stop-VenvProcesses -VenvPath $VenvDir
    try {
        Remove-Item -Recurse -Force $VenvDir -ErrorAction Stop
    } catch {
        Write-Host "Warning: existing venv is locked, will reuse it in-place." -ForegroundColor Yellow
    }
}

$venvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $UEPython -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "Created: $VenvDir" -ForegroundColor Green
} else {
    Write-Host "Reusing existing venv: $VenvDir" -ForegroundColor Green
}
Write-Host ""

$pipExe = Join-Path $VenvDir "Scripts\pip.exe"
if (-not (Test-Path $pipExe)) {
    Write-Host "ERROR: pip.exe not found: $pipExe" -ForegroundColor Red
    exit 1
}

function Invoke-PipInstall {
    param(
        [string]$PipExePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 600
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $PipExePath
    $psi.Arguments = $Arguments -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false

    $proc = [System.Diagnostics.Process]::Start($psi)
    $exited = $proc.WaitForExit($TimeoutSeconds * 1000)
    if (-not $exited) {
        try { $proc.Kill() } catch {}
        Write-Host "ERROR: pip timed out after $TimeoutSeconds seconds" -ForegroundColor Red
        return 124
    }
    return $proc.ExitCode
}

Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
$argsOnline = @('install', '-r', "`"$ReqFile`"", '--retries', '3', '--timeout', '120', '--progress-bar', 'on')
$exitCode = Invoke-PipInstall -PipExePath $pipExe -Arguments $argsOnline -TimeoutSeconds 900
if ($exitCode -ne 0) {
    Write-Host "ERROR: dependency installation failed (exit=$exitCode)" -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed" -ForegroundColor Green
Write-Host ""

Write-Host "[3/3] Verifying imports..." -ForegroundColor Yellow
& $venvPython -c "import streamlit,requests,pandas; print('deps_ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: dependency verify failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Cyan
Write-Host "You can now open Unreal Editor without runtime dependency install." -ForegroundColor Cyan
