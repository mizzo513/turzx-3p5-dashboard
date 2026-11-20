# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.19: fix IPC clock formatting and test manual NTP request channel.

No real NTP server, external service, or physical display is needed.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

import runtime_ipc
from internet_clock import InternetClock, NtpSample
from turzx_dashboard import DEFAULTS, TZ, clock_minute_key, datetime_text


class ClockStatusFormattingTests(unittest.TestCase):
    def test_seconds_have_exactly_one_colon_before_them(self):
        now=datetime(2026,11,20,11,3,23,tzinfo=TZ)
        for show_seconds in (False,True):
            for clock_12h in (False,True):
                with self.subTest(seconds=show_seconds,hour12=clock_12h):
                    config=dict(DEFAULTS,show_seconds=show_seconds,
                                clock_12h=clock_12h)
                    minute=clock_minute_key(now,config)
                    status=minute+(':'+now.strftime('%S') if show_seconds else '')
                    self.assertEqual(status,datetime_text(now,config))
                    self.assertNotIn('::',status)
                    if show_seconds:
                        self.assertTrue(status.endswith('11:03:23'))
                    else:
                        self.assertTrue(status.endswith('11:03'))

    def test_minute_key_stays_constant_during_one_minute(self):
        conf=dict(DEFAULTS,show_seconds=True)
        a=datetime(2026,11,20,11,3,1,tzinfo=TZ)
        b=datetime(2026,11,20,11,3,59,tzinfo=TZ)
        c=datetime(2026,11,20,11,4,0,tzinfo=TZ)
        self.assertEqual(clock_minute_key(a,conf),clock_minute_key(b,conf))
        self.assertNotEqual(clock_minute_key(a,conf),clock_minute_key(c,conf))


class ManualNTPChannelTests(unittest.TestCase):
    def test_sync_ntp_ipc_sets_only_manual_event(self):
        # Ephemeral port ensures the test won't bind the app's real port.
        with patch.object(runtime_ipc,'PORT',0):
            server=runtime_ipc.StatusServer()
            with patch.object(runtime_ipc,'PORT',server.server.server_address[1]):
                with server as state:
                    state.update(app_version='test')
                    self.assertFalse(state.ntp_sync_requested.is_set())
                    self.assertTrue(runtime_ipc.request_ntp_sync())
                    self.assertTrue(state.ntp_sync_requested.is_set())
                    self.assertFalse(state.stop_requested.is_set())
                    self.assertFalse(state.reconnect_requested.is_set())
                    self.assertEqual(runtime_ipc.get_runtime_status()['app_version'],'test')
                    state.ntp_sync_requested.clear()
                    self.assertFalse(state.ntp_sync_requested.is_set())
                    self.assertTrue(runtime_ipc.request_ntp_sync())
                    self.assertTrue(state.ntp_sync_requested.is_set())

    def test_clock_accepts_manual_ntp_result_without_changing_system_clock(self):
        # The actual engine uses the same CLOCK.accept as automatic syncing.
        clock=InternetClock()
        sample=NtpSample('ntp.nict.jp',1_700_000_000.0,100.0,0.02,0.15)
        clock.accept(sample)
        self.assertAlmostEqual(clock.current_unix(102.0),1_700_000_002.0)
        self.assertEqual(clock.state(102.0)['time_source'],'NTP')


if __name__=='__main__':
    unittest.main()
