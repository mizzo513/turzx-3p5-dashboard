# -*- coding: utf-8 -*-
"""v3.9 exact 480x320 two-panel layout and old-layout migration regressions."""
from __future__ import annotations
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import ImageDraw, Image
import panel_layout as panels
import turzx_dashboard as app
from text_layout import ELEMENTS


class V39LayoutTests(unittest.TestCase):
    def setUp(self):
        self.conf=copy.deepcopy(app.DEFAULTS)
        self.now=datetime(2026,11,18,13,15,tzinfo=app.TZ)
        self.weather=app.Weather(city='白山市',temperature=14.6,high=16.4,low=8.0,
                                 precip=25,humidity=76,wind=3.0,code=3,
                                 fetched=self.now)
        self.train=app.choose_trains(self.now,self.conf)

    def test_no_separate_footer_and_no_route_header(self):
        self.assertNotIn('footer',panels.PANELS)
        self.assertNotIn('train_header',ELEMENTS)
        self.assertNotIn('train_header_note',ELEMENTS)
        self.assertEqual(panels.settings(self.conf,'weather')['x'],5)
        self.assertLessEqual(panels.settings(self.conf,'weather')['w'],125)
        self.assertGreaterEqual(panels.settings(self.conf,'train')['w'],340)
        self.assertEqual(panels.draw_panel(ImageDraw.Draw(Image.new('RGB',(480,320))),
                                          self.conf,'weather')[3],315)
        self.assertEqual(panels.draw_panel(ImageDraw.Draw(Image.new('RGB',(480,320))),
                                          self.conf,'train')[3],315)

    def test_four_clocks_are_individually_rendered_and_do_not_overlap(self):
        boxes={}
        img=app.render_original(self.now,self.weather,self.train,self.conf,hit_boxes=boxes)
        self.assertEqual(img.size,(480,320))
        for n in range(1,4):
            panel=boxes[f'panel:train_{n}']
            cols=[boxes[f'text:{name}_{n}'] for name in
                  ('train_time','train_kan_arr','train_kan_dep','train_arrive')]
            for (x0,y0,x1,y1) in cols:
                self.assertGreaterEqual(x0,panel[0])
                self.assertLessEqual(x1,panel[2]+2)
                self.assertGreaterEqual(y0,panel[1])
                self.assertLess(y1,panel[3])
            for left,right in zip(cols,cols[1:]):
                self.assertLess(left[2],right[0],(n,left,right))
            self.assertIn(f'text:train_detail_{n}',boxes)

    def test_status_is_inside_weather_and_train_panels(self):
        boxes={}
        app.render_original(self.now,self.weather,self.train,self.conf,hit_boxes=boxes)
        for outer,inner in [('weather','footer_weather'),
                            ('train','footer_train'),('train','train_source_note')]:
            x0,y0,x1,y1=boxes[f'panel:{outer}']
            l,t,r,b=boxes[f'text:{inner}']
            self.assertTrue(x0<=l<r<=x1 and y0<=t<b<=y1,(outer,inner,(l,t,r,b)))

    def test_city_and_current_temperature_have_no_prefix_or_decimal(self):
        seen={}
        original=app.style_label
        def spy(draw,conf,key,text,*args,**kwargs):
            seen[key]=str(text)
            return original(draw,conf,key,text,*args,**kwargs)
        with patch.object(app,'style_label',side_effect=spy):
            app.render_original(self.now,self.weather,self.train,self.conf)
        self.assertEqual(seen['weather_city'],'白山市')
        self.assertEqual(seen['weather_temperature'],'15')
        self.assertEqual(seen['weather_temperature_unit'],'℃')
        self.assertFalse(any(key in seen for key in ('train_header','train_header_note')))

    def test_warning_suffix_is_not_rendered_for_3_minute_transfer(self):
        recorded={}
        original=app.style_label
        def spy(draw,conf,key,text,*args,**kwargs):
            recorded[key]=str(text)
            return original(draw,conf,key,text,*args,**kwargs)
        with patch.object(app,'style_label',side_effect=spy):
            app.render_original(self.now,self.weather,self.train,self.conf)
        self.assertIn('乗換3分',recorded['train_detail_1'])
        self.assertNotIn('注意',recorded['train_detail_1'])
        self.assertEqual(self.train.trains[0].transfer_arrive.strftime('%H:%M'),'13:42')
        self.assertEqual(self.train.trains[0].transfer_depart.strftime('%H:%M'),'13:45')

    def test_legacy_only_kanazawa_mode_does_not_require_four_times(self):
        cfg={**self.conf,'ir_route':'kanazawa_tsubata'}
        rows=app.choose_trains(self.now,cfg)
        hit={}
        img=app.render_original(self.now,self.weather,rows,cfg,hit_boxes=hit)
        self.assertEqual(img.size,(480,320))
        self.assertIn('text:train_legacy_time_1',hit)
        self.assertNotIn('text:train_kan_arr_1',hit)

    def test_migrate_old_saved_layout_but_preserve_other_settings(self):
        legacy={'weather_city':'津幡町','port':'COM11','train_count':2,
                'text_styles':{'train_time_1':{'x':401,'y':305,'size':44,'color':'#ABCDEF'}},
                'panel_styles':{'weather':{'x':140,'w':300,'fill':'#142536'}}}
        with tempfile.TemporaryDirectory() as tmp:
            location=Path(tmp)/'settings.json'
            location.write_text(json.dumps(legacy),encoding='utf-8')
            with patch.object(app,'SETTINGS',location):
                migrated=app.load_settings()
                self.assertEqual(migrated['layout_revision'],396)
                self.assertEqual(migrated['weather_city'],'津幡町')
                self.assertEqual(migrated['port'],'COM11')
                self.assertEqual(migrated['train_count'],2)
                self.assertEqual(migrated['text_styles']['train_time_1'],{'color':'#ABCDEF'})
                self.assertEqual(migrated['panel_styles']['weather'],{'fill':'#142536'})
                self.assertEqual(migrated['layout_backup_v383']['text_styles'],legacy['text_styles'])
                self.assertEqual(json.loads(location.read_text()),legacy) # no autosave
                app.save_settings(migrated)
                after=app.load_settings()
                self.assertEqual(after['layout_backup_v383']['panel_styles'],legacy['panel_styles'])
                self.assertEqual(after['text_styles'],migrated['text_styles'])


if __name__=='__main__':
    unittest.main()
