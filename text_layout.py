"""Human-editable text labels for the 480x320 unrotated layout."""
from __future__ import annotations
import re

# (Japanese name, x, y, font px, color hex, font kind, default width)
ELEMENTS = {
    'clock_datetime': ('日付・時刻', 13, 9, 23, '#F3F9FD', 'ja', 397),
    'version': ('右下バージョン', 431, 29, 9, '#9CB9CA', 'num', 40),
    'weather_city': ('天気 地域名', 13, 60, 17, '#F3F9FD', 'ja', 106),
    'weather_description': ('天気 状態', 65, 103, 12, '#F3F9FD', 'ja', 54),
    'weather_temperature': ('天気 現在気温 数値', 64, 122, 20, '#F3F9FD', 'num', 40),
    'weather_temperature_unit': ('天気 現在気温 単位', 103, 128, 13, '#F3F9FD', 'num', 18),
    'weather_high_label': ('最高 ラベル', 13, 159, 11, '#FAC563', 'ja', 49),
    'weather_high': ('最高気温 数値', 74, 159, 12, '#FAC563', 'num', 30),
    'weather_high_unit': ('最高気温 単位', 106, 161, 10, '#FAC563', 'num', 19),
    'weather_low_label': ('最低 ラベル', 13, 180, 11, '#21DFF0', 'ja', 49),
    'weather_low': ('最低気温 数値', 74, 180, 12, '#21DFF0', 'num', 30),
    'weather_low_unit': ('最低気温 単位', 106, 182, 10, '#21DFF0', 'num', 19),
    'weather_rain_label': ('降水 ラベル', 13, 207, 11, '#9CB9CA', 'ja', 49),
    'weather_rain': ('降水確率 数値', 74, 207, 11, '#F3F9FD', 'num', 30),
    'weather_rain_unit': ('降水確率 単位', 106, 209, 10, '#F3F9FD', 'num', 18),
    'weather_humidity_label': ('湿度 ラベル', 13, 231, 11, '#9CB9CA', 'ja', 49),
    'weather_humidity': ('湿度 数値', 74, 231, 11, '#F3F9FD', 'num', 30),
    'weather_humidity_unit': ('湿度 単位', 106, 233, 10, '#F3F9FD', 'num', 18),
    'weather_wind_label': ('風 ラベル', 13, 255, 11, '#9CB9CA', 'ja', 49),
    'weather_wind': ('風速 数値', 71, 255, 10, '#F3F9FD', 'num', 33),
    'weather_wind_unit': ('風速 単位', 106, 256, 9, '#F3F9FD', 'num', 20),
    'train_index_1': ('列車1 番号', 145, 81, 19, '#21DFF0', 'num', 25),
    'train_station_depart_1': ('列車1 加賀笠間 発', 176, 66, 10, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_1': ('列車1 金沢 着', 246, 66, 10, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_1': ('列車1 金沢 発', 316, 66, 10, '#9CB9CA', 'ja', 63),
    'train_station_arrive_1': ('列車1 津幡 着', 394, 66, 10, '#9CB9CA', 'ja', 65),
    'train_time_1': ('列車1 加賀笠間 発時刻', 173, 83, 17, '#F3F9FD', 'num', 64),
    'train_kan_arr_1': ('列車1 金沢 到着時刻', 243, 83, 17, '#F3F9FD', 'num', 64),
    'train_kan_dep_1': ('列車1 金沢 発車時刻', 313, 83, 17, '#F3F9FD', 'num', 64),
    'train_arrive_1': ('列車1 津幡 到着時刻', 390, 83, 17, '#F3F9FD', 'num', 73),
    'train_detail_1': ('列車1 乗換時間・番線', 175, 109, 11, '#9CB9CA', 'ja', 284),
    'train_legacy_time_1': ('列車1 金沢→津幡（旧表示）', 173, 83, 18, '#F3F9FD', 'num', 280),
    'train_index_2': ('列車2 番号', 145, 155, 19, '#21DFF0', 'num', 25),
    'train_station_depart_2': ('列車2 加賀笠間 発', 176, 140, 10, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_2': ('列車2 金沢 着', 246, 140, 10, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_2': ('列車2 金沢 発', 316, 140, 10, '#9CB9CA', 'ja', 63),
    'train_station_arrive_2': ('列車2 津幡 着', 394, 140, 10, '#9CB9CA', 'ja', 65),
    'train_time_2': ('列車2 加賀笠間 発時刻', 173, 157, 17, '#F3F9FD', 'num', 64),
    'train_kan_arr_2': ('列車2 金沢 到着時刻', 243, 157, 17, '#F3F9FD', 'num', 64),
    'train_kan_dep_2': ('列車2 金沢 発車時刻', 313, 157, 17, '#F3F9FD', 'num', 64),
    'train_arrive_2': ('列車2 津幡 到着時刻', 390, 157, 17, '#F3F9FD', 'num', 73),
    'train_detail_2': ('列車2 乗換時間・番線', 175, 183, 11, '#9CB9CA', 'ja', 284),
    'train_legacy_time_2': ('列車2 金沢→津幡（旧表示）', 173, 157, 18, '#F3F9FD', 'num', 280),
    'train_index_3': ('列車3 番号', 145, 229, 19, '#21DFF0', 'num', 25),
    'train_station_depart_3': ('列車3 加賀笠間 発', 176, 214, 10, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_3': ('列車3 金沢 着', 246, 214, 10, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_3': ('列車3 金沢 発', 316, 214, 10, '#9CB9CA', 'ja', 63),
    'train_station_arrive_3': ('列車3 津幡 着', 394, 214, 10, '#9CB9CA', 'ja', 65),
    'train_time_3': ('列車3 加賀笠間 発時刻', 173, 231, 17, '#F3F9FD', 'num', 64),
    'train_kan_arr_3': ('列車3 金沢 到着時刻', 243, 231, 17, '#F3F9FD', 'num', 64),
    'train_kan_dep_3': ('列車3 金沢 発車時刻', 313, 231, 17, '#F3F9FD', 'num', 64),
    'train_arrive_3': ('列車3 津幡 到着時刻', 390, 231, 17, '#F3F9FD', 'num', 73),
    'train_detail_3': ('列車3 乗換時間・番線', 175, 257, 11, '#9CB9CA', 'ja', 284),
    'train_legacy_time_3': ('列車3 金沢→津幡（旧表示）', 173, 231, 18, '#F3F9FD', 'num', 280),
    'train_placeholder_2': ('列車2 空欄表示', 166, 170, 14, '#5A768A', 'num', 170),
    'train_placeholder_3': ('列車3 空欄表示', 166, 243, 14, '#5A768A', 'num', 170),
    'train_empty': ('列車なしの案内', 150, 90, 14, '#FAC563', 'ja', 310),
    'footer_weather': ('天気枠内 更新時刻', 13, 290, 10, '#21DFF0', 'ja', 107),
    'train_source_note': ('乗換枠内 時刻表注記', 146, 290, 9, '#9CB9CA', 'ja', 195),
    'footer_train': ('乗換枠内 更新時刻', 376, 290, 10, '#21DFF0', 'ja', 91),
}

# All five numeric weather rows share the same right-hand column boundary.
# Other labels, including measurement units, continue to use left alignment.
WEATHER_RIGHT_ALIGNED_VALUES = frozenset((
    'weather_high', 'weather_low', 'weather_rain',
    'weather_humidity', 'weather_wind',
))

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
