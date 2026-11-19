# SPDX-License-Identifier: GPL-3.0-or-later
"""TURZX/Turing 3.5 Rev A 480x320: realtime clock + weather + train dashboard.

Image transfer based on the user-tested TURZX_3p5_Clock_Fix_V2.
Uses the working landscape(2) command, software rotation 180 degrees,
and a full-width 58px clock strip. This is NOT a firmware updater.
"""
from __future__ import annotations

import argparse
import hashlib
import socket
import csv
import copy
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, time as dt_time, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont
from runtime_ipc import StatusServer, current_state
from text_layout import props as style_props, validate_styles, ELEMENTS, WEATHER_RIGHT_ALIGNED_VALUES
from panel_layout import draw_panel, validate_panels, settings as panel_settings
from version_info import APP_VERSION
from internet_clock import InternetClock, query_ntp, NTP_SERVER
from weatherapi_provider import fetch_weatherapi, WeatherAPIError
from rail_official_status import RailNotice, fetch_official_rail_notice
from contextlib import nullcontext

BUNDLE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ROOT = (Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'TURZXDashboard'
        if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent)
ROOT.mkdir(parents=True, exist_ok=True)
SETTINGS = ROOT / 'settings.json'
CSV_PATH = ROOT / 'train_schedule.csv'
IR_SCHEDULE_PATH = ROOT / 'schedule.json' if (ROOT / 'schedule.json').is_file() else BUNDLE_ROOT / 'schedule.json'
# Source-mode patches may omit files or preserve older data. Never hide bundled fallback.

JSON_PATH = ROOT / 'train_results.json'
PREVIEW = ROOT / 'preview_480x320.png'
STATUS_PATH = ROOT / 'runtime_status.json'
STOP_PATH = ROOT / 'STOP_REQUEST.flag'
LOCK_PATH = ROOT / '.dashboard.lock'

W, H = 480, 320
CLOCK_STRIP = 58
CLOCK_BOX = (8, 6, 171, 54) # logical (unrotated) clock area
SECONDS_BOX = (116, 16, 166, 47) # logical seconds digits only, colon remains static
VID, PID = 0x1A86, 0x5722
SERIAL_IDS = {'USB35INCHIPSV2', 'USB35INCHIPS'}
TZ = timezone(timedelta(hours=9), name="JST")
OFFICIAL_TIMETABLE = 'https://www.ishikawa-railway.jp/timetable/index.html'

CITIES = {
    '白山市': (36.5144, 136.5656),
    '金沢市': (36.5613, 136.6562),
    '津幡町': (36.6693, 136.7288),
    '小松市': (36.4084, 136.4455),
    '加賀市': (36.3024, 136.3146),
    '七尾市': (37.0432, 136.9678),
}
DEFAULTS = {
    'port': 'AUTO',
    'weather_city': '白山市',
    'weather_latitude': 36.5144,
    'weather_longitude': 136.5656,
    'weather_update_minutes': 10,
    'auto_start_display': True, # launch USB engine automatically when GUI opens
    'weather_provider': 'weatherapi', # weatherapi or openmeteo
    'weatherapi_key': '', # local settings only, never bundled into public releases
    'train_source': 'ir_schedule',  # bundled IR timetable, csv, json, or google_transit
    'ir_route': 'via_kanazawa',  # via_kanazawa or kanazawa_tsubata; old configs migrate automatically
    'train_update_seconds': 30,
    'rail_status_enabled': True,
    'rail_status_update_minutes': 5, # request public IR/JR sources at most every 5 min
    'train_count': 3,
    'train_from': '金沢',
    'train_to': '津幡',
    'google_maps_api_key': '',
    'google_refresh_minutes': 15,
    'show_seconds': True,
    'clock_update_mode': 'compact', # compact or safe_strip
    'live_settings': True,
    'clock_12h': False,
    'ntp_server': NTP_SERVER,
    'ntp_sync_minutes': 30,
    'auto_update_check': True,
    'brightness_note': '',
    'layout_revision': 396, # rail-status strip + compact rows (v3.9.6)
    'text_styles': {},  # optional per-label x/y/size/color overrides
    'panel_styles': {},  # optional per-panel x/y/w/h/radius/fill/outline
}

BG = (5, 15, 27)
PANEL = (14, 34, 53)
PANEL2 = (19, 46, 67)
BORDER = (34, 101, 132)
WHITE = (243, 249, 253)
MUTED = (156, 185, 202)
CYAN = (33, 223, 240)
BLUE = (78, 173, 245)
GREEN = (85, 229, 162)
YELLOW = (250, 197, 99)
RED = (252, 116, 113)

logger = logging.getLogger('turzx')


def load_settings():
    conf = dict(DEFAULTS)
    if SETTINGS.exists():
        with SETTINGS.open(encoding='utf-8-sig') as fh:
            saved = json.load(fh)
        if not isinstance(saved, dict):
            raise ValueError('settings.json must contain an object')
        conf.update(saved)
        # A narrow weather panel and 4-column train clocks cannot safely reuse
        # old saved coordinates or font sizes. Preserve original styles for
        # rollback while carrying forward user-selected colors.
        if int(saved.get('layout_revision',0) or 0)<390:
            old_text=saved.get('text_styles') or {}
            old_panels=saved.get('panel_styles') or {}
            if (old_text or old_panels) and 'layout_backup_v383' not in saved:
                conf['layout_backup_v383']={
                    'text_styles':copy.deepcopy(old_text),
                    'panel_styles':copy.deepcopy(old_panels),
                }
            valid_text=set(__import__('text_layout').ELEMENTS)
            valid_panels=set(__import__('panel_layout').PANELS)
            conf['text_styles']={
                key:{'color':value['color']}
                for key,value in old_text.items()
                if key in valid_text and isinstance(value,dict) and 'color' in value
            } if isinstance(old_text,dict) else {}
            conf['panel_styles']={
                key:{name:value[name] for name in ('fill','outline') if name in value}
                for key,value in old_panels.items()
                if key in valid_panels and isinstance(value,dict)
                and any(name in value for name in ('fill','outline'))
            } if isinstance(old_panels,dict) else {}
        # V3.9.6: make room for the single-line rail notice above train 1.
        # Preserve all manual x, size and color edits by shifting only y, and
        # retain a full backup so the previous layout can be reconstructed.
        if int(saved.get('layout_revision',0) or 0)<396:
            old_text=conf.get('text_styles') or {}
            old_panels=conf.get('panel_styles') or {}
            if (old_text or old_panels) and 'layout_backup_v395' not in saved:
                conf['layout_backup_v395']={
                    'text_styles':copy.deepcopy(old_text),
                    'panel_styles':copy.deepcopy(old_panels),
                }
            moves={1:20,2:14,3:8}
            text_styles=copy.deepcopy(old_text) if isinstance(old_text,dict) else {}
            for key,style in text_styles.items():
                if not isinstance(style,dict):
                    continue
                # Prior wind default started at x=71; normalize it with the
                # other numeric columns. Other personalized x values persist.
                if key=='weather_wind' and style.get('x')==71:
                    style['x']=74
                matched=re.search(
                    r'^train_(?:index|station_depart|station_kan_arr|station_kan_dep|'
                    r'station_arrive|time|kan_arr|kan_dep|arrive|detail|legacy_time)_([123])$',key)
                if matched and 'y' in style:
                    n=int(matched.group(1))
                    style['y']=min(319,int(style['y'])+moves[n])
                if key=='train_placeholder_2' and 'y' in style:
                    style['y']=min(319,int(style['y'])+14)
                if key=='train_placeholder_3' and 'y' in style:
                    style['y']=min(319,int(style['y'])+8)
            conf['text_styles']=text_styles
            panel_styles=copy.deepcopy(old_panels) if isinstance(old_panels,dict) else {}
            for n,shift in moves.items():
                style=panel_styles.get('train_'+str(n))
                if isinstance(style,dict):
                    if 'y' in style:style['y']=min(319,int(style['y'])+(19 if n==1 else 12 if n==2 else 5))
                    if 'h' in style and int(style['h'])==69:style['h']=64
            conf['panel_styles']=panel_styles
        conf['layout_revision']=396
    return conf


def save_settings(config):
    dst = SETTINGS.with_suffix('.json.tmp')
    with dst.open('w', encoding='utf-8') as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    dst.replace(SETTINGS)


CLOCK = InternetClock()

def jp_now():
    """Return JST from the NTP-disciplined monotonic clock, or marked PC fallback."""
    return CLOCK.now_jst()


@dataclass
class Weather:
    city: str = '白山市'
    temperature: float | None = None
    high: float | None = None
    low: float | None = None
    precip: int | None = None
    humidity: int | None = None
    wind: float | None = None
    code: int | None = None
    fetched: datetime | None = None
    error: str | None = '未取得'
    provider: str = 'openmeteo'
    condition_text: str = ''
    raw_condition_code: int | None = None
    precip_mm: float | None = None # diagnostic only; never overrides conditions
    data_time: datetime | None = None


@dataclass
class Train:
    depart: datetime
    arrive: datetime
    line: str = ''
    platform: str = ''
    note: str = ''
    origin: str = '金沢'
    destination: str = '津幡'
    transfer_arrive: datetime | None = None
    transfer_depart: datetime | None = None
    transfer_arrival_platform: str = ''
    transfer_departure_platform: str = ''
    direct: bool = False


@dataclass
class TrainState:
    trains: list[Train] = field(default_factory=list)
    status: str = '未設定'
    source: str = 'csv'
    loaded: datetime | None = None
    error: str | None = None


def weather_description(code):
    if code is None:
        return '取得中'
    if code == 0: return '快晴'
    if code in (1,2): return '晴れ/曇り'
    if code == 3: return 'くもり'
    if code in (45,48): return '霧'
    if code in (51,53,55,56,57): return '霧雨'
    if code in (61,63,65,66,67,80,81,82): return '雨'
    if code in (71,73,75,77,85,86): return '雪'
    if code in (95,96,99): return '雷雨'
    return '天気'


def fetch_weather_openmeteo(conf, opener=urlopen):
    """Original Open-Meteo adapter retained for explicit provider selection."""
    params = {
        'latitude': float(conf['weather_latitude']),
        'longitude': float(conf['weather_longitude']),
        'current': 'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m',
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        'timezone': 'Asia/Tokyo',
        'wind_speed_unit': 'ms',
        'forecast_days': 2,
    }
    endpoint = 'https://api.open-meteo.com/v1/forecast?' + urlencode(params)
    req = Request(endpoint, headers={'User-Agent': 'TURZX-dashboard-demo/3.0 (personal-use)'})
    with opener(req, timeout=12) as response:
        doc = json.load(response)
    if 'error' in doc or not isinstance(doc.get('current'),dict):
        raise ValueError(str(doc.get('reason') or 'invalid Open-Meteo API response'))
    now = jp_now()
    current = doc['current']
    daily = doc.get('daily') or {}
    date_list = daily.get('time') or []
    i = date_list.index(now.date().isoformat()) if now.date().isoformat() in date_list else 0
    def day_value(key):
        arr = daily.get(key) or []
        return arr[i] if i < len(arr) else None
    def number(x):
        try: return float(x) if x is not None else None
        except (ValueError,TypeError): return None
    def integer(x):
        try: return round(float(x)) if x is not None else None
        except (ValueError,TypeError): return None
    return Weather(
        city=str(conf['weather_city']),
        temperature=number(current.get('temperature_2m')),
        high=number(day_value('temperature_2m_max')),
        low=number(day_value('temperature_2m_min')),
        precip=integer(day_value('precipitation_probability_max')),
        humidity=integer(current.get('relative_humidity_2m')),
        wind=number(current.get('wind_speed_10m')),
        code=integer(current.get('weather_code')),
        fetched=now,
        error=None,
        provider='openmeteo',
    )


def fetch_weather(conf, opener=urlopen):
    """Fetch only from the selected provider. Never silently switch sources."""
    provider=str(conf.get('weather_provider','weatherapi')).lower().strip()
    if provider=='openmeteo':
        return fetch_weather_openmeteo(conf,opener)
    if provider=='weatherapi':
        return Weather(**fetch_weatherapi(conf,opener,fetched=jp_now()))
    raise ValueError('天気の取得元が不正です')


def parse_clock(s):
    s = str(s or '').strip().replace('：', ':')
    if not re.fullmatch(r'\d{1,2}:\d{2}', s):
        raise ValueError('time must be HH:MM')
    h,m = map(int,s.split(':'))
    if h > 47 or m > 59:
        raise ValueError('time outside 00:00-47:59')
    return h,m


def as_datetime(day: date, text: str):
    hour,minute = parse_clock(text)
    return datetime.combine(day, dt_time(hour % 24,minute), tzinfo=TZ) + timedelta(days=hour//24)


def has_service(service, day):
    """Only enforce known day modes. Holiday-sensitive services should use exact dates in CSV."""
    s = str(service or 'daily').strip().lower()
    if s in ('daily','all','毎日',''): return True
    if s in ('weekday','平日'): return day.weekday() < 5
    if s in ('weekend','土日'): return day.weekday() >= 5
    if s.startswith('date:'): return s[5:] == day.isoformat()
    if s.startswith('except:'): return s[7:] != day.isoformat()
    return False  # Unknown service rules must never be assumed to run


def load_schedule_csv(path=CSV_PATH):
    if not Path(path).exists(): return []
    rows=[]
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        for number,row in enumerate(csv.DictReader(f),start=2):
            if not (row.get('depart') or '').strip(): continue
            try:
                parse_clock(row['depart']); parse_clock(row['arrive'])
            except Exception as exc:
                logger.warning('Ignored invalid timetable row %s: %s', number,exc)
                continue
            rows.append({k:(v or '').strip() for k,v in row.items()})
    return rows


def upcoming_from_csv(now, conf, path=CSV_PATH):
    rows = load_schedule_csv(path)
    if not rows:
        return TrainState([], '時刻表未登録', 'csv')
    result = []
    for days_from_today in (-1,0,1,2):
        d = now.date() + timedelta(days=days_from_today)
        for row in rows:
            if not has_service(row.get('service','daily'),d): continue
            if row.get('from') and row.get('from') != conf['train_from']: continue
            if row.get('to') and row.get('to') != conf['train_to']: continue
            dep=as_datetime(d,row['depart']); arr=as_datetime(d,row['arrive'])
            if arr < dep: arr += timedelta(days=1)
            duration=(arr-dep).total_seconds()/60
            if not 1<=duration<=180: continue
            if dep < now: continue
            result.append(Train(dep,arr,row.get('line',''),row.get('platform',''),row.get('note',''),conf['train_from'],conf['train_to']))
    result.sort(key=lambda x:x.depart)
    unique=[]
    seen=set()
    for t in result:
        key=(t.depart,t.arrive,t.line)
        if key not in seen:
            unique.append(t); seen.add(key)
    return TrainState(unique[:int(conf['train_count'])], '時刻表(予定)', 'csv', jp_now())


def resolve_ir_schedule(path=None):
    """Return (validated timetable, selected path), checking fallback only if needed.

    User-supplied schedule.json takes priority, but a damaged or incomplete file
    must not suppress the known-good schedule bundled with this version.
    """
    import rail_core
    if path is not None:
        candidates=[Path(path)]
    else:
        candidates=[ROOT/'schedule.json', BUNDLE_ROOT/'schedule.json', BUNDLE_ROOT/'fallback_data'/'schedule.json', Path(__file__).resolve().parent/'fallback_data'/'schedule.json']
    failures=[]
    checked=set()
    for candidate in candidates:
        candidate=Path(candidate)
        if candidate in checked:continue
        checked.add(candidate)
        if not candidate.is_file():
            failures.append(f'{candidate}: not found')
            continue
        try:
            doc=rail_core.load_schedule(candidate)
            if not doc.get('second'):
                raise ValueError('second timetable empty')
            return doc,candidate
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append(f'{candidate}: {exc}')
    raise FileNotFoundError('No valid schedule.json. '+' | '.join(failures))


def train_diagnostics(now, conf):
    """Offline, no COM access; expose exact data source and planned departures."""
    via=conf.get('train_source')=='ir_schedule' and conf.get('ir_route','via_kanazawa')=='via_kanazawa'
    result={'engine_version':APP_VERSION,'train_source':conf.get('train_source'),
            'train_from':'加賀笠間' if via else conf.get('train_from'), 'train_to':conf.get('train_to'),
            'ir_route':conf.get('ir_route','via_kanazawa'),
            'settings_file':str(SETTINGS)}
    if conf.get('train_source')=='ir_schedule':
        try:
            doc,p=resolve_ir_schedule()
            result.update(schedule_path=str(p),revision=str(doc.get('revision','')),
                          schedule_rows=len(doc['second']))
        except Exception as exc:
            result['schedule_error']=str(exc)
    try:
        state=choose_trains(now,conf)
        result.update(status=state.status,error=state.error,trains=[
            {'depart':t.depart.isoformat(),'arrive':t.arrive.isoformat(),
             'kanazawa_arrive':t.transfer_arrive.isoformat() if t.transfer_arrive else None,
             'kanazawa_depart':t.transfer_depart.isoformat() if t.transfer_depart else None,
             'direct':t.direct,'transfer_platform':(t.transfer_arrival_platform+'→'+t.transfer_departure_platform) if t.transfer_arrive else '',
             'train':t.line,'platform':t.platform} for t in state.trains])
    except Exception as exc:
        result.update(status='取得失敗',error=str(exc),trains=[])
    return result


def upcoming_from_ir_schedule(now, conf, path=None):
    """Use user-provided schedule.json, second leg = 金沢 -> 津幡.

    The timetable is static. Day type follows the source app's rail_core.active_rule;
    unknown running-day rules are never assumed valid.
    """
    import rail_core
    route=conf.get('ir_route','via_kanazawa')
    if route not in ('via_kanazawa','kanazawa_tsubata'):
        return TrainState([], '経路設定が不正', 'ir_schedule',error='Unsupported IR route')
    if conf.get('train_to')!='津幡':
        return TrainState([], '到着駅は津幡のみ対応', 'ir_schedule',error='Unsupported destination')
    if route=='kanazawa_tsubata' and conf.get('train_from')!='金沢':
        return TrainState([], '対象区間は金沢→津幡', 'ir_schedule',error='Unsupported stations')
    try:
        doc,selected_schedule=resolve_ir_schedule(path)
    except Exception as exc:
        return TrainState([], '時刻表未配置・読込失敗', 'ir_schedule',error=str(exc))
    # Both legs of the user-provided timetable are matched by rail_core;
    # no inferred departures or arrival times.
    if route=='via_kanazawa':
        result=[]
        for delta in (-1,0,1,2):
            day=now.date()+timedelta(days=delta)
            for j in rail_core.journeys_for_date(doc,day):
                if j.dep<now: continue
                result.append(Train(
                    depart=j.dep,arrive=j.arr,line=j.first_train+' / '+j.second_train,
                    platform=j.arr_platform,note='収録時刻表',origin='加賀笠間',destination='津幡',
                    transfer_arrive=j.kan_arr,transfer_depart=j.kan_dep,
                    transfer_arrival_platform=j.arr_platform,
                    transfer_departure_platform=j.dep_platform,direct=j.direct))
        result.sort(key=lambda t:(t.depart,t.arrive,t.line))
        unique=[];seen=set()
        for item in result:
            key=(item.depart,item.transfer_arrive,item.transfer_depart,item.arrive)
            if key not in seen:seen.add(key);unique.append(item)
        rev=str(doc.get('revision','')).replace('2026-','')
        source_label='加賀笠間→金沢→津幡 時刻表(予定)' if not rev else '経由時刻表'+rev+'改正'
        return TrainState(unique[:int(conf['train_count'])],source_label,'ir_schedule',jp_now())

    result=[]
    for delta in (-1,0,1,2):
        day=now.date()+timedelta(days=delta)
        for row in doc['second']:
            # [Kanazawa departure, Tsubata arrival, train number, day rule, platform]
            if not rail_core.active_rule(row[3],day):
                continue
            dep=as_datetime(day,row[0])
            arr=as_datetime(day,row[1])
            if arr<dep: arr+=timedelta(days=1)
            minutes=(arr-dep).total_seconds()/60
            if dep<now or minutes<1 or minutes>180:
                continue
            platform=str(row[4]).strip()
            if platform not in ('1','2','3','4','5','6','7'):
                platform=''
            train_no=str(row[2]).strip()
            result.append(Train(dep,arr,train_no,platform,'収録時刻表','金沢','津幡'))
    result.sort(key=lambda t:(t.depart,t.arrive,t.line))
    unique=[];seen=set()
    for item in result:
        key=(item.depart,item.arrive,item.line)
        if key not in seen:
            seen.add(key);unique.append(item)
    revision=str(doc.get('revision','')).replace('2026-','')
    source_label='収録時刻表(予定)' if not revision else '時刻表'+revision+'改正'
    return TrainState(unique[:int(conf['train_count'])],source_label,'ir_schedule',jp_now())


def train_from_external_json(now, conf, path=JSON_PATH):
    if not Path(path).exists():
        return TrainState([], 'JSON未設定', 'json')
    with Path(path).open(encoding='utf-8-sig') as f:
        doc=json.load(f)
    if not isinstance(doc,dict): raise ValueError('train_results.json must be an object')
    ttl = int(doc.get('valid_for_seconds', 900))
    updated=datetime.fromisoformat(doc['updated_at'])
    if updated.tzinfo is None: raise ValueError('updated_at requires timezone')
    if abs((now-updated).total_seconds()) > ttl:
        return TrainState([], '外部データ期限切れ', 'json')
    result=[]
    for row in doc.get('trains',[]):
        dep=datetime.fromisoformat(row['depart_at']); arr=datetime.fromisoformat(row['arrive_at'])
        if dep.tzinfo is None or arr.tzinfo is None: continue
        dep=dep.astimezone(TZ); arr=arr.astimezone(TZ)
        if now<=dep<=now+timedelta(days=1) and 0 < (arr-dep).total_seconds() <= 180*60:
            result.append(Train(dep,arr,str(row.get('line','')),str(row.get('platform','')),str(row.get('note','')),conf['train_from'],conf['train_to']))
    result.sort(key=lambda t:t.depart)
    return TrainState(result[:int(conf['train_count'])], '外部データ', 'json', jp_now())


def fetch_google_transit(conf, opener=urlopen):
    """Optional Google Routes API v2 (current, not legacy Directions).

    May incur charges; requires a user-owned API key with Routes API enabled.
    A route may contain only one train, and missing departures are never fabricated.
    """
    key = str(conf.get('google_maps_api_key','')).strip()
    if not key:
        return TrainState([], 'APIキー未設定', 'google_transit')
    now=jp_now()
    routes=[]
    # An individual route query returns the next recommended route, not a timetable;
    # use several query times to increase the chance of obtaining 2-3 departures.
    for plus in (0,20,40):
        at=now+timedelta(minutes=plus)
        stamp=at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        body={
            'origin': {'address': conf['train_from']+'駅, 石川県, 日本'},
            'destination': {'address': conf['train_to']+'駅, 石川県, 日本'},
            'travelMode': 'TRANSIT',
            'computeAlternativeRoutes': True,
            'departureTime':stamp,
            'languageCode':'ja',
            'regionCode':'JP',
            'transitPreferences': {'allowedTravelModes':['TRAIN','RAIL','LIGHT_RAIL']}
        }
        req=Request('https://routes.googleapis.com/directions/v2:computeRoutes',
                    data=json.dumps(body).encode('utf-8'),method='POST',
                    headers={'Content-Type':'application/json',
                             'X-Goog-Api-Key':key,
                             'X-Goog-FieldMask':'routes.legs.steps.travelMode,routes.legs.steps.transitDetails'})
        with opener(req,timeout=14) as response:
            doc=json.load(response)
        if doc.get('error'):
            raise RuntimeError('Google Routes API: '+str(doc['error'].get('message','unknown error')))
        for route in doc.get('routes',[]):
            for leg in route.get('legs',[]):
                transits=[step['transitDetails'] for step in leg.get('steps',[]) if step.get('transitDetails')]
                # One train, no transfer. Walking steps are harmless.
                if len(transits)!=1:continue
                td=transits[0]
                stop=td.get('stopDetails') or {}
                start_stop=str((stop.get('departureStop') or {}).get('name',''))
                end_stop=str((stop.get('arrivalStop') or {}).get('name',''))
                def matches(name,ja,roman):
                    text=name.casefold()
                    return ja in name or roman.casefold() in text
                if not matches(start_stop,conf['train_from'],'Kanazawa') or not matches(end_stop,conf['train_to'],'Tsubata'):
                    continue
                dep_s=stop.get('departureTime');arr_s=stop.get('arrivalTime')
                if not dep_s or not arr_s:continue
                def from_rfc3339(ts):
                    return datetime.fromisoformat(str(ts).replace('Z','+00:00')).astimezone(TZ)
                dep=from_rfc3339(dep_s);arr=from_rfc3339(arr_s)
                if dep<now or arr<=dep:continue
                line=td.get('transitLine') or {}
                vehicles=line.get('vehicle') or {}
                if vehicles.get('type') and vehicles.get('type') not in ('RAIL','HEAVY_RAIL','COMMUTER_TRAIN','HIGH_SPEED_TRAIN','TRAIN','LIGHT_RAIL'):
                    continue
                line_name=str(line.get('nameShort') or line.get('name') or '列車')
                routes.append(Train(dep,arr,line_name,'',str(td.get('headsign') or ''),conf['train_from'],conf['train_to']))
    routes.sort(key=lambda t:t.depart)
    seen=set(); result=[]
    for train in routes:
        unique=(train.depart,train.arrive)
        if unique not in seen:
            result.append(train);seen.add(unique)
    return TrainState(result[:int(conf['train_count'])], 'API経路(予定)' if result else '候補なし', 'google_transit', jp_now())


def choose_trains(now, conf):
    src=conf.get('train_source','csv')
    if src=='ir_schedule': return upcoming_from_ir_schedule(now,conf)
    if src=='csv': return upcoming_from_csv(now,conf)
    if src=='json': return train_from_external_json(now,conf)
    if src=='google_transit': return fetch_google_transit(conf)
    return TrainState([], 'データ源不明', src)


# All drawing is performed in natural landscape 480x320, then rotated 180 degrees.
FONT_PATHS={
    'ja': ['C:/Windows/Fonts/meiryo.ttc','C:/Windows/Fonts/YuGothB.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'],
    'num': ['C:/Windows/Fonts/segoeuib.ttf','C:/Windows/Fonts/arialbd.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
}
FONT_CACHE={}


def font(size, kind='ja'):
    key=(size,kind)
    if key in FONT_CACHE:return FONT_CACHE[key]
    for name in FONT_PATHS[kind]:
        if Path(name).is_file():
            FONT_CACHE[key]=ImageFont.truetype(name,size)
            return FONT_CACHE[key]
    FONT_CACHE[key]=ImageFont.load_default()
    return FONT_CACHE[key]


def measured_text(draw, text, size, max_width, kind='ja', min_size=8):
    text=str(text)
    for s in range(size,min_size-1,-1):
        f=font(s,kind)
        if draw.textbbox((0,0),text,font=f)[2] <= max_width:
            return text,f
    # Clip long label to available width, adding ellipsis.
    f=font(min_size,kind)
    trunc=text
    while trunc and draw.textbbox((0,0),trunc+'…',font=f)[2] > max_width:
        trunc=trunc[:-1]
    return (trunc+'…' if trunc else ''),f


def fit_text(draw,xy,text,size,max_width,fill=WHITE,kind='ja',min_size=9):
    result,f=measured_text(draw,text,size,max_width,kind,min_size=min_size)
    draw.text(xy,result,fill=fill,font=f)
    # Pillow includes ascender/descender bearing offsets in this box.
    return draw.textbbox(xy,result,font=f)


def style_label(draw, conf, key, text, min_size=8, max_width=None):
    spec=style_props(conf,key)
    width=spec['max_width'] if max_width is None else max(spec['max_width'],max_width)
    width=max(1,min(width,W-spec['x']-1))
    if key in WEATHER_RIGHT_ALIGNED_VALUES:
        # Numeric entries share an exact right edge (104px in the default
        # layout). The configured x shifts the entire right-aligned cell,
        # while font size changes never move its right edge.
        # Units are separate, left-anchored labels starting at x=106.
        right_edge=min(W-1,spec['x']+ELEMENTS[key][6])
        available=max(1,min(width,right_edge-spec['x']))
        shown,used_font=measured_text(draw,text,spec['size'],available,
                                      spec['kind'],min_size=min_size)
        ink=draw.textbbox((0,0),shown,font=used_font)
        origin=(right_edge-ink[2],spec['y'])
        draw.text(origin,shown,fill=spec['color'],font=used_font)
        return draw.textbbox(origin,shown,font=used_font)
    return fit_text(draw,(spec['x'],spec['y']),text,spec['size'],width,
                    spec['color'],spec['kind'],min_size=min_size)


def notice_region(conf):
    """Logical (unrotated) banner crop; bounded to the train panel."""
    spec=style_props(conf,'train_notice')
    panel=panel_settings(conf,'train')
    x0=max(panel['x']+7,spec['x'])
    y0=max(panel['y']+5,spec['y'])
    x1=min(W-4,panel['x']+panel['w']-7,spec['x']+spec['max_width'])
    y1=min(H-1,panel['y']+panel['h']-4,y0+17)
    return (x0,y0,max(x0+1,x1),max(y0+1,y1))


def notice_overflows(conf, text):
    x0,y0,x1,y1=notice_region(conf)
    spec=style_props(conf,'train_notice')
    measure=ImageDraw.Draw(Image.new('RGB',(2,2)))
    return measure.textlength(str(text),font=font(spec['size'],spec['kind']))>(x1-x0)


def draw_rail_notice(image, conf, text, scroll_px=0):
    """Draw a one-line marquee inside a clipped transparent overlay.

    This never spills into train times or panel edges. Static strings do not
    move; only text wider than the available band is horizontally scrolled.
    """
    x0,y0,x1,y1=notice_region(conf)
    w,h=x1-x0,y1-y0
    spec=style_props(conf,'train_notice')
    message=str(text or '運行情報：未確認')
    ft=font(spec['size'],spec['kind'])
    overlay=Image.new('RGBA',(w,h),(0,0,0,0))
    d=ImageDraw.Draw(overlay)
    ink=d.textbbox((0,0),message,font=ft)
    text_width=max(0,int(d.textlength(message,font=ft)+.5))
    scrollable=text_width>w
    gap=34
    offset=int(scroll_px)%(text_width+gap) if scrollable else 0
    baseline=1-ink[1]  # place glyph ink at top, avoiding font ascent artifacts
    color=spec['color']
    d.text((-offset,baseline),message,font=ft,fill=color)
    if scrollable:
        d.text((text_width+gap-offset,baseline),message,font=ft,fill=color)
    image.paste(overlay,(x0,y0),overlay)
    return (x0,y0,x1,y1),scrollable


def datetime_text(now, conf):
    days='月火水木金土日'
    date_part=now.strftime('%m/%d')+'('+days[now.weekday()]+') '
    tm=now.strftime('%I:%M' if conf.get('clock_12h') else '%H:%M')
    if conf.get('show_seconds', True):tm+=':'+now.strftime('%S')
    return date_part+tm


def clock_minute_key(now,conf):
    return datetime_text(now,conf)[:-2] if conf.get('show_seconds',True) else datetime_text(now,conf)


def clock_label_region(conf, now):
    """Full date/time label crop, covering old and new minute glyphs."""
    sp=style_props(conf,'clock_datetime')
    d=ImageDraw.Draw(Image.new('RGB',(2,2)))
    width=max(1,min(sp['max_width'],W-sp['x']-1))
    boxes=[]
    for moment in (now,now-timedelta(minutes=1)):
        shown,ft=measured_text(d,datetime_text(moment,conf),sp['size'],width,sp['kind'],min_size=8)
        boxes.append(d.textbbox((sp['x'],sp['y']),shown,font=ft))
    return (max(0,min(b[0] for b in boxes)-5),
            max(0,min(b[1] for b in boxes)-5),
            min(W,max(b[2] for b in boxes)+7),
            min(H,max(b[3] for b in boxes)+5))


def seconds_region(conf, now=None):
    """Exact seconds text crop, computed from the same font and text as renderer."""
    if now is None:now=jp_now()
    sp=style_props(conf,'clock_datetime')
    text=datetime_text(now,conf)
    if not conf.get('show_seconds',True):return (0,0,1,1)
    d=ImageDraw.Draw(Image.new('RGB',(W,H)))
    # Same width and font-fitting as style_label.
    width=max(1,min(sp['max_width'],W-sp['x']-1))
    drawn,f=measured_text(d,text,sp['size'],width,sp['kind'],min_size=8)
    if not drawn.endswith(now.strftime('%S')):
        # Unexpectedly clipped clock; request safe full header update.
        return (0,0,W,58)
    prefix=drawn[:-2]
    x=int(round(sp['x']+d.textlength(prefix,font=f)))
    bounds=d.textbbox((x,sp['y']),'88',font=f)
    return (max(0,min(x-4,bounds[0]-3)),max(0,bounds[1]-3),
            min(W,max(x+1,bounds[2]+4)),min(H,bounds[3]+3))


def card(draw,xy,rounded=10,fill=PANEL,outline=BORDER,width=1):
    draw.rounded_rectangle(xy,radius=rounded,fill=fill,outline=outline,width=width)


def draw_weather_icon(draw, code, x, y):
    # Simple drawn pictogram (no font-dependent emoji).
    if code is None:
        draw.ellipse((x+14,y+10,x+39,y+35),outline=MUTED,width=2);return
    sunny=code in (0,1,2)
    if sunny:
        draw.ellipse((x+5,y+2,x+33,y+30),fill=YELLOW)
        for dx,dy in ((0,-6),(0,35),(-10,14),(35,14)):
            draw.line((x+19,y+14,x+19+dx,y+14+dy),fill=YELLOW,width=2)
    if code not in (0,):
        draw.ellipse((x+7,y+21,x+31,y+39),fill=(180,209,224))
        draw.ellipse((x+20,y+15,x+47,y+39),fill=(190,217,233))
        draw.rounded_rectangle((x+9,y+29,x+50,y+41),radius=6,fill=(197,223,237))
    if code in (61,63,65,66,67,80,81,82):
        for dx in (15,27,39):draw.line((x+dx,y+44,x+dx-4,y+52),fill=CYAN,width=2)
    if code in (71,73,75,77,85,86):
        for dx in (15,27,39):draw.ellipse((x+dx,y+45,x+dx+3,y+48),fill=WHITE)
    if code in (95,96,99):
        draw.line((x+28,y+42,x+23,y+51,x+32,y+51,x+25,y+59),fill=YELLOW,width=3)


def value_or_dash(val,formatter=lambda a: str(a)):
    return '---' if val is None else formatter(val)


def render_original(now, weather, train_state, conf, hit_boxes=None, rail_notice=None, marquee_px=0):
    """Draw logical 480x320 dashboard; optionally return actual text/panel hitboxes."""
    img=Image.new('RGB',(W,H),BG)
    d=ImageDraw.Draw(img)
    def panel(key):
        box=draw_panel(d,conf,key)
        if hit_boxes is not None:hit_boxes['panel:'+key]=box
    def label(key,text,min_size=8,max_width=None):
        box=style_label(d,conf,key,text,min_size=min_size,max_width=max_width)
        if hit_boxes is not None:hit_boxes['text:'+key]=box

    panel('header')
    label('clock_datetime',datetime_text(now,conf))
    label('version','v'+APP_VERSION)

    # Compact weather panel: no prefecture prefix, integer temperatures.
    panel('weather')
    label('weather_city',weather.city)
    d.line((13,82,119,82),fill=BORDER)
    draw_weather_icon(d,weather.code,8,93)
    label('weather_description',weather.condition_text or ('キー未設定' if weather.code is None and weather.error and 'APIキー' in weather.error else weather_description(weather.code)))
    label('weather_temperature',value_or_dash(weather.temperature,lambda a:f'{a:.0f}'),12)
    label('weather_temperature_unit','℃' if weather.temperature is not None else '')
    d.line((13,150,119,150),fill=BORDER)
    label('weather_high_label','最高')
    label('weather_high',value_or_dash(weather.high,lambda a:f'{a:.0f}'))
    label('weather_high_unit','℃' if weather.high is not None else '')
    label('weather_low_label','最低')
    label('weather_low',value_or_dash(weather.low,lambda a:f'{a:.0f}'))
    label('weather_low_unit','℃' if weather.low is not None else '')
    label('weather_rain_label','降水')
    label('weather_rain',value_or_dash(weather.precip,lambda a:f'{a}'))
    label('weather_rain_unit','%' if weather.precip is not None else '')
    label('weather_humidity_label','湿度')
    label('weather_humidity',value_or_dash(weather.humidity,lambda a:f'{a}'))
    label('weather_humidity_unit','%' if weather.humidity is not None else '')
    label('weather_wind_label','風')
    label('weather_wind',value_or_dash(weather.wind,lambda a:f'{a:.1f}'))
    label('weather_wind_unit','m/s' if weather.wind is not None else '')

    # Four separate editable time columns per connection: boarding, Kanazawa
    # arrival, Kanazawa departure, and destination arrival. Do NOT combine
    # these into one text run: that silently shrinks digits on 480px hardware.
    panel('train')
    rail_text=(rail_notice.text if rail_notice is not None else '運行情報：未確認')
    notice_box,_scrolls=draw_rail_notice(img,conf,rail_text,marquee_px)
    if hit_boxes is not None:hit_boxes['text:train_notice']=notice_box
    d.line((142,77,465,77),fill=BORDER)
    for i in range(3):
        n=i+1
        panel(f'train_{n}')
        if i<len(train_state.trains):
            t=train_state.trains[i]
            label(f'train_index_{n}',str(n))
            if t.transfer_arrive is not None and t.transfer_depart is not None:
                label(f'train_station_depart_{n}','発')
                label(f'train_station_kan_arr_{n}','金沢着')
                label(f'train_station_kan_dep_{n}','金沢発')
                label(f'train_station_arrive_{n}','着')
                label(f'train_time_{n}',t.depart.strftime('%H:%M'),12)
                label(f'train_kan_arr_{n}',t.transfer_arrive.strftime('%H:%M'),12)
                label(f'train_kan_dep_{n}',t.transfer_depart.strftime('%H:%M'),12)
                label(f'train_arrive_{n}',t.arrive.strftime('%H:%M'),12)
                wait=int((t.transfer_depart-t.transfer_arrive).total_seconds()//60)
                platforms=(t.transfer_arrival_platform or '?')+'→'+(t.transfer_departure_platform or '?')
                caption=('直通（乗換不要）  ' if t.direct else f'乗換{wait}分  ')+platforms+'番線'
                if t.arrive.date()>t.depart.date():caption+=' 翌日着'
                if t.depart.date()>now.date():caption='翌日発 '+caption
                label(f'train_detail_{n}',caption)
            else:
                label(f'train_legacy_time_{n}',t.depart.strftime('%H:%M')+' → '+t.arrive.strftime('%H:%M'))
                duration=int(round((t.arrive-t.depart).total_seconds()/60))
                caption=(t.line or '列車')+'  '+f'{duration}分'
                if t.platform:caption+='  '+t.platform+'番線'
                if t.depart.date()>now.date():caption='翌日 '+caption
                elif t.arrive.date()>t.depart.date():caption+='  翌日着'
                label(f'train_detail_{n}',caption)
        elif i==0:
            label('train_empty',train_state.status)
        else:
            label(f'train_placeholder_{n}','-- : --')

    # Update timestamps are within their own panels, not in a fourth footer box.
    d.line((13,283,119,283),fill=BORDER)
    d.line((145,283,464,283),fill=BORDER)
    weather_status='更新 '+weather.fetched.strftime('%H:%M') if weather.fetched else '天気 未取得'
    train_status='更新 '+train_state.loaded.strftime('%H:%M') if train_state.loaded else '列車 未取得'
    label('footer_weather',weather_status)
    label('train_source_note','時刻表（予定）' if train_state.source=='ir_schedule' else train_state.source)
    label('footer_train',train_status)
    return img


def render_physical(now, weather, train_state, conf, rail_notice=None, marquee_px=0):
    return render_original(now,weather,train_state,conf,
                           rail_notice=rail_notice,marquee_px=marquee_px).transpose(Image.Transpose.ROTATE_180)


def orientation_packet():
    p=bytearray(16)
    p[5]=121;p[6]=102  # known-good RevA landscape = 2; pixel data rotated
    p[7:9]=W.to_bytes(2,'big');p[9:11]=H.to_bytes(2,'big')
    return bytes(p)


def region_packet(x0,y0,x1,y1):
    assert 0<=x0<=x1<W and 0<=y0<=y1<H
    return bytes((x0>>2,((x0&3)<<6)|(y0>>4),((y0&15)<<4)|(x1>>6),((x1&63)<<2)|(y1>>8),y1&255,197))


def rgb565le(image):
    pixels=image.convert('RGB').tobytes();out=bytearray(image.width*image.height*2)
    for i in range(0,len(pixels),3):
        r,g,b=pixels[i],pixels[i+1],pixels[i+2]
        c=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
        j=(i//3)*2;out[j]=c&255;out[j+1]=c>>8
    return out


def write_all(port,data):
    view=memoryview(data); pos=0
    while pos<len(view):
        n=port.write(view[pos:])
        if not n or n<0:raise IOError('serial write incomplete')
        pos+=n


def send_bitmap(port, image, x, y):
    write_all(port,region_packet(x,y,x+image.width-1,y+image.height-1))
    payload=rgb565le(image)
    # Same 480*8 byte chunks as the confirmed V2 kit.
    for start in range(0,len(payload),W*8):
        write_all(port,payload[start:start+W*8])
    port.flush()
    return len(payload)


def open_display(port_name):
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    found=[]
    for item in ports:
        if item.vid==VID and item.pid==PID and str(item.serial_number).upper() in SERIAL_IDS:
            found.append(item)
    if port_name.upper()=='AUTO':
        if len(found)!=1:raise RuntimeError('AUTO needs exactly 1 USB35INCHIPSV2. Found: '+str(len(found)))
        port_name=found[0].device
    elif not any(item.device.upper()==port_name.upper() for item in found):
        raise RuntimeError('Not a recognized 3.5-inch TURZX serial port: '+port_name)
    return serial.Serial(port_name,baudrate=115200,timeout=1,write_timeout=3,rtscts=True)


def log_setup():
    (ROOT/'logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.FileHandler(ROOT/'logs'/'dashboard.log',encoding='utf-8')] + ([logging.StreamHandler()] if sys.stderr is not None else []))


def save_runtime_status(**kwargs):
    """Update local IPC status in RAM; never write runtime_status.json."""
    state=current_state()
    if state is not None:
        state.update(pid=os.getpid(),**kwargs)


def settings_digest():
    try:
        raw=SETTINGS.read_bytes()
        return hashlib.sha256(raw).hexdigest()
    except OSError:
        return ''


def read_live_settings():
    """Validate and use a newly written settings file, otherwise retain old configuration."""
    fresh=load_settings()
    if fresh.get('weather_provider') not in ('weatherapi','openmeteo'):
        raise ValueError('Unknown weather provider')
    if fresh.get('train_source') not in ('ir_schedule','csv','json','google_transit'):
        raise ValueError('Unknown train source')
    if str(fresh.get('clock_update_mode','compact')) not in ('compact','safe_strip'):
        raise ValueError('Unknown clock update mode')
    fresh['ntp_sync_minutes']=int(fresh.get('ntp_sync_minutes',30))
    if not 5<=fresh['ntp_sync_minutes']<=1440:
        raise ValueError('NTP同期間隔は5～1440分です')
    if not isinstance(fresh.get('ntp_server'),str) or not fresh['ntp_server'].strip():
        raise ValueError('NTPサーバー名が未設定です')
    fresh['train_count']=max(1,min(3,int(fresh['train_count'])))
    if fresh.get('ir_route') not in ('via_kanazawa','kanazawa_tsubata'): fresh['ir_route']='via_kanazawa'
    fresh['train_update_seconds']=max(10,int(fresh['train_update_seconds']))
    fresh['weather_update_minutes']=max(5,int(fresh['weather_update_minutes']))
    fresh['rail_status_update_minutes']=max(5,min(60,int(fresh.get('rail_status_update_minutes',5))))
    fresh['rail_status_enabled']=bool(fresh.get('rail_status_enabled',True))
    if not str(fresh.get('port','')).strip():
        raise ValueError('Empty COM port')
    validate_styles(fresh)
    validate_panels(fresh)
    return fresh


def rotation_region(logical_box):
    """Map an exclusive-end logical crop box to the 180-degree physical frame."""
    x0,y0,x1,y1=logical_box
    assert 0<=x0<x1<=W and 0<=y0<y1<=H
    return W-x1,H-y1,W-x0,H-y0


def send_rotated_box(port, physical_frame, logical_box):
    x0,y0,x1,y1=rotation_region(logical_box)
    send_bitmap(port,physical_frame.crop((x0,y0,x1,y1)),x0,y0)


def acquire_singleton_lock():
    # File lock is held by the running process, with no stale-PID race after a crash.
    LOCK_PATH.touch(exist_ok=True)
    fh=LOCK_PATH.open('r+b')
    fh.seek(0);fh.write(b'1');fh.flush();fh.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def release_singleton_lock(fh):
    if not fh:return
    try:
        fh.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(),fcntl.LOCK_UN)
    except Exception:pass
    fh.close()


def run_dashboard(conf, preview=False, preview_demo=False, no_usb=False, seconds=0):
    rail_notice=RailNotice()
    weather=Weather(city=conf['weather_city'],provider=conf.get('weather_provider','weatherapi'))
    train=TrainState([], '読込中',conf['train_source'])
    if preview_demo:
        # Demo data exists only behind an explicit '--demo-preview' option, not live mode.
        now=jp_now()
        weather=Weather(city=conf['weather_city'],temperature=12.8,high=15.0,low=8.0,precip=20,humidity=68,wind=2.1,code=3,fetched=now,error=None)
        train=TrainState([Train(now+timedelta(minutes=i*18+7),now+timedelta(minutes=i*18+21),'普通',str(3+i%2)) for i in range(3)],'デモ用仮データ','demo',now)
        frame=render_physical(now,weather,train,conf)
        frame.save(ROOT/'preview_demo_only.png')
        print('DEMO ONLY: preview_demo_only.png (not actual train/weather data)')
        return
    if preview:
        now=jp_now()
        try:
            train=choose_trains(now,conf)
        except Exception as exc:
            train=TrainState([], '列車取得失敗',conf['train_source'],error=str(exc))
        frame=render_physical(now,weather,train,conf)
        frame.save(PREVIEW)
        print('Preview saved:',PREVIEW)
        return

    weather_every=max(5,int(conf['weather_update_minutes']))*60
    train_every=max(10,int(conf['train_update_seconds']))
    notice_every=max(5,int(conf.get('rail_status_update_minutes',5)))*60
    port_name=conf['port']
    future=None
    rail_future=None
    rail_due=0.0
    weather_due=0.0
    notice_future=None
    notice_due=0.0
    marquee_px=0
    previous_marquee_px=0
    next_marquee=0.0
    prev_frame=None
    prev_data_signature=None
    last_hm=None
    last_seconds=None
    previous_clock=None
    next_retry=0.0
    device=None
    force_full=True
    usb_error=''
    last_usb_check=0.0
    last_transfer_ms=0.0
    last_transfer_kind=''
    last_status=0.0
    last_settings_poll=0.0
    last_settings_hash=settings_digest()
    began=time.monotonic()
    ntp_future=None
    ntp_future_server=None
    ntp_due=0.0
    pool=ThreadPoolExecutor(max_workers=4)
    try:
        try:STOP_PATH.unlink(missing_ok=True)
        except Exception:pass
        try:STATUS_PATH.unlink(missing_ok=True)  # remove any V3.4 heartbeat file once
        except Exception:pass
        while not seconds or time.monotonic()-began<seconds:
            tick=time.monotonic()
            # NTP requests are asynchronous: USB refresh and GUI remain responsive.
            if ntp_future is None and tick>=ntp_due:
                ntp_future_server=str(conf.get('ntp_server',NTP_SERVER)).strip()
                ntp_future=pool.submit(query_ntp,ntp_future_server,2.5)
                ntp_due=tick+max(5,int(conf.get('ntp_sync_minutes',30)))*60
            if ntp_future is not None and ntp_future.done():
                try:
                    sample=ntp_future.result()
                    if sample.server==str(conf.get('ntp_server',NTP_SERVER)).strip():
                        CLOCK.accept(sample)
                        logger.info('NTP synchronized: %s, offset %.3fs, RTT %.3fs',
                                    sample.server,sample.offset_seconds,sample.rtt_seconds)
                        # Corrected date may change the upcoming train list and header.
                        rail_due=0.0
                        last_hm=None;last_seconds=None;prev_data_signature=None
                except Exception as exc:
                    CLOCK.failed(str(exc))
                    logger.warning('NTP unavailable; using last sync or PC fallback: %s',exc)
                    ntp_due=min(ntp_due,tick+60)
                ntp_future=None
                ntp_future_server=None
            now=jp_now()
            ipc=current_state()
            if STOP_PATH.exists() or (ipc and ipc.stop_requested.is_set()):
                logger.info('Stop requested from settings GUI')
                STOP_PATH.unlink(missing_ok=True)
                break
            if ipc and ipc.reconnect_requested.is_set():
                ipc.reconnect_requested.clear()
                logger.info('Manual USB reconnect requested')
                if device is not None:
                    try:device.close()
                    except Exception:pass
                device=None
                next_retry=0.0
                force_full=True
                usb_error='再接続処理中'
                last_hm=None;last_seconds=None

            # Read settings periodically, without terminating the renderer.
            if tick-last_settings_poll>=.25:
                last_settings_poll=tick
                current_hash=settings_digest()
                if current_hash!=last_settings_hash:
                    try:
                        incoming=read_live_settings()
                        prev_conf=dict(conf)
                        conf.clear();conf.update(incoming)
                        last_settings_hash=current_hash
                        logger.info('Live settings applied; weather=%s, port=%s, clock=%s',conf['weather_city'],conf['port'],conf.get('clock_update_mode'))
                        if any(prev_conf.get(k)!=conf.get(k) for k in ('weather_city','weather_latitude','weather_longitude','weather_update_minutes','weather_provider','weatherapi_key')):
                            weather=Weather(city=conf['weather_city'],provider=conf.get('weather_provider','weatherapi'))
                            weather_due=0.0
                            future=None  # the old in-flight request is ignored
                        if any(prev_conf.get(k)!=conf.get(k) for k in ('rail_status_enabled','rail_status_update_minutes')):
                            notice_future=None
                            notice_due=0.0
                            marquee_px=0
                            if not conf.get('rail_status_enabled',True):
                                rail_notice=RailNotice('運行情報：表示OFF')
                        if any(prev_conf.get(k)!=conf.get(k) for k in ('ntp_server','ntp_sync_minutes')):
                            ntp_due=0.0
                        if any(prev_conf.get(k)!=conf.get(k) for k in ('train_source','ir_route','train_from','train_to','train_update_seconds','train_count','google_maps_api_key','google_refresh_minutes')):
                            train=TrainState([], '更新中',conf['train_source'])
                            rail_due=0.0
                            rail_future=None
                        weather_every=max(5,int(conf['weather_update_minutes']))*60
                        train_every=max(10,int(conf['train_update_seconds']))
                        notice_every=max(5,int(conf.get('rail_status_update_minutes',5)))*60
                        if port_name!=conf['port']:
                            port_name=conf['port']
                            if device is not None:
                                try:device.close()
                                except Exception:pass
                                device=None
                            next_retry=0.0
                            force_full=True
                        prev_data_signature=None
                        last_hm=None;last_seconds=None;previous_clock=None
                    except Exception as exc:
                        logger.error('Live settings are invalid; retaining previous settings: %s',exc)

            if future is None and tick>=weather_due:
                future=pool.submit(fetch_weather,dict(conf))
                weather_due=tick+weather_every
            if future is not None and future.done():
                try:
                    weather=future.result()
                    logger.info('Weather updated for %s: %s degC',weather.city,weather.temperature)
                except Exception as exc:
                    logger.error('Weather API unavailable: %s',exc)
                    weather.error=str(exc)[:60]
                    if weather.fetched is None:weather.city=conf['weather_city']
                    weather_due=min(weather_due,tick+60)
                future=None
            if rail_future is None and tick>=rail_due:
                if conf['train_source']=='google_transit':
                    rail_due=tick+max(5,int(conf['google_refresh_minutes']))*60
                    rail_future=pool.submit(fetch_google_transit,dict(conf))
                else:
                    rail_due=tick+train_every
                    rail_future=pool.submit(choose_trains,now,dict(conf))
            if rail_future is not None and rail_future.done():
                try:
                    train=rail_future.result()
                except Exception as exc:
                    logger.warning('Train data unavailable: %s',exc)
                    train=TrainState([], '列車取得失敗',str(conf['train_source']),error=str(exc))
                    rail_due=min(rail_due,tick+60)
                rail_future=None
            if train.source=='google_transit':
                current=[t for t in train.trains if t.depart>=now]
                train=TrainState(current,'API経路(予定)' if current else '次の便を再検索中',train.source,train.loaded,train.error)

            # Public IR JSON and JR West official text at a polite five-minute
            # interval. Unknown/failed sources NEVER imply normal operation.
            if conf.get('rail_status_enabled',True):
                if notice_future is None and tick>=notice_due:
                    notice_future=pool.submit(fetch_official_rail_notice)
                    notice_due=tick+notice_every
                if notice_future is not None and notice_future.done():
                    try:
                        current_notice=notice_future.result()
                        if current_notice.text != rail_notice.text:
                            marquee_px=0
                            next_marquee=tick+2.0
                        rail_notice=current_notice
                        logger.info('Rail sources: IR=%s, Nanao=%s',
                                    rail_notice.ir.state,rail_notice.nanao.state)
                    except Exception as exc:
                        logger.warning('Rail status unavailable: %s',type(exc).__name__)
                        rail_notice=RailNotice('運行情報：未確認')
                        notice_due=min(notice_due,tick+60)
                    notice_future=None
            else:
                rail_notice=RailNotice('運行情報：表示OFF')

            # Sample the NTP/PC clock after data processing. Never derive time
            # by counting screen refreshes or elapsed USB transfers.
            now=jp_now()
            scrolling=notice_overflows(conf,rail_notice.text)
            # Scroll updates are optional. Defer when near the next second,
            # leaving room for a higher-priority clock packet.
            if scrolling and tick>=next_marquee and now.microsecond<600000:
                marquee_px+=16
                next_marquee=tick+1.7
            if not scrolling and marquee_px:
                marquee_px=0
            marquee_changed=(marquee_px!=previous_marquee_px)
            data_signature=(
                weather.city,weather.temperature,weather.high,weather.low,weather.precip,
                weather.humidity,weather.wind,weather.code,weather.error,
                weather.provider,weather.condition_text,weather.raw_condition_code,
                weather.fetched.strftime('%H:%M') if weather.fetched else None,
                train.status,rail_notice.text,
                tuple((t.depart.isoformat(),t.arrive.isoformat(),t.line,t.platform) for t in train.trains),
                now.date()
            )
            changed=prev_data_signature is None or data_signature!=prev_data_signature
            hm=clock_minute_key(now,conf)
            sec=now.strftime('%S') if conf.get('show_seconds',True) else ''
            hm_due=hm!=last_hm
            sec_due=sec!=last_seconds
            redraw=changed or hm_due or sec_due or marquee_changed or force_full

            # Check PnP presence periodically, including while no frame changes.
            # Never disable/re-enable Windows devices without user permission.
            if not no_usb and device is not None and tick-last_usb_check>=1.0:
                last_usb_check=tick
                try:
                    from serial.tools import list_ports
                    attached=any(p.device.upper()==device.port.upper()
                                 and p.vid==VID and p.pid==PID
                                 for p in list_ports.comports())
                    if not attached:
                        raise OSError('USBシリアルデバイスが切断されました')
                except Exception as exc:
                    usb_error=str(exc)
                    logger.warning('USB disconnected: %s',exc)
                    try:device.close()
                    except Exception:pass
                    device=None
                    force_full=True
                    next_retry=tick+1.0

            if not no_usb and device is None and tick>=next_retry:
                try:
                    device=open_display(port_name)
                    write_all(device,orientation_packet())
                    time.sleep(.12)  # tested Rev A orientation setup
                    last_usb_check=tick
                    usb_error=''
                    force_full=True
                    logger.info('Connected and initialized: %s',device.port)
                except Exception as exc:
                    usb_error=f'{type(exc).__name__}: {exc}'
                    logger.warning('LCD connection unavailable: %s',usb_error)
                    if device is not None:
                        try:device.close()
                        except Exception:pass
                    device=None
                    next_retry=tick+5.0

            did_update=False
            if no_usb and redraw:
                frame=render_physical(now,weather,train,conf,
                                      rail_notice=rail_notice,marquee_px=marquee_px)
                frame.save(PREVIEW)
                did_update=True
            elif device is not None and redraw:
                # Avoid a full 480x320 render on every 50 ms idle loop.
                frame=render_physical(now,weather,train,conf,
                                      rail_notice=rail_notice,marquee_px=marquee_px)
                transfer_start=time.monotonic()
                kind='clock'
                try:
                    if force_full or changed:
                        kind='full'
                        send_bitmap(device,frame,0,0)
                        logger.info('Full frame sent (%s; weather=%s)',train.status,weather.error or 'OK')
                    elif hm_due:
                        # Minute rollover no longer blocks the following
                        # second on a complete 480x320 bitmap transmission.
                        kind='clock-minute'
                        header=clock_label_region(conf,now)
                        if conf.get('clock_update_mode','compact')=='safe_strip' and header[3]<=CLOCK_STRIP:
                            send_bitmap(device,frame.crop((0,H-CLOCK_STRIP,W,H)),0,H-CLOCK_STRIP)
                        else:
                            send_rotated_box(device,frame,header)
                        if marquee_changed:
                            send_rotated_box(device,frame,notice_region(conf))
                    else:
                        # Clock is sent FIRST, before optional marquee motion.
                        if sec_due and conf.get('show_seconds',True):
                            if conf.get('clock_update_mode','compact')=='safe_strip':
                                if seconds_region(conf,now)[3]>CLOCK_STRIP:
                                    send_rotated_box(device,frame,clock_label_region(conf,now))
                                else:
                                    send_bitmap(device,frame.crop((0,H-CLOCK_STRIP,W,H)),0,H-CLOCK_STRIP)
                            else:
                                send_rotated_box(device,frame,seconds_region(conf,now))
                        if marquee_changed:
                            kind='clock+marquee' if sec_due else 'marquee'
                            send_rotated_box(device,frame,notice_region(conf))
                    last_transfer_ms=round((time.monotonic()-transfer_start)*1000,1)
                    last_transfer_kind=kind
                    usb_error=''
                    force_full=False
                    did_update=True
                except Exception as exc:
                    usb_error=f'{type(exc).__name__}: {exc}'
                    logger.warning('USB transfer failed: %s; retry in 5s',usb_error)
                    try:device.close()
                    except Exception:pass
                    device=None
                    next_retry=time.monotonic()+5.0
                    force_full=True

            # Do not mark failed transfers as rendered; a reconnect must
            # reinitialize the LCD and send a fresh complete image.
            if did_update:
                previous_marquee_px=marquee_px
                prev_frame=frame
                prev_data_signature=data_signature
                last_hm=hm
                last_seconds=sec
                previous_clock=hm+sec
            if tick-last_status>1.0:
                save_runtime_status(app_version=APP_VERSION,
                                    connected=device is not None if not no_usb else False,
                                    usb_error=usb_error,
                                    last_transfer_ms=last_transfer_ms,
                                    last_transfer_kind=last_transfer_kind,
                                    preview_mode=no_usb,
                                    port=port_name,
                                    clock=hm+(':'+sec if sec else ''),
                                    weather_city=weather.city,
                                    weather_provider=weather.provider,
                                    weather_condition=weather.condition_text or weather_description(weather.code),
                                    weather_status='OK' if weather.error is None else '待機/エラー',
                                    train_status=train.status,
                                    rail_status=rail_notice.text,
                                    rail_status_updated=rail_notice.fetched.isoformat() if rail_notice.fetched else '',
                                    settings_hash=last_settings_hash,
                                    clock_update_mode=conf.get('clock_update_mode','compact'),
                                    **CLOCK.state())
                last_status=tick
            time.sleep(.05)
    finally:
        if device:
            try:device.close()
            except Exception:pass
        pool.shutdown(wait=False,cancel_futures=True)
        logger.info('Stopped; port released')
        # All status lives in RAM; no heartbeat file is left behind.


def main():
    parser=argparse.ArgumentParser(description='TURZX 3.5 live dashboard. User-confirmed Rev A landscape + software 180° rotation.')
    parser.add_argument('--port',default=None,help='COM port override')
    parser.add_argument('--preview',action='store_true',help='Create preview with missing data labels, no USB')
    parser.add_argument('--demo-preview',action='store_true',help='Create fake sample preview, never sends to device')
    parser.add_argument('--no-usb',action='store_true',help='Update preview_480x320.png continuously, no USB')
    parser.add_argument('--seconds',type=int,default=0,help='Run for N seconds then quit (for testing)')
    args=parser.parse_args()
    log_setup();conf=load_settings()
    if args.port:conf['port']=args.port
    logger.info('Weather city: %s, %s/%s',conf['weather_city'],conf['weather_latitude'],conf['weather_longitude'])
    logger.info('Application version: %s; source root: %s; bundle root: %s',APP_VERSION,ROOT,BUNDLE_ROOT)
    logger.info('Train source: %s',conf['train_source'])
    if conf.get('train_source')=='ir_schedule':
        diag=train_diagnostics(jp_now(),conf)
        logger.info('IR timetable diagnostics: source=%s, revision=%s, candidates=%d, error=%s',
                    diag.get('schedule_path'),diag.get('revision'),len(diag.get('trains',[])),diag.get('error'))
    lock=None
    try:
        if not args.preview and not args.demo_preview:
            lock=acquire_singleton_lock()
            if lock is None:
                logger.warning('Another TURZX dashboard instance is already running. Refusing second instance.')
                return 3
        server_context=(nullcontext() if (args.preview or args.demo_preview) else StatusServer())
        with server_context:
            run_dashboard(conf,args.preview,args.demo_preview,args.no_usb,args.seconds)
    except KeyboardInterrupt:
        logger.info('Stopped by Ctrl+C')
    except Exception:
        logger.exception('Application error')
        return 1
    finally:
        release_singleton_lock(lock)
    return 0

if __name__=='__main__':sys.exit(main())
