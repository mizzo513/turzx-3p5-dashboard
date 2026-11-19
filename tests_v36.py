# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.6 tests. Hardware and Windows EXE build must also be verified on device."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from PIL import ImageChops

import panel_layout
import turzx_dashboard as dash
import update_manager
from text_layout import ELEMENTS
from version_info import APP_VERSION

class TestsV36(unittest.TestCase):
    def setUp(self):
        self.cfg=copy.deepcopy(dash.DEFAULTS)
        self.now=datetime(2026,11,18,13,15,0,tzinfo=dash.TZ)
        self.w=dash.Weather()
        self.trains=dash.TrainState()

    def test_new_date_and_version(self):
        self.assertEqual(dash.datetime_text(self.now,self.cfg),'11/18(水) 13:15:00')
        self.assertNotIn('title',ELEMENTS)
        self.assertEqual(APP_VERSION,'3.9.6')
        boxes={}
        dash.render_original(self.now,self.w,self.trains,self.cfg,hit_boxes=boxes)
        for key in ('clock_datetime','version'):
            self.assertIn('text:'+key,boxes)
        self.assertEqual(boxes['panel:header'],(5,5,474,45))

    def test_seconds_crop_contains_all_changed_pixels(self):
        for sec in (9,19,39,59):
            a=self.now.replace(second=sec)
            b=self.now.replace(second=(sec+1)%60)
            im1=dash.render_original(a,self.w,self.trains,self.cfg)
            im2=dash.render_original(b,self.w,self.trains,self.cfg)
            delta=ImageChops.difference(im1,im2).getbbox()
            box=dash.seconds_region(self.cfg,b)
            self.assertIsNotNone(delta)
            self.assertTrue(box[0]<=delta[0] and box[1]<=delta[1] and box[2]>=delta[2] and box[3]>=delta[3],(box,delta))
            self.assertLess((box[2]-box[0])*(box[3]-box[1]),3000)

    def test_panels_are_editable(self):
        boxes={}
        old=dash.render_original(self.now,self.w,self.trains,self.cfg,hit_boxes=boxes)
        self.cfg['panel_styles']={'train_1':{'x':182,'y':96,'w':275,'h':52,'radius':2,'border_width':3,
                                           'outline':'#FF0000','fill':'#252525'}}
        panel_layout.validate_panels(self.cfg)
        changed_boxes={}
        new=dash.render_original(self.now,self.w,self.trains,self.cfg,hit_boxes=changed_boxes)
        self.assertEqual(changed_boxes['panel:train_1'],(182,96,456,147))
        self.assertNotEqual(old.tobytes(),new.tobytes())

    def test_panel_rejects_offscreen(self):
        self.cfg['panel_styles']={'header':{'x':471,'w':40}}
        with self.assertRaises(ValueError):panel_layout.validate_panels(self.cfg)

    def test_visible_label_bounds_from_renderer(self):
        boxes={}
        dash.render_original(self.now,self.w,self.trains,self.cfg,hit_boxes=boxes)
        b=boxes['text:clock_datetime']
        self.assertTrue(10<=b[0]<b[2]<=400 and 5<=b[1]<b[3]<55)
        self.assertGreater(b[2]-b[0],100)  # old editor's arbitrary 17px selection was wrong

    def test_updater_manifest_validation(self):
        fakeexe=b'MZ'+b'\x00'*1500
        payload={'app_id':update_manager.APP_ID,'filename':update_manager.EXE_NAME,'version':'3.9.7',
                 'size':len(fakeexe),'sha256':hashlib.sha256(fakeexe).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'update.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('manifest.json',json.dumps(payload));z.writestr(update_manager.EXE_NAME,fakeexe)
            self.assertEqual(update_manager.manifest_from_zip(p)['version'],'3.9.7')
            dest=Path(tmp)/'staged.exe'
            update_manager.extract_verified(p,dest)
            self.assertEqual(dest.read_bytes(),fakeexe)
            payload['sha256']='0'*64
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('manifest.json',json.dumps(payload));z.writestr(update_manager.EXE_NAME,fakeexe)
            with self.assertRaises(ValueError):update_manager.extract_verified(p,Path(tmp)/'bad.exe')

    def test_updater_old_version_is_rejected(self):
        self.assertLess(update_manager.version_tuple('3.5.0'),update_manager.version_tuple(APP_VERSION))
        with self.assertRaises(ValueError):update_manager.version_tuple('3.6;evil')

if __name__=='__main__':unittest.main()
