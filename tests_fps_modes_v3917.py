# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.17: numeric FPS, fixed/transfer-adaptive scheduler and safe defaults."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from marquee_scheduler import MarqueeScheduler
import turzx_dashboard as app


class MarqueeFPSModesTests(unittest.TestCase):
    def test_default_is_adaptive_ten_fps_to_preserve_old_configuration(self):
        self.assertEqual(app.DEFAULTS['rail_scroll_fps'],10)
        self.assertEqual(app.DEFAULTS['rail_scroll_fps_mode'],'adaptive')
        s=MarqueeScheduler()
        self.assertAlmostEqual(s.interval,.1)
        s.record_transfer(.08)
        self.assertAlmostEqual(s.interval,.12)

    def test_fixed_mode_never_deliberately_slows_due_to_usb_ema(self):
        s=MarqueeScheduler(target_fps=20.0,fps_mode='fixed',
                           pixels_per_second=40)
        s.reset(0)
        self.assertAlmostEqual(s.interval,.05)
        s.record_transfer(.08)
        self.assertAlmostEqual(s.interval,.05)
        s.record_transfer(.3)
        self.assertAlmostEqual(s.interval,.05)
        self.assertEqual(s.candidate(2.05,0,clock_due=True,second_fraction=.98),2)

    def test_adaptive_mode_respects_fps_ceiling_and_backpressure(self):
        for fps in (5.0,10.0,15.0,20.0,30.0):
            with self.subTest(fps=fps):
                s=MarqueeScheduler(target_fps=fps,fps_mode='adaptive')
                s.reset(0)
                self.assertAlmostEqual(s.interval,1/fps)
                s.record_transfer(.08)
                self.assertGreaterEqual(s.interval,1/fps)
                self.assertGreaterEqual(s.interval,.12-1e-8)
                s.record_transfer(.5)
                self.assertLessEqual(s.interval,.8)

    def test_absolute_deadlines_do_not_accumulate_polling_jitter(self):
        s=MarqueeScheduler(target_fps=20,fps_mode='fixed',
                           pixels_per_second=100)
        s.reset(100.0)
        self.assertEqual(s.candidate(102.061,0,clock_due=False,
                                     second_fraction=.06),6)
        # The next deadline remains 102.10 rather than 102.111
        self.assertAlmostEqual(s.next_frame_at,102.10,places=6)
        self.assertIsNone(s.candidate(102.099,6,clock_due=False,
                                     second_fraction=.09))
        self.assertEqual(s.candidate(102.101,6,clock_due=False,
                                     second_fraction=.10),10)
        s.candidate(102.506,10,clock_due=False,second_fraction=.5)
        self.assertAlmostEqual(s.next_frame_at,102.55,places=6)

    def test_mode_change_live_target_and_reset(self):
        s=MarqueeScheduler(target_fps=10,fps_mode='adaptive')
        s.reset(0)
        s.record_transfer(.2)
        self.assertAlmostEqual(s.interval,.3)
        s.target_fps=25
        s.fps_mode='fixed'
        s.reset(10)
        self.assertAlmostEqual(s.interval,.04)
        self.assertEqual(s.sent_frames,0)


class FPSSettingsTests(unittest.TestCase):
    def test_old_saved_json_gets_compatible_defaults(self):
        old={'rail_scroll_speed_px_s':20,'rail_status_enabled':True,
             'weather_city':'津幡町'}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'settings.json'
            path.write_text(json.dumps(old),encoding='utf-8')
            with patch.object(app,'SETTINGS',path):
                saved=app.load_settings()
                self.assertEqual(saved['rail_scroll_fps'],10)
                self.assertEqual(saved['rail_scroll_fps_mode'],'adaptive')

    def test_runtime_accepts_valid_fps_and_rejects_bad_inputs(self):
        original=app.load_settings
        for fps in (1,7.5,15,20,30):
            for mode in ('fixed','adaptive'):
                with self.subTest(fps=fps,mode=mode):
                    conf=copy.deepcopy(app.DEFAULTS)
                    conf.update(rail_scroll_fps=fps,rail_scroll_fps_mode=mode)
                    with patch.object(app,'load_settings',return_value=conf):
                        selected=app.read_live_settings()
                    self.assertEqual(selected['rail_scroll_fps'],float(fps))
                    self.assertEqual(selected['rail_scroll_fps_mode'],mode)
        for fps in (0,-5,31,float('nan'),float('inf'),'oops'):
            conf=copy.deepcopy(app.DEFAULTS)
            conf['rail_scroll_fps']=fps
            with self.subTest(fps=fps),patch.object(app,'load_settings',return_value=conf):
                with self.assertRaises(ValueError):
                    app.read_live_settings()
        conf=copy.deepcopy(app.DEFAULTS)
        conf['rail_scroll_fps_mode']='free'
        with patch.object(app,'load_settings',return_value=conf):
            with self.assertRaises(ValueError):
                app.read_live_settings()


if __name__=='__main__':
    unittest.main()
