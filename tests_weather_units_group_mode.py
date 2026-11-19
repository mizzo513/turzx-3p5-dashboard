# -*- coding: utf-8 -*-
"""Weather unit editing and selected-group/individual-mode regression tests."""
import copy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from layout_editor import LayoutEditor
from layout_groups import GROUPS, adjust_group
from text_layout import ELEMENTS, props
import turzx_dashboard as app


class FakeVar:
    def __init__(self,value):
        self.value=str(value)
    def get(self):return self.value
    def set(self,value):self.value=str(value)


class TextGroupAndWeatherUnits(unittest.TestCase):
    def test_weather_has_separate_editable_numbers_and_units(self):
        expected=['weather_temperature','weather_high','weather_low',
                  'weather_rain','weather_humidity','weather_wind']
        for name in expected:
            with self.subTest(name=name):
                self.assertIn(name,ELEMENTS)
                self.assertIn(name+'_unit',ELEMENTS)
                self.assertNotEqual(props({},name)['x'],props({},name+'_unit')['x'])
        self.assertEqual(len(GROUPS['天気｜単位（5種）'][1]),5)
        self.assertEqual(len(GROUPS['天気｜数値（5種）'][1]),5)

    def test_weather_renderer_emits_numeric_and_unit_as_independent_text(self):
        now=datetime(2026,11,19,10,0,tzinfo=app.TZ)
        conf=copy.deepcopy(app.DEFAULTS)
        weather=app.Weather(city='白山市',temperature=12.6,high=18.0,low=7.0,
                            precip=100,humidity=91,wind=3.5,code=63,fetched=now)
        seen={}
        real=app.style_label
        def capture(draw,cfg,key,value,*a,**kw):
            seen[key]=str(value)
            return real(draw,cfg,key,value,*a,**kw)
        hit={}
        with patch.object(app,'style_label',side_effect=capture):
            image=app.render_original(now,weather,app.TrainState(),conf,hit_boxes=hit)
        self.assertEqual(image.size,(480,320))
        expected={
            'weather_temperature':('13','°'),
            'weather_high':('18','°C'),
            'weather_low':('7','°C'),
            'weather_rain':('100','%'),
            'weather_humidity':('91','%'),
            'weather_wind':('3.5','m/s'),
        }
        wx0,wy0,wx1,wy1=hit['panel:weather']
        for name,(number,unit) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(seen[name],number)
                self.assertEqual(seen[name+'_unit'],unit)
                left=hit['text:'+name]
                right=hit['text:'+name+'_unit']
                self.assertLess(left[2],right[0]+2,(name,left,right))
                for bounds in (left,right):
                    self.assertTrue(wx0<=bounds[0]<=bounds[2]<=wx1+1,(name,bounds))
                    self.assertTrue(wy0<=bounds[1]<=bounds[3]<=wy1+1,(name,bounds))

    def test_adjust_weather_units_does_not_touch_numbers(self):
        group='天気｜単位（5種）'
        changed=adjust_group({}, {}, group,dx=-2,dsize=1)
        self.assertEqual(len(changed),5)
        for key in GROUPS[group][1]:
            self.assertEqual(changed[key]['x'],ELEMENTS[key][1]-2)
            self.assertEqual(changed[key]['size'],ELEMENTS[key][3]+1)
        self.assertNotIn('weather_rain',changed)

    def make_editor(self,individual):
        editor=LayoutEditor.__new__(LayoutEditor)
        editor.selected=('text','train_time_1')
        editor.individual_mode=FakeVar('') # replaced below with bool getter
        editor.individual_mode=SimpleNamespace(get=lambda:individual)
        editor.text_styles={}
        editor.panel_styles={}
        editor.loading=False
        editor.status=SimpleNamespace(set=lambda _value:None)
        editor.unsaved=False
        editor.queue_refresh=lambda:None
        selected=props({},'train_time_1')
        editor.vars={x:FakeVar(selected[x]) for x in ('x','y','size','color')}
        return editor

    def test_default_group_entry_changes_four_related_times(self):
        editor=self.make_editor(False)
        old=props({},'train_time_1')
        editor.vars['x'].set(old['x']+2)
        editor.on_field_edit()
        keys=GROUPS['列車1｜時刻（4箇所）'][1]
        self.assertEqual(set(editor.text_styles),set(keys))
        for key in keys:
            self.assertEqual(editor.text_styles[key]['x'],ELEMENTS[key][1]+2)
        self.assertTrue(editor.unsaved)

    def test_individual_checkbox_stages_only_selected_item(self):
        editor=self.make_editor(True)
        old=props({},'train_time_1')
        editor.vars['size'].set(old['size']+2)
        editor.on_field_edit()
        self.assertEqual(set(editor.text_styles),{'train_time_1'})
        self.assertEqual(editor.text_styles['train_time_1']['size'],old['size']+2)

    def test_group_font_size_change_preserves_existing_colors(self):
        editor=self.make_editor(False)
        editor.text_styles={'train_kan_arr_1':{'color':'#112233'}}
        original=props({'text_styles':editor.text_styles},'train_time_1')
        editor.vars['size'].set(original['size']+1)
        editor.on_field_edit()
        self.assertEqual(editor.text_styles['train_kan_arr_1']['color'],'#112233')
        self.assertEqual(editor.text_styles['train_kan_arr_1']['size'],18)


if __name__=='__main__':
    unittest.main()
