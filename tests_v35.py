# SPDX-License-Identifier: GPL-3.0-or-later
"""No-device tests for the V3.5 features."""
import copy
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_ipc
import turzx_dashboard as dash
from text_layout import props, validate_styles


class TestsV35(unittest.TestCase):
    def test_ipc_memory_status_and_stop(self):
        with runtime_ipc.StatusServer() as state:
            state.update(clock='11:22:33', settings_hash='abc', connected=False)
            r=runtime_ipc.get_runtime_status()
            self.assertEqual(r['clock'],'11:22:33')
            self.assertTrue(runtime_ipc.request_stop())
            self.assertTrue(state.stop_requested.is_set())
        self.assertIsNone(runtime_ipc.current_state())

    def test_no_status_write(self):
        with tempfile.TemporaryDirectory() as d:
            old=dash.STATUS_PATH
            dash.STATUS_PATH=Path(d)/'runtime_status.json'
            try:
                with runtime_ipc.StatusServer() as state:
                    dash.save_runtime_status(clock='12:13:14', connected=True)
                    self.assertFalse(dash.STATUS_PATH.exists())
                    self.assertEqual(state.read()['clock'],'12:13:14')
            finally:
                dash.STATUS_PATH=old

    def test_default_style_is_known_good(self):
        cfg=copy.deepcopy(dash.DEFAULTS)
        for key in ('clock_datetime','version','weather_temperature','train_time_1'):
            sp=props(cfg,key)
            self.assertTrue(0<=sp['x']<480)
            self.assertTrue(0<=sp['y']<320)
        self.assertLess((lambda b:(b[2]-b[0])*(b[3]-b[1]))(dash.seconds_region(cfg)),60*60)

    def test_moving_seconds_uses_dynamic_region(self):
        cfg=copy.deepcopy(dash.DEFAULTS)
        cfg['text_styles']={'clock_datetime':{'x':235,'y':110,'size':16,'color':'#ABCDEF'}}
        validate_styles(cfg)
        box=dash.seconds_region(cfg)
        self.assertTrue(235<=box[0]<=480 and 100<=box[1]<=140)
        self.assertLessEqual(box[2],480)
        self.assertLessEqual(box[3],320)
        self.assertNotEqual(box,dash.seconds_region(dash.DEFAULTS))
        now=dash.jp_now()
        frame=dash.render_physical(now,dash.Weather(),dash.TrainState(),cfg)
        box_physical=dash.rotation_region(box)
        self.assertEqual(frame.crop(box_physical).size,(box[2]-box[0],box[3]-box[1]))

    def test_editor_customizes_pixels(self):
        now=dash.jp_now()
        conf=copy.deepcopy(dash.DEFAULTS)
        source=dash.render_original(now,dash.Weather(),dash.TrainState(),conf)
        conf['text_styles']={'clock_datetime':{'x':230,'y':20,'size':20,'color':'#FF0000'}}
        changed=dash.render_original(now,dash.Weather(),dash.TrainState(),conf)
        self.assertNotEqual(source.tobytes(),changed.tobytes())
        self.assertEqual(props(conf,'clock_datetime')['color'],'#FF0000')

    def test_unknown_style_is_ignored_and_bad_style_rejected(self):
        cfg=copy.deepcopy(dash.DEFAULTS)
        cfg['text_styles']={'nonexistent':{'x':10}}
        validate_styles(cfg)
        cfg['text_styles']={'clock_datetime':{'x':-1}}
        with self.assertRaises(ValueError):validate_styles(cfg)
        cfg['text_styles']={'clock_datetime':{'color':'invalid'}}
        with self.assertRaises(ValueError):validate_styles(cfg)


if __name__=='__main__':
    unittest.main(verbosity=2)
