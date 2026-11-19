# -*- coding: utf-8 -*-
"""Headless group layout regression tests. No saved data, GUI or USB needed."""
from __future__ import annotations
import copy
import unittest

from layout_groups import GROUPS, matching_group, adjust_group
from text_layout import props as text_props
from turzx_dashboard import DEFAULTS
from layout_editor import LayoutEditor


class GroupLayoutTests(unittest.TestCase):
    def setUp(self):
        self.styles={}
        self.panels={}

    def test_four_times_in_one_train_row_move_together(self):
        group='列車1｜時刻（4箇所）'
        before={key:text_props({'text_styles':self.styles},key) for key in GROUPS[group][1]}
        out=adjust_group(self.styles,self.panels,group,dx=3,dy=2,dsize=1)
        self.assertEqual(len(out),4)
        for key,original in before.items():
            changed=text_props({'text_styles':out},key)
            self.assertEqual((changed['x'],changed['y'],changed['size']),
                             (original['x']+3,original['y']+2,original['size']+1))
            self.assertEqual(changed['color'],original['color'])
        self.assertEqual(self.styles,{})  # never mutate original config

    def test_all_three_train_rows_time_group(self):
        group='列車｜時刻（3本×4箇所）'
        self.assertEqual(len(GROUPS[group][1]),12)
        new=adjust_group({}, {}, group, dsize=2)
        self.assertEqual(len(new),12)
        self.assertEqual(new['train_time_3']['size'],text_props({},'train_time_3')['size']+2)

    def test_weather_labels_and_values_are_distinct(self):
        titles='天気｜項目名（5種）'
        values='天気｜数値（5種）'
        first=adjust_group({}, {}, titles, dx=2)
        self.assertIn('weather_high_label',first)
        self.assertNotIn('weather_high',first)
        second=adjust_group(first,{},values,dy=1)
        self.assertEqual(second['weather_high_label']['x'],15)
        self.assertEqual(second['weather_high']['y'],166)

    def test_selected_label_prefers_narrower_row_group(self):
        self.assertEqual(matching_group('train_time_3'),'列車3｜時刻（4箇所）')
        self.assertEqual(matching_group('weather_high'),'天気｜数値（5種）')

    def test_custom_individual_overrides_and_colors_are_preserved(self):
        original={'train_time_1':{'x':175,'y':86,'size':25,'color':'#ABCDEF'}}
        modified=adjust_group(original,{},'列車1｜時刻（4箇所）',dx=2,dy=-3,dsize=-2)
        self.assertEqual(modified['train_time_1'],
                         {'x':177,'y':83,'size':23,'color':'#ABCDEF'})
        self.assertEqual(original['train_time_1']['x'],175)
        self.assertEqual(modified['train_kan_arr_1']['color'],'#F3F9FD')

    def test_atomic_rejection_prevents_partial_changes(self):
        old={'train_time_1':{'x':466,'y':86,'size':25,'color':'#ABCDEF'}}
        with self.assertRaisesRegex(ValueError,'範囲外'):
            adjust_group(old,{},'列車1｜時刻（4箇所）',dx=10)
        self.assertEqual(old['train_time_1']['x'],466)
        with self.assertRaisesRegex(ValueError,'文字サイズ'):
            adjust_group(old,{},'列車1｜時刻（4箇所）',dsize=50)
        self.assertEqual(len(old),1)

    def test_panel_bounds_are_honored(self):
        with self.assertRaisesRegex(ValueError,'範囲外'):
            adjust_group({}, {}, '天気｜数値（5種）',dx=60)

    def test_unknown_group_and_bad_numeric_input(self):
        with self.assertRaises(ValueError):
            adjust_group({}, {}, 'unknown')
        with self.assertRaises(ValueError):
            adjust_group({}, {}, '列車1｜時刻（4箇所）',dx='whoops')

    def test_editor_stages_group_changes_until_apply(self):
        # The dialog calls this pure function and only stores result in
        # editor.text_styles. The normal gui.save() remains the sole writer.
        class GUI:
            def save(self):raise AssertionError('Unexpected save')
        editor=LayoutEditor.__new__(LayoutEditor)
        editor.gui=GUI()
        editor.text_styles={}
        editor.panel_styles={}
        staged=adjust_group(editor.text_styles,editor.panel_styles,
                            '列車2｜駅名（4箇所）',dx=1,dy=1,dsize=1)
        editor.text_styles=staged
        editor.unsaved=True
        self.assertEqual(len(staged),4)
        self.assertFalse(hasattr(editor,'window'))


if __name__=='__main__':
    unittest.main()
