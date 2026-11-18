# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Windows single EXE and offline update ZIP on a Windows PC."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT))
from version_info import APP_VERSION, APP_ID

EXE_NAME='TURZX_3p5_Dashboard.exe'


def main():
    if os.name!='nt':
        raise RuntimeError('Windows向けEXEはWindowsでビルドしてください')
    subprocess.run([sys.executable,'-m','pip','install','--upgrade','pyinstaller>=6.20','pillow>=11','pyserial>=3.5'],check=True)
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
         '--name','TURZX_3p5_Dashboard',
         '--add-data',f'{PROJECT/"schedule.json"};.',
         '--add-data',f'{PROJECT/"fallback_data"};fallback_data',
         '--add-data',f'{PROJECT/"train_schedule.csv"};.',
         '--hidden-import','PIL.ImageTk',
         '--hidden-import','serial.tools.list_ports',
         '--collect-submodules','serial',
         str(PROJECT/'turzx_app.py')]
    subprocess.run(cmd,check=True,cwd=PROJECT)
    exe=PROJECT/'dist'/EXE_NAME
    if not exe.is_file() or exe.stat().st_size<1024:
        raise RuntimeError('EXEの生成結果が見つかりません')
    sha=hashlib.sha256()
    with exe.open('rb') as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b''):
            sha.update(chunk)
    manifest={'app_id':APP_ID,'filename':EXE_NAME,'version':APP_VERSION,
              'size':exe.stat().st_size,'sha256':sha.hexdigest(),
              'created_utc':datetime.now(timezone.utc).isoformat(),
              'format':1}
    update=PROJECT/'dist'/f'TURZX_Update_v{APP_VERSION}.zip'
    with zipfile.ZipFile(update,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        z.write(exe,arcname=EXE_NAME)
    print('\nBuild complete:')
    print(' EXE :',exe)
    print(' ZIP :',update)
    print(' SHA256 :',sha.hexdigest())
    print('The EXE is portable. The update ZIP can be selected in the app settings.')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('BUILD FAILED:',exc,file=sys.stderr)
        sys.exit(1)
