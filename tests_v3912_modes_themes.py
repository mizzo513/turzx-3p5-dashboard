# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.12: first-leg trains, fixed-X platform text and ten theme presets."""
import copy
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import turzx_dashboard as dash
from layout_groups import GROUPS, matching_group, adjust_group
from text_layout import ELEMENTS
from theme_presets import PRESETS, DEFAULT_PRESET, palette


class ThemeDataTests(unittest.TestCase):
    def test_exactly_ten_complete_fixed_palettes(self):
        self.assertEqual(len(PRESETS),10)
        self.assertIn(DEFAULT_PRESET,PRESETS)
        required={'window','surface','ink','muted','tab','hover','selected',
                  'selected_ink','hover_ink','border','button','button_ink',
                  'field','accent'}
        for name,colors in PRESETS.items():
            with self.subTest(name=name):
                self.assertEqual(set(colors),required)
                for color in colors.values():
                    self.assertRegex(color,r'^#[0-9A-Fa-f]{6}$')
                self.assertNotEqual(colors['selected'],colors['tab'])
        self.assertEqual(palette('unknown'),PRESETS[DEFAULT_PRESET])

    def test_settings_and_lcd_palettes_are_separate(self):
        self.assertEqual(dash.DEFAULTS['settings_color_preset'],DEFAULT_PRESET)
        self.assertNotIn('settings_color_preset',ELEMENTS)


class FirstLegAndAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,18,13,15,tzinfo=dash.TZ)
        self.conf=copy.deepcopy(dash.DEFAULTS)

    def test_only_first_leg_has_real_arrivals_and_no_transfers(self):
        self.conf['ir_route']='kaga_kanazawa'
        state=dash.upcoming_from_ir_schedule(self.now,self.conf)
        self.assertEqual(state.source,'ir_schedule')
        self.assertEqual(len(state.trains),3)
        self.assertTrue(all(
            t.origin=='加賀笠間' and t.destination=='金沢' and
            t.transfer_arrive is None and t.transfer_depart is None and
            t.arrive>t.depart for t in state.trains))
        first=state.trains[0]
        self.assertEqual(first.depart.strftime('%H:%M'),'13:25')
        self.assertEqual(first.arrive.strftime('%H:%M'),'13:42')
        self.assertEqual(first.platform,'5')
        self.assertNotIn('津幡',state.status)
        diag=dash.train_diagnostics(self.now,self.conf)
        self.assertEqual(diag['train_from'],'加賀笠間')
        self.assertEqual(diag['train_to'],'金沢')
        self.assertTrue(all(item['kanazawa_arrive'] is None
                            for item in diag['trains']))

    def test_first_leg_day_rules_and_next_day(self):
        self.conf['ir_route']='kaga_kanazawa'
        later=datetime(2026,11,18,23,45,tzinfo=dash.TZ)
        state=dash.upcoming_from_ir_schedule(later,self.conf)
        self.assertEqual(len(state.trains),3)
        self.assertTrue(all(t.depart.date()>later.date()
                            for t in state.trains))
        self.assertEqual(state.trains[0].depart.strftime('%H:%M'),'05:35')
        holiday=datetime(2026,11,23,7,45,tzinfo=dash.TZ)
        state=dash.upcoming_from_ir_schedule(holiday,self.conf)
        self.assertNotIn('629M',[t.line for t in state.trains])

    def test_two_station_draw_does_not_invent_kanazawa_departure(self):
        self.conf['ir_route']='kaga_kanazawa'
        state=dash.upcoming_from_ir_schedule(self.now,self.conf)
        captured={}
        original=dash.style_label
        def spy(draw,conf,key,text,*a,**kw):
            captured[key]=str(text)
            return original(draw,conf,key,text,*a,**kw)
        boxes={}
        with patch.object(dash,'style_label',side_effect=spy):
            dash.render_original(self.now,dash.Weather(),state,self.conf,
                                 hit_boxes=boxes)
        for n in range(1,4):
            self.assertEqual(captured[f'train_station_depart_{n}'],'加賀笠間発')
            self.assertEqual(captured[f'train_station_kan_arr_{n}'],'金沢着')
            self.assertNotIn(f'train_kan_dep_{n}',captured)
            self.assertNotIn(f'train_arrive_{n}',captured)
            self.assertIn('番線着',captured[f'train_transfer_platform_{n}'])

    def test_platforms_fixed_x_even_with_varying_transfer_minute_widths(self):
        state=dash.upcoming_from_ir_schedule(self.now,self.conf)
        # Vary wait values independently, preserving all other train fields.
        candidates=[]
        for n,t in enumerate(state.trains):
            t=copy.copy(t)
            t.transfer_depart=t.transfer_arrive+timedelta(minutes=(3,12,105)[n])
            t.transfer_departure_platform=('7','6','3')[n]
            candidates.append(t)
        state.trains=candidates
        boxes={}
        captions={}
        original=dash.style_label
        def spy(draw,conf,key,text,*a,**kw):
            if key.startswith('train_detail_') or key.startswith('train_transfer_platform_'):
                captions[key]=str(text)
            return original(draw,conf,key,text,*a,**kw)
        with patch.object(dash,'style_label',side_effect=spy):
            dash.render_original(self.now,dash.Weather(),state,self.conf,
                                 hit_boxes=boxes)
        xs={boxes[f'text:train_transfer_platform_{n}'][0] for n in range(1,4)}
        self.assertEqual(xs,{345})
        for i,delay in enumerate((3,12,105),1):
            self.assertIn(f'乗換{delay}分',captions[f'train_detail_{i}'])
            self.assertNotIn('番線',captions[f'train_detail_{i}'])
            self.assertIn('番線',captions[f'train_transfer_platform_{i}'])
            self.assertLess(boxes[f'text:train_detail_{i}'][2],
                            boxes[f'text:train_transfer_platform_{i}'][0])
        self.assertEqual(GROUPS[matching_group('train_transfer_platform_1')][1],
                         tuple(f'train_transfer_platform_{i}' for i in range(1,4)))

    def test_platform_group_keeps_all_three_columns_aligned(self):
        group=matching_group('train_transfer_platform_1')
        changed=adjust_group({}, {}, group,dx=-4,dsize=1)
        self.assertEqual(
            [changed[f'train_transfer_platform_{i}']['x'] for i in range(1,4)],
            [341,341,341])

    def test_existing_routes_remain_available(self):
        self.assertEqual(
            dash.upcoming_from_ir_schedule(self.now,self.conf).trains[0].destination,
            '津幡')
        self.conf['ir_route']='kanazawa_tsubata'
        legacy=dash.upcoming_from_ir_schedule(self.now,self.conf)
        self.assertEqual(legacy.trains[0].origin,'金沢')
        self.assertEqual(legacy.trains[0].destination,'津幡')


if __name__=='__main__':
    unittest.main()
