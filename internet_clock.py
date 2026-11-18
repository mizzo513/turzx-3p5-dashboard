# SPDX-License-Identifier: GPL-3.0-or-later
"""Internet-clock implementation using NTP (RFC 5905) and monotonic time.

NICT primary endpoint: ntp.nict.jp, UDP/123. No system time modification.
When NTP is not available, use the computer clock (explicitly labelled).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import socket
import struct
import time
import threading

JST = timezone(timedelta(hours=9), name='JST')
NTP_EPOCH = 2208988800
NTP_SERVER = 'ntp.nict.jp'
MAX_SYNC_AGE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class NtpSample:
    server: str
    utc_at_receive: float  # Unix seconds corrected using offset calculation
    monotonic_at_receive: float
    rtt_seconds: float
    offset_seconds: float


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


class InternetClock:
    """Monotonic clock anchored to last successful network time synchronization."""
    def __init__(self, max_age_seconds: float=MAX_SYNC_AGE_SECONDS):
        self._lock=threading.RLock()
        self._sample: NtpSample|None = None
        self._max_age=float(max_age_seconds)
        self._error='未同期'

    def accept(self, sample: NtpSample):
        with self._lock:
            self._sample=sample
            self._error=''

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
                return {'time_source':'NTP','ntp_server':s.server,
                        'ntp_age_seconds':int(tick-s.monotonic_at_receive),
                        'ntp_offset_seconds':round(s.offset_seconds,3),'ntp_error':self._error}
            return {'time_source':'PC (NTP未同期)','ntp_server':s.server if s else '',
                    'ntp_age_seconds':None,'ntp_offset_seconds':None,'ntp_error':self._error}
