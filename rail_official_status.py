# SPDX-License-Identifier: GPL-3.0-or-later
"""Read ONLY publicly presented short operation-status summaries from official sites.

IR's public homepage gets its notice from /train_state.json.  JR West's
Japanese site became client-rendered in January 2026, so its *official*
English-language Hokuriku page provides the visible Nanao-line text.  No
unpublished API, private JSON endpoint, page automation, or other provider is
used.  Unknown/error NEVER means normal service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import json
import re

IR_DATA_URL='https://www.ishikawa-railway.jp/train_state.json'
IR_PAGE_URL='https://www.ishikawa-railway.jp/ishi-train/'
JR_HOKURIKU_URL='https://global.trafficinfo.westjr.co.jp/en/hokuriku'
JR_PAGE_URL='https://trafficinfo.westjr.co.jp/?areaId=1'
MAX_BODY=512_000
TIMEOUT=9
REQUEST_HEADERS={
    'User-Agent':'TURZX-Dashboard/3.9 (personal status display; public web pages)',
    'Accept':'text/html,application/json;q=0.9',
}
ROUTE=['大聖寺','加賀温泉','動橋','粟津','小松','明峰','能美根上','小舞子','美川',
       '加賀笠間','西松任','松任','野々市','西金沢','金沢','東金沢','森本','津幡','倶利伽羅']
ROUTE_START=ROUTE.index('加賀笠間')
ROUTE_END=ROUTE.index('津幡')
STATION_PATTERN=r'(?:'+('|'.join(map(re.escape,sorted(ROUTE,key=len,reverse=True))))+r')'
RANGE_PATTERN=re.compile(
    '('+STATION_PATTERN+r')\s*(?:駅)?\s*[〜～~\-－―]\s*('+STATION_PATTERN+r')\s*(?:駅)?'
)


@dataclass(frozen=True)
class LineInfo:
    label: str
    state: str = '未確認'  # normal / impacted / irrelevant / unknown
    detail: str = ''


@dataclass(frozen=True)
class RailNotice:
    text: str = '運行情報：取得中'
    ir: LineInfo = LineInfo('IR')
    nanao: LineInfo = LineInfo('七尾線')
    fetched: datetime | None = None


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.skip=0

    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'):
            self.skip+=1
        elif tag in ('div','p','li','tr','h1','h2','h3','br'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script','style','noscript') and self.skip:
            self.skip-=1
        elif tag in ('div','p','li','tr','h1','h2','h3'):
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(html):
    parser=_VisibleHTML()
    parser.feed(html)
    return re.sub(r'\s+',' ',''.join(parser.parts)).strip()


def _short(text, limit=90):
    return re.sub(r'\s+',' ',str(text or '')).strip()[:limit]


def affects_ir_route(message):
    """Only report a specific impact when a segment touches 加賀笠間〜津幡."""
    if re.search(r'全線|全区間|全列車|IRいしかわ鉄道線全体',message):
        return True
    for a,b in RANGE_PATTERN.findall(message):
        i,j=ROUTE.index(a),ROUTE.index(b)
        if max(min(i,j),ROUTE_START)<=min(max(i,j),ROUTE_END):
            return True
    # Explicitly named stations within the user's route are direct evidence.
    return any(name in message for name in ROUTE[ROUTE_START:ROUTE_END+1])


def parse_ir(data):
    """Parse the exact public /train_state.json fields used by the official site."""
    entry=data.get('train_state') if isinstance(data,dict) else None
    if not isinstance(entry,dict):
        return LineInfo('IR')
    status=str(entry.get('status') or '').strip()
    title=_short(entry.get('title'),160)
    if not title:
        return LineInfo('IR')
    if re.search(r'平常どおり|平常運転|通常どおり|遅れはありません',title):
        return LineInfo('IR','normal','平常')
    if affects_ir_route(title):
        # Display short descriptive fragment, not the original full notice.
        kind=('運転見合わせ' if re.search('運転見合わせ|運転を見合わせ',title)
              else '運休' if '運休' in title or '取り止め' in title
              else '遅延' if re.search('遅れ|遅延',title)
              else '運行情報')
        return LineInfo('IR','impacted','IR：'+kind+'（'+_short(title,85)+'）')
    # The source reports an issue, but its own text does not identify our
    # section. Avoid an out-of-route false alarm and do NOT mark normal.
    return LineInfo('IR','unknown','IR：影響区間未確認')


NANAO_RE=re.compile(r'\bNanao\s+Line\b',re.I)
OTHER_LINE_RE=re.compile(r'\b(?:Hokuriku|Obama|Himi|Takayama|Oito|Johanna|Etsumi-Hoku|Kuzuryu)\s+Line\b',re.I)
NORMAL_RE=re.compile(r'\b(?:Normal\s+(?:Service|Operation)|Operating\s+Normally|No\s+(?:Disruptions|Delays))\b',re.I)
IMPACT_RE=re.compile(r'(?i)Delay|Suspension|Suspended|Cancellation|Cancelled|Cancell?ed|Disruption|Resum|Storm|Strong Wind')
TRANSLATED={'Tsubata':'津幡','Kanazawa':'金沢','Wakuraonsen':'和倉温泉',
            'Hakui':'羽咋','Nanao':'七尾','Takamatsu':'高松','Nakanoto':'中能登'}


def parse_nanao(html):
    """Use the official English Hokuriku line's visible text.

    JR's Japanese page is JS-rendered; the official multilingual site sends
    translated, visible public text in initial HTML. A generic Nanao incident
    outside Tsubata is deliberately NOT shown as affecting the chosen route.
    """
    content=plain_text(html)
    matches=list(NANAO_RE.finditer(content))
    if not matches:
        return LineInfo('七尾線')
    impacted=[]
    saw_normal=False
    saw_other=False
    for match in matches[:8]:
        chunk=content[match.end():match.end()+430]
        # Each public status card ends in "more". Exclude the automatic
        # translation disclaimer and subsequent unrelated lines.
        chunk=re.split(r'\bmore\b|This information has been translated|【',chunk,
                       maxsplit=1,flags=re.I)[0]
        next_line=OTHER_LINE_RE.search(chunk)
        if next_line:
            chunk=chunk[:next_line.start()]
        if NORMAL_RE.search(chunk[:75]):
            saw_normal=True
            continue
        if not IMPACT_RE.search(chunk[:190]):
            continue
        section=re.search(
            r'(?i)\bBetween\s+([A-Za-z\- ]{2,28}?)\s+and\s+([A-Za-z\- ]{2,30}?)\s+(?:Cause|more|$)',
            chunk)
        starts_tsubata=bool(re.search(r'(?i)\bTsubata\b',chunk[:250]))
        entire=bool(re.search(r'(?i)(Entire|Whole|All)\s+(?:Nanao\s+)?Line',chunk))
        if not starts_tsubata and not entire and not re.search(r'(?i)\bKanazawa\b',chunk[:250]):
            saw_other=True
            continue
        tomorrow=bool(re.search(r'\bTomorrow\b',chunk[:110],re.I))
        if re.search(r'(?i)Possibility|Possibly|May\s+be\s+Suspended',chunk):
            kind='運休の可能性'
        elif re.search(r'(?i)Resum',chunk):
            kind='運転再開'
        elif re.search(r'(?i)Delay',chunk):
            kind='遅延'
        elif re.search(r'(?i)Cancel',chunk):
            kind='運休'
        else:
            kind='運転見合わせ'
        info=('明日 ' if tomorrow else '')+kind
        if section:
            a,b=(section.group(1).strip(),section.group(2).strip())
            translated=lambda v:next((ja for en,ja in TRANSLATED.items()
                                     if en.lower()==v.lower()),v)
            info+='（'+translated(a)+'～'+translated(b)+'）'
        if re.search(r'\bStrong\s+Wind\b',chunk,re.I):
            info+='・強風'
        elif re.search(r'\bHeavy\s+Rain\b',chunk,re.I):
            info+='・大雨'
        formatted='七尾線：'+_short(info,90)
        if formatted not in impacted:
            impacted.append(formatted)
    if impacted:
        return LineInfo('七尾線','impacted',' / '.join(impacted[:2]))
    if saw_normal:
        return LineInfo('七尾線','normal','平常')
    if saw_other:
        return LineInfo('七尾線','irrelevant','対象区間外の情報のみ')
    return LineInfo('七尾線')


def combine(ir, nanao, fetched=None):
    notifications=[item.detail for item in (ir,nanao) if item.state=='impacted']
    if notifications:
        msg='　｜　'.join(notifications)
    else:
        # Don't falsely announce normal if either source is not confirmed.
        labels=[]
        for item in (ir,nanao):
            labels.append(f'{item.label}：'+
                          ('平常' if item.state=='normal' else
                           '対象区間の障害情報なし' if item.state=='irrelevant'
                           else '未確認'))
        msg='　/　'.join(labels)
    return RailNotice(text=msg,ir=ir,nanao=nanao,
                      fetched=fetched or datetime.now(timezone.utc))


def _read(opener,url):
    req=Request(url,headers=REQUEST_HEADERS)
    with opener(req,timeout=TIMEOUT) as response:
        raw=response.read(MAX_BODY+1)
        if len(raw)>MAX_BODY:
            raise ValueError('Rail operation page exceeds size limit')
        charset=response.headers.get_content_charset() if hasattr(response,'headers') else None
        return raw.decode(charset or 'utf-8','replace')


def fetch_official_rail_notice(opener=urlopen, *, fetched=None):
    """Attempt each independent official source; keep the other's result on failure."""
    try:
        ir=parse_ir(json.loads(_read(opener,IR_DATA_URL)))
    except Exception:
        ir=LineInfo('IR')
    try:
        nanao=parse_nanao(_read(opener,JR_HOKURIKU_URL))
    except Exception:
        nanao=LineInfo('七尾線')
    return combine(ir,nanao,fetched=fetched)
