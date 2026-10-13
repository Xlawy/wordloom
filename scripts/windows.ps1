param(
    [ValidateSet('install', 'start', 'validate', 'mock', 'build')]
    [string]$Action = 'start'
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this script in native Windows PowerShell.' }
$Project = Split-Path $PSScriptRoot -Parent
Set-Location $Project
$Python = Join-Path $Project '.venv-win\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if ($Action -eq 'install') {
    if (-not (Test-Path $Python)) {
        if (Test-Path (Join-Path $Project '.venv-win')) {
            throw 'Incomplete .venv-win exists; inspect/rename it before retrying. Nothing was deleted.'
        }
        & py -3.13 -c "import sys; assert sys.platform == 'win32'"
        if ($LASTEXITCODE -ne 0) { throw 'Install native Windows Python 3.13 with the py launcher.' }
        & py -3.13 -m venv .venv-win
        if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    }
}
if (-not (Test-Path $Python)) { throw 'Run windows.ps1 install first. The WSL .venv is never used.' }
& $Python -c "import sys; assert sys.platform == 'win32'"
if ($LASTEXITCODE -ne 0) { throw 'Expected a native Windows Python environment' }
switch ($Action) {
    'install' {
        & $Python -m pip install -e .
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $Python -m pip check
    }
    'start' { & $Python -m wordloom }
    'validate' { & $Python scripts\validate.py --native-credentials --native-hotkeys --output validation\windows }
    'mock' { & $Python scripts\mock_server.py --port 8765 }
    'build' {
        & $Python -m pip install -e '.[build]'
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $Python scripts\build_desktop.py
    }
}
exit $LASTEXITCODE
