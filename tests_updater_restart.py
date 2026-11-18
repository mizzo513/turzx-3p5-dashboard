# -*- coding: utf-8 -*-
"""Regression tests for safe PyInstaller onefile updates and independent restart."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_manager


class FrozenUpdateTests(unittest.TestCase):
    def test_remove_private_pyi_context(self):
        original = {
            'PATH':'C:\\Windows', 'TEMP':'C:\\Temp', '_PYI_APPLICATION_HOME_DIR':'C:\\Temp\\_MEI_old',
            '_PYI_PARENT_PROCESS_LEVEL':'1', '_PYI_ARCHIVE_FILE':'C:\\old.exe',
            '_MEIPASS2':'C:\\old', 'PYINSTALLER_RESET_ENVIRONMENT':'0',
        }
        cleaned=update_manager.clean_frozen_environment(original)
        self.assertEqual(cleaned['PATH'],original['PATH'])
        self.assertEqual(cleaned['TEMP'],original['TEMP'])
        self.assertEqual(cleaned['PYINSTALLER_RESET_ENVIRONMENT'],'1')
        self.assertFalse(any(k.upper().startswith('_PYI_') for k in cleaned))
        self.assertNotIn('_MEIPASS2',cleaned)
        self.assertIn('_PYI_APPLICATION_HOME_DIR',original)

    def test_preflight_launch_has_fresh_environment(self):
        captured={}
        def fake_run(args,**kwargs):
            captured.update(args=args,kwargs=kwargs)
            return subprocess.CompletedProcess(args,0)
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'sample.new.exe'
            with patch.object(update_manager.subprocess,'run',side_effect=fake_run):
                with patch.dict(os.environ,{'_PYI_APPLICATION_HOME_DIR':'old_mei',
                                            '_PYI_PARENT_PROCESS_LEVEL':'1'}):
                    self.assertTrue(update_manager.preflight_executable(exe))
        self.assertEqual(captured['args'][1],'--self-test')
        self.assertEqual(captured['kwargs']['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
        self.assertNotIn('_PYI_APPLICATION_HOME_DIR',captured['kwargs']['env'])
        self.assertEqual(captured['kwargs']['timeout'],60)
        self.assertEqual(captured['kwargs']['stdin'],subprocess.DEVNULL)

    def test_failed_preflight_stops_before_replacement(self):
        with patch.object(update_manager.subprocess,'run',return_value=subprocess.CompletedProcess(['test'],5)):
            with self.assertRaisesRegex(RuntimeError,'事前起動テスト'):
                update_manager.preflight_executable(Path('new.exe'))

    def test_preflight_os_error_is_reported(self):
        with patch.object(update_manager.subprocess,'run',side_effect=OSError('blocked')):
            with self.assertRaisesRegex(RuntimeError,'事前起動テスト'):
                update_manager.preflight_executable(Path('new.exe'))

    def test_helper_guards_against_inherited_temp_path(self):
        script=update_manager.POWERSHELL_APPLY
        self.assertIn('PYINSTALLER_RESET_ENVIRONMENT',script)
        self.assertIn("Reset-PyInstallerEnvironment",script)
        self.assertIn("Remove-Item",script)
        self.assertIn("Check-Exe $Target",script)
        self.assertIn("'--self-test'",script)
        self.assertIn('Old EXE restored from backup',script)
        self.assertIn('Start-Process -FilePath $Target',script)


if __name__=='__main__':
    unittest.main()
