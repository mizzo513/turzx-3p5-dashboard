# -*- coding: utf-8 -*-
"""Conservative current-weather fusion: verified precipitation > nearby gauge > model.

Never claim a dry observation from blank radar pixels. Forecast hourly and daily
values are left untouched; only current condition icon/label is replaced.
"""
from __future__ import annotations
import datetime as dt
import math
from dataclasses import dataclass

UTC = dt.timezone.utc


@dataclass(frozen=True)
class CurrentWeather:
    code: int
    label: str
    source: str
    observed_at: str = ''
    note: str = ''


def _num(value):
    try:
        val = float(value)
        return val if math.isfinite(val) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _recent(time_text, now, limit_minutes):
    try:
        stamp = dt.datetime.fromisoformat(time_text)
        if stamp.tzinfo is None:
            return False
        if now is None:
            now = dt.datetime.now(UTC)
        if now.tzinfo is None:
            return False
        seconds = (now.astimezone(UTC) - stamp.astimezone(UTC)).total_seconds()
        return -300 <= seconds <= 60 * limit_minutes
    except (TypeError, ValueError, AttributeError):
        return False



def weather_kind(code):
    """WMO category mapping shared with the sister desktop weather widget."""
    try: code=int(code)
    except (TypeError,ValueError): return 'cloud'
    if code in (0,1): return 'sun'
    if code==2: return 'partly'
    if code in (3,45,48): return 'cloud'
    if code in (51,53,55,56,57,61,63,65,66,67,80,81,82): return 'rain'
    if code in (71,73,75,77,85,86): return 'snow'
    if code in (95,96,99): return 'storm'
    return 'cloud'


def weather_label(code):
    kind=weather_kind(code)
    if code==0:return '快晴'
    return {'sun':'晴れ','partly':'晴れ時々曇り','cloud':'曇り・霧',
            'rain':'雨','snow':'雪','storm':'雷雨'}[kind]


def decide_current_weather(forecast, observations=None, now=None):
    model = (forecast or {}).get('current') or {}
    code = model.get('weather_code', 3)
    try:
        code = int(code)
    except (ValueError, TypeError):
        code = 3
    if code not in range(100):
        code = 3
    observations = observations or {}
    radar = observations.get('radar') or {}
    amedas = observations.get('amedas') or {}
    model_snow = _num(model.get('snowfall'))
    model_rain = max((_num(model.get(k)) or 0) for k in ('precipitation', 'rain', 'showers'))
    model_snowing = weather_kind(code) == 'snow' or (model_snow is not None and model_snow > 0)

    level = radar.get('level')
    if isinstance(level, int) and 1 <= level <= 8 and _recent(radar.get('observed_at'), now, 30):
        is_snow = model_snowing
        return CurrentWeather(71 if is_snow else 61, '雪(実況)' if is_snow else '雨(実況)',
                              '気象庁 降水ナウキャスト', radar['observed_at'],
                              f'降水強度：凡例 {level}/8。雨雪の区分は予報による推定')

    station_rain = _num(amedas.get('precipitation10m'))
    distance = _num(amedas.get('distance_km'))
    if (station_rain is not None and station_rain >= 0.1 and
            distance is not None and distance <= 12 and
            _recent(amedas.get('observed_at'), now, 35)):
        is_snow = model_snowing
        name = '雪' if is_snow else '雨'
        label = f'{name}(周辺)' if distance > 3 else f'{name}(観測)'
        return CurrentWeather(71 if is_snow else 61, label,
                              '気象庁 アメダス', amedas['observed_at'],
                              f'{amedas.get("station", "観測所")}：直近10分 {station_rain:g}mm、地点から約{distance:g}km')

    # If forecast indicates precipitation, do not suppress it based on no echo.
    if model_snowing:
        return CurrentWeather(71, '雪', 'Open-Meteo (予報モデル)')
    if model_rain >= 0.1 or weather_kind(code) in ('rain', 'storm'):
        if weather_kind(code) == 'storm':
            return CurrentWeather(95, '雷雨', 'Open-Meteo (予報モデル)')
        return CurrentWeather(61, '雨', 'Open-Meteo (予報モデル)')

    # Sun duration is a nearby observed proxy; only use it at very close range.
    sunshine = _num(amedas.get('sun10m'))
    is_day = model.get('is_day') in (1, True)
    if (is_day and sunshine is not None and sunshine >= 8 and
            distance is not None and distance <= 5 and
            _recent(amedas.get('observed_at'), now, 35)):
        return CurrentWeather(0, '晴れ(観測)', '気象庁 アメダス', amedas['observed_at'],
                              f'{amedas.get("station", "観測所")}：直近10分 日照 {sunshine:g}分、地点から約{distance:g}km')

    # Cloud cover provides a smoother now-condition than categorical WMO code.
    cloud = _num(model.get('cloud_cover'))
    if code in (45, 48):
        return CurrentWeather(code, '曇り・霧', 'Open-Meteo (予報モデル)')
    if cloud is not None:
        if cloud < 20:
            return CurrentWeather(0, '晴れ', 'Open-Meteo (雲量推定)')
        if cloud < 75:
            return CurrentWeather(2, '晴れ時々曇り', 'Open-Meteo (雲量推定)')
        return CurrentWeather(3, '曇り', 'Open-Meteo (雲量推定)')
    return CurrentWeather(code, weather_label(code), 'Open-Meteo (天気コード)')
