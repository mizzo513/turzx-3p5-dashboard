# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable visual panel geometry and colors (logical 480 x 320 coordinates)."""
from __future__ import annotations
import re

# name, (left, top, right, bottom), radius, fill, border, thickness
PANELS = {
    'header': ('上段 時計枠', (5, 5, 474, 45), 9, '#0E2235', '#226584', 1),
    'weather': ('天気全体枠', (5, 51, 127, 315), 9, '#0E2235', '#226584', 1),
    'train': ('列車全体枠', (133, 51, 474, 315), 9, '#0E2235', '#226584', 1),
    'train_1': ('列車1枠', (138, 79, 469, 150), 7, '#0C3644', '#55E5A2', 1),
    'train_2': ('列車2枠', (138, 155, 469, 226), 7, '#132E43', '#226584', 1),
    'train_3': ('列車3枠', (138, 231, 469, 307), 7, '#132E43', '#226584', 1),
}

def settings(conf, key):
    label, xy, radius, fill, border, thickness = PANELS[key]
    overrides = conf.get('panel_styles') or {}
    value = overrides.get(key, {}) if isinstance(overrides, dict) else {}
    if not isinstance(value, dict): value = {}
    def as_int(name, base, low, high):
        try: return min(high, max(low, int(value.get(name,base))))
        except (ValueError, TypeError): return base
    x0,y0,x1,y1=xy
    left=as_int('x',x0,0,479); top=as_int('y',y0,0,319)
    width=as_int('w',x1-x0+1,2,480)
    height=as_int('h',y1-y0+1,2,320)
    width=min(width, 480-left)
    height=min(height, 320-top)
    def color(key,base):
        v=str(value.get(key,base)).upper()
        return v if re.fullmatch(r'#[0-9A-F]{6}',v) else base
    return {'x':left,'y':top,'w':width,'h':height,
            'radius':as_int('radius',radius,0,30),
            'border_width':as_int('border_width',thickness,0,12),
            'fill':color('fill',fill),'outline':color('outline',border)}


def validate_panels(conf):
    changes = conf.get('panel_styles') or {}
    if not isinstance(changes,dict):raise ValueError('panel_styles はオブジェクトが必要です')
    for key,val in changes.items():
        if key not in PANELS: continue
        if not isinstance(val,dict):raise ValueError(f'{key}: 不正なパネル設定')
        for name,lo,hi in (('x',0,479),('y',0,319),('w',2,480),('h',2,320),('radius',0,30),('border_width',0,12)):
            if name in val and not lo<=int(val[name])<=hi:raise ValueError(f'{key}/{name} の数値が範囲外です')
        for name in ('fill','outline'):
            if name in val and not re.fullmatch(r'#[0-9a-fA-F]{6}',str(val[name])):
                raise ValueError(f'{key}/{name} は #RRGGBB で指定してください')
        sp=settings(conf,key)
        if sp['x']+int(val.get('w',sp['w']))>480 or sp['y']+int(val.get('h',sp['h']))>320:
            raise ValueError(f'{key}: 枠が画面外へはみ出します')


def draw_panel(draw, conf, key):
    sp=settings(conf,key)
    x,y,w,h=sp['x'],sp['y'],sp['w'],sp['h']
    bound=(x,y,x+w-1,y+h-1)
    radius=min(sp['radius'],(w-1)//2,(h-1)//2)
    # outline-width=0: no outline
    kwargs={'radius':radius,'fill':sp['fill']}
    if sp['border_width']:
        kwargs.update(outline=sp['outline'],width=sp['border_width'])
    draw.rounded_rectangle(bound,**kwargs)
    return bound
