"""Human-editable text labels for the 480x320 unrotated layout."""
from __future__ import annotations
import re

# (Japanese name, x, y, font px, color hex, font kind, default width)
ELEMENTS = {
    'clock_datetime': ('日付・時刻', 13, 9, 23, '#F3F9FD', 'ja', 397),
    'version': ('右上 バージョン', 425, 31, 9, '#9CB9CA', 'num', 42),
    'weather_city': ('天気 地域名', 13, 60, 18, '#F3F9FD', 'ja', 106),
    'weather_description': ('天気 状態', 65, 103, 13, '#F3F9FD', 'ja', 54),
    'weather_temperature': ('天気 現在気温 数値', 64, 122, 22, '#F3F9FD', 'num', 40),
    'weather_temperature_unit': ('天気 現在気温 単位', 103, 127, 14, '#F3F9FD', 'ja', 18),
    'weather_high_label': ('最高 ラベル', 13, 165, 12, '#FAC563', 'ja', 49),
    'weather_high': ('最高気温 数値', 74, 165, 13, '#FAC563', 'num', 30),
    'weather_high_unit': ('最高気温 単位', 106, 167, 11, '#FAC563', 'ja', 19),
    'weather_low_label': ('最低 ラベル', 13, 191, 12, '#21DFF0', 'ja', 49),
    'weather_low': ('最低気温 数値', 74, 191, 13, '#21DFF0', 'num', 30),
    'weather_low_unit': ('最低気温 単位', 106, 193, 11, '#21DFF0', 'ja', 19),
    'weather_rain_label': ('降水 ラベル', 13, 219, 12, '#9CB9CA', 'ja', 49),
    'weather_rain': ('降水確率 数値', 74, 219, 12, '#F3F9FD', 'num', 30),
    'weather_rain_unit': ('降水確率 単位', 106, 221, 11, '#F3F9FD', 'num', 18),
    'weather_humidity_label': ('湿度 ラベル', 13, 249, 12, '#9CB9CA', 'ja', 49),
    'weather_humidity': ('湿度 数値', 74, 249, 12, '#F3F9FD', 'num', 30),
    'weather_humidity_unit': ('湿度 単位', 106, 251, 11, '#F3F9FD', 'num', 18),
    'weather_wind_label': ('風 ラベル', 13, 280, 12, '#9CB9CA', 'ja', 49),
    'weather_wind': ('風速 数値', 74, 280, 12, '#F3F9FD', 'num', 30),
    'weather_wind_unit': ('風速 単位', 106, 282, 10, '#F3F9FD', 'num', 20),
    'train_notice': ('運行情報テロップ', 146, 60, 11, '#FAC563', 'ja', 315),
    'train_index_1': ('列車1 番号', 145, 104, 20, '#21DFF0', 'num', 25),
    'train_service_first_1': ('列車1 前半 列車番号・運行状況', 172, 85, 12, '#78B8EF', 'ja', 140),
    'train_service_second_1': ('列車1 後半 列車番号・運行状況', 322, 85, 12, '#78B8EF', 'ja', 141),
    'train_station_depart_1': ('列車1 加賀笠間 発', 176, 88, 11, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_1': ('列車1 金沢 着', 246, 88, 11, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_1': ('列車1 金沢 発', 316, 88, 11, '#9CB9CA', 'ja', 63),
    'train_station_arrive_1': ('列車1 津幡 着', 394, 88, 11, '#9CB9CA', 'ja', 65),
    'train_time_1': ('列車1 加賀笠間 発時刻', 173, 107, 18, '#F3F9FD', 'num', 64),
    'train_kan_arr_1': ('列車1 金沢 到着時刻', 243, 107, 18, '#F3F9FD', 'num', 64),
    'train_kan_dep_1': ('列車1 金沢 発車時刻', 313, 107, 18, '#F3F9FD', 'num', 64),
    'train_arrive_1': ('列車1 津幡 到着時刻', 390, 107, 18, '#F3F9FD', 'num', 73),
    'train_detail_1': ('列車1 乗換時間・情報', 175, 135, 12, '#9CB9CA', 'ja', 164),
    'train_transfer_platform_1': ('列車1 乗換ホーム（固定位置）', 345, 135, 12, '#F3F9FD', 'ja', 110),
    'train_legacy_time_1': ('列車1 金沢→津幡（旧表示）', 173, 107, 19, '#F3F9FD', 'num', 280),
    'train_index_2': ('列車2 番号', 145, 180, 20, '#21DFF0', 'num', 25),
    'train_service_first_2': ('列車2 前半 列車番号・運行状況', 172, 161, 12, '#78B8EF', 'ja', 140),
    'train_service_second_2': ('列車2 後半 列車番号・運行状況', 322, 161, 12, '#78B8EF', 'ja', 141),
    'train_station_depart_2': ('列車2 加賀笠間 発', 176, 164, 11, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_2': ('列車2 金沢 着', 246, 164, 11, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_2': ('列車2 金沢 発', 316, 164, 11, '#9CB9CA', 'ja', 63),
    'train_station_arrive_2': ('列車2 津幡 着', 394, 164, 11, '#9CB9CA', 'ja', 65),
    'train_time_2': ('列車2 加賀笠間 発時刻', 173, 183, 18, '#F3F9FD', 'num', 64),
    'train_kan_arr_2': ('列車2 金沢 到着時刻', 243, 183, 18, '#F3F9FD', 'num', 64),
    'train_kan_dep_2': ('列車2 金沢 発車時刻', 313, 183, 18, '#F3F9FD', 'num', 64),
    'train_arrive_2': ('列車2 津幡 到着時刻', 390, 183, 18, '#F3F9FD', 'num', 73),
    'train_detail_2': ('列車2 乗換時間・情報', 175, 211, 12, '#9CB9CA', 'ja', 164),
    'train_transfer_platform_2': ('列車2 乗換ホーム（固定位置）', 345, 211, 12, '#F3F9FD', 'ja', 110),
    'train_legacy_time_2': ('列車2 金沢→津幡（旧表示）', 173, 183, 19, '#F3F9FD', 'num', 280),
    'train_index_3': ('列車3 番号', 145, 256, 20, '#21DFF0', 'num', 25),
    'train_service_first_3': ('列車3 前半 列車番号・運行状況', 172, 237, 12, '#78B8EF', 'ja', 140),
    'train_service_second_3': ('列車3 後半 列車番号・運行状況', 322, 237, 12, '#78B8EF', 'ja', 141),
    'train_station_depart_3': ('列車3 加賀笠間 発', 176, 240, 11, '#9CB9CA', 'ja', 62),
    'train_station_kan_arr_3': ('列車3 金沢 着', 246, 240, 11, '#9CB9CA', 'ja', 63),
    'train_station_kan_dep_3': ('列車3 金沢 発', 316, 240, 11, '#9CB9CA', 'ja', 63),
    'train_station_arrive_3': ('列車3 津幡 着', 394, 240, 11, '#9CB9CA', 'ja', 65),
    'train_time_3': ('列車3 加賀笠間 発時刻', 173, 259, 18, '#F3F9FD', 'num', 64),
    'train_kan_arr_3': ('列車3 金沢 到着時刻', 243, 259, 18, '#F3F9FD', 'num', 64),
    'train_kan_dep_3': ('列車3 金沢 発車時刻', 313, 259, 18, '#F3F9FD', 'num', 64),
    'train_arrive_3': ('列車3 津幡 到着時刻', 390, 259, 18, '#F3F9FD', 'num', 73),
    'train_detail_3': ('列車3 乗換時間・情報', 175, 287, 12, '#9CB9CA', 'ja', 164),
    'train_transfer_platform_3': ('列車3 乗換ホーム（固定位置）', 345, 287, 12, '#F3F9FD', 'ja', 110),
    'train_legacy_time_3': ('列車3 金沢→津幡（旧表示）', 173, 259, 19, '#F3F9FD', 'num', 280),
    'train_placeholder_2': ('列車2 空欄表示', 166, 196, 14, '#5A768A', 'num', 170),
    'train_placeholder_3': ('列車3 空欄表示', 166, 271, 14, '#5A768A', 'num', 170),
    'train_empty': ('列車なしの案内', 150, 95, 14, '#FAC563', 'ja', 310),
    'footer_weather': ('右上 天気更新時刻', 355, 7, 10, '#21DFF0', 'ja', 112),
    'footer_train': ('右上 乗換更新時刻', 355, 19, 10, '#85E5A2', 'ja', 112),
}

# All five numeric weather rows share the same right-hand column boundary.
# Other labels, including measurement units, continue to use left alignment.
HEADER_RIGHT_ALIGNED_VALUES = frozenset(('footer_weather', 'footer_train', 'version'))

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
