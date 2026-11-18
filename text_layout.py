"""Human-editable text labels for the 480x320 unrotated layout."""
from __future__ import annotations
import re

# (Japanese name, x, y, font px, color hex, font kind, default width)
ELEMENTS = {
    'clock_datetime': ('日付・時刻', 13, 11, 25, '#F3F9FD', 'ja', 397),
    'version': ('右下バージョン', 433, 40, 9, '#9CB9CA', 'num', 38),
    'weather_city': ('天気 地域名', 13, 68, 14, '#F3F9FD', 'ja', 149),
    'weather_description': ('天気 状態', 66, 108, 13, '#F3F9FD', 'ja', 90),
    'weather_temperature': ('天気 現在気温', 68, 132, 24, '#F3F9FD', 'num', 95),
    'weather_high_label': ('最高 ラベル', 13, 174, 12, '#FAC563', 'ja', 45),
    'weather_high': ('最高気温', 77, 174, 13, '#FAC563', 'num', 80),
    'weather_low_label': ('最低 ラベル', 13, 194, 12, '#21DFF0', 'ja', 45),
    'weather_low': ('最低気温', 77, 194, 13, '#21DFF0', 'num', 80),
    'weather_rain_label': ('降水 ラベル', 13, 216, 11, '#9CB9CA', 'ja', 52),
    'weather_rain': ('降水確率', 77, 216, 12, '#F3F9FD', 'num', 80),
    'weather_humidity_label': ('湿度 ラベル', 13, 239, 11, '#9CB9CA', 'ja', 52),
    'weather_humidity': ('湿度', 77, 239, 12, '#F3F9FD', 'num', 80),
    'weather_wind_label': ('風 ラベル', 13, 261, 11, '#9CB9CA', 'ja', 52),
    'weather_wind': ('風速', 77, 261, 11, '#F3F9FD', 'num', 80),
    'train_header': ('路線名', 182, 69, 17, '#F3F9FD', 'ja', 194),
    'train_header_note': ('列車件数ラベル', 402, 74, 11, '#21DFF0', 'ja', 65),
    'train_index_1': ('列車1 番号', 186, 102, 15, '#21DFF0', 'num', 20),
    'train_time_1': ('列車1 時刻', 209, 99, 20, '#F3F9FD', 'num', 248),
    'train_detail_1': ('列車1 詳細', 209, 128, 11, '#9CB9CA', 'ja', 248),
    'train_index_2': ('列車2 番号', 186, 164, 15, '#21DFF0', 'num', 20),
    'train_time_2': ('列車2 時刻', 209, 161, 20, '#F3F9FD', 'num', 248),
    'train_detail_2': ('列車2 詳細', 209, 190, 11, '#9CB9CA', 'ja', 248),
    'train_index_3': ('列車3 番号', 186, 226, 15, '#21DFF0', 'num', 20),
    'train_time_3': ('列車3 時刻', 209, 223, 20, '#F3F9FD', 'num', 248),
    'train_detail_3': ('列車3 詳細', 209, 252, 11, '#9CB9CA', 'ja', 248),
    'train_placeholder_2': ('列車2 空欄表示', 194, 168, 14, '#5A768A', 'num', 80),
    'train_placeholder_3': ('列車3 空欄表示', 194, 230, 14, '#5A768A', 'num', 80),
    'train_empty': ('列車なしの案内', 194, 107, 14, '#FAC563', 'ja', 268),
    'footer_weather': ('下段 天気状態', 13, 296, 10, '#21DFF0', 'ja', 135),
    'footer_train': ('下段 列車状態', 168, 296, 10, '#9CB9CA', 'ja', 295),
}

def props(conf, key):
    label, x, y, size, color, kind, width = ELEMENTS[key]
    override = conf.get('text_styles') or {}
    info = override.get(key, {}) if isinstance(override,dict) else {}
    if not isinstance(info,dict): info={}
    def bounded_int(name, fallback, lo, hi):
        try: return max(lo,min(hi,int(info.get(name,fallback))))
        except (ValueError,TypeError): return fallback
    c=str(info.get('color',color)).strip().upper()
    if not re.fullmatch('#[0-9A-F]{6}',c): c=color
    return {
        'x': bounded_int('x', x, 0, 479),
        'y': bounded_int('y', y, 0, 319),
        'size': bounded_int('size', size, 8, 52),
        'color': c,
        'kind': kind,
        'max_width': max(width, int(width*bounded_int('size',size,8,52)/size)),
    }

def validate_styles(conf):
    styles=conf.get('text_styles',{})
    if not isinstance(styles,dict):raise ValueError('text_styles must be an object')
    for key, value in styles.items():
        if key not in ELEMENTS:continue
        if not isinstance(value,dict):raise ValueError(f'{key} must be an object')
        for f,hi in (('x',479),('y',319),('size',52)):
            if f in value and not (0<=int(value[f])<=hi):raise ValueError(f'{key} {f} is outside allowed range')
        if 'size' in value and int(value['size'])<8:raise ValueError(f'{key} font size too small')
        if 'color' in value and not re.fullmatch('#[0-9a-fA-F]{6}',str(value['color'])):
            raise ValueError(f'{key} color must be #RRGGBB')
