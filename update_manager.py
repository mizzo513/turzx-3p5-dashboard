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


# This script is created temporarily in LOCALAPPDATA, not distributed as a
# second application. The installed program remains a single EXE.
POWERSHELL_APPLY = r'''param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Backup,
    [Parameter(Mandatory=$true)][string]$Hash,
    [Parameter(Mandatory=$true)][string]$Log
)
$ErrorActionPreference='Stop'
function Note([string]$s) {
    Add-Content -LiteralPath $Log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$s) -Encoding UTF8
}
try {
    if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash.ToLowerInvariant()) {
        throw 'Hash mismatch before replacement'
    }
    Note 'EXE validated. Waiting for previous GUI and USB engine to exit.'
    $done=$false
    for ($i=0; $i -lt 120; $i++) {
        try {
            # File.Replace is atomic on NTFS; backup is kept next to installed EXE.
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
    Start-Process -FilePath $Target -WorkingDirectory (Split-Path $Target -Parent)
    Note 'New EXE launched successfully'
    exit 0
} catch {
    Note ('FAILED: '+$_.Exception.Message)
    if (-not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
        Copy-Item -LiteralPath $Backup -Destination $Target -Force
        Note 'Backed up EXE restored'
    }
    exit 1
}
'''


def start_update_gui(gui):
    root=gui.root
    if not getattr(sys,'frozen',False):
        messagebox.showinfo('更新機能','Pythonソースで起動中です。更新ZIPは単一EXE版専用です。\nソース版の更新は差分パッチを適用してください。',parent=root)
        return
    selected=filedialog.askopenfilename(parent=root,title='TURZX更新ZIPを選択',filetypes=[('更新ZIP','*.zip')])
    if not selected:return
    stage=None
    try:
        manifest=manifest_from_zip(selected)
        question=(f"V{APP_VERSION} → V{manifest['version']} に更新しますか？\n\n"
                  '実行中の表示を停止し、旧EXEをバックアップして入れ替えます。\n'
                  '設定・時刻表のユーザーデータは保持します。\n\n'
                  '※発行者の電子署名は確認しません。信頼できるZIPのみ選択してください。')
        if not messagebox.askyesno('アップデートの確認',question,parent=root):return
        target=Path(sys.executable).resolve()
        if target.name.lower()!=EXE_NAME.lower():
            raise ValueError(f'実行EXE名が異なります: {target.name}')
        if not target.is_file():raise ValueError('更新対象EXEが見つかりません')
        # Stage beside installed EXE: required by atomic File.Replace.
        stage=target.parent/f'.turzx_update_{uuid.uuid4().hex}.new.exe'
        extract_verified(selected,stage)
        data_dir=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'TURZXDashboard'/'updates'
        data_dir.mkdir(parents=True,exist_ok=True)
        helper=data_dir/f'apply_{uuid.uuid4().hex}.ps1'
        helper.write_text(POWERSHELL_APPLY,encoding='utf-8-sig')
        backup=target.with_name(f'{target.stem}_backup_v{APP_VERSION}.exe')
        log=data_dir/'updater.log'
        command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                 '-File',str(helper),'-Source',str(stage),'-Target',str(target),
                 '-Backup',str(backup),'-Hash',manifest['sha256'],'-Log',str(log)]
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        # Ask the USB engine to release its serial port and executable before replacing.
        from runtime_ipc import request_stop
        request_stop()
        subprocess.Popen(command,cwd=str(target.parent),stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         creationflags=flags,close_fds=True)
        messagebox.showinfo('更新開始','表示ソフトを終了し、新しいEXEへ切り替えます。\n'
                            '元のEXEはバックアップとして保存されます。\n'
                            '更新できなかった場合は「updates\\updater.log」を確認してください。',parent=root)
        root.after(100,root.destroy)
    except Exception as exc:
        if stage is not None:stage.unlink(missing_ok=True)
        messagebox.showerror('アップデート失敗',str(exc),parent=root)
