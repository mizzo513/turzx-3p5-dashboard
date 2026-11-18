# -*- coding: utf-8 -*-
"""NICT reachability and time synchronization self-test (no display writes)."""
from datetime import datetime,timezone,timedelta
from internet_clock import query_ntp

if __name__=='__main__':
    try:
        sample=query_ntp()
        local=datetime.fromtimestamp(sample.utc_at_receive,timezone(timedelta(hours=9)))
        print('NICT NTP: OK')
        print('JST:',local.strftime('%Y/%m/%d %H:%M:%S.%f')[:-3])
        print('Offset from PC clock: %.3f seconds'%sample.offset_seconds)
        print('NTP network RTT: %.3f seconds'%sample.rtt_seconds)
    except Exception as exc:
        print('NICT NTP: FAILED:',exc)
        print('Check Internet access and outbound/inbound UDP port 123.')
        raise SystemExit(1)
