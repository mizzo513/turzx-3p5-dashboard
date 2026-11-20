# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.8 marquee timing and pixel-accurate partial transfer tests."""
import unittest
from datetime import datetime
from types import SimpleNamespace

from marquee_scheduler import MarqueeScheduler
from turzx_dashboard import (
    DEFAULTS, TZ, Weather, TrainState,
    render_original, render_notice_patch,
)
from PIL import Image


class TestMarqueeScheduler(unittest.TestCase):
    def test_nominal_ten_fps_and_original_travel_speed(self):
        sched=MarqueeScheduler()
        sched.reset(10.0)
        self.assertAlmostEqual(sched.interval,0.1)
        self.assertIsNone(
            sched.candidate(12.09,0,clock_due=False,second_fraction=.09))
        # At 9.4 px/second the first 100ms may have no whole-pixel move.
        self.assertIsNone(
            sched.candidate(12.1,0,clock_due=False,second_fraction=.1))
        at_200ms=sched.candidate(
            12.2,0,clock_due=False,second_fraction=.2)
        self.assertEqual(at_200ms,1)
        self.assertEqual(
            sched.candidate(12.3,at_200ms,clock_due=False,second_fraction=.3),
            2)

    def test_skipped_com_positions_do_not_slow_travel(self):
        sched=MarqueeScheduler()
        sched.reset(0)
        first=sched.candidate(
            2.2,0,clock_due=False,second_fraction=.2)
        self.assertIsNotNone(first)
        # A late transfer can skip candidate positions. The next offset
        # catches up to monotonic elapsed time, not a frame counter.
        later=sched.candidate(
            2.6,first,clock_due=False,second_fraction=.6)
        self.assertGreater(later,first+1)

    def test_second_boundary_is_not_reserved_at_ten_fps(self):
        sched=MarqueeScheduler()
        sched.reset(0)
        at_boundary=sched.candidate(
            2.2,0,clock_due=True,second_fraction=.99)
        self.assertEqual(at_boundary,1)
        self.assertEqual(sched.skipped_frames,0)
        self.assertEqual(
            sched.candidate(
                2.4,at_boundary,clock_due=False,second_fraction=.01),
            3)

    def test_adaptive_fps_on_slow_usb(self):
        sched=MarqueeScheduler()
        sched.reset(0)
        sched.record_transfer(.32)
        self.assertAlmostEqual(sched.interval,.48)
        sched.record_transfer(.02)
        self.assertLess(sched.interval,.48)
        self.assertGreaterEqual(sched.interval,.1)
        sched.reset(5)
        self.assertAlmostEqual(sched.interval,.1)

    def test_disabled_and_reset(self):
        sched=MarqueeScheduler()
        sched.reset(0)
        sched.disable()
        self.assertIsNone(sched.candidate(20,0,clock_due=False,second_fraction=.2))
        sched.reset(20)
        self.assertIsNone(sched.candidate(21,0,clock_due=False,second_fraction=.2))


class TestMarqueeRendering(unittest.TestCase):
    def test_partial_update_matches_full_screen(self):
        now=datetime(2026,11,19,12,30,23,tzinfo=TZ)
        conf=dict(DEFAULTS)
        message='運行情報：IRいしかわ鉄道の列車に遅延が発生しています。'*3
        for offset in (0,1,2,17,149):
            base=render_original(
                now,Weather(),TrainState(),conf,skip_rail_notice=True)
            whole=render_original(
                now,Weather(),TrainState(),conf,
                rail_notice=SimpleNamespace(text=message),
                marquee_px=offset).transpose(Image.Transpose.ROTATE_180)
            patch,x,y=render_notice_patch(base,conf,message,offset)
            self.assertIsInstance(patch,Image.Image)
            expected=whole.crop((x,y,x+patch.width,y+patch.height))
            self.assertEqual(expected.tobytes(),patch.tobytes())
            self.assertLess(patch.width*patch.height,480*320/10)

    def test_partial_update_preserves_custom_panel_colors(self):
        now=datetime(2026,11,19,12,30,23,tzinfo=TZ)
        conf=dict(DEFAULTS)
        conf['panel_styles']={'train':{'fill':'#335577'}}
        conf['text_styles']={'train_notice':{'color':'#FAFAFA'}}
        msg='運行情報テスト'*12
        base=render_original(
            now,Weather(),TrainState(),conf,skip_rail_notice=True)
        whole=render_original(
            now,Weather(),TrainState(),conf,
            rail_notice=SimpleNamespace(text=msg),
            marquee_px=13).transpose(Image.Transpose.ROTATE_180)
        patch,x,y=render_notice_patch(base,conf,msg,13)
        self.assertEqual(patch.tobytes(),
                         whole.crop((x,y,x+patch.width,y+patch.height)).tobytes())


if __name__=='__main__':
    unittest.main()
