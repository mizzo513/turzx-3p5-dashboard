# SPDX-License-Identifier: GPL-3.0-or-later
"""Text and panel visual editor with exact Pillow text bounds, independent wheel."""
from __future__ import annotations
import copy
import re
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from PIL import ImageTk
from panel_layout import PANELS, settings as panel_props, validate_panels
from layout_wheel import wheel_value, NUMERIC_FIELDS
from layout_groups import GROUPS, matching_group, adjust_group
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
        self.unsaved=False
        self.refresh_job=None
        self.status=tk.StringVar(value='プレビューは実機へ送信しません。編集後に「実機へ即時反映」を押してください。')
        self.hit_boxes={}

        header=ttk.Frame(self.window,padding=(12,8));header.grid(row=0,column=0,sticky='ew')
        ttk.Label(header,text='文字・パネル枠の編集 (480×320)',font=('Yu Gothic UI',14,'bold')).pack(anchor='w')
        ttk.Label(header,text='数値欄のホイールで±1、Shift+ホイールで±10。プレビューのみ変更し、実機は保存ボタンで反映。',foreground='#597184').pack(anchor='w')
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
        self.individual_mode=tk.BooleanVar(value=False)
        self.group_label=tk.StringVar(value='')
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
            if key in NUMERIC_FIELDS:
                # Only the hovered numeric entry handles the event. "break"
                # prevents both the editor list and the background settings
                # window from scrolling.
                entry.bind('<MouseWheel>',lambda event,n=key:self.on_numeric_wheel(event,n))
                entry.bind('<Button-4>',lambda event,n=key:self.on_numeric_wheel(event,n,linux_direction=1))
                entry.bind('<Button-5>',lambda event,n=key:self.on_numeric_wheel(event,n,linux_direction=-1))
            if key in ('color','outline','fill'):
                ttk.Button(fields,text='選択',width=5,command=lambda n=key:self.pick_color(n)).grid(row=row,column=2,padx=(0,3))
            self.fieldwidgets[key]=(lbl,entry)
        for var in self.vars.values():var.trace_add('write',self.on_field_edit)
        actions=ttk.Frame(fields)
        actions.grid(row=10,column=0,columnspan=3,pady=(6,0),sticky='w')
        self.individual_switch=ttk.Checkbutton(
            actions,text='個別設定',
            variable=self.individual_mode,command=self.on_mode_change)
        self.individual_switch.pack(side='left',padx=(0,8))
        ttk.Button(actions,text='選択を初期化',command=self.reset_one).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='全て初期化',command=self.reset_all).pack(side='left')

        bottom=ttk.Frame(self.window,padding=(12,3,12,4));bottom.grid(row=3,column=0,sticky='ew')
        ttk.Button(bottom,text='実機へ即時反映（保存）',command=self.apply).pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='文字グループ一括調整',command=self.open_group_editor).pack(side='left',padx=(0,8))
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
        if kind=='text':
            group=self.selected_group()
            self.group_label.set(
                '一括調整：'+group+'（X・Y・文字サイズ）'
                if group and not self.individual_mode.get() else
                '個別調整：選択文字のみ')
            self.individual_switch.configure(state='normal' if group else 'disabled')
        else:
            self.group_label.set('パネル枠は個別に調整')
            self.individual_switch.configure(state='disabled')
        self.loading=False

    def selected_group(self):
        if self.selected[0]!='text':
            return None
        key=self.selected[1]
        group=matching_group(key)
        return group if group in GROUPS and key in GROUPS[group][1] else None

    def is_group_mode(self):
        selector=getattr(self,'individual_mode',None)
        return bool(self.selected_group() and selector is not None and not selector.get())

    def on_mode_change(self):
        self.load_selected()
        self.refresh()

    def on_field_edit(self,*_):
        if self.loading:return
        kind,key=self.selected
        try:
            if kind=='text':
                new={a:int(self.vars[a].get()) for a in ('x','y','size')}
                new['color']=self.vars['color'].get().upper()
                if not (0<=new['x']<480 and 0<=new['y']<320 and 8<=new['size']<=52):return
                if not re.fullmatch(r'#[0-9A-F]{6}',new['color']):return
                if self.is_group_mode():
                    old=text_props({'text_styles':self.text_styles},key)
                    dx=new['x']-old['x']
                    dy=new['y']-old['y']
                    dsize=new['size']-old['size']
                    if dx or dy or dsize:
                        try:
                            self.text_styles=adjust_group(
                                self.text_styles,self.panel_styles,
                                self.selected_group(),dx=dx,dy=dy,dsize=dsize)
                        except ValueError as exc:
                            self.status.set('調整不可：'+str(exc))
                            self.load_selected()
                            return
                    # Color remains an individual property, even in group mode.
                    if new['color']!=old['color']:
                        self.text_styles[key]={**self.text_styles.get(key,{}),
                                               'color':new['color']}
                else:
                    self.text_styles[key]=new
            else:
                new={a:int(self.vars[a].get()) for a in ('x','y','w','h','radius','border_width')}
                new['fill']=self.vars['fill'].get().upper()
                new['outline']=self.vars['outline'].get().upper()
                if not all(re.fullmatch(r'#[0-9A-F]{6}',new[a]) for a in ('fill','outline')):return
                if not (0<=new['x']<480 and 0<=new['y']<320 and 2<=new['w']<=480-new['x'] and 2<=new['h']<=320-new['y'] and 0<=new['radius']<=30 and 0<=new['border_width']<=12):return
                self.panel_styles[key]=new
        except (ValueError,TypeError):return
        self.unsaved=True
        self.status.set('未反映：プレビューのみ更新しました。実機へ反映するには「実機へ即時反映（保存）」を押してください。')
        self.queue_refresh()

    def on_numeric_wheel(self,event,name,linux_direction=None):
        """Change the hovered numeric entry; never save or communicate with hardware."""
        if name not in NUMERIC_FIELDS:
            return 'break'
        kind,_=self.selected
        if (kind=='text' and name not in ('x','y','size')) or (
                kind=='panel' and name=='size'):
            return 'break'
        if linux_direction is None:
            delta=getattr(event,'delta',0)
            if not delta:
                return 'break'
            direction=1 if delta>0 else -1
        else:
            direction=linux_direction
        props=self.current_props()
        try:
            current=int(self.vars[name].get())
        except (TypeError,ValueError):
            current=int(props[name])
        new_value=wheel_value(name,current,direction,kind=kind,geometry=props,
                              shift=bool(getattr(event,'state',0)&0x0001))
        if new_value!=current or self.vars[name].get()!=str(new_value):
            self.vars[name].set(str(new_value))
            # A StringVar trace updates preview-only self.text_styles/panel_styles.
            # Deliberately do NOT call gui.save(), write settings, or send USB.
        return 'break'

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
        self.drag={'x':x,'y':y,'kind':'resize' if corner else 'move',
                   'initial':p.copy(),'base_styles':copy.deepcopy(self.text_styles)}

    def on_drag(self,event):
        if not self.drag:return
        kind,key=self.selected
        p=self.drag['initial'];dx=event.x-self.drag['x'];dy=event.y-self.drag['y']
        if kind=='text':
            if self.is_group_mode():
                try:
                    self.text_styles=adjust_group(
                        self.drag['base_styles'],self.panel_styles,self.selected_group(),
                        dx=dx,dy=dy)
                except ValueError:
                    return
            else:
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
        self.unsaved=True
        self.status.set('未反映：プレビューのみ更新しました。保存ボタンを押すと実機へ反映されます。')
        self.load_selected();self.queue_refresh()

    def on_up(self,_event):
        self.drag=None

    def pick_color(self,name):
        value=self.vars[name].get()
        chosen=colorchooser.askcolor(color=value if re.fullmatch('#[0-9A-Fa-f]{6}',value) else '#FFFFFF',
                                     parent=self.window,title='色選択')[1]
        if chosen:self.vars[name].set(chosen.upper())

    def open_group_editor(self):
        """Move and resize multiple related text labels without changing USB output.

        The separate dialog does not change the current individual text editor
        selection. All adjustments are staged until the main Apply button.
        """
        dialog=tk.Toplevel(self.window)
        dialog.title('文字グループ一括調整')
        dialog.geometry('525x270')
        dialog.resizable(False,False)
        dialog.transient(self.window)
        frame=ttk.Frame(dialog,padding=15)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='同じ枠内の文字をまとめて調整',
                  font=('Yu Gothic UI',12,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,8))
        ttk.Label(frame,text='文字グループ').grid(row=1,column=0,sticky='w')
        chosen=tk.StringVar(value=matching_group(self.selected[1]))
        ttk.Combobox(frame,textvariable=chosen,values=tuple(GROUPS),
                     state='readonly',width=41).grid(row=1,column=1,columnspan=2,sticky='ew',padx=(9,0),pady=4)
        values={}
        labels=(('dx','左右移動（px）'),('dy','上下移動（px）'),('dsize','文字サイズ増減（px）'))
        for row,(key,label) in enumerate(labels,start=2):
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=3)
            values[key]=tk.StringVar(value='0')
            entry=ttk.Spinbox(frame,from_=-50,to=50,textvariable=values[key],width=10)
            entry.grid(row=row,column=1,sticky='w',padx=(9,6))
            # Existing editor already uses numeric wheel; this dialog allows
            # wheel increments as well without ever saving automatically.
            def increment(event,name=key):
                try:
                    amount=int(values[name].get())
                except (TypeError,ValueError):
                    amount=0
                delta=10 if event.state & 0x0001 else 1
                if event.delta<0:delta=-delta
                values[name].set(str(max(-250,min(250,amount+delta))))
                return 'break'
            entry.bind('<MouseWheel>',increment)
        ttk.Label(frame,text='各文字の間隔・色は維持。値はプレビューだけに反映されます。',
                  foreground='#597184').grid(row=5,column=0,columnspan=3,sticky='w',pady=(9,6))
        actions=ttk.Frame(frame)
        actions.grid(row=6,column=0,columnspan=3,sticky='w')
        def preview_adjustment():
            try:
                staged=adjust_group(self.text_styles,self.panel_styles,chosen.get(),
                                    dx=values['dx'].get(),dy=values['dy'].get(),
                                    dsize=values['dsize'].get())
                self.text_styles=staged
                self.unsaved=True
                self.status.set('文字グループを一括調整しました（未保存）。実機へ反映するには保存ボタンを押してください。')
                self.load_selected()
                self.refresh()
                for var in values.values():var.set('0')
            except (ValueError,TypeError) as exc:
                messagebox.showwarning('一括調整できません',str(exc),parent=dialog)
        ttk.Button(actions,text='プレビューへ適用',command=preview_adjustment).pack(side='left',padx=(0,10))
        ttk.Button(actions,text='閉じる',command=dialog.destroy).pack(side='left')

    def reset_one(self):
        kind,key=self.selected
        (self.text_styles if kind=='text' else self.panel_styles).pop(key,None)
        self.unsaved=True
        self.status.set('未反映：選択項目を初期化しました。保存ボタンで実機へ反映してください。')
        self.load_selected();self.refresh()

    def reset_all(self):
        if messagebox.askyesno('初期化','すべての文字・枠を標準レイアウトに戻しますか？',parent=self.window):
            self.text_styles={};self.panel_styles={}
            self.unsaved=True
            self.status.set('未反映：プレビューは初期化されています。保存ボタンで実機へ反映してください。')
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
                self.unsaved=False
                self.status.set('保存しました。表示中の実機に変更が反映されます。文字や枠の重なりはプレビューで確認してください。')
        except Exception as exc:
            messagebox.showerror('レイアウト設定エラー',str(exc),parent=self.window)
