# -*- coding: utf-8 -*-
"""Offline tests of current-weather judgement and JMA radar data decoders."""
import datetime as dt
import struct
import unittest
import zlib
from weather_judgement import decide_current_weather
from jma_observation import (JMA_RAIN_RGB, decode_png_rgba, latest_radar_frame,
                              pick_nearby_amedas, rain_class, sample_radar_tiles, tile_position)
from weather_fusion import CURRENT_FIELDS

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 19, 7, 10, tzinfo=UTC)
STAMP = (NOW - dt.timedelta(minutes=5)).isoformat()


def forecast(code=3, cloud=95, precipitation=0, snow=0, daylight=1):
    return {'current': {'weather_code': code, 'cloud_cover': cloud, 'precipitation': precipitation,
                        'snowfall': snow, 'is_day': daylight}}


def png_chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def make_png(patch=None):
    pixels = bytearray()
    for y in range(256):
        pixels.append(0)
        for x in range(256):
            pixels.extend((patch or {}).get((x, y), (0, 0, 0, 0)))
    return (b'\x89PNG\r\n\x1a\n' +
            png_chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 6, 0, 0, 0)) +
            png_chunk(b'IDAT', zlib.compress(bytes(pixels))) +
            png_chunk(b'IEND', b''))


class CurrentConditionsTests(unittest.TestCase):
    def test_observed_rain_priority(self):
        got = decide_current_weather(forecast(), {'radar': {'level': 4, 'observed_at': STAMP}}, NOW)
        self.assertEqual((got.code, got.label), (61, '雨(実況)'))

    def test_snow_is_model_assisted(self):
        got = decide_current_weather(forecast(code=71, snow=0.4),
                                     {'radar': {'level': 3, 'observed_at': STAMP}}, NOW)
        self.assertEqual(got.label, '雪(実況)')

    def test_old_radar_does_not_override(self):
        old = (NOW - dt.timedelta(minutes=60)).isoformat()
        got = decide_current_weather(forecast(cloud=12),
                                     {'radar': {'level': 4, 'observed_at': old}}, NOW)
        self.assertEqual(got.label, '晴れ')

    def test_near_station_rain_is_labeled_as_nearby(self):
        rain = {'station': '金沢', 'distance_km': 6,
                'precipitation10m': 1.0, 'observed_at': STAMP}
        self.assertEqual(decide_current_weather(forecast(), {'amedas': rain}, NOW).label, '雨(周辺)')

    def test_distant_station_does_not_override(self):
        rain = {'distance_km': 14, 'precipitation10m': 1.0, 'observed_at': STAMP}
        self.assertEqual(decide_current_weather(forecast(), {'amedas': rain}, NOW).label, '曇り')

    def test_no_radar_echo_does_not_remove_forecast_rain(self):
        obs = {'radar': {'level': 0, 'observed_at': STAMP}}
        self.assertEqual(decide_current_weather(forecast(code=61, precipitation=0.5), obs, NOW).label, '雨')

    def test_daytime_sunshine_only(self):
        obs = {'amedas': {'sun10m': 9, 'distance_km': 2, 'observed_at': STAMP}}
        self.assertEqual(decide_current_weather(forecast(), obs, NOW).label, '晴れ(観測)')
        self.assertEqual(decide_current_weather(forecast(daylight=0), obs, NOW).label, '曇り')

    def test_cloud_cover_and_legacy_model(self):
        self.assertEqual(decide_current_weather(forecast(cloud=53), now=NOW).label, '晴れ時々曇り')
        self.assertEqual(decide_current_weather({'current': {'weather_code': 2}}, now=NOW).label,
                         '晴れ時々曇り')

    def test_url_requests_extended_current_variables(self):
        url = CURRENT_FIELDS
        for field in ('cloud_cover', 'precipitation', 'rain', 'showers', 'snowfall'):
            self.assertIn(field, url)


class JmaDataTests(unittest.TestCase):
    def test_legend(self):
        for idx, rgb in enumerate(JMA_RAIN_RGB, 1):
            self.assertEqual(rain_class(*rgb, 255), idx)
        self.assertIsNone(rain_class(255, 0, 255, 255))
        self.assertEqual(rain_class(0, 0, 0, 0), 0)

    def test_frame_freshness(self):
        valid = {'basetime': '20261119070500', 'validtime': '20261119070500', 'elements': ['hrpns']}
        stale = {'basetime': '20261119050000', 'validtime': '20261119050000', 'elements': ['hrpns']}
        self.assertEqual(latest_radar_frame([stale, valid], NOW), valid)
        self.assertIsNone(latest_radar_frame([stale], NOW))

    def test_png_and_pixel_sampling(self):
        city = (36.669, 136.731)
        x, y = tile_position(*city)
        raw = make_png({(x % 256, y % 256): (*JMA_RAIN_RGB[2], 255)})
        frame = {'basetime': '20261119070500', 'validtime': '20261119070500'}
        self.assertEqual(len(decode_png_rgba(raw)), 256 * 256 * 4)
        self.assertEqual(sample_radar_tiles(frame, *city, fetch_tile=lambda url: raw), 3)
        self.assertEqual(sample_radar_tiles(frame, *city, fetch_tile=lambda url: make_png()), 0)
        with self.assertRaises(ValueError):
            decode_png_rgba(raw[:-10] + b'broken')

    def test_station_selection_and_quality(self):
        city = {'latitude': 36.5, 'longitude': 136.6}
        table = {'12345': {'lat': [36, 30], 'lon': [136, 36], 'kjName': '近隣'}}
        wet = pick_nearby_amedas(table, {'12345': {'precipitation10m': [0.4, 0]}}, city)
        self.assertEqual(wet['precipitation10m'], 0.4)
        bad = pick_nearby_amedas(table, {'12345': {'precipitation10m': [5, 5]}}, city)
        self.assertIsNone(bad)


if __name__ == '__main__':
    unittest.main()
