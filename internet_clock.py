# SPDX-License-Identifier: GPL-3.0-or-later
"""Internet clock: prefer NTP, fall back to HTTPS, then PC clock.

NICT NTP uses UDP/123; TimeAPI.io uses TLS over TCP/443. Both accepted
samples anchor the display clock to time.monotonic(). Neither path sets
the operating system's clock.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import socket
import struct
import time
import threading
import json
from urllib.request import Request, urlopen

JST = timezone(timedelta(hours=9), name='JST')
NTP_EPOCH = 2208988800
NTP_SERVER = 'ntp.nict.jp'
MAX_SYNC_AGE_SECONDS = 6 * 3600
HTTPS_TIME_URL = 'https://timeapi.io/api/Time/current/zone?timeZone=Asia/Tokyo'
HTTPS_MAX_BYTES = 8192


@dataclass(frozen=True)
class NtpSample:
    server: str
    utc_at_receive: float  # Unix seconds corrected using offset calculation
    monotonic_at_receive: float
    rtt_seconds: float
    offset_seconds: float
    source: str = 'NTP'  # HTTPS uses the same monotonic sample representation
    estimated_error_seconds: float | None = None


def _encode_ntp_timestamp(unix_time: float) -> bytes:
    ntp = unix_time + NTP_EPOCH
    sec = int(ntp)
    frac = int((ntp - sec) * 2**32)
    return struct.pack('!II', sec % 2**32, frac)


def _decode_ntp_timestamp(raw: bytes, reference_unix: float) -> float:
    sec,frac = struct.unpack('!II',raw)
    # Select the NTP era nearest the client's coarse current year.
    era = round((reference_unix + NTP_EPOCH - sec)/(2**32))
    return (sec + era*2**32 - NTP_EPOCH) + frac/2**32


def decode_reply(data: bytes, sent_stamp: bytes, client_sent: float,
                 client_received: float, server: str, mono_received: float) -> NtpSample:
    """Validate the NTP reply and calculate the current UTC at arrival.

    Does not trust an uncorrelated UDP reply or a server reporting unsynchronized state.
    """
    if len(data) < 48:
        raise ValueError('NTP応答が短すぎます')
    li = (data[0] >> 6) & 0x3
    version = (data[0] >> 3) & 0x7
    mode = data[0] & 0x7
    stratum = data[1]
    if li == 3 or mode not in (4, 5) or version not in (3, 4) or not 1 <= stratum <= 15:
        raise ValueError('NTPサーバーが有効な同期時刻を返していません')
    if data[24:32] != sent_stamp:
        raise ValueError('NTP応答のリクエスト照合に失敗しました')
    t2 = _decode_ntp_timestamp(data[32:40], client_sent)
    t3 = _decode_ntp_timestamp(data[40:48], client_sent)
    if t2 <= 0 or t3 <= 0 or t3 < t2 or data[40:48] == bytes(8):
        raise ValueError('NTP応答のタイムスタンプが不正です')
    rtt = (client_received - client_sent) - (t3 - t2)
    if not -0.10 <= rtt <= 5.0:
        raise ValueError(f'NTP往復遅延の異常値: {rtt:.3f}s')
    offset = ((t2 - client_sent) + (t3 - client_received)) / 2.0
    return NtpSample(server, client_received + offset, mono_received, max(0.0,rtt), offset)


def query_ntp(server: str=NTP_SERVER, timeout: float=2.5) -> NtpSample:
    """Perform one bounded UDP NTP request without changing the PC clock."""
    if not (isinstance(server,str) and server.strip() and len(server) <= 253):
        raise ValueError('NTPサーバー名が不正です')
    server=server.strip()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.settimeout(timeout)
        udp.connect((server, 123))
        t1 = time.time()
        stamp=_encode_ntp_timestamp(t1)
        packet=bytearray(48)
        packet[0]=0x23  # version 4 / client mode 3
        packet[40:48]=stamp
        sent_mono=time.monotonic()
        udp.send(packet)
        received=udp.recv(512)
        got_mono=time.monotonic()
    # Use monotonic duration for t4 so local clock changes during the request
    # cannot corrupt the offset estimate.
    t4=t1+(got_mono-sent_mono)
    return decode_reply(received,stamp,t1,t4,server,got_mono)


class TimeSyncError(RuntimeError):
    """Both external time sources failed; include independently useful causes."""
    def __init__(self, ntp_error: str, https_error: str):
        self.ntp_error = ntp_error
        self.https_error = https_error
        super().__init__(
            'NTP: ' + ntp_error + ' / HTTPS: ' + https_error)


def query_https_time(opener=urlopen, *, timeout: float=5.0) -> NtpSample:
    """Get actual server-provided JST time via HTTPS; no browser/OCR needed.

    The server's timestamp is assumed to represent approximately the request
    midpoint, so adding half the round-trip time estimates the time at
    receipt. The RTT/2 figure is a rough network uncertainty indicator,
    NOT a guaranteed clock accuracy bound or an NTP-equivalent precision.
    """
    request=Request(HTTPS_TIME_URL,headers={
        'Accept':'application/json',
        'User-Agent':'TURZX-Dashboard/3.9 (clock fallback)'})
    sent_unix=time.time()
    sent_mono=time.monotonic()
    with opener(request,timeout=timeout) as response:
        payload=response.read(HTTPS_MAX_BYTES+1)
    received_mono=time.monotonic()
    if len(payload)>HTTPS_MAX_BYTES:
        raise ValueError('HTTPS時刻応答が大きすぎます')
    try:
        doc=json.loads(payload)
        if not isinstance(doc,dict) or str(doc.get('timeZone',''))!='Asia/Tokyo':
            raise ValueError('HTTPS時刻のタイムゾーンが不正です')
        value=str(doc['dateTime'])
        server_time=datetime.fromisoformat(value.replace('Z','+00:00'))
        if server_time.tzinfo is None:
            # TimeAPI.io zone endpoint returns naive wall time in requested TZ.
            server_time=server_time.replace(tzinfo=JST)
        unix=server_time.timestamp()
        if not 1_577_836_800 < unix < 4_102_444_800:  # years 2020..2100
            raise ValueError('HTTPS時刻が有効範囲外です')
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('HTTPS時刻の応答形式が不正です') from exc
    rtt=max(0.0,received_mono-sent_mono)
    at_receive=unix+rtt*0.5
    # Estimate offset against a monotonic-relative local clock. It is used
    # only for display diagnostics; system time is never modified.
    local_at_receive=sent_unix+rtt
    return NtpSample(
        server='timeapi.io', utc_at_receive=at_receive,
        monotonic_at_receive=received_mono, rtt_seconds=rtt,
        offset_seconds=at_receive-local_at_receive,
        source='HTTPS', estimated_error_seconds=rtt*0.5)


def query_time_with_fallback(server: str=NTP_SERVER, *,
                             ntp_timeout: float=2.5,
                             https_timeout: float=5.0,
                             ntp_query=None, https_query=None):
    """Try NTP then HTTPS. Return (sample, ntp_failure_reason).

    Dependency injection makes both network failure paths testable offline
    without weakening the actual connection policy.
    """
    if ntp_query is None:
        ntp_query=query_ntp
    if https_query is None:
        https_query=query_https_time
    try:
        return ntp_query(server,ntp_timeout),''
    except Exception as ntp_exc:
        ntp_error=str(ntp_exc) or type(ntp_exc).__name__
    try:
        return https_query(timeout=https_timeout),ntp_error
    except Exception as https_exc:
        https_error=str(https_exc) or type(https_exc).__name__
        raise TimeSyncError(ntp_error,https_error) from https_exc


class InternetClock:
    """Monotonic clock anchored to last successful network time synchronization."""
    def __init__(self, max_age_seconds: float=MAX_SYNC_AGE_SECONDS):
        self._lock=threading.RLock()
        self._sample: NtpSample|None = None
        self._max_age=float(max_age_seconds)
        self._error='未同期'

    def accept(self, sample: NtpSample, *, fallback_reason: str=''):
        with self._lock:
            self._sample=sample
            self._error=str(fallback_reason)[:160] if fallback_reason else ''

    def failed(self, error: str):
        with self._lock:
            self._error=str(error)[:160]

    def current_unix(self, monotonic_value=None):
        tick=time.monotonic() if monotonic_value is None else monotonic_value
        with self._lock:
            s=self._sample
            if s is not None and 0 <= tick-s.monotonic_at_receive < self._max_age:
                return s.utc_at_receive + tick-s.monotonic_at_receive
        return time.time()

    def now_jst(self):
        return datetime.fromtimestamp(self.current_unix(), JST)

    def state(self, monotonic_value=None):
        tick=time.monotonic() if monotonic_value is None else monotonic_value
        with self._lock:
            s=self._sample
            if s is not None and 0 <= tick-s.monotonic_at_receive < self._max_age:
                return {'time_source':s.source,'ntp_server':s.server,
                        'ntp_age_seconds':int(tick-s.monotonic_at_receive),
                        'ntp_offset_seconds':round(s.offset_seconds,3),
                        'ntp_error':self._error,
                        'time_sync_rtt_ms':round(s.rtt_seconds*1000,1),
                        'time_estimated_error_ms':(
                            round(s.estimated_error_seconds*1000,1)
                            if s.estimated_error_seconds is not None else None)}
            return {'time_source':'PC (NTP未同期)','ntp_server':s.server if s else '',
                    'ntp_age_seconds':None,'ntp_offset_seconds':None,
                    'ntp_error':self._error,
                    'time_sync_rtt_ms':None,'time_estimated_error_ms':None}
