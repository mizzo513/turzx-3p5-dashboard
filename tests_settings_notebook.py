# -*- coding: utf-8 -*-
"""Windows Tk regression tests for the compact, tabbed settings GUI.

Must create the real GUI rather than relying on source-text assertions.
Does not contact APIs, start the USB engine or save credentials to disk.
"""
import copy
import os
import tkinter as tk
import unittest

from settings_gui import SettingsWindow


@unittest.skipUnless(os.name=='nt','Tk GUI integration requires Windows runner')
class TestSettingsNotebook(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.root.withdraw()
        self.gui=SettingsWindow(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        if self.root.winfo_exists():
            self.gui.close()

    def test_notebook_has_four_short_sections_and_fixed_footer(self):
        self.assertEqual(
            [self.gui.tabs.tab(page,'text') for page in self.gui.tabs.tabs()],
            ['表示・時計','天気','乗換','外観・更新']
        )
        self.assertEqual(len(self.gui._tab_canvases),4)
        self.assertEqual(self.gui.tabs.grid_info()['row'],1)
        self.assertEqual(self.gui.root.geometry().split('x')[0],'725')
        self.assertEqual(self.gui.root.geometry().split('x')[1].split('+')[0],'505')
        # Save, weather API test, display start/stop, exit are NOT descendants
        # of any notebook page and remain in the fixed root footer.
        from tkinter import ttk
        buttons=[w for w in self.root.winfo_children()
                 if isinstance(w,ttk.Frame) and w.grid_info().get('row')==2]
        self.assertEqual(len(buttons),1)
        footer=buttons[0]
        all_footer_children=list(footer.winfo_children())
        self.assertTrue(any(isinstance(w,ttk.Frame) for w in all_footer_children))
        commands=[w.cget('text') for row in all_footer_children
                  if isinstance(row,ttk.Frame)
                  for w in row.winfo_children() if isinstance(w,ttk.Button)]
        self.assertEqual(commands,
            ['設定を即時反映','表示開始','表示停止','ディスプレイ再接続','終了'])

    def test_update_button_is_next_to_title_and_visible_across_tabs(self):
        from tkinter import ttk
        top=[w for w in self.root.winfo_children()
             if isinstance(w,ttk.Frame) and w.grid_info().get('row')==0]
        self.assertEqual(len(top),1)
        titlebar=top[0]
        children=list(titlebar.winfo_children())
        headings=[w for w in children if isinstance(w,ttk.Label)
                  and 'TURZX 3.5 設定' in w.cget('text')]
        self.assertEqual(len(headings),1)
        buttons=[w for w in children if isinstance(w,ttk.Button)]
        self.assertEqual(len(buttons),1)
        self.assertIs(buttons[0],self.gui.header_update_button)
        self.assertEqual(buttons[0].cget('text'),'更新確認')
        self.assertEqual(children.index(buttons[0]),children.index(headings[0])+1)
        self.assertEqual(buttons[0].winfo_manager(),'pack')
        for page in self.gui.tabs.tabs():
            self.gui.tabs.select(page)
            self.root.update_idletasks()
            self.assertTrue(buttons[0].winfo_ismapped() or
                            self.root.state()=='withdrawn')
        # The update check is no longer hidden inside the maintenance tab.
        self.assertEqual(len(buttons),1)

    def test_every_tab_is_scrollable_and_independent(self):
        pages=self.gui.tabs.tabs()
        self.assertEqual(len(set(str(self.gui._tab_canvases[p]) for p in pages)),4)
        for page in pages:
            canvas=self.gui._tab_canvases[page]
            self.assertEqual(str(canvas.master),page)
            self.assertEqual(str(canvas.cget('yscrollcommand'))!='',True)
            self.assertIsNotNone(canvas.find_all())

    def test_tabs_have_contrasting_colors_and_equal_pixel_width(self):
        from tkinter import ttk
        self.assertEqual(self.gui.tabs.cget('style'),'TURZX.TNotebook')
        style=ttk.Style(self.root)
        # Clam makes custom tab backgrounds effective on Windows native themes.
        self.assertEqual(style.theme_use(),'clam')
        tab_style='TURZX.TNotebook.Tab'
        # Selected and inactive backgrounds use distinct, readable colors.
        self.assertNotEqual(
            style.lookup(tab_style,'background',('selected',)),
            style.lookup(tab_style,'background',('!selected',)))
        self.assertEqual(style.lookup(tab_style,'foreground',('selected',)),
                         '#FFFFFF')
        self.assertEqual(
            self.gui._tab_width_px,
            max(self.gui._tab_font.measure(self.gui.tabs.tab(p,'text'))
                for p in self.gui.tabs.tabs())+44)
        widths=[]
        for page in self.gui.tabs.tabs():
            label=self.gui.tabs.tab(page,'text')
            padding=self.gui.tabs.tab(page,'padding')
            if isinstance(padding,str):
                padding=self.root.tk.splitlist(padding)
            # Tk may return pixel values as strings.
            left,top,right,bottom=(int(x) for x in padding)
            self.assertEqual((top,bottom),(8,8))
            widths.append(self.gui._tab_font.measure(label)+left+right)
        self.assertEqual(len(set(widths)),1)
        self.assertEqual(widths[0],self.gui._tab_width_px)

    def test_ten_palettes_switch_color_only_and_are_saved(self):
        from theme_presets import PRESETS
        from tkinter import ttk
        self.assertEqual(len(PRESETS),10)
        style=ttk.Style(self.root)
        pages=self.gui.tabs.tabs()
        before=[self.gui.tabs.tab(page,'padding') for page in pages]
        before_width=self.gui._tab_width_px
        for theme,colors in PRESETS.items():
            self.gui.vars['settings_color_preset'].set(theme)
            self.gui._on_palette_change()
            self.assertEqual(
                style.lookup('TURZX.TNotebook.Tab','background',('selected',)),
                colors['selected'])
            self.assertEqual(
                style.lookup('TURZX.TNotebook.Tab','foreground',('selected',)),
                colors['selected_ink'])
            # Clam gives the selected tab 2px of extra expansion by default.
            # The custom style must override this for every interaction state.
            for state in (('selected',),('active',),('!selected',),()):
                expand=style.lookup('TURZX.TNotebook.Tab','expand',state)
                self.assertEqual(
                    tuple(str(n) for n in self.root.tk.splitlist(expand)),
                    ('0','0','0','0'),(theme,state,expand))
            self.assertNotEqual(colors['selected'],colors['tab'])
            self.assertEqual(before_width,self.gui._tab_width_px)
            self.assertEqual(before,
                             [self.gui.tabs.tab(page,'padding') for page in pages])
            self.assertEqual(style.map('TURZX.TNotebook.Tab','padding'),[])
            self.assertEqual(style.map('TURZX.TNotebook.Tab','font'),[])
            self.assertEqual(self.gui.read_form()['settings_color_preset'],theme)
        self.gui.vars['settings_color_preset'].set('存在しないテーマ')
        with self.assertRaises(ValueError):
            self.gui.read_form()

    def test_weather_api_button_is_inside_weather_tab_only(self):
        from tkinter import ttk
        weather=self.gui.tabs.tabs()[1]
        canvas=self.gui._tab_canvases[weather]
        self.assertEqual(self.gui.weather_test_button.master.master,canvas)
        self.assertEqual(self.gui.weather_test_button.cget('text'),'天気APIテスト')
        self.assertEqual(self.gui.weather_test_button.winfo_manager(),'grid')
        # It must never be one of the globally-visible footer buttons.
        footer=[w for w in self.root.winfo_children()
                if isinstance(w,ttk.Frame) and w.grid_info().get('row')==2][0]
        controls=[w.cget('text') for child in footer.winfo_children()
                  if isinstance(child,ttk.Frame)
                  for w in child.winfo_children() if isinstance(w,ttk.Button)]
        self.assertNotIn('天気APIテスト',controls)

    def test_first_leg_route_can_be_selected_and_saved(self):
        choices=('加賀笠間→金沢→津幡','加賀笠間→金沢','金沢→津幡')
        combo=self.gui.vars['ir_route']
        for display,mapped in zip(choices,('via_kanazawa',
                                         'kaga_kanazawa','kanazawa_tsubata')):
            combo.set(display)
            self.assertEqual(self.gui.read_form()['ir_route'],mapped)

    def test_marquee_pixels_per_second_edit_and_validation(self):
        self.assertIn('rail_scroll_speed_px_s',self.gui.vars)
        self.gui.vars['rail_scroll_speed_px_s'].set('23.5')
        self.assertAlmostEqual(self.gui.read_form()['rail_scroll_speed_px_s'],23.5)
        self.gui.vars['rail_scroll_speed_px_s'].set('0')
        self.assertEqual(self.gui.read_form()['rail_scroll_speed_px_s'],0)
        for value in ('-0.1','61','nan','inf','abc'):
            with self.subTest(value=value):
                self.gui.vars['rail_scroll_speed_px_s'].set(value)
                with self.assertRaises(ValueError):
                    self.gui.read_form()

    def test_all_settings_still_participate_in_single_save(self):
        required={'port','show_seconds','clock_12h','ntp_server','ntp_sync_minutes',
                  'clock_update_mode','auto_start_display','weather_city','weather_latitude',
                  'weather_longitude','weather_update_minutes','weather_provider',
                  'weatherapi_key','train_source','ir_route','train_update_seconds',
                  'train_count','google_maps_api_key','auto_update_check',
                  'rail_status_enabled','rail_status_update_minutes'}
        self.assertTrue(required.issubset(self.gui.vars),required-set(self.gui.vars))
        original=copy.deepcopy(self.gui.conf)
        self.gui.vars['weather_city'].set('津幡町')
        self.gui.vars['weather_latitude'].set('36.6693')
        self.gui.vars['weather_longitude'].set('136.7288')
        self.gui.vars['weatherapi_key'].set('LOCAL_TEST_NOT_REAL')
        self.gui.vars['weather_provider'].set('WeatherAPI.com')
        self.gui.vars['show_seconds'].set(False)
        self.gui.vars['train_count'].set('2')
        self.gui.vars['auto_update_check'].set(False)
        self.gui.vars['rail_status_enabled'].set(False)
        self.gui.vars['rail_status_update_minutes'].set('8')
        self.gui.vars['auto_start_display'].set(False)
        updated=self.gui.read_form()
        self.assertEqual(updated['weather_city'],'津幡町')
        self.assertEqual(updated['weather_provider'],'weatherapi')
        self.assertEqual(updated['weatherapi_key'],'LOCAL_TEST_NOT_REAL')
        self.assertEqual(updated['train_count'],2)
        self.assertFalse(updated['show_seconds'])
        self.assertFalse(updated['auto_update_check'])
        self.assertFalse(updated['rail_status_enabled'])
        self.assertEqual(updated['rail_status_update_minutes'],8)
        self.assertFalse(updated['auto_start_display'])
        self.assertEqual(updated['text_styles'],original['text_styles'])
        self.assertEqual(updated['panel_styles'],original['panel_styles'])
        self.assertEqual(self.gui.conf,original) # changes stay staged until Save


if __name__=='__main__':
    unittest.main()
