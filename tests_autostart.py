# -*- coding: utf-8 -*-
"""Startup regressions: auto-start the USB engine but never double-start."""
from __future__ import annotations
from types import SimpleNamespace
import unittest

from settings_gui import SettingsWindow
from turzx_dashboard import DEFAULTS
from version_info import APP_VERSION


class StartupTests(unittest.TestCase):
    def editor(self, *, enabled=True, runtime=None):
        window=SettingsWindow.__new__(SettingsWindow)
        window.vars={'auto_start_display':SimpleNamespace(get=lambda:enabled)}
        starts=[]
        afters=[]
        window.runtime_state=lambda:runtime
        window.start=lambda **kwargs:starts.append(('start',kwargs.get('save_before_launch',True)))
        window.root=SimpleNamespace(after=lambda ms,callback:afters.append((ms,callback)))
        return window,starts,afters

    def test_default_is_autostart(self):
        self.assertTrue(DEFAULTS['auto_start_display'])

    def test_no_engine_starts_immediately(self):
        win,started,callbacks=self.editor(runtime=None)
        win._autostart_engine()
        self.assertEqual(started,[('start',False)])
        self.assertEqual(callbacks,[])

    def test_already_running_current_engine_not_duplicated(self):
        win,started,callbacks=self.editor(runtime={'app_version':APP_VERSION})
        win._autostart_engine()
        self.assertEqual(started,[])
        self.assertEqual(callbacks,[])

    def test_old_engine_retry_then_new_engine(self):
        win,started,callbacks=self.editor(runtime={'app_version':'3.9.3'})
        win._autostart_engine()
        self.assertEqual(started,[])
        self.assertEqual(callbacks[0][0],500)
        win.runtime_state=lambda:None
        callbacks[0][1]()
        self.assertEqual(started,[('start',False)])

    def test_disabled_autostart_never_starts(self):
        win,started,callbacks=self.editor(enabled=False)
        win._autostart_engine()
        self.assertEqual(started,[])
        self.assertEqual(callbacks,[])

    def test_retry_limit_avoids_infinite_loop(self):
        win,started,callbacks=self.editor(runtime={'app_version':'old'})
        win._autostart_engine(attempt=20)
        self.assertEqual(started,[])
        self.assertEqual(callbacks,[])


if __name__=='__main__':
    unittest.main()
