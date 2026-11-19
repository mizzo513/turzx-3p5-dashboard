# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for v3.9.7 TURZX USB and clock scheduling helpers."""
import unittest
from datetime import datetime, timezone, timedelta

from runtime_ipc import IPCState
from turzx_dashboard import DEFAULTS, clock_label_region, seconds_region, notice_region


class ClockAndReconnectTests(unittest.TestCase):
    def test_clock_region_is_bounded_and_smaller_than_full_frame(self):
        now = datetime(2026, 11, 19, 23, 59, 59,
                       tzinfo=timezone(timedelta(hours=9)))
        rect = clock_label_region(DEFAULTS, now)
        x0, y0, x1, y1 = rect
        self.assertTrue(0 <= x0 < x1 <= 480)
        self.assertTrue(0 <= y0 < y1 <= 320)
        self.assertLess((x1-x0)*(y1-y0), 480*320)

    def test_clock_region_handles_day_rollover_and_custom_location(self):
        conf = dict(DEFAULTS)
        conf['text_styles'] = {'clock_datetime': {'x': 44, 'y': 77, 'size': 29}}
        now = datetime(2026, 11, 20, 0, 0, 1,
                       tzinfo=timezone(timedelta(hours=9)))
        for rect in (clock_label_region(conf, now),
                     seconds_region(conf, now)):
            x0, y0, x1, y1 = rect
            self.assertTrue(0 <= x0 < x1 <= 480)
            self.assertTrue(0 <= y0 < y1 <= 320)

    def test_notice_and_clock_are_separate_default_regions(self):
        now = datetime(2026, 11, 19, 9, 30, 23,
                       tzinfo=timezone(timedelta(hours=9)))
        clock = seconds_region(DEFAULTS, now)
        notice = notice_region(DEFAULTS)
        self.assertTrue(clock[3] <= notice[1] or notice[3] <= clock[1]
                        or clock[2] <= notice[0] or notice[2] <= clock[0])

    def test_ipc_state_has_separate_reconnect_event(self):
        state = IPCState()
        self.assertFalse(state.reconnect_requested.is_set())
        self.assertFalse(state.stop_requested.is_set())
        state.reconnect_requested.set()
        self.assertTrue(state.reconnect_requested.is_set())
        self.assertFalse(state.stop_requested.is_set())


if __name__ == '__main__':
    unittest.main()
