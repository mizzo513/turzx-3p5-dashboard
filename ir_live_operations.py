# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only IR official live train positions and delays.

IR's public ishi-train page uses /api/v1/trains. This module reads the
same JSON displayed by the official page; it does not scrape pixels or
claim the absence of a train means cancellation or departure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.request import Request, urlopen

ENDPOINT = 'https://www.ishikawa-railway.jp/api/v1/trains'
MAX_BYTES = 256_000
TIMEOUT_SECONDS = 6
# Captured feed in 2026-11 has @dct:valid 30 seconds after @dc:date.
# Small grace for server-side cache/retrieval timing, never indefinite reuse.
VALIDITY_GRACE_SECONDS = 45
# IR line west -> east. Station tokens are from /api/v1/definitions.
WEST_EAST_STATIONS = (
    'Daishoji', 'Kagaonsen', 'Iburihashi', 'Awazu', 'Komatsu',
    'Meiho', 'Nomi-Neagari', 'Komaiko', 'Mikawa', 'Kaga-Kasama',
    'Nishi-Matto', 'Matto', 'Nonoichi', 'Nishi-Kanazawa', 'Kanazawa',
    'Higashi-Kanazawa', 'Morimoto', 'Tsubata', 'Kurikara',
)
INDEX = {s: i for i, s in enumerate(WEST_EAST_STATIONS)}
STOP_NAMES = {
    '大聖寺':'Daishoji', '加賀温泉':'Kagaonsen', '動橋':'Iburihashi',
    '粟津':'Awazu', '小松':'Komatsu', '明峰':'Meiho',
    '能美根上':'Nomi-Neagari', '小舞子':'Komaiko', '美川':'Mikawa',
    '加賀笠間':'Kaga-Kasama', '西松任':'Nishi-Matto', '松任':'Matto',
    '野々市':'Nonoichi', '西金沢':'Nishi-Kanazawa', '金沢':'Kanazawa',
    '東金沢':'Higashi-Kanazawa', '森本':'Morimoto', '津幡':'Tsubata',
    '倶利伽羅':'Kurikara',
}
TRAIN_RE = re.compile(r'^0*([0-9]{1,6})([A-Z]{1,3})$')


def normalize_train_number(number):
    value = str(number or '').strip().upper()
    match = TRAIN_RE.fullmatch(value)
    if match:
        return str(int(match.group(1))) + match.group(2)
    return value


def station_code(value):
    if not isinstance(value,str) or value.lower()=='null':
        return ''
    if not value.startswith('odpt.Station:'):
        return ''
    return value.rsplit('.',1)[-1]


def parse_time(value):
    if not isinstance(value,str) or not value:
        raise ValueError('列車情報に有効期限/観測時刻がありません')
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('列車情報の時刻にタイムゾーンがありません')
    return stamp


@dataclass(frozen=True)
class LiveTrain:
    number: str
    observed: datetime
    valid_until: datetime
    delay: int | None
    direction: str
    at_station: str
    to_station: str
    origin: str
    destination: str

    def fresh_at(self, now):
        if now.tzinfo is None:
            return False
        if self.observed.astimezone(timezone(timedelta(hours=9))).date() != now.astimezone(timezone(timedelta(hours=9))).date():
            return False
        if self.observed > now + timedelta(seconds=60):
            return False
        if self.valid_until < self.observed:
            return False
        return now <= self.valid_until + timedelta(seconds=VALIDITY_GRACE_SECONDS)


@dataclass(frozen=True)
class LiveTrainState:
    trains: tuple[LiveTrain,...] = ()
    fetched: datetime | None = None
    error: str = ''

    def current_matches(self, number, now):
        wanted = normalize_train_number(number)
        matches = [r for r in self.trains
                   if normalize_train_number(r.number)==wanted and r.fresh_at(now)]
        # Ambiguous duplicate numbers are never used to assert a train status.
        return matches[0] if len(matches)==1 else None

    def fresh_count(self, now):
        return sum(record.fresh_at(now) for record in self.trains)


def parse_live_feed(document, fetched=None):
    if not isinstance(document,list):
        raise ValueError('IR在線情報が配列ではありません')
    if len(document)>400:
        raise ValueError('IR在線情報の列車数が異常です')
    records=[]
    for row in document:
        if not isinstance(row,dict) or row.get('@type')!='odpt:Train':
            continue
        raw_no=str(row.get('odpt:trainNumber') or '').strip()
        if not TRAIN_RE.fullmatch(raw_no):
            continue
        observed=parse_time(row.get('@dc:date'))
        valid=parse_time(row.get('@dct:valid'))
        raw_delay=row.get('odpt:delay')
        try:
            delay=int(raw_delay) if raw_delay is not None else None
            if delay is not None and not 0<=delay<=1440:
                delay=None
        except (TypeError,ValueError):
            delay=None
        records.append(LiveTrain(
            normalize_train_number(raw_no),observed,valid,delay,
            str(row.get('odpt:railDirection') or ''),
            station_code(row.get('odpt:fromStation')),
            station_code(row.get('odpt:toStation')),
            station_code(row.get('odpt:startingStation')),
            station_code(row.get('odpt:terminalStation')),
        ))
    return LiveTrainState(tuple(records),fetched)


def fetch_live_trains(opener=urlopen):
    """One public HTTP GET, with bounded response size and timeout."""
    req=Request(ENDPOINT,headers={
        'User-Agent':'TURZX-Dashboard/3.9 (personal-use official live train status)',
        'Accept':'application/json'})
    try:
        with opener(req,timeout=TIMEOUT_SECONDS) as response:
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError('IR在線情報の応答が大きすぎます')
        return parse_live_feed(json.loads(raw.decode('utf-8-sig')),
                               datetime.now(timezone.utc))
    except Exception as exc:
        return LiveTrainState(error=f'{type(exc).__name__}: {str(exc)[:140]}')


def _direction(live):
    # Direction in the actual official IR feed:
    # Toyama = east (towards Tsubata); Fukui = west (towards Daishoji).
    if live.direction.endswith('.Toyama'):
        return 1
    if live.direction.endswith('.Fukui'):
        return -1
    if live.origin in INDEX and live.destination in INDEX:
        diff=INDEX[live.destination]-INDEX[live.origin]
        return 1 if diff>0 else -1 if diff<0 else 0
    return 0


def status_for_leg(train_no,boarding,alighting,now,live_state):
    """Return ('正常' | '遅延 N分' | '発車済', '#hex') or None.

    The reference point is the actual *boarding* station, not the transfer
    destination: 加賀笠間 for leg 1 and 金沢 for leg 2.
    """
    if live_state is None:
        return None
    live=live_state.current_matches(train_no,now)
    if live is None:
        return None
    begin=STOP_NAMES.get(boarding)
    end=STOP_NAMES.get(alighting)
    if begin not in INDEX or end not in INDEX:
        return None
    desired=1 if INDEX[end]>INDEX[begin] else -1 if INDEX[end]<INDEX[begin] else 0
    direction=_direction(live)
    if not desired or direction!=desired:
        return None
    at=INDEX.get(live.at_station)
    nxt=INDEX.get(live.to_station) if live.to_station else None
    if at is None:
        return None
    # Avoid treating an impossible backwards/too distant next station as
    # conclusive motion past the platform.
    if nxt is not None and (nxt-at)*desired <= 0:
        return None
    if live.delay is not None and live.delay>0:
        return f'遅延 {live.delay}分','#FAC563'
    if live.delay is None:
        return None
    dist=(at-INDEX[begin])*desired
    if dist>0:
        return '発車済','#9CB9CA'
    if dist==0 and nxt is not None and (nxt-INDEX[begin])*desired>0:
        return '発車済','#9CB9CA'
    # At or approaching the boarding station in the expected direction.
    return '正常','#55E5A2'
