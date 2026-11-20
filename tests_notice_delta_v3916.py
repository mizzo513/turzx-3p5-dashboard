# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.16: exact changed-pixel USB rectangles for rail marquee updates.

Every patch must reconstruct the full renderer from the previously displayed
frame, including cleared pixels, alternative fonts, user layout overrides,
180-degree rotation, and no-change frames.
"""
import copy
import unittest
from datetime import datetime
from types import SimpleNamespace

from PIL import ImageChops

from turzx_dashboard import (
    DEFAULTS, TZ, Weather, TrainState, W, H,
    render_original, render_notice_patch, notice_region, rgb565le,
)


class TestAdaptiveNoticeTransfer(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,20,9,22,45,tzinfo=TZ)
        self.conf=copy.deepcopy(DEFAULTS)
        self.weather=Weather()
        self.train=TrainState()

    def physical(self,conf,text,offset):
        return render_original(
            self.now,self.weather,self.train,conf,
            rail_notice=SimpleNamespace(text=text),
            marquee_px=offset).transpose(__import__('PIL.Image',fromlist=['Transpose']).Transpose.ROTATE_180)

    def apply_patch(self,previous,patch,x,y):
        actual=previous.copy()
        if patch is not None:
            self.assertGreater(patch.width,0)
            self.assertGreater(patch.height,0)
            self.assertGreaterEqual(x,0)
            self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+patch.width,W)
            self.assertLessEqual(y+patch.height,H)
            actual.paste(patch,(x,y))
        return actual

    def check_transition(self,conf,text,from_px,to_px):
        base=render_original(
            self.now,self.weather,self.train,conf,skip_rail_notice=True)
        old=self.physical(conf,text,from_px)
        expected=self.physical(conf,text,to_px)
        patch,x,y=render_notice_patch(
            base,conf,text,to_px,previous_scroll_px=from_px)
        actual=self.apply_patch(old,patch,x,y)
        self.assertIsNone(ImageChops.difference(actual,expected).getbbox(),
                          (from_px,to_px,patch.size if patch else None))
        if patch is not None:
            expected_patch=expected.crop((x,y,x+patch.width,y+patch.height))
            self.assertEqual(patch.tobytes(),expected_patch.tobytes())
            self.assertEqual(len(rgb565le(patch)),patch.width*patch.height*2)
            full=notice_region(conf)
            self.assertLessEqual(patch.width,full[2]-full[0])
            self.assertLessEqual(patch.height,full[3]-full[1])
        return patch

    def test_real_changed_pixel_bbox_saves_height_and_width(self):
        conf=self.conf
        msg='運行情報：IRいしかわ鉄道の遅延情報が発表されています。'*2
        full=notice_region(conf)
        full_bytes=(full[2]-full[0])*(full[3]-full[1])*2
        frames=[self.check_transition(conf,msg,p,q)
                for p,q in ((0,1),(1,2),(2,3),(7,8),(25,26))]
        self.assertTrue(any(
            patch is not None and patch.width*patch.height*2<full_bytes
            for patch in frames))
        self.assertTrue(any(
            patch is not None and patch.height<full[3]-full[1]
            for patch in frames))

    def test_multiple_font_sizes_colors_and_custom_positions(self):
        msg='運行情報：JR七尾線の列車に遅れが発生しています。'*3
        for size in (8,11,14,22,32):
            with self.subTest(size=size):
                conf=copy.deepcopy(self.conf)
                conf['text_styles']={'train_notice':{
                    'size':size,'x':149,'y':56,'color':'#DAA349'}}
                conf['panel_styles']={'train':{'fill':'#335577'}}
                for old,new in ((0,1),(3,4),(23,24),(140,141)):
                    self.check_transition(conf,msg,old,new)

    def test_wrap_boundary_clears_old_glyphs_without_ghosting(self):
        msg='遅延報告：'+'金沢' * 40
        for old,new in ((0,100),(100,200),(200,400),
                        (400,550),(550,0),(0,999)):
            self.check_transition(self.conf,msg,old,new)

    def test_short_text_is_static_and_does_not_need_usb_frame(self):
        text='IR：平常'
        blank=self.check_transition(self.conf,text,0,990)
        self.assertIsNone(blank)

    def test_same_offset_does_not_retransmit_pixels(self):
        msg='運行情報：JR七尾線の遅れによるお知らせ'*5
        self.assertIsNone(self.check_transition(self.conf,msg,19,19))

    def test_offset_skipping_and_multiple_frame_sequence(self):
        msg='運行情報：IRいしかわ鉄道の列車に遅延が発生しています。'*3
        conf=self.conf
        base=render_original(
            self.now,self.weather,self.train,conf,skip_rail_notice=True)
        on_lcd=self.physical(conf,msg,0)
        for pos in (1,3,4,9,23,25,70,71,135,136,0):
            old_pos=0 if pos==1 else previous_pos
            patch,x,y=render_notice_patch(
                base,conf,msg,pos,previous_scroll_px=old_pos)
            on_lcd=self.apply_patch(on_lcd,patch,x,y)
            expected=self.physical(conf,msg,pos)
            self.assertIsNone(ImageChops.difference(on_lcd,expected).getbbox(),
                              (old_pos,pos))
            previous_pos=pos


if __name__=='__main__':
    unittest.main()
