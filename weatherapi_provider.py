# SPDX-License-Identifier: GPL-3.0-or-later
"""WeatherAPI.com (forecast.json) adapter for the TURZX weather dashboard.

The API's condition code is authoritative for the displayed weather text and
pictogram. The precipitation amount is retained for diagnostics ONLY: it never
changes the condition code or weather description.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import urllib.error
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT='https://api.weatherapi.com/v1/forecast.json'

# WeatherAPI condition_code -> (compact Japanese label, approximate WMO code
# used ONLY for the existing weather pictogram). No rain thresholds are used.
CODE_TO_WEATHER={
    1000:('晴れ',0), 1003:('晴れ時々曇り',2), 1006:('曇り',3), 1009:('くもり',3),
    1030:('もや',45),
    1063:('所により雨',80), 1066:('所により雪',71), 1069:('みぞれの可能性',66),
    1072:('霧雨の可能性',51), 1087:('雷の可能性',95),
    1114:('吹雪',73), 1117:('暴風雪',75),
    1135:('霧',45), 1147:('着氷性の霧',48),
    1150:('弱い霧雨',51), 1153:('霧雨',53), 1168:('着氷性霧雨',56),
    1171:('強い霧雨',57),
    1180:('所により小雨',61), 1183:('小雨',61),
    1186:('時々雨',63), 1189:('雨',63),
    1192:('時々強い雨',65), 1195:('大雨',65),
    1198:('着氷性の雨',66), 1201:('強い着氷性雨',67),
    1204:('弱いみぞれ',66), 1207:('強いみぞれ',67),
    1210:('所により小雪',71), 1213:('小雪',71),
    1216:('時々雪',73), 1219:('雪',73),
    1222:('時々大雪',75), 1225:('大雪',75),
    1237:('あられ',77),
    1240:('弱いにわか雨',80), 1243:('強いにわか雨',81),
    1246:('激しいにわか雨',82),
    1249:('弱いみぞれ雨',66), 1252:('強いみぞれ雨',67),
    1255:('弱いにわか雪',85), 1258:('強いにわか雪',86),
    1261:('弱いあられ',77), 1264:('強いあられ',77),
    1273:('雷雨',95), 1276:('強い雷雨',96),
    1279:('雷雪',95), 1282:('強い雷雪',99),
}


class WeatherAPIError(ValueError):
    """Client-safe WeatherAPI message without a URL (which contains the key)."""


def _number(value):
    try:return float(value) if value is not None else None
    except (TypeError,ValueError):return None


def _integer(value):
    try:return int(round(float(value))) if value is not None else None
    except (TypeError,ValueError):return None


def _check_error(doc):
    if not isinstance(doc,dict):
        raise WeatherAPIError('WeatherAPIの応答形式が不正です')
    info=doc.get('error')
    if not info:return
    code=info.get('code') if isinstance(info,dict) else None
    msgs={
        1002:'APIキーが指定されていません',
        2006:'APIキーが無効です',
        2007:'WeatherAPIの利用回数上限です',
        2008:'WeatherAPIの利用が制限されています',
        1003:'検索地点が指定されていません',
        1005:'APIリクエストが不正です',
        1006:'地点が見つかりません',
        2009:'現在の契約では利用できない機能です',
    }
    raise WeatherAPIError(msgs.get(code,f'WeatherAPIエラー (code={code or "unknown"})'))


def parse_forecast(doc, city, *, fetched=None):
    """Return normalized fields without importing the dashboard module."""
    _check_error(doc)
    current=doc.get('current')
    day_list=(doc.get('forecast') or {}).get('forecastday') or []
    if not isinstance(current,dict) or not isinstance(day_list,list) or not day_list:
        raise WeatherAPIError('WeatherAPIの現在天候・日別予報がありません')
    day=day_list[0].get('day') if isinstance(day_list[0],dict) else None
    cond=current.get('condition')
    if not isinstance(day,dict) or not isinstance(cond,dict):
        raise WeatherAPIError('WeatherAPIの天気コードまたは日別予報がありません')
    code=_integer(cond.get('code'))
    if code is None:
        raise WeatherAPIError('WeatherAPIの天気コードがありません')
    label,wmo=CODE_TO_WEATHER.get(code,(str(cond.get('text') or '天候不明')[:12],None))
    fetched=fetched or datetime.now(timezone.utc)
    updated=current.get('last_updated_epoch')
    try:
        data_time=datetime.fromtimestamp(int(updated),tz=timezone.utc) if updated is not None else None
    except (OSError,ValueError,OverflowError,TypeError):
        data_time=None
    # WeatherAPI wind_kph is km/h; dashboard expects m/s.
    wind_kph=_number(current.get('wind_kph'))
    return dict(
        city=str(city),
        temperature=_number(current.get('temp_c')),
        high=_number(day.get('maxtemp_c')),
        low=_number(day.get('mintemp_c')),
        precip=_integer(day.get('daily_chance_of_rain')),
        humidity=_integer(current.get('humidity')),
        wind=wind_kph/3.6 if wind_kph is not None else None,
        code=wmo,
        condition_text=label,
        raw_condition_code=code,
        precip_mm=_number(current.get('precip_mm')),
        provider='weatherapi',
        data_time=data_time,
        fetched=fetched,
        error=None,
    )


def fetch_weatherapi(conf, opener=urlopen, *, fetched=None):
    key=str(conf.get('weatherapi_key') or '').strip()
    if not key:
        raise WeatherAPIError('WeatherAPIのAPIキーが未設定です（設定画面で入力してください）')
    q=f"{float(conf['weather_latitude']):.6f},{float(conf['weather_longitude']):.6f}"
    params={'key':key,'q':q,'days':1,'aqi':'no','alerts':'no','lang':'ja'}
    request=Request(ENDPOINT+'?'+urlencode(params),
                    headers={'User-Agent':'TURZX-Dashboard/WeatherAPI','Accept':'application/json'})
    try:
        with opener(request,timeout=12) as response:
            doc=json.load(response)
    except urllib.error.HTTPError as exc:
        # Avoid printing the request URL: it contains the private API key.
        if exc.code in (401,403):
            raise WeatherAPIError('WeatherAPIのAPIキー・権限を確認してください') from None
        if exc.code==429:
            raise WeatherAPIError('WeatherAPIの利用回数上限に達しました') from None
        raise WeatherAPIError(f'WeatherAPIとの通信に失敗しました (HTTP {exc.code})') from None
    except urllib.error.URLError:
        raise WeatherAPIError('WeatherAPIへのネットワーク接続に失敗しました') from None
    return parse_forecast(doc,conf.get('weather_city','白山市'),fetched=fetched)
