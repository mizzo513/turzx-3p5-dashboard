# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows integration test: exercise the real updater under poisoned _PYI_* env.

This intentionally uses copied, identical frozen EXEs and -NoLaunch. It tests
the *replacement path* including backup, self-test, environment reset and log.
It never touches any installed app or runs the interactive GUI.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from update_manager import POWERSHELL_APPLY

PROJECT=Path(__file__).resolve().parent.parent
EXE=PROJECT/'dist'/'TURZX_3p5_Dashboard.exe'


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fd:
        for chunk in iter(lambda:fd.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    if os.name!='nt':
        print('Skipped: Windows integration only')
        return 0
    if not EXE.exists():
        raise FileNotFoundError(EXE)
    with tempfile.TemporaryDirectory(prefix='turzx_upgrade_integration_') as root:
        base=Path(root)
        source=base/'staged.new.exe'
        target=base/'TURZX_3p5_Dashboard.exe'
        backup=base/'previous_backup.exe'
        helper=base/'test_update.ps1'
        log=base/'updater.log'
        source.write_bytes(EXE.read_bytes())
        target.write_bytes(EXE.read_bytes())
        hash_value=sha256(source)
        helper.write_text(POWERSHELL_APPLY,encoding='utf-8-sig')
        env=os.environ.copy()
        # Simulate an updater launched from PyInstaller's old onefile process.
        env['_PYI_APPLICATION_HOME_DIR']=str(base/'old_MEI_directory_that_does_not_exist')
        env['_PYI_ARCHIVE_FILE']=str(target)
        env['_PYI_PARENT_PROCESS_LEVEL']='1'
        env.pop('PYINSTALLER_RESET_ENVIRONMENT',None)
        cmd=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
             '-File',str(helper),'-Source',str(source),'-Target',str(target),
             '-Backup',str(backup),'-Hash',hash_value,'-Log',str(log),'-NoLaunch']
        result=subprocess.run(cmd,env=env,timeout=150,check=False,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        print('Exit:',result.returncode)
        print('Updater log:\n',log.read_text(encoding='utf-8-sig') if log.exists() else '(missing)')
        if result.returncode!=0:
            print(result.stderr,file=sys.stderr)
            raise RuntimeError('Updater integration failed')
        if not target.is_file() or sha256(target)!=hash_value:
            raise AssertionError('Updated target is missing or corrupted')
        if not backup.exists():
            raise AssertionError('Rollback backup was not retained')
        if source.exists():
            raise AssertionError('Staged file should be moved during atomic replacement')
        if 'New EXE startup test OK' not in log.read_text(encoding='utf-8-sig'):
            raise AssertionError('New EXE was not verified after replacement')
        print('Updater Windows integration passed')
    return 0


if __name__=='__main__':
    sys.exit(main())
