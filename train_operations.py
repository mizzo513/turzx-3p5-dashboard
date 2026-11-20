# SPDX-License-Identifier: GPL-3.0-or-later
"""Safely match publicly announced IR train cancellations to displayed legs.

Only public official news pages are fetched, at the existing five-minute
rail-status cadence. These are announcements, not train tracking telemetry.
A train not listed in an announcement is NEVER presumed to run normally.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import re

NEWS_URL='https://www.ishikawa-railway.jp/news/'
HEADERS={'User-Agent':'TURZX-Dashboard/3.9 (personal-use train information)',
         'Accept':'text/html'}
MAX_BODY=512_000
FETCH_TIMEOUT=8
# Relative geography is only used to test overlap of *explicit* stop ranges.
STATIONS=('敦賀','福井','芦原温泉','加賀温泉','小松','加賀笠間',
          '松任','金沢','東金沢','津幡','高松','七尾')
INDEX={s:i for i,s in enumerate(STATIONS)}
STATUS_COLORS={'運休':'#FC7471','遅延':'#FAC563',
               '正常':'#55E5A2','発車前':'#78B8EF',
               '未確認':'#9CB9CA'}


@dataclass(frozen=True)
class OperationRecord:
    train_no: str
    kind: str  # cancelled, delayed, normal (only with explicit per-train proof)
    minutes: int | None = None
    start: str = ''
    end: str = ''
    source_url: str = ''


@dataclass
class TrainOperations:
    items: tuple[OperationRecord,...] = ()
    fetched: datetime | None = None
    error: str = ''


class _NewsLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.href=''
        self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            self.href=dict(attrs).get('href','')
            self.parts=[]
    def handle_data(self,data):
        if self.href:
            self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href:
            self.links.append((self.href,''.join(self.parts).strip()))
            self.href=''
            self.parts=[]


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):
            self.hidden+=1
        elif tag in ('p','br','li','div','section','tr','h1','h2','h3'):
            self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.hidden:
            self.hidden-=1
        elif tag in ('p','li','div','section','tr','h1','h2','h3'):
            self.parts.append(' ')
    def handle_data(self,data):
        if not self.hidden:
            self.parts.append(data)


def _plain(html):
    p=_Text()
    p.feed(html)
    return re.sub(r'\s+',' ',''.join(p.parts)).strip()


def _load(opener,url):
    req=Request(url,headers=HEADERS)
    with opener(req,timeout=FETCH_TIMEOUT) as response:
        raw=response.read(MAX_BODY+1)
        if len(raw)>MAX_BODY:
            raise ValueError('公式記事のサイズが制限を超えました')
        return raw.decode('utf-8','replace')


def official_news_candidates(html):
    p=_NewsLinks()
    p.feed(html)
    found=[]
    for href,title in p.links:
        url=urljoin(NEWS_URL,href)
        if (urlsplit(url).netloc!='www.ishikawa-railway.jp'
                or not re.fullmatch(r'/news/\d+',urlsplit(url).path)
                or not re.search(r'運休|運転取り止め|運転とりやめ|列車運転取り止め',
                                 title)):
            continue
        if url not in found:
            found.append(url)
    return found[:4]


def article_matches_day(text,day):
    # A publication date alone is not sufficient: an article published
    # yesterday may announce today's cancellations. Require the affected
    # date to be explicitly printed in the source body.
    date_string=f'{day.month}月{day.day}日'
    return bool(re.search(r'(?<!\d)'+re.escape(date_string),text))


def _scope(text):
    """Return an unambiguous cancelled segment or all-lines marker."""
    match=re.search(r'[（(]([^()（）]{1,60})[)）]',text)
    if not match:
        return None
    phrase=re.sub(r'\s+','',match.group(1))
    if '全区間' in phrase or '全線' in phrase:
        return ('*','*')
    stops=re.findall(r'([^駅()（）～〜~\-－―間]{1,10})駅',phrase)
    # For fused notation '芦原温泉駅金沢駅間', explicit station
    # boundaries delimit two exact source names.
    if len(stops)>=2:
        a,b=stops[-2:]
        if a in INDEX and b in INDEX:
            return a,b
    return None


def parse_cancelled_article(html,day,url):
    body=_plain(html)
    if not (article_matches_day(body,day)
            and re.search(r'運転取り止め|運休|運転とりやめ',body)):
        return ()
    matches=list(re.finditer(r'(?<![0-9A-Za-z])(\d{2,5}[A-Z])\b',body))
    found=[]
    for i,m in enumerate(matches):
        # A train number with a named affected segment on an official
        # cancellation list is stronger evidence than a route-wide alert.
        following=body[m.end():matches[i+1].start() if i+1<len(matches) else len(body)]
        following=following[:180]
        segment=_scope(following)
        if not segment:
            continue
        found.append(OperationRecord(
            train_no=m.group(1),kind='cancelled',
            start=segment[0],end=segment[1],source_url=url))
    return tuple(found)


def affects_leg(record,start,end):
    if record.start=='*' and record.end=='*':
        return True
    if record.start not in INDEX or record.end not in INDEX:
        return False
    if start not in INDEX or end not in INDEX:
        return False
    a,b=sorted((INDEX[record.start],INDEX[record.end]))
    c,d=sorted((INDEX[start],INDEX[end]))
    return max(a,c)<min(b,d)


def matching_record(operations,train_no,origin,destination):
    for record in getattr(operations,'items',()):
        if record.train_no==str(train_no) and affects_leg(record,origin,destination):
            return record
    return None


def public_train_status(train_no,depart,now,operations=None,
                        origin='加賀笠間',destination='金沢'):
    """Return (caption, color) using only supported train-specific proof.

    Timetable future departures are '発車前' by *schedule*, not by live
    tracking. No reported issue is never translated to '正常'.
    """
    number=str(train_no or '').strip()
    rec=matching_record(operations,number,origin,destination)
    if rec:
        if rec.kind=='cancelled':
            label='運休';color=STATUS_COLORS[label]
        elif rec.kind=='delayed' and rec.minutes is not None and rec.minutes>0:
            label=f'遅延 {rec.minutes}分';color=STATUS_COLORS['遅延']
        elif rec.kind=='normal':
            label='正常';color=STATUS_COLORS[label]
        else:
            label='未確認';color=STATUS_COLORS[label]
    elif depart>now:
        label='発車前';color=STATUS_COLORS[label]
    else:
        label='未確認';color=STATUS_COLORS[label]
    return (number or '列車')+' '+label,color


def fetch_official_train_operations(day=None,opener=urlopen):
    """Fetch recent official IR cancellation announcements, without guesses.

    Failure leaves an empty/unknown status set (and a diagnostic error).
    Never carry yesterday's cancellation to another date.
    """
    from datetime import datetime
    from datetime import timezone as _tz
    day=day or datetime.now().date()
    seen={}
    errors=[]
    try:
        candidates=official_news_candidates(_load(opener,NEWS_URL))
    except Exception as exc:
        return TrainOperations(fetched=datetime.now(_tz.utc),
                               error='記事一覧：'+str(exc)[:130])
    for url in candidates:
        try:
            records=parse_cancelled_article(_load(opener,url),day,url)
            for record in records:
                seen[(record.train_no,record.start,record.end)]=record
        except Exception as exc:
            errors.append(url.rsplit('/',1)[-1]+':'+str(exc)[:90])
    return TrainOperations(tuple(seen.values()),datetime.now(_tz.utc),
                           '; '.join(errors)[:240])
