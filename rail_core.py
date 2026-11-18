# -*- coding: utf-8 -*-
"""IRいしかわ鉄道・帰宅ウィジェットのPython版経路計算。

時刻表はユーザー提供の IR Home Widget v2.6 同梱 schedule.json を使用。
路線を推測で追加しない。すべて日本標準時・静的ダイヤ。
"""
from __future__ import annotations
import calendar
import datetime as dt
import json
import math
import os
from pathlib import Path
from dataclasses import dataclass

JST = dt.timezone(dt.timedelta(hours=9), name="JST")


def now_jst() -> dt.datetime:
    return dt.datetime.now(tz=JST)


def appdata_dir() -> Path:
    return Path(os.environ.get('APPDATA') or Path.home())


def combined_dir() -> Path:
    return appdata_dir() / 'CombinedDeskWidget'


def _safe_read(path):
    try:
        with Path(path).open('r', encoding='utf-8-sig') as f:
            val=json.load(f)
            return val if isinstance(val,dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def load_schedule(path):
    val = _safe_read(path)
    if not (isinstance(val.get('first'),list) and isinstance(val.get('second'),list)):
        raise ValueError('schedule.json に first/second データがありません。')
    for leg in ('first','second'):
        for entry in val[leg]:
            if not isinstance(entry, list) or len(entry) < 5:
                raise ValueError(f'schedule.json の {leg} に不正な行があります。')
            parse_time(entry[0]); parse_time(entry[1])
    return val


def _parse_int(value, fallback, lower, upper):
    try: return min(upper,max(lower,int(value)))
    except (ValueError,TypeError): return fallback


def default_rail_settings():
    return {'walk':15, 'candidates':3, 'manual_platforms':{}}


def _normalize_manual(src):
    # Original Go settings may use multiple map key conventions. Preserve all keys.
    return src if isinstance(src,dict) else {}


def load_rail_settings(base=None):
    """Combined settings take precedence; read legacy IRHomeWidget config on first run.

    Never overwrite existing old app configuration. New settings stored separately.
    """
    base = Path(base) if base else combined_dir()
    saved = _safe_read(base / 'rail_settings.json')
    if not saved:
        saved = _safe_read(appdata_dir() / 'IRHomeWidget' / 'config.json')
    defaults = default_rail_settings()
    defaults['walk'] = _parse_int(saved.get('walk',15),15,0,90)
    defaults['candidates'] = _parse_int(saved.get('candidates',3),3,1,10)
    defaults['manual_platforms'] = _normalize_manual(saved.get('manual_platforms'))
    return defaults


def save_rail_settings(settings,base=None):
    folder = Path(base) if base else combined_dir()
    folder.mkdir(parents=True,exist_ok=True)
    import tempfile
    fd, temp_path=tempfile.mkstemp(dir=str(folder), prefix='.rail_',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(settings,f,ensure_ascii=False,indent=2)
        os.replace(temp_path, folder / 'rail_settings.json')
    finally:
        if os.path.exists(temp_path): os.unlink(temp_path)


def parse_time(value: str) -> tuple[int,int]:
    h, m = str(value).strip().split(':')
    h, m = int(h), int(m)
    if not 0 <= h <= 23 or not 0 <= m <= 59:
        raise ValueError(f'無効な時刻: {value}')
    return h,m


def date_time(day:dt.date,time_text:str):
    h,m=parse_time(time_text)
    return dt.datetime(day.year,day.month,day.day,h,m,tzinfo=JST)


def _nth_weekday(year,month,weekday,n):
    first=dt.date(year,month,1)
    offset=(weekday-first.weekday())%7
    return first+dt.timedelta(days=offset+7*(n-1))


def _vernal_day(year):
    return int(20.8431+0.242194*(year-1980)-int((year-1980)/4))


def _autumn_day(year):
    return int(23.2488+0.242194*(year-1980)-int((year-1980)/4))


def jp_holidays(year):
    """近年の祝日規則。国の特別措置や臨時休日は網羅しない。"""
    dates={
        dt.date(year,1,1),
        _nth_weekday(year,1,0,2),
        dt.date(year,2,11), dt.date(year,2,23),
        dt.date(year,3,_vernal_day(year)),
        dt.date(year,4,29), dt.date(year,5,3), dt.date(year,5,4),dt.date(year,5,5),
        _nth_weekday(year,7,0,3), dt.date(year,8,11),
        _nth_weekday(year,9,0,3), dt.date(year,9,_autumn_day(year)),
        _nth_weekday(year,10,0,2),dt.date(year,11,3),dt.date(year,11,23),
    }
    # Sunday substitute holiday: first next non-holiday. Applies from 1973 onward.
    for d in sorted(list(dates)):
        if d.weekday()==6:
            sub=d+dt.timedelta(days=1)
            while sub in dates: sub+=dt.timedelta(days=1)
            dates.add(sub)
    # Citizen's holiday is sandwiched by two national holidays.
    day=dt.date(year,1,2)
    while day.year==year:
        if day.weekday()!=6 and day not in dates and day-dt.timedelta(days=1) in dates and day+dt.timedelta(days=1) in dates:
            dates.add(day)
        day+=dt.timedelta(days=1)
    return dates


def is_holiday(day):
    return day.weekday()>=5 or day in jp_holidays(day.year)


def active_rule(rule,day):
    r=str(rule).lower()
    if r in ('all','every','daily',''):return True
    if r in ('weekday','workday'):return not is_holiday(day)
    if r in ('holiday','weekend'):return is_holiday(day)
    # Unknown calendar condition is not silently turned into daily service.
    return False


def get_platform(manual,leg,entry,side):
    """Manual platform override with stable keys; fall back to source timetable.

    New key: `first|345M|18:24|arr` / `second|467M|18:45|dep`.
    """
    original = str(entry[4]).strip()
    key = f'{leg}|{entry[2]}|{entry[0]}|{side}'
    if isinstance(manual,dict):
        value=manual.get(key)
        # A generic Go format may have stored a single train-departure key with
        # fields 'arr'/'dep' or Japanese names. Read these without modifying them.
        if value is None:
            for candidate in (f'{entry[2]}|{entry[0]}',f'{entry[2]}@{entry[0]}',
                              f'{entry[2]}_{entry[0]}',f'{entry[2]}:{entry[0]}'):
                row=manual.get(candidate)
                if isinstance(row,dict):
                    value=row.get(side,row.get('arrival' if side=='arr' else 'departure'))
                    if value is not None: break
        if isinstance(value,dict): value=value.get(side)
        if value is not None:
            candidate=str(value).strip()
            if candidate in ('1','2','3','4','5','6','7'): return candidate
            if candidate=='': return ''
    return original if original in ('1','2','3','4','5','6','7') else ''


@dataclass(frozen=True)
class Journey:
    dep: dt.datetime       # 加賀笠間出発
    kan_arr: dt.datetime   # 金沢着
    kan_dep: dt.datetime   # 金沢発
    arr: dt.datetime       # 津幡着
    first_train: str
    second_train: str
    arr_platform: str
    dep_platform: str
    direct: bool

    @property
    def transfer_minutes(self): return int((self.kan_dep-self.kan_arr).total_seconds()//60)
    @property
    def travel_minutes(self): return int((self.arr-self.dep).total_seconds()//60)
    @property
    def platform_label(self):
        if self.direct:return '直通'
        if self.arr_platform or self.dep_platform:
            return f'{self.arr_platform or "?"}→{self.dep_platform or "?"}'
        return '--'
    @property
    def transfer_label(self):
        return ('停車' if self.direct else '乗換') + str(self.transfer_minutes) + '分'


def _make_leg(day, row):
    departure=date_time(day,row[0])
    arrival=date_time(day,row[1])
    if arrival<departure: arrival+=dt.timedelta(days=1)
    return departure,arrival


def is_direct(first,second,schedule):
    if first[2]==second[2]:return True
    for pair in schedule.get('direct_pairs',[]):
        if (isinstance(pair,list) and len(pair)>=4 and
            str(pair[0])==str(first[2]) and str(pair[1])==str(second[2]) and
            str(pair[2])==str(first[0]) and str(pair[3])==str(second[0])):
            return True
    return False


def journeys_for_date(schedule,day,manual_platforms=None,max_wait_minutes=120):
    """One best arrival connection per origin-departure service for the chosen day."""
    manual_platforms=manual_platforms if isinstance(manual_platforms,dict) else {}
    candidates=[]
    second=[]
    for second_day in (day,day+dt.timedelta(days=1)):
        for row in schedule['second']:
            if not active_rule(row[3],second_day): continue
            dep,arr=_make_leg(second_day,row)
            second.append((row,dep,arr))
    for first_row in schedule['first']:
        if not active_rule(first_row[3],day):continue
        dep,kan_arr=_make_leg(day,first_row)
        matching=[]
        for second_row,kan_dep,arr in second:
            wait=(kan_dep-kan_arr).total_seconds()/60
            if not 0<=wait<=max_wait_minutes:continue
            direct=is_direct(first_row,second_row,schedule)
            matching.append((arr,0 if direct else 1,kan_dep,second_row,direct))
        if not matching:continue
        arr,direct_rank,kan_dep,second_row,direct=min(matching,key=lambda x:(x[0],x[1],x[2]))
        candidates.append(Journey(
            dep=dep,kan_arr=kan_arr,kan_dep=kan_dep,arr=arr,
            first_train=str(first_row[2]), second_train=str(second_row[2]),
            arr_platform=get_platform(manual_platforms,'first',first_row,'arr'),
            dep_platform=get_platform(manual_platforms,'second',second_row,'dep'),
            direct=direct,
        ))
    return sorted(candidates, key=lambda x:(x.dep,x.arr,x.first_train))


def next_journey(schedule,at=None,walk=15,manual_platforms=None):
    at=at or now_jst()
    if at.tzinfo is None:at=at.replace(tzinfo=JST)
    else:at=at.astimezone(JST)
    earliest=at+dt.timedelta(minutes=walk)
    for offset in range(3):
        day=at.date()+dt.timedelta(days=offset)
        for j in journeys_for_date(schedule,day,manual_platforms):
            if j.dep>=earliest: return j
    return None


def minutes_until(journey,at=None):
    at=at or now_jst()
    if at.tzinfo is None:at=at.replace(tzinfo=JST)
    return max(0,math.ceil((journey.dep-at).total_seconds()/60))


def hhmm(moment):
    return moment.strftime('%H:%M')


def date_caption(day):
    return day.strftime('%m/%d')+'（'+'月火水木金土日'[day.weekday()]+'）'


def platform_edit_key(leg,entry,side):
    return f'{leg}|{entry[2]}|{entry[0]}|{side}'


def override_for_journey(journey,manual):
    # Store stable keys; first/second train and departure-time uniquely identify
    # the source row within each of the two schedule tables.
    return (f'first|{journey.first_train}|{hhmm(journey.dep)}|arr',
            f'second|{journey.second_train}|{hhmm(journey.kan_dep)}|dep')
