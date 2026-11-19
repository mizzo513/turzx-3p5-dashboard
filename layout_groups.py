# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure grouped text layout editing for TURZX 480x320.

Group edits move each member by the same delta and change its font by the
same size delta, preserving its relative placement and any custom colors.
Nothing in this module saves settings or communicates with the USB display.
"""
from __future__ import annotations
import copy

from panel_layout import settings as panel_props
from text_layout import ELEMENTS, props as text_props


def _keys(prefixes, count=3):
    return tuple(f'{prefix}_{i}' for i in range(1,count+1) for prefix in prefixes)


STATION_FIELDS=('train_station_depart','train_station_kan_arr',
                'train_station_kan_dep','train_station_arrive')
TIME_FIELDS=('train_time','train_kan_arr','train_kan_dep','train_arrive')

# Japanese labels are displayed directly in the editor's group dropdown.
# All groups are intentionally contained in one logical panel.
GROUPS={
    '天気｜地域名・天候':
        ('weather',('weather_city','weather_description')),
    # Separate one-member groups: the editor defaults to independent size and
    # position for the temperature number and degree symbol.
    '天気｜現在気温 数値':
        ('weather',('weather_temperature',)),
    '天気｜現在気温 単位':
        ('weather',('weather_temperature_unit',)),
    # Optional paired adjustment remains available in the group dialog.
    '天気｜現在気温（数値と単位 一括）':
        ('weather',('weather_temperature','weather_temperature_unit')),
    '天気｜項目名（5種）':
        ('weather',('weather_high_label','weather_low_label',
                    'weather_rain_label','weather_humidity_label','weather_wind_label')),
    '天気｜数値（5種）':
        ('weather',('weather_high','weather_low','weather_rain',
                    'weather_humidity','weather_wind')),
    '天気｜単位（5種）':
        ('weather',('weather_high_unit','weather_low_unit','weather_rain_unit',
                    'weather_humidity_unit','weather_wind_unit')),
    '列車｜駅名（3本×4箇所）':('train',_keys(STATION_FIELDS)),
    '列車｜時刻（3本×4箇所）':('train',_keys(TIME_FIELDS)),
    '列車｜番号（3本）':('train',_keys(('train_index',))),
    '列車｜乗換案内（3本）':('train',_keys(('train_detail',))),
    '列車｜旧モード時刻（3本）':('train',_keys(('train_legacy_time',))),
}

for _number in range(1,4):
    GROUPS[f'列車{_number}｜駅名（4箇所）']=(
        f'train_{_number}',tuple(f'{name}_{_number}' for name in STATION_FIELDS))
    GROUPS[f'列車{_number}｜時刻（4箇所）']=(
        f'train_{_number}',tuple(f'{name}_{_number}' for name in TIME_FIELDS))

# Catch accidental drift if fields are renamed in the main renderer.
for _label,(_panel,_keys_list) in GROUPS.items():
    for _key in _keys_list:
        if _key not in ELEMENTS:
            raise RuntimeError(f'Invalid layout group {_label}: {_key}')


def matching_group(key):
    """Prefer the narrowest, most local group for a selected individual text."""
    groups=[label for label,(_,keys) in GROUPS.items() if key in keys]
    return min(groups,key=lambda label:len(GROUPS[label][1])) if groups else next(iter(GROUPS))


def adjust_group(text_styles, panel_styles, group, *, dx=0, dy=0, dsize=0):
    """Return staged text styles after an all-or-nothing group adjustment.

    Raises ValueError if any anchor would leave the corresponding panel or if
    font sizes leave [8..52]. No member is silently clamped independently.
    """
    if group not in GROUPS:
        raise ValueError('文字グループが見つかりません')
    try:
        dx,dy,dsize=(int(dx),int(dy),int(dsize))
    except (TypeError,ValueError) as exc:
        raise ValueError('移動量・サイズ変更量は整数で指定してください') from exc

    panel, keys=GROUPS[group]
    panel_setting=panel_props({'panel_styles':panel_styles},panel)
    min_x=panel_setting['x']+2
    max_x=panel_setting['x']+panel_setting['w']-3
    min_y=panel_setting['y']+2
    max_y=panel_setting['y']+panel_setting['h']-3

    staged=copy.deepcopy(text_styles or {})
    for key in keys:
        original=text_props({'text_styles':staged},key)
        new_x=original['x']+dx
        new_y=original['y']+dy
        new_size=original['size']+dsize
        if not (min_x<=new_x<=max_x and min_y<=new_y<=max_y):
            raise ValueError(f'{ELEMENTS[key][0]} が対応する枠の範囲外になります')
        if not 8<=new_size<=52:
            raise ValueError(f'{ELEMENTS[key][0]} の文字サイズは8〜52pxの範囲です')
        old=staged.get(key,{})
        staged[key]={**old,'x':new_x,'y':new_y,'size':new_size,
                     'color':original['color']}
    return staged
