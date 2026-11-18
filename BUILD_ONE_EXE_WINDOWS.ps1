$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'py' }
if ($python -eq 'py') { & py -3 tools\build_release.py }
else { & $python tools\build_release.py }
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
