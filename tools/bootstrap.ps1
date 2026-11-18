param(
    [Parameter(Mandatory=$true)][string]$Root,
    [switch]$AutoLaunch,
    [switch]$SetupOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = [System.IO.Path]::GetFullPath($Root)
$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$Log = Join-Path $LogDir 'setup_install.log'
$script:Python = $null
$script:Prefix = @()

function Note([string]$message) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message)
    Write-Host $line
    try { Add-Content -LiteralPath $Log -Value $line -Encoding UTF8 } catch {}
}

function Check-Python([string]$exe, [string[]]$prefix) {
    if (-not $exe) { return $false }
    if ($exe -match '(?i)\\WindowsApps\\python(?:3)?\.exe$') { return $false }
    try {
        $code = "import sys, venv, ensurepip, tkinter; assert (3,11) <= sys.version_info[:2] <= (3,14); assert sys.maxsize > 2**32; print(sys.executable)"
        $out = & $exe @prefix -c $code 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $true }
    } catch {}
    return $false
}

function Use-Python([string]$exe, [string[]]$prefix) {
    if (Check-Python $exe $prefix) {
        $script:Python = $exe
        $script:Prefix = $prefix
        Note ('Using Python: ' + $exe + ' ' + ($prefix -join ' '))
        return $true
    }
    return $false
}

function Find-Python {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        'C:\Program Files\Python314\python.exe',
        'C:\Program Files\Python313\python.exe',
        'C:\Program Files\Python312\python.exe',
        'C:\Program Files\Python311\python.exe'
    )
    foreach ($f in $candidates) {
        if ((Test-Path -LiteralPath $f -PathType Leaf) -and (Use-Python $f @())) { return $true }
    }
    # Windows may have multiple Python installations; use a known version, not an arbitrary Store alias.
    $pyCmd = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($tag in @('-3.14', '-3.13', '-3.12', '-3.11')) {
            if (Use-Python $pyCmd.Source @($tag)) { return $true }
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and (Use-Python $cmd.Source @())) { return $true }
    }
    return $false
}

function Install-Python {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'This bundled installer currently targets 64-bit Windows.'
    }
    # Normal install from WinGet, if available.
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Note 'Python not found: trying WinGet (Python.Python.3.14, current-user scope).'
        try {
            & $winget.Source install --id Python.Python.3.14 -e --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
            $exitCode = $LASTEXITCODE
            Note ('WinGet returned: ' + $exitCode)
            if (Find-Python) { return }
        } catch { Note ('WinGet unavailable: ' + $_.Exception.Message) }
    } else { Note 'WinGet is not installed; using the official Python.org installer.' }

    # A pinned official release with published SHA256.
    $version = '3.14.10'
    $file = 'python-3.14.10-amd64.exe'
    $url = 'https://www.python.org/ftp/python/3.14.10/' + $file
    $expectedSHA256 = '92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965'
    $download = Join-Path $env:TEMP $file
    Note ('Downloading official Python installer: ' + $url)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if (-not (Test-Path $download)) { Invoke-WebRequest -Uri $url -OutFile $download -UseBasicParsing }
    $actual = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expectedSHA256) {
        Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
        throw 'The downloaded Python installer SHA256 does not match the official checksum. Installation stopped.'
    }
    $sig = Get-AuthenticodeSignature -FilePath $download
    if ($sig.Status -ne 'Valid') { throw ('Python installer signature is not valid: ' + $sig.Status) }
    Note 'Official file hash and signature verified; installing for current user.'
    $arguments = '/quiet InstallAllUsers=0 PrependPath=0 Include_pip=1 Include_tcltk=1 Include_launcher=1 Include_test=0'
    $p = Start-Process -FilePath $download -ArgumentList $arguments -PassThru -Wait
    Note ('Official installer returned code: ' + $p.ExitCode)
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw ('Python installer failed with exit code ' + $p.ExitCode) }
    if (-not (Find-Python)) { throw 'Python was installed but could not be located. Try signing out and in, then rerun START_HERE.' }
}

function Verify-Environment([string]$venvExe, [switch]$Quiet) {
    $check = Join-Path $Root 'tools\verify_env.py'
    if (-not (Test-Path -LiteralPath $check -PathType Leaf)) {
        throw 'Missing tools\verify_env.py. Extract the complete package.'
    }
    if ($Quiet) {
        & $venvExe $check --quiet
    } else {
        & $venvExe $check | Out-Host
    }
    return ($LASTEXITCODE -eq 0)
}

function Build-Environment {
    $venvExe = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvExe) {
        try {
            & $venvExe -c 'import sys, tkinter, venv; assert sys.version_info >= (3,11)' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment is invalid.' }
        } catch {
            Note 'Existing venv is not functional. Backing it up and rebuilding.'
            $backup = Join-Path $Root ('.venv_invalid_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
            Move-Item -LiteralPath (Join-Path $Root '.venv') -Destination $backup
        }
    }
    if (-not (Test-Path -LiteralPath $venvExe)) {
        Note 'Creating private virtual environment (.venv).'
        $installArgs = @($script:Prefix) + @('-m', 'venv', (Join-Path $Root '.venv'))
        & $script:Python @installArgs | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python virtual environment.' }
    }
    # Avoid broken nested quoting in `python -c` under Windows PowerShell 5.1.
    # Run the separate on-disk verification script as an ordinary Python file.
    Note 'Checking installed dependencies using tools\verify_env.py.'
    if (Verify-Environment $venvExe -Quiet) {
        Note 'Dependencies already installed; reusing existing virtual environment.'
    } else {
        Note 'Installing Pillow and pyserial inside the private environment.'
        & $venvExe -m pip install --disable-pip-version-check --upgrade 'Pillow>=11.3,<14' 'pyserial>=3.5,<4' | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed. Check proxy/internet access.' }
    }
    Note 'Checking imports and generating offline preview.'
    if (-not (Verify-Environment $venvExe)) { throw 'Python package import test failed; check the environment verification output above.' }
    & $venvExe (Join-Path $Root 'turzx_dashboard.py') --preview | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard preview failed. See logs/dashboard.log.' }
    return $venvExe
}

function Configure-Port([string]$venvExe) {
    Note 'Detecting USB35INCHIPSV2 device and configuring port.'
    & $venvExe (Join-Path $Root 'tools\detect_port.py') --settings (Join-Path $Root 'settings.json') | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'COM port detection/configuration failed.' }
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Note ('Configured port: ' + $cfg.port)
    return $cfg.port
}

try {
    Note '==== TURZX v3.6 ONE CLICK SETUP BEGIN ===='
    Note ('Project directory: ' + $Root)
    if (-not (Test-Path (Join-Path $Root 'schedule.json'))) { throw 'schedule.json is missing. Extract the entire ZIP.' }
    if (-not (Test-Path (Join-Path $Root 'turzx_dashboard.py'))) { throw 'turzx_dashboard.py is missing. Extract the entire ZIP.' }
    if (-not (Find-Python)) { Install-Python }
    $venv = Build-Environment
    $port = Configure-Port $venv
    Note '==== SETUP SUCCESS ===='
    if ($AutoLaunch -and -not $SetupOnly) {
        if ($port -eq 'AUTO') {
            Note 'Starting hidden live dashboard (pythonw, no runtime console).'
            $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
            $launcher = Join-Path $Root 'Start_Display_Hidden.vbs'
            Start-Process -FilePath $wscript -ArgumentList ('"' + $launcher + '"') -WorkingDirectory $Root | Out-Null
        } else {
            Note 'Opening the settings GUI (no runtime console).'
            $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
            $launcher = Join-Path $Root 'Open_Live_Settings.vbs'
            Start-Process -FilePath $wscript -ArgumentList ('"' + $launcher + '"') -WorkingDirectory $Root | Out-Null
        }
    }
    Note 'Setup complete. Use run_dashboard_windows.bat or open_settings_windows.bat later.'
    exit 0
} catch {
    Note ('ERROR: ' + $_.Exception.Message)
    Note ('Error type: ' + $_.Exception.GetType().FullName)
    Write-Host ''
    Write-Host 'SETUP FAILED: see logs/setup_install.log' -ForegroundColor Red
    exit 1
}
