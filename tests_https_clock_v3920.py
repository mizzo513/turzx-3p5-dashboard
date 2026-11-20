# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.20: HTTPS TimeAPI.io fallback, NTP priority and PC-clock failover.

All tests mock the network; the API is not contacted during CI.
"""
import io
import json
import math
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from internet_clock import (
    HTTPS_TIME_URL, JST, InternetClock, NtpSample, TimeSyncError,
    query_https_time, query_time_with_fallback,
)


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self,*_args):
        self.close()


class HTTPSClockTests(unittest.TestCase):
    def test_real_timeapi_shape_and_midpoint_rtt_correction(self):
        payload=json.dumps({
            'dateTime':'2026-11-20T11:45:52.7489872',
            'timeZone':'Asia/Tokyo',
        }).encode('utf-8')
        called=[]
        def opener(req,timeout):
            called.append((req.full_url,timeout))
            return FakeHTTPResponse(payload)
        with patch('internet_clock.time.time',return_value=1_795_164_000.0),\
             patch('internet_clock.time.monotonic',side_effect=[100.,100.24]):
            sample=query_https_time(opener,timeout=4.0)
        self.assertEqual(called,[(HTTPS_TIME_URL,4.0)])
        self.assertEqual(sample.source,'HTTPS')
        self.assertEqual(sample.server,'timeapi.io')
        self.assertAlmostEqual(sample.rtt_seconds,.24,places=6)
        self.assertAlmostEqual(sample.estimated_error_seconds,.12,places=6)
        unix=datetime.fromisoformat('2026-11-20T11:45:52.748987').replace(
            tzinfo=JST).timestamp()
        self.assertAlmostEqual(sample.utc_at_receive,unix+.12,places=5)
        clock=InternetClock()
        clock.accept(sample,fallback_reason='timed out')
        state=clock.state(monotonic_value=101.0)
        self.assertEqual(state['time_source'],'HTTPS')
        self.assertEqual(state['ntp_error'],'timed out')
        self.assertEqual(state['time_estimated_error_ms'],120.0)
        self.assertAlmostEqual(clock.current_unix(101.0),
                               sample.utc_at_receive+.76,places=5)

    def test_bad_http_response_is_never_accepted(self):
        invalid=(
            {'dateTime':'2026-11-20T11:45:52','timeZone':'UTC'},
            {'timeZone':'Asia/Tokyo'},
            {'dateTime':'yesterday','timeZone':'Asia/Tokyo'},
            {'dateTime':'1970-01-01T00:00:00','timeZone':'Asia/Tokyo'},
            [],
        )
        for doc in invalid:
            with self.subTest(doc=doc):
                with self.assertRaises(ValueError):
                    query_https_time(
                        lambda req,timeout:FakeHTTPResponse(json.dumps(doc).encode()))
        with self.assertRaises(ValueError):
            query_https_time(lambda req,timeout:FakeHTTPResponse(b'X'*9000))

    def test_successful_ntp_prevents_any_https_request(self):
        sample=NtpSample('ntp.nict.jp',1760000000.,2.0,.01,.002)
        ntp=Mock(return_value=sample)
        https=Mock(side_effect=AssertionError('must not use HTTPS'))
        result,reason=query_time_with_fallback(
            'ntp.nict.jp',ntp_query=ntp,https_query=https)
        self.assertIs(result,sample)
        self.assertEqual(reason,'')
        ntp.assert_called_once_with('ntp.nict.jp',2.5)
        https.assert_not_called()

    def test_ntp_timeout_uses_https_instead_of_pc(self):
        sample=NtpSample('timeapi.io',1760000000.,100.0,.16,.5,
                         source='HTTPS',estimated_error_seconds=.08)
        ntp=Mock(side_effect=TimeoutError('timed out'))
        https=Mock(return_value=sample)
        got,error=query_time_with_fallback('ntp.nict.jp',
                                           ntp_query=ntp,https_query=https)
        self.assertIs(got,sample)
        self.assertEqual(error,'timed out')
        ntp.assert_called_once_with('ntp.nict.jp',2.5)
        https.assert_called_once_with(timeout=5.0)
        clock=InternetClock()
        clock.accept(got,fallback_reason=error)
        self.assertEqual(clock.state(100.1)['time_source'],'HTTPS')

    def test_both_sources_fail_then_pc_clock_is_reported(self):
        with self.assertRaises(TimeSyncError) as context:
            query_time_with_fallback(
                'ntp.nict.jp',
                ntp_query=Mock(side_effect=TimeoutError('NTP timed out')),
                https_query=Mock(side_effect=OSError('HTTPS blocked')))
        failure=context.exception
        self.assertEqual(failure.ntp_error,'NTP timed out')
        self.assertEqual(failure.https_error,'HTTPS blocked')
        self.assertIn('HTTPS blocked',str(failure))
        clock=InternetClock()
        clock.failed(str(failure))
        state=clock.state()
        self.assertTrue(state['time_source'].startswith('PC'))
        self.assertIn('HTTPS blocked',state['ntp_error'])
        self.assertIsNone(state['time_sync_rtt_ms'])

    def test_previous_external_clock_remains_valid_temporarily(self):
        clock=InternetClock(max_age_seconds=500)
        sample=NtpSample('timeapi.io',1760000000.,100.0,.15,.03,
                         source='HTTPS')
        clock.accept(sample)
        clock.failed('NTP timed out / HTTPS blocked')
        self.assertEqual(clock.state(200.)['time_source'],'HTTPS')
        self.assertTrue(clock.state(601.)['time_source'].startswith('PC'))


if __name__=='__main__':
    unittest.main()
