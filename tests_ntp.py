# -*- coding: utf-8 -*-
"""No-network tests for V3.6.2 Internet Clock."""
import unittest
import struct
import copy
from datetime import datetime
from unittest.mock import patch
import internet_clock as n
import turzx_dashboard as d


class InternetTimeTests(unittest.TestCase):
    def make_reply(self, t1, sent, t2, t3, *, li=0, mode=4, version=4, stratum=1):
        payload=bytearray(48)
        payload[0]=(li<<6)|(version<<3)|mode
        payload[1]=stratum
        payload[24:32]=sent
        payload[32:40]=n._encode_ntp_timestamp(t2)
        payload[40:48]=n._encode_ntp_timestamp(t3)
        return bytes(payload)

    def test_ntp_delta_against_bad_pc_clock(self):
        t1=1730000000.0
        sent=n._encode_ntp_timestamp(t1)
        # PC is 2 minutes behind the real time.
        packet=self.make_reply(t1,sent,t1+120.04,t1+120.05)
        got=n.decode_reply(packet,sent,t1,t1+0.12,'ntp.nict.jp',300.0)
        self.assertAlmostEqual(got.offset_seconds,119.985,places=3)
        self.assertAlmostEqual(got.utc_at_receive,t1+120.105,places=3)
        c=n.InternetClock()
        c.accept(got)
        self.assertAlmostEqual(c.current_unix(303.5),got.utc_at_receive+3.5,places=4)
        self.assertEqual(c.state(303.5)['time_source'],'NTP')

    def test_ntp_timestamp_fraction(self):
        x=1740000000.1234
        self.assertAlmostEqual(n._decode_ntp_timestamp(n._encode_ntp_timestamp(x),x),x,places=6)

    def test_reject_unmatched_response(self):
        t1=1730000000.0
        packet=self.make_reply(t1,b'ABCDEFGH',t1+.1,t1+.11)
        with self.assertRaisesRegex(ValueError,'照合'):
            n.decode_reply(packet,n._encode_ntp_timestamp(t1),t1,t1+.15,'ntp.nict.jp',100)

    def test_reject_server_unsynchronized(self):
        t1=1730000000.0
        packet=self.make_reply(t1,n._encode_ntp_timestamp(t1),t1+.1,t1+.11,li=3)
        with self.assertRaisesRegex(ValueError,'同期'):
            n.decode_reply(packet,n._encode_ntp_timestamp(t1),t1,t1+.15,'ntp.nict.jp',100)

    def test_reject_invalid_mode(self):
        t1=1730000000.0
        packet=self.make_reply(t1,n._encode_ntp_timestamp(t1),t1+.1,t1+.11,mode=3)
        with self.assertRaises(ValueError):
            n.decode_reply(packet,n._encode_ntp_timestamp(t1),t1,t1+.15,'ntp.nict.jp',100)

    def test_reject_delay_too_long(self):
        t1=1730000000.0
        packet=self.make_reply(t1,n._encode_ntp_timestamp(t1),t1+.1,t1+.11)
        with self.assertRaisesRegex(ValueError,'遅延'):
            n.decode_reply(packet,n._encode_ntp_timestamp(t1),t1,t1+10,'ntp.nict.jp',100)

    def test_fallback_before_first_sync(self):
        c=n.InternetClock()
        with patch('internet_clock.time.time',return_value=1730000010.0):
            self.assertEqual(c.current_unix(200),1730000010.0)
        self.assertIn('PC',c.state(200)['time_source'])

    def test_fallback_when_stale_and_error(self):
        c=n.InternetClock(max_age_seconds=600)
        sample=n.NtpSample('ntp.nict.jp',1730000000,100,0.01,10)
        c.accept(sample)
        c.failed('UDP timed out')
        self.assertEqual(c.state(150)['time_source'],'NTP')
        self.assertEqual(c.state(710)['time_source'],'PC (NTP未同期)')
        with patch('internet_clock.time.time',return_value=123):
            self.assertEqual(c.current_unix(710),123)

    def test_timezone_japan(self):
        c=n.InternetClock()
        sample=n.NtpSample('ntp.nict.jp',0,100,0.01,0)
        c.accept(sample)
        with patch('internet_clock.time.monotonic',return_value=100.0):
            self.assertEqual(c.now_jst().strftime('%Y-%m-%d %H:%M:%S'),'1970-01-01 09:00:00')

    def test_config_default_and_live_validation(self):
        self.assertEqual(d.DEFAULTS['ntp_server'],'ntp.nict.jp')
        self.assertEqual(d.DEFAULTS['ntp_sync_minutes'],30)
        with patch.object(d,'load_settings',return_value={**d.DEFAULTS,'ntp_sync_minutes':0}):
            with self.assertRaises(ValueError):d.read_live_settings()

    def test_settings_status_preserves_no_json_heartbeat(self):
        self.assertIn('time_source',n.InternetClock().state())
        self.assertIn('NTP',n.InternetClock().state()['time_source'])

if __name__=='__main__':unittest.main()
