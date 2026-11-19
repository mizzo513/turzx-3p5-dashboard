# -*- coding: utf-8 -*-
"""Five weather values align right; their units stay independently left-aligned.

Pure Pillow tests do not need USB hardware, real weather requests or Tk.
"""
import copy
from datetime import datetime
import unittest
from PIL import Image, ImageDraw
from text_layout import ELEMENTS, WEATHER_RIGHT_ALIGNED_VALUES, props
from turzx_dashboard import DEFAULTS, Weather, TrainState, TZ, render_original, style_label


NUMERIC_KEYS=('weather_high','weather_low','weather_rain',
              'weather_humidity','weather_wind')


class WeatherValueAlignment(unittest.TestCase):
    def setUp(self):
        self.cfg=copy.deepcopy(DEFAULTS)
        self.draw=ImageDraw.Draw(Image.new('RGB',(480,320)))
    
    def test_same_right_edge_for_all_five_default_values(self):
        self.assertEqual(set(NUMERIC_KEYS),set(WEATHER_RIGHT_ALIGNED_VALUES))
        boundaries=set()
        for key,text in zip(NUMERIC_KEYS,('18','7','100','98','3.5')):
            with self.subTest(key=key):
                bounds=style_label(self.draw,self.cfg,key,text)
                expected=ELEMENTS[key][1]+ELEMENTS[key][6]
                self.assertEqual(bounds[2],expected)
                boundaries.add(bounds[2])
                unit=style_label(self.draw,self.cfg,key+'_unit',
                                 'm/s' if key=='weather_wind' else '%')
                self.assertGreaterEqual(unit[0],106)
                self.assertGreater(unit[0],bounds[2])
        self.assertEqual(boundaries,{104})

    def test_right_edge_does_not_shift_with_number_of_digits(self):
        for key in NUMERIC_KEYS:
            boundaries=[]
            for value in ('1','12','100','-5','3.5','---'):
                bounds=style_label(self.draw,self.cfg,key,value)
                boundaries.append(bounds[2])
            self.assertEqual(set(boundaries),{104},(key,boundaries))

    def test_custom_x_and_font_size_keep_right_alignment(self):
        self.cfg['text_styles']={'weather_high':{'x':68,'size':19,'color':'#AABBCC'}}
        bounds=style_label(self.draw,self.cfg,'weather_high','12')
        self.assertEqual(bounds[2],68+ELEMENTS['weather_high'][6])
        self.assertEqual(props(self.cfg,'weather_high')['color'],'#AABBCC')
        # Unit settings do not depend on the numeric label's changes.
        unit=style_label(self.draw,self.cfg,'weather_high_unit','°C')
        self.assertEqual(unit[0],ELEMENTS['weather_high_unit'][1])

    def test_actual_render_uses_right_justification_with_independent_units(self):
        now=datetime(2026,11,19,12,0,tzinfo=TZ)
        w=Weather(city='白山市',high=7,low=10,precip=100,
                  humidity=9,wind=3.5,fetched=now)
        boxes={}
        image=render_original(now,w,TrainState(),self.cfg,hit_boxes=boxes)
        self.assertEqual(image.size,(480,320))
        for name in NUMERIC_KEYS:
            with self.subTest(name=name):
                number=boxes['text:'+name]
                unit=boxes['text:'+name+'_unit']
                self.assertEqual(number[2],104)
                self.assertGreaterEqual(unit[0],106)
                self.assertLess(number[2],unit[0])


if __name__=='__main__':
    unittest.main()
