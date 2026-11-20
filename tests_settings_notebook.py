# -*- coding: utf-8 -*-
"""Windows Tk regression tests for the compact, tabbed settings GUI.

Must create the real GUI rather than relying on source-text assertions.
Does not contact APIs, start the USB engine or save credentials to disk.
"""
import copy
import os
import tkinter as tk
import unittest
from unittest.mock import patch

from settings_gui import SettingsWindow


@unittest.skipUnless(os.name=='nt','Tk GUI integration requires Windows runner')
class TestSettingsNotebook(unittest.TestCase):
    def setUp(self):
        # The actual pixel-geometry test maps the real window and processes
        # Tk events. Suppress scheduled USB auto-start, update checks and
        # runtime polling: testing the tab visuals must not launch a second
        # dashboard engine or alter shared runtime_status.json.
        for target in ('_autostart_engine','check_github_update','poll_runtime'):
            mock=patch.object(SettingsWindow,target,lambda self,*args,**kw: None)
            mock.start()
            self.addCleanup(mock.stop)
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
        self.assertEqual(style.theme_use(),'clam')
        tab_style='TURZX.TNotebook.Tab'
        self.assertNotEqual(
            style.lookup(tab_style,'background',('selected',)),
            style.lookup(tab_style,'background',('!selected',)))
        self.assertEqual(style.lookup(tab_style,'foreground',('selected',)),
                         '#FFFFFF')
        max_width=max(
            self.gui._tab_font.measure(self.gui.tabs.tab(p,'text'))
            for p in self.gui.tabs.tabs())
        self.assertGreaterEqual(
            self.gui._tab_width_chars*self.gui._tab_font.measure('0'),
            max_width)
        self.assertEqual(
            int(style.configure(tab_style,'width')),
            self.gui._tab_width_chars)
        # Clam's native "TNotebook.Tab" has a selected-only padding map.
        # Testing expand alone missed the actual shrinking observed in screenshots.
        expected=('18','8','18','8')
        for state in (('selected',),('active',),('!selected',),()):
            pad=style.lookup(tab_style,'padding',state)
            self.assertEqual(
                tuple(str(v) for v in self.root.tk.splitlist(pad)),
                expected,(state,pad))
            expand=style.lookup(tab_style,'expand',state)
            self.assertEqual(
                tuple(str(v) for v in self.root.tk.splitlist(expand)),
                ('0','0','0','0'),(state,expand))

    def test_real_tab_geometry_constant_after_selection_and_theme_changes(self):
        """Actually measure visible Tk tab hit boxes, not tab option values."""
        from theme_presets import PRESETS
        # The setup withdraws the GUI so sizing tests need a mapped window.
        self.root.deiconify()
        try:
            self.root.update()
            notebook=self.gui.tabs
            pages=notebook.tabs()
            self.assertEqual(len(pages),4)

            def point_to_tab(x,y):
                try:
                    return notebook.index(f'@{x},{y}')
                except tk.TclError:
                    return None

            def geometry():
                # Find the horizontal strip intersecting all four tabs.
                width=notebook.winfo_width()
                for y in (16,20,24,28,32):
                    indexes=[point_to_tab(x,y) for x in range(width)]
                    spans=[]
                    for i in range(4):
                        xs=[x for x,idx in enumerate(indexes) if idx==i]
                        if xs:
                            spans.append((min(xs),max(xs)))
                    if len(spans)==4:
                        break
                else:
                    self.fail('Could not measure all visible notebook tabs')
                out=[]
                for i,(left,right) in enumerate(spans):
                    x=(left+right)//2
                    ys=[y for y in range(0,60)
                        if point_to_tab(x,y)==i]
                    self.assertTrue(ys,(i,left,right))
                    out.append((left,right,len(ys),min(ys),max(ys)))
                return out

            original=None
            # Compare actual hit-box widths/heights/positions after EVERY
            # selection and palette change. A selected 30px-wide tab must fail.
            for preset in PRESETS:
                self.gui.vars['settings_color_preset'].set(preset)
                self.gui._on_palette_change()
                for page in pages:
                    notebook.select(page)
                    self.root.update()
                    data=geometry()
                    widths=[right-left+1 for left,right,_,_,_ in data]
                    heights=[h for _,_,h,_,_ in data]
                    self.assertLessEqual(max(widths)-min(widths),1,
                                         (preset,page,widths))
                    self.assertLessEqual(max(heights)-min(heights),1,
                                         (preset,page,heights))
                    if original is None:
                        original=data
                    self.assertEqual(data,original,(preset,page,data,original))
        finally:
            self.root.withdraw()
            self.root.update_idletasks()

    def test_ten_palettes_switch_color_only_and_are_saved(self):
        from theme_presets import PRESETS
        from tkinter import ttk
        self.assertEqual(len(PRESETS),10)
        style=ttk.Style(self.root)
        pages=self.gui.tabs.tabs()
        before_width=self.gui._tab_width_px
        before_chars=self.gui._tab_width_chars
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
            self.assertEqual(before_chars,self.gui._tab_width_chars)
            self.assertEqual(
                tuple(str(v) for v in self.root.tk.splitlist(
                    style.lookup('TURZX.TNotebook.Tab','padding',('selected',)))),
                ('18','8','18','8'))
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
