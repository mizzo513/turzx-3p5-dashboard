# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.10: consolidated header refresh times and expanded content layout."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops
import turzx_dashboard as app
from panel_layout import settings as panel_settings
from text_layout import ELEMENTS


class HeaderRefreshLayoutTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,19,17,5,17,tzinfo=app.TZ)
        self.conf=copy.deepcopy(app.DEFAULTS)
        self.weather=app.Weather(city='白山市',temperature=15.3,
                                 high=18.3,low=7.0,precip=40,
                                 humidity=78,wind=3.6,code=3,
                                 fetched=self.now-timedelta(minutes=5))
        self.train=app.choose_trains(self.now,self.conf)
        self.train.loaded=self.now-timedelta(minutes=1)

    def test_timestamps_and_version_are_inside_the_header(self):
        boxes={}
        seen={}
        original=app.style_label
        def record(draw,conf,key,text,*args,**kwargs):
            seen[key]=text
            return original(draw,conf,key,text,*args,**kwargs)
        with patch.object(app,'style_label',side_effect=record):
            app.render_original(self.now,self.weather,self.train,self.conf,
                                hit_boxes=boxes)
        self.assertEqual(seen['footer_weather'],'天気 17:00')
        self.assertEqual(seen['footer_train'],'乗換 17:04')
        self.assertEqual(seen['version'],'v'+app.APP_VERSION)
        header=boxes['panel:header']
        clock=boxes['text:clock_datetime']
        statuses=[boxes['text:'+k] for k in
                  ('footer_weather','footer_train','version')]
        for bounds in statuses:
            self.assertGreater(bounds[0],300)
            self.assertGreaterEqual(bounds[1],header[1])
            self.assertLessEqual(bounds[2],header[2])
            self.assertLessEqual(bounds[3],header[3])
            self.assertGreater(bounds[0],clock[2]+8)
        for first,second in zip(statuses,statuses[1:]):
            self.assertLessEqual(first[3],second[1]+1)
        self.assertEqual(boxes['text:footer_weather'][2],
                         boxes['text:footer_train'][2])
        self.assertEqual(boxes['text:version'][2],
                         boxes['text:footer_weather'][2])

    def test_missing_refresh_time_is_fully_visible(self):
        self.weather.fetched=None
        self.train.loaded=None
        seen={}
        original=app.style_label
        def record(draw,conf,key,text,*args,**kwargs):
            seen[key]=text
            return original(draw,conf,key,text,*args,**kwargs)
        with patch.object(app,'style_label',side_effect=record):
            app.render_original(self.now,self.weather,self.train,self.conf)
        self.assertEqual(seen['footer_weather'],'天気 --:--')
        self.assertEqual(seen['footer_train'],'乗換 --:--')

    def test_train_refresh_time_changes_even_with_same_departures(self):
        initial=app.render_original(self.now,self.weather,self.train,self.conf)
        later=copy.copy(self.train)
        later.loaded=self.train.loaded+timedelta(minutes=1)
        after=app.render_original(self.now,self.weather,later,self.conf)
        changed=ImageChops.difference(initial,after).getbbox()
        self.assertIsNotNone(changed)
        self.assertLess(changed[3],47)  # only the header stamp differs

    def test_freed_weather_and_train_area_contains_resized_content(self):
        boxes={}
        app.render_original(self.now,self.weather,self.train,self.conf,hit_boxes=boxes)
        weather=boxes['panel:weather']
        wind=boxes['text:weather_wind']
        wind_unit=boxes['text:weather_wind_unit']
        self.assertGreater(wind[1],270)
        for bounds in (wind,wind_unit):
            self.assertLess(bounds[3],weather[3])
        train_panel=boxes['panel:train']
        self.assertGreater(boxes['panel:train_3'][3],300)
        self.assertEqual(boxes['panel:train_1'][3],150)
        self.assertEqual(boxes['panel:train_2'][1],155)
        self.assertEqual(boxes['panel:train_3'][1],231)
        for i in range(1,4):
            p=boxes[f'panel:train_{i}']
            for key in ('train_time','train_kan_arr','train_kan_dep',
                        'train_arrive','train_detail'):
                b=boxes[f'text:{key}_{i}']
                self.assertGreaterEqual(b[1],p[1])
                self.assertLessEqual(b[3],p[3]+1,(i,key,b,p))
        self.assertNotIn('text:train_source_note',boxes)
        self.assertGreaterEqual(train_panel[3],310)

    def test_migration_preserves_relative_custom_positions_and_colors(self):
        old={
            'layout_revision':396,
            'text_styles':{
                'footer_weather':{'x':15,'y':292,'size':12,'color':'#11AABB'},
                'footer_train':{'x':377,'y':293,'color':'#22CCDD'},
                'train_time_3':{'x':175,'y':241,'size':18},
                'weather_wind':{'y':258,'color':'#FFFFFF'},
            },
            'panel_styles':{
                'train_3':{'x':141,'y':215,'w':325,'h':65,'fill':'#101010'}
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            setting=Path(tmp)/'settings.json'
            setting.write_text(json.dumps(old),encoding='utf-8')
            with patch.object(app,'SETTINGS',setting):
                migrated=app.load_settings()
                self.assertEqual(migrated['layout_revision'],397)
                weather=migrated['text_styles']['footer_weather']
                self.assertEqual((weather['x'],weather['y'],weather['size'],weather['color']),
                                 (357,9,12,'#11AABB'))
                train=migrated['text_styles']['footer_train']
                self.assertEqual((train['x'],train['y']),(356,22))
                self.assertEqual(migrated['text_styles']['train_time_3']['y'],261)
                self.assertEqual(migrated['text_styles']['weather_wind']['y'],283)
                panel=migrated['panel_styles']['train_3']
                self.assertEqual((panel['x'],panel['y'],panel['w'],panel['h']),
                                 (141,233,325,78))
                self.assertIn('layout_backup_v399',migrated)
                self.assertEqual(migrated['layout_backup_v399']['text_styles'],
                                 old['text_styles'])
                self.assertEqual(json.loads(setting.read_text()),old)
                app.save_settings(migrated)
                again=app.load_settings()
                self.assertEqual(again['text_styles'],migrated['text_styles'])

    def test_existing_editor_ids_remain_and_layout_revision_changes(self):
        self.assertEqual(app.DEFAULTS['layout_revision'],397)
        for key in ('footer_weather','footer_train','version',
                    'weather_wind','weather_temperature'):
            self.assertIn(key,ELEMENTS)
        self.assertEqual(panel_settings(self.conf,'train_3')['h'],77)


if __name__=='__main__':
    unittest.main()
