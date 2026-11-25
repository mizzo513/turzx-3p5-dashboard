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


# The station displayed in the public train-position feed is the
# most recently reported station, not a guaranteed proof of passage.
CODE_TO_JP={code:name for name,code in STOP_NAMES.items()}


def inspect_live_leg(train_no, boarding, alighting, scheduled_depart, now, live_state):
    """Explain the official-data verdict for one planned boarding.

    A position beyond the boarding station before the scheduled departure
    conflicts with the timetable. The caller must show 未確認, never 発車済.
    This diagnostic is deliberately pure and usable in the local status UI.
    """
    details={
        'number':normalize_train_number(train_no),
        'boarding':boarding,'alighting':alighting,
        'scheduled_depart':scheduled_depart.isoformat() if scheduled_depart else '',
        'observed':'','valid_until':'','from_station':'',
        'to_station':'','delay_minutes':None,
        'api_status':None,'reason':'照合可能な在線情報なし',
    }
    if live_state is None:
        details['reason']='在線情報をまだ取得していません'
        return details
    if live_state.error:
        details['reason']='在線情報取得失敗: '+live_state.error[:140]
        return details
    candidates=[r for r in live_state.trains if
                normalize_train_number(r.number)==details['number']]
    if not candidates:
        details['reason']='公式の在線一覧に該当列車なし（発車・運休の証拠ではありません）'
        return details
    if len(candidates)!=1:
        details['reason']='列車番号が重複しており位置を特定できません'
        return details
    live=candidates[0]
    details.update({
        'observed':live.observed.isoformat(),
        'valid_until':live.valid_until.isoformat(),
        'from_station':CODE_TO_JP.get(live.at_station,live.at_station or '―'),
        'to_station':CODE_TO_JP.get(live.to_station,live.to_station or '―'),
        'delay_minutes':live.delay,
    })
    if not live.fresh_at(now):
        details['reason']='在線情報の取得時刻または有効期限が不適合'
        return details
    begin=STOP_NAMES.get(boarding)
    end=STOP_NAMES.get(alighting)
    if begin not in INDEX or end not in INDEX:
        details['reason']='乗車駅または降車駅の駅コードを解決できません'
        return details
    desired=1 if INDEX[end]>INDEX[begin] else -1 if INDEX[end]<INDEX[begin] else 0
    direction=_direction(live)
    if not desired or direction!=desired:
        details['reason']='公式の進行方向が予定区間と一致しません'
        return details
    at=INDEX.get(live.at_station)
    nxt=INDEX.get(live.to_station) if live.to_station else None
    if at is None:
        details['reason']='公式の現在駅が不明です'
        return details
    if live.to_station and nxt is None:
        details['reason']='次駅コードが未知のため位置を判定できません'
        return details
    if nxt is not None and (nxt-at)*desired <= 0:
        details['reason']='現在駅と次駅の進行方向が矛盾しています'
        return details

    # Announcement/API delay supersedes the basic normal/passed states;
    # it is still recorded with precise station diagnostics.
    if live.delay is not None and live.delay>0:
        details['api_status']=f'遅延 {live.delay}分'
        details['reason']='公式データの列車別遅延'
        return details
    if live.delay is None:
        details['reason']='遅延分数が未提供'
        return details

    passed=((at-INDEX[begin])*desired>0 or
            (at==INDEX[begin] and nxt is not None and
             (nxt-INDEX[begin])*desired>0))
    if passed:
        if (scheduled_depart is not None and
                (now<scheduled_depart or live.observed<scheduled_depart)):
            details['api_status']='未確認'
            details['reason']='位置は乗車駅通過後を示すが予定発車時刻前（時刻表と矛盾）'
        else:
            details['api_status']='発車済'
            details['reason']='公式位置が乗車駅通過後を示しています'
    else:
        details['api_status']='正常'
        details['reason']=('乗車駅に停車中（次駅への発車記録なし）'
                           if at==INDEX[begin] and nxt is None else
                           '公式位置が乗車駅より手前です')
    return details


def status_for_leg(train_no, boarding, alighting, now, live_state,
                   scheduled_depart=None):
    """Return official position status or None when no reliable evidence."""
    details=inspect_live_leg(train_no,boarding,alighting,
                             scheduled_depart,now,live_state)
    status=details['api_status']
    return (status,{'正常':'#55E5A2','遅延':'#FAC563',
                    '発車済':'#9CB9CA','未確認':'#9CB9CA'
                    }.get(status.split(' ',1)[0],'#9CB9CA')) if status else None
