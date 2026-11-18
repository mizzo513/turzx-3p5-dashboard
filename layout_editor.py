# SPDX-License-Identifier: GPL-3.0-or-later
"""Text and panel visual editor with exact Pillow text bounds, independent wheel."""
from __future__ import annotations
import copy
import re
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from PIL import ImageTk
from panel_layout import PANELS, settings as panel_props, validate_panels
from text_layout import ELEMENTS, props as text_props, validate_styles
from turzx_dashboard import Weather, TrainState, choose_trains, jp_now, render_original
from version_info import APP_VERSION


class LayoutEditor:
    def __init__(self, gui):
        self.gui=gui
        self.window=tk.Toplevel(gui.root)
        self.window.title('TURZX 3.5｜文字と枠のレイアウト編集 V'+APP_VERSION)
        self.window.geometry('845x725')
        self.window.minsize(760,640)
        self.window.columnconfigure(0,weight=1)
        self.window.rowconfigure(2,weight=1)
        self.text_styles=copy.deepcopy(gui.conf.get('text_styles') or {})
        self.panel_styles=copy.deepcopy(gui.conf.get('panel_styles') or {})
        self.selected=('text','clock_datetime')
        self.drag=None
        self.loading=False
        self.refresh_job=None
        self.status=tk.StringVar(value='プレビューは実機へ送信しません。編集後に「実機へ即時反映」を押してください。')
        self.hit_boxes={}

        header=ttk.Frame(self.window,padding=(12,8));header.grid(row=0,column=0,sticky='ew')
        ttk.Label(header,text='文字・パネル枠の編集 (480×320)',font=('Yu Gothic UI',14,'bold')).pack(anchor='w')
        ttk.Label(header,text='左で編集対象を選択。プレビューの対象をドラッグして移動できます。枠は右下をドラッグして拡大縮小します。',foreground='#597184').pack(anchor='w')
        self.preview=tk.Canvas(self.window,width=480,height=320,highlightthickness=1,highlightbackground='#70879f',cursor='hand2')
        self.preview.grid(row=1,column=0,pady=(2,8))
        self.preview.bind('<ButtonPress-1>',self.on_down)
        self.preview.bind('<B1-Motion>',self.on_drag)
        self.preview.bind('<ButtonRelease-1>',self.on_up)
        # Explicitly stop wheel events inside the editor so none reach the settings toplevel.
        self.window.bind('<MouseWheel>',lambda event:'break')

        controls=ttk.Frame(self.window,padding=(14,0,14,4))
        controls.grid(row=2,column=0,sticky='nsew')
        controls.columnconfigure(1,weight=1)
        controls.rowconfigure(0,weight=1)
        left=ttk.Frame(controls);left.grid(row=0,column=0,sticky='nsw',padx=(0,12))
        ttk.Label(left,text='編集する文字・枠').pack(anchor='w')
        listframe=ttk.Frame(left);listframe.pack(fill='both',expand=True)
        sb=ttk.Scrollbar(listframe)
        self.listbox=tk.Listbox(listframe,height=11,width=25,yscrollcommand=sb.set,exportselection=False)
        sb.configure(command=self.listbox.yview)
        self.listbox.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
        # Listbox handles wheel natively on Windows; do not intercept or forward to parent.
        self.keys=[('text',k) for k in ELEMENTS]+[('panel',k) for k in PANELS]
        for category,key in self.keys:
            caption=ELEMENTS[key][0] if category=='text' else PANELS[key][0]
            self.listbox.insert('end',('文字：' if category=='text' else '枠　：')+caption)
        self.listbox.selection_set(0)
        self.listbox.bind('<<ListboxSelect>>',self.on_selection)

        fields=ttk.LabelFrame(controls,text='選択項目の設定',padding=9)
        fields.grid(row=0,column=1,sticky='nsew')
        fields.columnconfigure(1,weight=1)
        self.vars={k:tk.StringVar() for k in ('x','y','size','color','w','h','radius','border_width','outline','fill')}
        self.fieldwidgets={}
        entries=[('x','X座標'),('y','Y座標'),('size','文字サイズ (px)'),('color','文字色 (#RRGGBB)'),
                 ('w','枠の幅 (px)'),('h','枠の高さ (px)'),('radius','角丸半径'),
                 ('border_width','枠線の太さ'),('outline','枠線色 (#RRGGBB)'),('fill','背景色 (#RRGGBB)')]
        for row,(key,label) in enumerate(entries):
            lbl=ttk.Label(fields,text=label)
            lbl.grid(row=row,column=0,sticky='w',pady=1)
            entry=ttk.Entry(fields,textvariable=self.vars[key],width=13)
            entry.grid(row=row,column=1,sticky='ew',pady=1,padx=(8,4))
            if key in ('color','outline','fill'):
                ttk.Button(fields,text='選択',width=5,command=lambda n=key:self.pick_color(n)).grid(row=row,column=2,padx=(0,3))
            self.fieldwidgets[key]=(lbl,entry)
        for var in self.vars.values():var.trace_add('write',self.on_field_edit)
        actions=ttk.Frame(fields);actions.grid(row=10,column=0,columnspan=3,pady=(9,0),sticky='w')
        ttk.Button(actions,text='選択項目を初期化',command=self.reset_one).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='全項目を初期化',command=self.reset_all).pack(side='left')

        bottom=ttk.Frame(self.window,padding=(12,3,12,4));bottom.grid(row=3,column=0,sticky='ew')
        ttk.Button(bottom,text='実機へ即時反映（保存）',command=self.apply).pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='プレビュー更新',command=self.refresh).pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='閉じる',command=self.window.destroy).pack(side='right')
        ttk.Label(self.window,textvariable=self.status,foreground='#21709c',padding=(12,0,12,8)).grid(row=4,column=0,sticky='ew')
        self.load_selected()
        self.refresh()

    def current_props(self):
        kind,key=self.selected
        if kind=='text':return text_props({'text_styles':self.text_styles},key)
        return panel_props({'panel_styles':self.panel_styles},key)

    def load_selected(self):
        self.loading=True
        kind,key=self.selected
        p=self.current_props()
        for name in self.vars:
            self.vars[name].set(str(p[name]) if name in p else '')
        names=('x','y','size','color') if kind=='text' else ('x','y','w','h','radius','border_width','outline','fill')
        # Hide entries not applicable to the selected type.
        for name,(label,entry) in self.fieldwidgets.items():
            if name in names:
                label.grid();entry.grid()
            else:
                label.grid_remove();entry.grid_remove()
        self.loading=False

    def on_field_edit(self,*_):
        if self.loading:return
        kind,key=self.selected
        try:
            if kind=='text':
                new={a:int(self.vars[a].get()) for a in ('x','y','size')}
                new['color']=self.vars['color'].get().upper()
                if not (0<=new['x']<480 and 0<=new['y']<320 and 8<=new['size']<=52):return
                if not re.fullmatch(r'#[0-9A-F]{6}',new['color']):return
                self.text_styles[key]=new
            else:
                new={a:int(self.vars[a].get()) for a in ('x','y','w','h','radius','border_width')}
                new['fill']=self.vars['fill'].get().upper()
                new['outline']=self.vars['outline'].get().upper()
                if not all(re.fullmatch(r'#[0-9A-F]{6}',new[a]) for a in ('fill','outline')):return
                if not (0<=new['x']<480 and 0<=new['y']<320 and 2<=new['w']<=480-new['x'] and 2<=new['h']<=320-new['y'] and 0<=new['radius']<=30 and 0<=new['border_width']<=12):return
                self.panel_styles[key]=new
        except (ValueError,TypeError):return
        self.queue_refresh()

    def on_selection(self,_event=None):
        idx=self.listbox.curselection()
        if not idx:return
        self.selected=self.keys[idx[0]]
        self.load_selected();self.refresh()

    def set_selection(self,target):
        if target not in self.keys:return
        idx=self.keys.index(target)
        self.listbox.selection_clear(0,'end')
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.selected=target
        self.load_selected();self.refresh()

    def get_bounds(self,target):
        box=self.hit_boxes.get(target[0]+':'+target[1])
        if box is not None:return box
        p=self.current_props()
        return (p['x'],p['y'],p['x']+max(1,p.get('w',12))-1,p['y']+max(1,p.get('h',16))-1)

    def on_down(self,event):
        x,y=event.x,event.y
        if not (0<=x<480 and 0<=y<320):return
        selected_box=self.get_bounds(self.selected)
        selected_panel=self.selected[0]=='panel'
        corner=selected_panel and abs(x-selected_box[2])<=9 and abs(y-selected_box[3])<=9
        if not corner:
            # Clicking an actual rendered text selects that text; panel hit testing selects smallest containing panel.
            text_matches=[];panel_matches=[]
            for item in self.keys:
                box=self.hit_boxes.get(item[0]+':'+item[1])
                if box and box[0]-2<=x<=box[2]+2 and box[1]-2<=y<=box[3]+2:
                    if item[0]=='text':text_matches.append(item)
                    else:panel_matches.append(((box[2]-box[0]+1)*(box[3]-box[1]+1),item))
            target=text_matches[-1] if text_matches else (min(panel_matches)[1] if panel_matches else self.selected)
            if target!=self.selected:
                self.set_selection(target)
        p=self.current_props()
        self.drag={'x':x,'y':y,'kind':'resize' if corner else 'move','initial':p.copy()}

    def on_drag(self,event):
        if not self.drag:return
        kind,key=self.selected
        p=self.drag['initial'];dx=event.x-self.drag['x'];dy=event.y-self.drag['y']
        if kind=='text':
            new={'x':min(479,max(0,p['x']+dx)), 'y':min(319,max(0,p['y']+dy)),
                 'size':p['size'],'color':p['color']}
            self.text_styles[key]=new
        else:
            if self.drag['kind']=='resize':
                new=dict(p)
                new['w']=min(480-new['x'],max(2,p['w']+dx))
                new['h']=min(320-new['y'],max(2,p['h']+dy))
            else:
                new=dict(p)
                new['x']=min(480-new['w'],max(0,p['x']+dx))
                new['y']=min(320-new['h'],max(0,p['y']+dy))
            self.panel_styles[key]=new
        self.load_selected();self.queue_refresh()

    def on_up(self,_event):
        self.drag=None

    def pick_color(self,name):
        value=self.vars[name].get()
        chosen=colorchooser.askcolor(color=value if re.fullmatch('#[0-9A-Fa-f]{6}',value) else '#FFFFFF',
                                     parent=self.window,title='色選択')[1]
        if chosen:self.vars[name].set(chosen.upper())

    def reset_one(self):
        kind,key=self.selected
        (self.text_styles if kind=='text' else self.panel_styles).pop(key,None)
        self.load_selected();self.refresh()

    def reset_all(self):
        if messagebox.askyesno('初期化','すべての文字・枠を標準レイアウトに戻しますか？',parent=self.window):
            self.text_styles={};self.panel_styles={}
            self.load_selected();self.refresh()

    def preview_config(self):
        try:cfg=self.gui.read_form()
        except (ValueError,TypeError):cfg=dict(self.gui.conf)
        cfg['text_styles']=copy.deepcopy(self.text_styles)
        cfg['panel_styles']=copy.deepcopy(self.panel_styles)
        return cfg

    def queue_refresh(self):
        if self.refresh_job is not None:
            self.window.after_cancel(self.refresh_job)
        self.refresh_job=self.window.after(40,self.refresh)

    def refresh(self):
        self.refresh_job=None
        cfg=self.preview_config()
        now=jp_now();weather=Weather(city=cfg.get('weather_city','白山市'))
        try:train=choose_trains(now,cfg)
        except Exception:train=TrainState([],'読込失敗',cfg.get('train_source','ir_schedule'))
        boxes={}
        img=render_original(now,weather,train,cfg,hit_boxes=boxes)
        self.hit_boxes=boxes
        self.bitmap=ImageTk.PhotoImage(img)
        self.preview.delete('all')
        self.preview.create_image(0,0,image=self.bitmap,anchor='nw')
        box=boxes.get(self.selected[0]+':'+self.selected[1])
        if box:
            x0,y0,x1,y1=box
            self.preview.create_rectangle(x0,y0,x1,y1,outline='#FFDB3D',width=2,dash=(4,2))
            if self.selected[0]=='panel':
                self.preview.create_rectangle(x1-4,y1-4,x1+4,y1+4,fill='#FFDB3D',outline='#171717')
        else:
            # Invisible value in current dataset: show its configurable anchor instead.
            p=self.current_props()
            x,y=p['x'],p['y']
            self.preview.create_line(x-5,y,x+5,y,fill='#FFDB3D',width=2)
            self.preview.create_line(x,y-5,x,y+5,fill='#FFDB3D',width=2)

    def apply(self):
        try:
            cfg=self.preview_config()
            validate_styles(cfg);validate_panels(cfg)
            # Update persisted data only after successful validation.
            self.gui.conf['text_styles']=copy.deepcopy(self.text_styles)
            self.gui.conf['panel_styles']=copy.deepcopy(self.panel_styles)
            if self.gui.save():
                self.status.set('保存しました。表示中の実機に変更が反映されます。文字や枠の重なりはプレビューで確認してください。')
        except Exception as exc:
            messagebox.showerror('レイアウト設定エラー',str(exc),parent=self.window)
