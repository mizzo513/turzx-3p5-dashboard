# SPDX-License-Identifier: GPL-3.0-or-later
"""Simple Windows settings GUI for the 3.5-inch TURZX automatic dashboard."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import time
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from turzx_dashboard import CITIES, CSV_PATH, JSON_PATH, IR_SCHEDULE_PATH, ROOT, resolve_ir_schedule, OFFICIAL_TIMETABLE, load_settings, save_settings, fetch_weather, load_schedule_csv, train_diagnostics, render_original, jp_now, Weather, choose_trains
import webbrowser
from runtime_ipc import get_runtime_status, request_stop
from text_layout import validate_styles
from panel_layout import validate_panels
from version_info import APP_VERSION


class SettingsWindow:
    def __init__(self, root):
        self.root=root
        self.conf=load_settings()
        self.child=None
        self.await_hash=None
        self.last_message=''
        root.title('TURZX 3.5 設定 V'+APP_VERSION+'（即時反映）')
        # Compact notebook: each tab scrolls independently at high DPI.
        # The action/status bar stays on screen regardless of the selected tab.
        root.geometry('800x540')
        root.minsize(700,425)
        root.columnconfigure(0,weight=1)
        root.rowconfigure(1,weight=1)
        titlebar=ttk.Frame(root,padding=(12,8,12,4))
        titlebar.grid(row=0,column=0,sticky='ew')
        ttk.Label(titlebar,text='TURZX 3.5 設定  V'+APP_VERSION,
                  font=('Yu Gothic UI',13,'bold')).pack(side='left')
        ttk.Label(titlebar,text='480×320 / 画像180度回転',
                  foreground='#52677c').pack(side='right')
        self.tabs=ttk.Notebook(root)
        self.tabs.grid(row=1,column=0,sticky='nsew',padx=10,pady=(1,4))
        self._tab_canvases={}
        display_tab=self._create_settings_tab('表示・時計')
        weather_tab=self._create_settings_tab('天気')
        train_tab=self._create_settings_tab('乗換')
        manage_tab=self._create_settings_tab('外観・更新')
        root.bind('<MouseWheel>',self._on_tab_wheel)
        self.vars={}
        main=display_tab
        r=0
        ttk.Label(main,text='表示・USB・時計',font=('Yu Gothic UI',11,'bold')).grid(
            row=r,column=0,columnspan=3,sticky='w',pady=(0,6));r+=1
        self.vars['auto_start_display']=tk.BooleanVar(value=bool(self.conf.get('auto_start_display',True)))
        ttk.Checkbutton(main,text='アプリ起動時に実機への表示を自動開始',
                        variable=self.vars['auto_start_display']).grid(
                            row=r,column=0,columnspan=3,sticky='w',pady=(0,5));r+=1
        self.field(main,'USBポート','port',r,'AUTO');r+=1
        ttk.Label(main,text='AUTO：USB35INCHIPSV2を自動認識。接続機が複数ある場合はCOM番号を入力',foreground='#5c7184').grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        ttk.Separator(main).grid(row=r,column=0,columnspan=3,sticky='ew',pady=12);r+=1
        ttk.Label(main,text='時計表示・転送方式',font=('Yu Gothic UI',11,'bold')).grid(row=r,column=0,columnspan=3,sticky='w',pady=(0,5));r+=1
        self.vars['show_seconds']=tk.BooleanVar(value=bool(self.conf.get('show_seconds',True)))
        ttk.Checkbutton(main,text='秒を表示する（毎秒更新）',variable=self.vars['show_seconds']).grid(row=r,column=0,columnspan=2,sticky='w');r+=1
        self.vars['clock_12h']=tk.BooleanVar(value=bool(self.conf.get('clock_12h',False)))
        ttk.Checkbutton(main,text='12時間表記',variable=self.vars['clock_12h']).grid(row=r,column=0,columnspan=2,sticky='w');r+=1
        ttk.Label(main,text='時刻取得：NICT NTP（インターネット優先）',foreground='#21709c').grid(row=r,column=0,columnspan=3,sticky='w',pady=(6,2));r+=1
        self.field(main,'NTPサーバー','ntp_server',r,'ntp.nict.jp');r+=1
        self.field(main,'時刻再同期間隔（分）','ntp_sync_minutes',r,'30');r+=1
        ttk.Label(main,text='UDP 123が遮断されている場合はPC時刻へ切替。同期成功後は最長6時間保持。PCの時計は変更しません。',foreground='#5c7184',wraplength=710).grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        self.vars['clock_update_mode']=tk.StringVar(value=self.conf.get('clock_update_mode','compact'))
        ttk.Label(main,text='秒表示の転送方式').grid(row=r,column=0,sticky='w',pady=5)
        ttk.Combobox(main,textvariable=self.vars['clock_update_mode'],values=['compact','safe_strip'],state='readonly',width=25).grid(row=r,column=1,sticky='ew',padx=(10,0));r+=1
        ttk.Label(main,text='compact：秒の数字だけ更新 / safe_strip：従来の横幅全体更新（文字崩れ時）',foreground='#5c7184').grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        main=manage_tab
        r=0
        ttk.Label(main,text='レイアウト編集',font=('Yu Gothic UI',11,'bold')).grid(
            row=r,column=0,columnspan=3,sticky='w',pady=(0,8));r+=1
        ttk.Button(main,text='文字・枠の配置／サイズ／色を編集',command=self.open_layout_editor).grid(row=r,column=0,columnspan=3,sticky='w',pady=(7,0));r+=1
        look=ttk.Frame(main);look.grid(row=r,column=0,columnspan=3,sticky='w',pady=(5,0));r+=1
        ttk.Button(look,text='現在の設定で画面プレビュー',command=self.preview_current).pack(side='left',padx=(0,8))
        ttk.Button(look,text='標準レイアウトへ戻す',command=self.reset_layout).pack(side='left')
        ttk.Separator(main).grid(row=r,column=0,columnspan=3,sticky='ew',pady=10);r+=1
        ttk.Label(main,text='更新・メンテナンス',font=('Yu Gothic UI',11,'bold')).grid(
            row=r,column=0,columnspan=3,sticky='w',pady=(0,8));r+=1
        update_row=ttk.Frame(main);update_row.grid(row=r,column=0,columnspan=3,sticky='w',pady=(4,6));r+=1
        ttk.Button(update_row,text='GitHubで最新版を確認',command=self.check_github_update).pack(side='left',padx=(0,8))
        ttk.Button(update_row,text='更新ZIPを手動で選択',command=self.open_update).pack(side='left')
        self.vars['auto_update_check']=tk.BooleanVar(value=bool(self.conf.get('auto_update_check',True)))
        ttk.Checkbutton(main,text='設定画面を開いたときに最新版を自動確認（更新前に確認あり）',variable=self.vars['auto_update_check']).grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        main=weather_tab
        r=0
        ttk.Label(main,text='天気情報（WeatherAPI.com / Open-Meteo）',
                  font=('Yu Gothic UI',11,'bold')).grid(row=r,column=0,columnspan=3,sticky='w',pady=(0,7));r+=1
        ttk.Label(main,text='天気API取得元').grid(row=r,column=0,sticky='w',pady=5)
        self.vars['weather_provider']=tk.StringVar(
            value='WeatherAPI.com' if self.conf.get('weather_provider','weatherapi')=='weatherapi' else 'Open-Meteo')
        self.weather_provider_combo=ttk.Combobox(
            main,textvariable=self.vars['weather_provider'],
            values=['WeatherAPI.com','Open-Meteo'],state='readonly',width=27)
        self.weather_provider_combo.grid(row=r,column=1,sticky='ew',padx=(10,0));r+=1
        self.field(main,'WeatherAPI.com APIキー','weatherapi_key',r,show='*');r+=1
        ttk.Label(main,text='WeatherAPI.com使用時はAPIキーが必要です。キーはPCの設定に保存し、GitHubには送信しません。',
                  foreground='#5c7184',wraplength=710).grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        ttk.Button(main,text='WeatherAPI.comで無料APIキーを取得',
                   command=lambda:webbrowser.open('https://www.weatherapi.com/signup.aspx')
                   ).grid(row=r,column=0,columnspan=3,sticky='w',pady=(3,6));r+=1
        self.vars['weather_city']=tk.StringVar(value=self.conf.get('weather_city','白山市'))
        ttk.Label(main,text='天気の地域').grid(row=r,column=0,sticky='w',pady=5)
        self.city_combo=ttk.Combobox(main,textvariable=self.vars['weather_city'],values=list(CITIES)+['任意の地点'],state='readonly',width=27)
        self.city_combo.grid(row=r,column=1,sticky='ew',padx=(10,0))
        self.city_combo.bind('<<ComboboxSelected>>',self.city_changed)
        r+=1
        self.field(main,'緯度','weather_latitude',r);r+=1
        self.field(main,'経度','weather_longitude',r);r+=1
        self.field(main,'天気更新間隔（分）','weather_update_minutes',r);r+=1
        main=train_tab
        r=0
        ttk.Label(main,text='列車：加賀笠間 → 金沢 → 津幡',
                  font=('Yu Gothic UI',11,'bold')).grid(row=r,column=0,columnspan=3,sticky='w',pady=(0,7));r+=1
        ttk.Label(main,text='時刻情報の取得元').grid(row=r,column=0,sticky='w',pady=5)
        self.vars['train_source']=tk.StringVar(value=self.conf.get('train_source','ir_schedule'))
        combo=ttk.Combobox(main,textvariable=self.vars['train_source'],values=['ir_schedule','csv','json','google_transit'],state='readonly')
        combo.grid(row=r,column=1,sticky='ew',padx=(10,0));r+=1
        ttk.Label(main,text='ir_schedule：同梱2026/3/14改正ダイヤ / csv・json：外部連携 / google_transit：APIキー',foreground='#5c7184',wraplength=710).grid(row=r,column=0,columnspan=3,sticky='w',pady=(0,5));r+=1
        ttk.Label(main,text='IR時刻表の表示区間').grid(row=r,column=0,sticky='w',pady=5)
        route_choices=('加賀笠間→金沢→津幡','金沢→津幡')
        self.vars['ir_route']=tk.StringVar(value=route_choices[0] if self.conf.get('ir_route','via_kanazawa')=='via_kanazawa' else route_choices[1])
        ttk.Combobox(main,textvariable=self.vars['ir_route'],values=route_choices,state='readonly',width=28).grid(row=r,column=1,sticky='ew',padx=(10,0));r+=1
        ttk.Label(main,text='IR時刻表に収録された列車同士を金沢で接続。遅延・運休は反映しません。',foreground='#5c7184').grid(row=r,column=0,columnspan=3,sticky='w');r+=1
        self.field(main,'列車更新間隔（秒）','train_update_seconds',r);r+=1
        self.field(main,'表示列車数（最大3）','train_count',r);r+=1
        self.field(main,'Google Routes APIキー（任意）','google_maps_api_key',r,show='*');r+=1
        btnrow=ttk.Frame(main);btnrow.grid(row=r,column=0,columnspan=3,sticky='w',pady=(5,7));r+=1
        ttk.Button(btnrow,text='列車候補・データを診断',command=self.diagnose_trains).grid(row=0,column=0,sticky='w',padx=(0,8),pady=(0,4))
        ttk.Button(btnrow,text='同梱時刻表を開く',command=self.open_schedule).grid(row=0,column=1,sticky='w',padx=(0,8),pady=(0,4))
        ttk.Button(btnrow,text='公式時刻表を見る',command=lambda:webbrowser.open(OFFICIAL_TIMETABLE)).grid(row=0,column=2,sticky='w',pady=(0,4))
        ttk.Button(btnrow,text='CSVの読込',command=self.import_csv).grid(row=1,column=0,sticky='w',padx=(0,8))
        ttk.Button(btnrow,text='CSVを開く',command=self.open_csv).grid(row=1,column=1,sticky='w')
        # Persistent controls: tab switching never hides Save / Start / Stop.
        footer=ttk.Frame(root,padding=(12,7,12,9))
        footer.grid(row=2,column=0,sticky='ew')
        footer.columnconfigure(0,weight=1)
        ttk.Separator(footer).grid(row=0,column=0,sticky='ew',pady=(0,6))
        self.status=tk.StringVar(value='設定を変更したら「設定を即時反映」で保存してください。')
        ttk.Label(footer,textvariable=self.status,foreground='#21709c',
                  wraplength=744,justify='left').grid(row=1,column=0,sticky='ew',pady=(0,6))
        row=ttk.Frame(footer)
        row.grid(row=2,column=0,sticky='ew')
        ttk.Button(row,text='設定を即時反映',command=self.save).pack(side='left',padx=(0,7))
        ttk.Button(row,text='天気APIテスト',command=self.test_weather).pack(side='left',padx=(0,7))
        ttk.Button(row,text='表示開始',command=self.start).pack(side='left',padx=(0,7))
        ttk.Button(row,text='表示停止',command=self.stop).pack(side='left',padx=(0,7))
        ttk.Button(row,text='終了',command=self.close).pack(side='right')
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(800,self.poll_runtime)
        if self.conf.get('auto_update_check',True):
            self.root.after(1800,lambda:self.check_github_update(silent=True))
        if self.conf.get('auto_start_display',True):
            self.root.after(350,self._autostart_engine)

    def _create_settings_tab(self,title):
        """Create an independent scrollable page for compact or high-DPI screens."""
        page=ttk.Frame(self.tabs)
        self.tabs.add(page,text=title)
        page.rowconfigure(0,weight=1)
        page.columnconfigure(0,weight=1)
        canvas=tk.Canvas(page,highlightthickness=0,borderwidth=0)
        canvas.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(page,orient='vertical',command=canvas.yview)
        scroll.grid(row=0,column=1,sticky='ns')
        canvas.configure(yscrollcommand=scroll.set)
        inner=ttk.Frame(canvas,padding=(12,8,12,10))
        window=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.columnconfigure(1,weight=1)
        inner.bind('<Configure>',lambda _e,c=canvas:c.configure(scrollregion=c.bbox('all')))
        canvas.bind('<Configure>',lambda e,c=canvas,item=window:c.itemconfigure(item,width=e.width))
        self._tab_canvases[str(page)]=canvas
        return inner

    def _on_tab_wheel(self,event):
        """Scroll only the active settings page, never a detached layout editor."""
        try:
            page=self.tabs.select()
            canvas=self._tab_canvases.get(str(page))
            if canvas is None or not event.delta:
                return
            hovered=self.root.winfo_containing(event.x_root,event.y_root)
            if hovered is None or hovered.winfo_toplevel() is not self.root:
                return
            # Do not scroll the tab when pointer is over the persistent buttons.
            if not str(hovered).startswith(str(canvas.master)):
                return
            units=-int(event.delta/120)
            if not units:units=-1 if event.delta>0 else 1
            canvas.yview_scroll(units,'units')
        except (tk.TclError,AttributeError):
            pass

    def field(self, main, label, name, row, fallback=None, show=None):
        self.vars[name]=tk.StringVar(value=str(self.conf.get(name, fallback or '')))
        ttk.Label(main,text=label).grid(row=row,column=0,sticky='w',pady=4)
        ttk.Entry(main,textvariable=self.vars[name],show=show).grid(row=row,column=1,sticky='ew',padx=(10,0))

    def city_changed(self,_event=None):
        v=self.vars['weather_city'].get()
        if v in CITIES:
            lat,lon=CITIES[v]
            self.vars['weather_latitude'].set(str(lat))
            self.vars['weather_longitude'].set(str(lon))

    def read_form(self):
        conf=dict(self.conf)
        for name,var in self.vars.items():
            value=var.get()
            conf[name]=value.strip() if isinstance(value,str) else value
        if conf['weather_city']=='任意の地点':
            # Can customize coordinates and then display a meaningful place label.
            conf['weather_city']='任意地点'
        conf['weather_latitude']=float(conf['weather_latitude'])
        conf['weather_longitude']=float(conf['weather_longitude'])
        if not (-90<=conf['weather_latitude']<=90 and -180<=conf['weather_longitude']<=180):
            raise ValueError('緯度・経度を確認してください。')
        provider_name=conf.get('weather_provider','WeatherAPI.com')
        provider_values={'WeatherAPI.com':'weatherapi','Open-Meteo':'openmeteo'}
        if provider_name not in provider_values:
            raise ValueError('天気APIの取得元が不正です')
        conf['weather_provider']=provider_values[provider_name]
        conf['weatherapi_key']=str(conf.get('weatherapi_key') or '').strip()
        conf['weather_update_minutes']=int(conf['weather_update_minutes'])
        conf['ntp_sync_minutes']=int(conf.get('ntp_sync_minutes',30))
        if not 5 <= conf['ntp_sync_minutes'] <= 1440:
            raise ValueError('時刻再同期間隔は5～1440分にしてください。')
        if not str(conf.get('ntp_server','')).strip():
            raise ValueError('NTPサーバー名が空欄です。')
        conf['train_update_seconds']=int(conf['train_update_seconds'])
        choice=conf.get('ir_route','加賀笠間→金沢→津幡')
        mapping={'加賀笠間→金沢→津幡':'via_kanazawa','金沢→津幡':'kanazawa_tsubata'}
        if choice not in mapping:raise ValueError('IR時刻表の表示区間が不正です')
        conf['ir_route']=mapping[choice]
        conf['train_count']=int(conf['train_count'])
        if conf['train_count']<1 or conf['train_count']>3:raise ValueError('列車表示数は1～3です。')
        if conf['train_update_seconds']<10:raise ValueError('列車更新間隔は10秒以上です。')
        if conf['weather_update_minutes']<5:raise ValueError('天気更新間隔は5分以上です。')
        if conf['train_source'] not in ('ir_schedule','csv','json','google_transit'):raise ValueError('列車取得元の設定が不正です。')
        if not conf['port']:raise ValueError('COMポートを指定してください。')
        if conf['clock_update_mode'] not in ('compact','safe_strip'):raise ValueError('時計の更新方式が不正です。')
        validate_styles(conf)
        validate_panels(conf)
        return conf

    def save(self):
        try:
            self.conf=self.read_form();save_settings(self.conf)
        except Exception as exc:
            messagebox.showerror('設定エラー',str(exc));return False
        self.await_hash=hashlib.sha256((ROOT/'settings.json').read_bytes()).hexdigest()
        if self.runtime_state():
            self.status.set('設定を保存しました。表示アプリへの反映を確認中…')
        else:
            self.await_hash=None
            self.status.set('設定を保存しました。表示開始時に適用されます。')
        return True

    def test_weather(self):
        try:conf=self.read_form()
        except Exception as exc:messagebox.showerror('入力エラー',str(exc));return
        self.status.set('天気APIと通信中...')
        def work():
            try:
                w=fetch_weather(conf)
                at=w.data_time.astimezone(jp_now().tzinfo).strftime('%H:%M') if w.data_time else '不明'
                label=w.condition_text or ('code '+str(w.code))
                origin='WeatherAPI.com' if w.provider=='weatherapi' else 'Open-Meteo'
                rain=f'、現在降水量 {w.precip_mm}mm（判定には不使用）' if w.precip_mm is not None else ''
                result=f'{origin} / {w.city}: {label}、気温 {w.temperature}℃、当日降水確率 {w.precip}%、気象データ時刻 {at}{rain}'
            except Exception as exc:result='天気APIに接続できません：'+str(exc)[:140]
            self.root.after(0,lambda:self.status.set(result))
        threading.Thread(target=work,daemon=True).start()

    def import_csv(self):
        source=filedialog.askopenfilename(title='train_schedule.csv を選択',filetypes=[('CSV','*.csv')])
        if not source:return
        try:
            from shutil import copyfile
            rows=load_schedule_csv(source)
            if not rows:raise ValueError('有効な depart/arrive データがありません。')
            copyfile(source,CSV_PATH)
            self.status.set(f'CSVを読込みました：{len(rows)}件。データを再読込するには「設定を即時反映」を押してください。')
        except Exception as exc:messagebox.showerror('CSVエラー',str(exc))

    def open_schedule(self):
        try:
            _doc,path=resolve_ir_schedule()
        except Exception as exc:
            messagebox.showwarning('時刻表がありません',str(exc),parent=self.root);return
        if sys.platform=='win32':
            import os
            os.startfile(str(path))
        else: self.status.set(str(path))

    def open_csv(self):
        if not CSV_PATH.exists():
            messagebox.showwarning('CSVがありません','train_schedule.csv が存在しません。');return
        if sys.platform=='win32':import os;os.startfile(str(CSV_PATH))
        else: self.status.set(str(CSV_PATH))

    def diagnose_trains(self):
        """Show the actual selected source, timetable path and next trains."""
        try:
            conf=self.read_form()
            check=train_diagnostics(jp_now(),conf)
            messages=[f"画面/エンジンのバージョン：V{APP_VERSION}",
                      f"取得元：{check['train_source']}",
                      f"区間：{check['train_from']} → {check['train_to']}",
                      f"時刻表：{check.get('schedule_path','(未検出 / ir_schedule以外)')}",
                      f"改正：{check.get('revision','--')}",
                      f"件数：{check.get('schedule_rows','--')}",
                      f"結果：{check.get('status','--')}"]
            if check.get('error') or check.get('schedule_error'):
                messages.append('エラー：'+str(check.get('error') or check.get('schedule_error')))
            for n,t in enumerate(check.get('trains',[]),1):
                messages.append(f"{n}. {t['depart'][11:16]} → {t['arrive'][11:16]}  {t['train']}  {t['platform']}番線")
            if not check.get('trains'):
                messages.append('候補がありません。取得元・区間・時刻表を確認してください。')
            messagebox.showinfo('列車データ診断', '\n'.join(messages), parent=self.root)
        except Exception as exc:
            messagebox.showerror('診断エラー',str(exc),parent=self.root)

    def reset_layout(self):
        """Explicit reset to the standard picture without changing weather/trains."""
        if not messagebox.askyesno('レイアウト初期化',
              '文字と枠の位置・色・サイズだけを初期状態に戻しますか？\n天気・列車・COMの設定は維持します。',parent=self.root):
            return
        try:
            self.conf=self.read_form()
            if (ROOT/'settings.json').exists():
                from shutil import copy2
                stamp=time.strftime('%Y%m%d_%H%M%S')
                copy2(ROOT/'settings.json',ROOT/f'settings_before_layout_reset_{stamp}.json')
            self.conf['text_styles']={}
            self.conf['panel_styles']={}
            save_settings(self.conf)
            self.status.set('標準レイアウトに戻しました。実機には通常0.5秒以内に反映されます。')
        except Exception as exc:
            messagebox.showerror('初期化エラー',str(exc),parent=self.root)

    def preview_current(self):
        """Preview current form and layout using the SAME renderer as the device.

        The weather API is fetched on a worker thread; no invented train/weather
        data are used. Renderer matches the device's logical upright 480x320.
        """
        try:
            conf=self.read_form()
            now=jp_now()
            state=choose_trains(now,conf)
            weather=Weather(city=conf.get('weather_city','白山市'))
            image=render_original(now,weather,state,conf)
        except Exception as exc:
            messagebox.showerror('プレビューエラー',str(exc),parent=self.root);return
        from PIL import ImageTk
        win=tk.Toplevel(self.root)
        win.title('現在の設定でプレビュー｜V'+APP_VERSION)
        win.resizable(False,False)
        text=ttk.Label(win,text='実機を180度回転設置した状態の正立表示。天気は取得後に反映します。',padding=(8,6))
        text.pack()
        view=ttk.Label(win)
        view.pack(padx=8,pady=6)
        def set_image(pic):
            try:
                if not win.winfo_exists():return
                view.photo=ImageTk.PhotoImage(pic)
                view.configure(image=view.photo)
            except tk.TclError:pass
        set_image(image)
        ttk.Label(win,text='列車：設定された取得元から抽出（遅延・運休は未反映）',padding=(8,0,8,8)).pack()
        def worker():
            try: fetched=fetch_weather(dict(conf))
            except Exception:fetched=weather
            def done():
                try:
                    if win.winfo_exists():
                        set_image(render_original(jp_now(),fetched,choose_trains(jp_now(),conf),conf))
                except Exception:pass
            try:self.root.after(0,done)
            except tk.TclError:pass
        threading.Thread(target=worker,daemon=True).start()

    def open_layout_editor(self):
        from layout_editor import LayoutEditor
        LayoutEditor(self)

    def open_update(self):
        from update_manager import start_update_gui
        start_update_gui(self)

    def check_github_update(self, silent=False):
        from github_update_ui import check_for_updates
        check_for_updates(self,silent=silent)

    def runtime_state(self):
        return get_runtime_status()

    def poll_runtime(self):
        state=self.runtime_state()
        if state and state.get('app_version')!=APP_VERSION:
            ver=state.get('app_version') or '不明（旧版）'
            self.status.set('注意：表示エンジン V'+ver+' が動作中です。設定画面は V'+APP_VERSION+' です。表示停止→開始してください。')
            try:self.root.after(800,self.poll_runtime)
            except tk.TclError:pass
            return
        if self.await_hash and state and state.get('settings_hash')==self.await_hash:
            self.status.set('設定反映完了｜'+state.get('clock','--:--')+'｜時刻 '+state.get('time_source','--')+'｜天気 '+state.get('weather_city','')+'｜列車 '+state.get('train_status',''))
            self.await_hash=None
        elif not self.await_hash and state:
            status_msg='動作中 '+state.get('clock','')+'｜時刻 '+state.get('time_source','同期中')+'｜'+('実機接続' if state.get('connected') else '接続待ち')+'｜'+state.get('port','')
            if self.last_message!=status_msg:
                self.last_message=status_msg
                self.status.set(status_msg)
        try:self.root.after(800,self.poll_runtime)
        except tk.TclError:pass

    def _autostart_engine(self, attempt=0):
        """Run the saved display automatically without opening a second engine.

        During an app upgrade, the previous version's engine may still be
        stopping. Allow it to exit before launching the new EXE engine.
        """
        try:
            if not self.vars['auto_start_display'].get():
                return
            state=self.runtime_state()
            if state:
                if state.get('app_version') != APP_VERSION and attempt < 20:
                    self.root.after(500,lambda:self._autostart_engine(attempt+1))
                return
            self.start()
        except tk.TclError:
            return

    def start(self):
        if not self.save():return
        if self.runtime_state():
            self.status.set('表示アプリは動作中です。設定はそのまま反映されます。');return
        try:
            # The frozen single EXE runs both GUI and background engine.
            if getattr(sys,'frozen',False):
                cmd=[sys.executable,'--engine']
            else:
                executable=Path(sys.executable)
                gui_exe=executable.with_name('pythonw.exe') if sys.platform=='win32' else executable
                if sys.platform=='win32' and not gui_exe.exists():
                    raise FileNotFoundError('pythonw.exe がありません。setupを確認してください。')
                cmd=[str(gui_exe),str(Path(__file__).resolve().with_name('turzx_dashboard.py'))]
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            logfile=(ROOT/'logs');logfile.mkdir(exist_ok=True)
            # In pythonw mode stderr and stdout may not exist, route to files.
            out=open(logfile/'background_stdout.log','a',encoding='utf-8')
            err=open(logfile/'background_stderr.log','a',encoding='utf-8')
            try:
                self.child=subprocess.Popen(cmd,cwd=str(ROOT),creationflags=flags,stdout=out,stderr=err,stdin=subprocess.DEVNULL)
            finally:
                out.close();err.close()
            self.status.set('非表示で起動しました。接続状況を確認しています…')
        except Exception as exc:messagebox.showerror('起動エラー',str(exc))

    def stop(self):
        if not self.runtime_state():
            self.status.set('表示アプリは動作していません。');return
        try:
            if not request_stop():
                (ROOT/'STOP_REQUEST.flag').write_text('stop',encoding='ascii')
            self.status.set('表示停止を要求しました。USB通信が完了すると終了します。')
        except Exception as exc:messagebox.showerror('停止エラー',str(exc))

    def close(self):
        # Closing the GUI leaves the background display running.
        self.root.unbind('<MouseWheel>')
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk()
    try: SettingsWindow(root);root.mainloop()
    except Exception as exc:
        messagebox.showerror('起動エラー',str(exc));raise
