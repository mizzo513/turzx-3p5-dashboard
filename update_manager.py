# SPDX-License-Identifier: GPL-3.0-or-later
"""Manual, local updater for a portable PyInstaller single EXE.

The update ZIP must contain precisely manifest.json and the app EXE. This
checks integrity, NOT publisher authenticity; install only trusted packages.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

from version_info import APP_ID, APP_VERSION

EXE_NAME = 'TURZX_3p5_Dashboard.exe'
MAX_PACKAGE = 300 * 1024 * 1024


def version_tuple(value):
    value=str(value)
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}',value):
        raise ValueError('バージョン番号の形式が不正です')
    v=tuple(int(x) for x in value.split('.'))
    return v+(0,)*(4-len(v))


def manifest_from_zip(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=2 or set(names)!={'manifest.json',EXE_NAME}:
            raise ValueError('更新ZIP内のファイル構成が不正です')
        exe_info=archive.getinfo(EXE_NAME)
        if not 1024<=exe_info.file_size<=MAX_PACKAGE:
            raise ValueError('EXEサイズが正常範囲外です')
        if archive.getinfo('manifest.json').file_size>8192:
            raise ValueError('manifest.jsonが大きすぎます')
        meta=json.loads(archive.read('manifest.json').decode('utf-8'))
    if not isinstance(meta,dict) or meta.get('app_id')!=APP_ID or meta.get('filename')!=EXE_NAME:
        raise ValueError('TURZX用の更新パッケージではありません')
    if not re.fullmatch(r'[a-f0-9]{64}',str(meta.get('sha256',''))):
        raise ValueError('SHA256指定が不正です')
    if int(meta.get('size',0))!=exe_info.file_size:
        raise ValueError('ファイルサイズがmanifestと一致しません')
    if version_tuple(meta.get('version',''))<=version_tuple(APP_VERSION):
        raise ValueError(f'新しいバージョンではありません（現在 {APP_VERSION}）')
    return meta


def extract_verified(path,destination):
    """Extract only the fixed EXE file to a pre-created local staging path."""
    meta=manifest_from_zip(path)
    sha=hashlib.sha256();written=0
    try:
        with zipfile.ZipFile(path) as archive, archive.open(EXE_NAME) as inp, open(destination,'xb') as out:
            while True:
                data=inp.read(1024*1024)
                if not data:break
                written+=len(data)
                if written>MAX_PACKAGE:raise ValueError('EXEがサイズ上限を超えています')
                sha.update(data);out.write(data)
        if written!=meta['size'] or sha.hexdigest()!=meta['sha256']:
            raise ValueError('EXEのSHA256が一致しません。更新を中止しました')
        with open(destination,'rb') as fh:
            if fh.read(2)!=b'MZ':raise ValueError('EXEヘッダーが不正です')
        return meta
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def clean_frozen_environment(env=None):
    """Avoid passing PyInstaller onefile parent's extracted-temp context to updates.

    New EXE instances must be independent from the parent frozen executable.
    See PyInstaller Common Issues and Pitfalls: PYINSTALLER_RESET_ENVIRONMENT.
    """
    original=os.environ if env is None else env
    clean={key:value for key,value in original.items()
           if not key.upper().startswith('_PYI_') and key.upper() != '_MEIPASS2'}
    clean['PYINSTALLER_RESET_ENVIRONMENT']='1'
    return clean


def preflight_executable(executable, *, timeout=60):
    """Start staged new EXE in isolated environment BEFORE replacing the old one."""
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    try:
        result=subprocess.run(
            [str(executable),'--self-test'],
            env=clean_frozen_environment(),
            cwd=str(Path(executable).parent),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, timeout=timeout, check=False
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'新EXEの事前起動テストに失敗しました: {exc}') from exc
    if result.returncode != 0:
        raise RuntimeError(
            f'新EXEの事前起動テストに失敗しました (exit={result.returncode})。'
            '旧EXEは変更していません。')
    return True


# This script is created temporarily in LOCALAPPDATA, not distributed as a
# second application. The installed program remains a single EXE.
POWERSHELL_APPLY = r'''param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Backup,
    [Parameter(Mandatory=$true)][string]$Hash,
    [Parameter(Mandatory=$true)][string]$Log,
    [switch]$NoLaunch
)
$ErrorActionPreference='Stop'
$done=$false
function Note([string]$s) {
    Add-Content -LiteralPath $Log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$s) -Encoding UTF8
}
function Reset-PyInstallerEnvironment {
    # This PowerShell process is a descendant of the *old* onefile EXE.
    # Do not pass its extracted _MEI directory back into the replacement EXE.
    Get-ChildItem Env: | Where-Object {
        $_.Name -like '_PYI_*' -or $_.Name -eq '_MEIPASS2'
    } | ForEach-Object {
        Remove-Item -LiteralPath ('Env:'+$_.Name) -ErrorAction SilentlyContinue
    }
    $env:PYINSTALLER_RESET_ENVIRONMENT='1'
}
function Sha256Of([string]$File) {
    # Use built-in .NET crypto instead of the optional Get-FileHash cmdlet.
    $stream=[System.IO.File]::OpenRead($File)
    try {
        $sha=[System.Security.Cryptography.SHA256]::Create()
        try {
            return [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant()
        } finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}
function Check-Exe([string]$Path) {
    Reset-PyInstallerEnvironment
    Note ('Validating EXE startup: '+$Path)
    $proc=Start-Process -FilePath $Path -ArgumentList '--self-test' -PassThru -WindowStyle Hidden -WorkingDirectory (Split-Path $Path -Parent)
    if (-not $proc.WaitForExit(60000)) {
        try { $proc.Kill() } catch {}
        throw 'New EXE startup test timed out'
    }
    if ($proc.ExitCode -ne 0) { throw ('New EXE startup test failed (exit '+$proc.ExitCode+')') }
    Note 'New EXE startup test OK'
}
try {
    Reset-PyInstallerEnvironment
    if ((Sha256Of $Source) -ne $Hash.ToLowerInvariant()) {
        throw 'Hash mismatch before replacement'
    }
    Note 'EXE validated. Waiting for previous GUI and USB engine to exit.'
    for ($i=0; $i -lt 120; $i++) {
        try {
            [System.IO.File]::Replace($Source,$Target,$Backup,$true)
            $done=$true
            break
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 500
        } catch [System.UnauthorizedAccessException] {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $done) { throw 'Old EXE is still in use, or target is not writable' }
    Note ('EXE replaced, backup retained: '+$Backup)
    Check-Exe $Target
    if (-not $NoLaunch) {
        Reset-PyInstallerEnvironment
        Start-Process -FilePath $Target -WorkingDirectory (Split-Path $Target -Parent)
        Note 'New independent EXE launched'
    } else {
        Note 'Validated updated EXE without GUI launch (integration test)'
    }
    exit 0
} catch {
    Note ('FAILED: '+$_.Exception.Message)
    if ($done -and (Test-Path -LiteralPath $Backup)) {
        try {
            Copy-Item -LiteralPath $Backup -Destination $Target -Force
            Note 'Old EXE restored from backup after failed startup'
        } catch {
            Note ('Backup restore failed: '+$_.Exception.Message)
        }
    } elseif (-not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
        Copy-Item -LiteralPath $Backup -Destination $Target -Force
        Note 'Missing EXE restored from backup'
    }
    exit 1
}
'''


def start_update_gui(gui):
    root=gui.root
    selected=filedialog.askopenfilename(parent=root,title='TURZX更新ZIPを選択',filetypes=[('更新ZIP','*.zip')])
    if selected:
        install_update_package(gui,selected)


def install_update_package(gui, selected, *, already_confirmed=False, expected_version=None):
    """Install a trusted verified ZIP, selected locally or downloaded from GitHub."""
    root=gui.root
    if not getattr(sys,'frozen',False):
        messagebox.showinfo('更新機能','Pythonソース版ではEXEを置換できません。\nGitHubでEXEをビルドしてからご利用ください。',parent=root)
        return False
    stage=None
    try:
        manifest=manifest_from_zip(selected)
        if expected_version is not None and manifest['version']!=expected_version:
            raise ValueError('GitHubで確認したバージョンとZIPが一致しません')
        if not already_confirmed:
            question=(f"V{APP_VERSION} → V{manifest['version']} に更新しますか？\n\n"
                      '実行中の表示を停止し、旧EXEをバックアップして入れ替えます。\n'
                      '設定・時刻表のユーザーデータは保持します。\n\n'
                      '※発行者の電子署名は確認しません。信頼できるZIPのみ選択してください。')
            if not messagebox.askyesno('アップデートの確認',question,parent=root):return False
        target=Path(sys.executable).resolve()
        if target.name.lower()!=EXE_NAME.lower():
            raise ValueError(f'実行EXE名が異なります: {target.name}')
        if not target.is_file():raise ValueError('更新対象EXEが見つかりません')
        stage=target.parent/f'.turzx_update_{uuid.uuid4().hex}.new.exe'
        extract_verified(selected,stage)
        preflight_executable(stage)
        data_dir=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'TURZXDashboard'/'updates'
        data_dir.mkdir(parents=True,exist_ok=True)
        helper=data_dir/f'apply_{uuid.uuid4().hex}.ps1'
        helper.write_text(POWERSHELL_APPLY,encoding='utf-8-sig')
        backup=target.with_name(f'{target.stem}_backup_v{APP_VERSION}_{uuid.uuid4().hex[:8]}.exe')
        log=data_dir/'updater.log'
        command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                 '-File',str(helper),'-Source',str(stage),'-Target',str(target),
                 '-Backup',str(backup),'-Hash',manifest['sha256'],'-Log',str(log)]
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        from runtime_ipc import request_stop
        request_stop()
        subprocess.Popen(command,cwd=str(target.parent),stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         creationflags=flags,close_fds=True,env=clean_frozen_environment())
        messagebox.showinfo('更新開始','表示ソフトを終了し、新しいEXEへ切り替えます。\n'
                            '元のEXEはバックアップとして保存されます。\n'
                            '失敗した場合は updates\\updater.log を確認してください。',parent=root)
        root.after(100,root.destroy)
        return True
    except Exception as exc:
        if stage is not None:stage.unlink(missing_ok=True)
        messagebox.showerror('アップデート失敗',str(exc),parent=root)
        return False
