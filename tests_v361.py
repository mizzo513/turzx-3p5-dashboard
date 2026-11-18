# -*- coding: utf-8 -*-
import unittest, tempfile, copy, json, shutil
from pathlib import Path
from datetime import datetime
import turzx_dashboard as d
from version_info import APP_VERSION
from PIL import ImageChops

class VersionRegression(unittest.TestCase):
    def setUp(self):
        self.conf=copy.deepcopy(d.DEFAULTS)
        self.now=datetime(2026,11,18,13,15,tzinfo=d.TZ)
    def test_version_one_source(self):
        self.assertEqual(APP_VERSION,'3.7.0')
        import settings_gui, layout_editor
        self.assertIn('APP_VERSION',Path(settings_gui.__file__).read_text(encoding='utf-8'))
        self.assertIn('APP_VERSION',Path(layout_editor.__file__).read_text(encoding='utf-8'))
    def test_train_data_and_render(self):
        status=d.train_diagnostics(self.now,self.conf)
        self.assertEqual(status['schedule_rows'],56)
        self.assertEqual(len(status['trains']),3)
        self.assertEqual(status['trains'][0]['depart'][11:16],'13:31')
        self.assertEqual(status['train_source'],'ir_schedule')
        train=d.choose_trains(self.now,self.conf)
        boxes={}
        img=d.render_original(self.now,d.Weather(city='白山市'),train,self.conf,hit_boxes=boxes)
        self.assertEqual(img.size,(480,320))
        self.assertIn('text:train_time_1',boxes)
        self.assertIn('text:train_time_2',boxes)
        self.assertIn('text:train_time_3',boxes)
    def test_fallback_from_bad_local_schedule(self):
        original_root=d.ROOT; original_bundle=d.BUNDLE_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                a=Path(tmp)/'user'; b=Path(tmp)/'bundle'
                a.mkdir();b.mkdir()
                (a/'schedule.json').write_text('{broken')
                shutil.copyfile(original_bundle/'schedule.json',b/'schedule.json')
                d.ROOT=a;d.BUNDLE_ROOT=b
                doc,chosen=d.resolve_ir_schedule()
                self.assertEqual(chosen,b/'schedule.json')
                self.assertEqual(doc['revision'],'2026-03-14')
        finally:
            d.ROOT=original_root;d.BUNDLE_ROOT=original_bundle
    def test_missing_sources_visible_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=d.upcoming_from_ir_schedule(self.now,self.conf,path=Path(tmp)/'missing.json')
            self.assertEqual(s.trains,[])
            self.assertIn('時刻表',s.status)
            self.assertTrue(s.error)
    def test_revert_defaults_removes_legacy_override(self):
        custom=copy.deepcopy(self.conf)
        custom['text_styles']={'train_time_1':{'x':400,'y':300}}
        custom['panel_styles']={'train_1':{'x':400,'w':70}}
        img1=d.render_original(self.now,d.Weather(),d.choose_trains(self.now,self.conf),self.conf)
        img2=d.render_original(self.now,d.Weather(),d.choose_trains(self.now,custom),custom)
        self.assertIsNotNone(ImageChops.difference(img1,img2).getbbox())
        custom['text_styles']={};custom['panel_styles']={}
        img3=d.render_original(self.now,d.Weather(),d.choose_trains(self.now,custom),custom)
        self.assertEqual(img1.tobytes(),img3.tobytes())

if __name__=='__main__':unittest.main()
