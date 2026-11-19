# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.9 regression tests for weather fallback, scroll speed, and unit controls."""
import copy
import io
import json
import math
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from layout_groups import GROUPS, adjust_group, matching_group
from marquee_scheduler import MarqueeScheduler
from text_layout import props
from turzx_dashboard import Weather
import weather_fusion


NOW=datetime(2026,11,19,7,10,tzinfo=timezone.utc)
STAMP=datetime(2026,11,19,7,5,tzinfo=timezone.utc).isoformat()


class WeatherFusionIntegrationTests(unittest.TestCase):
    def test_observed_rain_replaces_provider_current_condition_only(self):
        baseline=Weather(city='金沢市',temperature=16,high=20,low=10,precip=75,
                         code=0,condition_text='晴れ',error=None,provider='weatherapi')
        evidence={'model':{'weather_code':0,'cloud_cover':10,'is_day':1},
                  'observations':{'radar':{'level':3,'observed_at':STAMP}}}
        merged=weather_fusion.judge_weather(baseline,evidence,NOW)
        self.assertEqual((merged.label,merged.code),('雨(実況)',61))
        # The calling dashboard retains all forecast fields from baseline.
        self.assertEqual((baseline.temperature,baseline.high,baseline.low,baseline.precip),
                         (16,20,10,75))
        self.assertEqual(baseline.condition_text,'晴れ')

    def test_model_fallback_when_radar_unavailable(self):
        baseline=Weather(condition_text='晴れ',code=0,provider='weatherapi')
        evidence={'model':{'weather_code':3,'cloud_cover':92},
                  'observations':{'radar':None,'amedas':None,'errors':['radar timeout']}}
        got=weather_fusion.judge_weather(baseline,evidence,NOW)
        self.assertEqual(got.label,'曇り')
        self.assertTrue(got.source.startswith('Open-Meteo'))

    def test_weatherapi_preserved_when_all_extra_sources_unavailable(self):
        baseline=Weather(condition_text='晴れ',code=0,provider='weatherapi')
        evidence={'model':None,'observations':{'radar':None,'amedas':None}}
        self.assertIsNone(weather_fusion.judge_weather(baseline,evidence,NOW))

    def test_positive_jma_radar_overrides_when_model_offline(self):
        baseline=Weather(code=0,condition_text='晴れ',provider='weatherapi')
        evidence={'model':None,'observations':{'radar':{'level':4,'observed_at':STAMP}}}
        self.assertEqual(weather_fusion.judge_weather(baseline,evidence,NOW).label,'雨(実況)')

    def test_missing_radar_does_not_overwrite_provider_with_clouds(self):
        baseline=Weather(code=0,condition_text='晴れ',provider='weatherapi')
        evidence={'model':None,'observations':{'radar':{'level':0,'observed_at':STAMP}}}
        self.assertIsNone(weather_fusion.judge_weather(baseline,evidence,NOW))

    def test_independent_errors_do_not_hide_other_sources(self):
        cfg={'weather_latitude':36.6693,'weather_longitude':136.7288}
        observation={'radar':{'level':2,'observed_at':STAMP},'errors':['amedas: unavailable']}
        with patch.object(weather_fusion,'fetch_model_current',side_effect=OSError('offline')), \
             patch.object(weather_fusion,'fetch_observations',return_value=observation):
            got=weather_fusion.fetch_weather_evidence(cfg)
        self.assertIsNone(got['model'])
        self.assertEqual(got['observations'],observation)
        self.assertEqual(len(got['errors']),2)

    def test_current_request_fields_include_all_model_inputs(self):
        for field in ('weather_code','cloud_cover','is_day','precipitation',
                      'rain','showers','snowfall'):
            self.assertIn(field,weather_fusion.CURRENT_FIELDS)


class MarqueeSpeedControlTests(unittest.TestCase):
    def test_pixels_per_second_is_a_rate_not_a_frame_step(self):
        s=MarqueeScheduler(pixels_per_second=20.0)
        s.reset(0)
        self.assertEqual(s.candidate(2.2,0,clock_due=False,second_fraction=.2),4)
        fast=s.candidate(2.4,4,clock_due=False,second_fraction=.4)
        self.assertEqual(fast,8)
        s.pixels_per_second=10.0
        s.reset(5)
        self.assertEqual(s.candidate(7.2,0,clock_due=False,second_fraction=.2),2)

    def test_zero_speed_holds_stationary_text(self):
        s=MarqueeScheduler(pixels_per_second=0)
        s.reset(0)
        self.assertIsNone(s.candidate(2.2,0,clock_due=False,second_fraction=.2))
        self.assertIsNone(s.candidate(4.2,0,clock_due=False,second_fraction=.2))


class TemperatureIndividualEditTests(unittest.TestCase):
    def test_number_and_unit_match_individual_groups_by_default(self):
        a=matching_group('weather_temperature')
        b=matching_group('weather_temperature_unit')
        self.assertNotEqual(a,b)
        self.assertEqual(GROUPS[a][1],('weather_temperature',))
        self.assertEqual(GROUPS[b][1],('weather_temperature_unit',))
        self.assertIn('天気｜現在気温（数値と単位 一括）',GROUPS)

    def test_adjustment_to_number_does_not_change_unit(self):
        a=matching_group('weather_temperature')
        changed=adjust_group({}, {}, a, dx=-3, dsize=2)
        self.assertEqual(set(changed),{'weather_temperature'})
        self.assertEqual(changed['weather_temperature']['size'],24)
        self.assertEqual(props({'text_styles':changed},'weather_temperature_unit')['size'],14)

    def test_adjustment_to_unit_does_not_change_number(self):
        b=matching_group('weather_temperature_unit')
        changed=adjust_group({}, {}, b, dy=2, dsize=-2)
        self.assertEqual(set(changed),{'weather_temperature_unit'})
        self.assertEqual(props({'text_styles':changed},'weather_temperature')['size'],22)
        self.assertEqual(props({'text_styles':changed},'weather_temperature_unit')['size'],12)


if __name__=='__main__':
    unittest.main()
