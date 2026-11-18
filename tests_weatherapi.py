# -*- coding: utf-8 -*-
"""Offline regressions for WeatherAPI.com provider selection and conditions.

Never contact WeatherAPI.com or expose a real API key.
"""
import copy
import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import turzx_dashboard as app
import weatherapi_provider as provider


class FakeResponse(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def response(code=1003,precip_mm=17.0,day_chance=100):
    return {
        'current': {
            'last_updated':'2026-11-18 16:00',
            'last_updated_epoch':1794985200,
            'temp_c':13.6, 'humidity':94, 'wind_kph':18.0,
            'precip_mm':precip_mm,
            'condition': {'text':'Partly cloudy','code':code},
        },
        'forecast':{'forecastday':[{
            'date':'2026-11-18',
            'day':{'maxtemp_c':17.4, 'mintemp_c':8.6,
                   'daily_chance_of_rain':day_chance}
        }]},
    }


class WeatherAPIProviderTests(unittest.TestCase):
    def setUp(self):
        self.conf={**copy.deepcopy(app.DEFAULTS),
                   'weather_city':'白山市',
                   'weather_latitude':36.5144,
                   'weather_longitude':136.5656,
                   'weather_provider':'weatherapi',
                   'weatherapi_key':'TEST_API_KEY_NOT_REAL'}
        self.at=datetime(2026,11,18,7,45,tzinfo=timezone.utc)

    def test_default_weatherapi_selected_without_overwriting_existing_location(self):
        self.assertEqual(app.DEFAULTS['weather_provider'],'weatherapi')
        self.assertEqual(app.DEFAULTS['weatherapi_key'],'')
        self.assertEqual(app.DEFAULTS['weather_city'],'白山市')
        self.assertEqual(app.DEFAULTS['weather_latitude'],36.5144)
        self.assertEqual(app.DEFAULTS['weather_update_minutes'],10)

    def test_weatherapi_condition_is_authoritative_even_with_heavy_rain_amount(self):
        parsed=provider.parse_forecast(response(code=1003,precip_mm=19,day_chance=100),
                                       '白山市',fetched=self.at)
        self.assertEqual(parsed['condition_text'],'晴れ時々曇り')
        self.assertEqual(parsed['code'],2)
        self.assertEqual(parsed['raw_condition_code'],1003)
        self.assertEqual(parsed['precip'],100)
        self.assertEqual(parsed['precip_mm'],19)
        self.assertEqual(parsed['provider'],'weatherapi')

    def test_heavy_rain_code_yields_heavy_rain_without_precip_override(self):
        data=provider.parse_forecast(response(code=1195,precip_mm=0,day_chance=0),
                                     '白山市',fetched=self.at)
        self.assertEqual(data['condition_text'],'大雨')
        self.assertEqual(data['code'],65)
        self.assertEqual(data['precip_mm'],0)

    def test_all_codes_map_to_supported_pictograms(self):
        self.assertGreater(len(provider.CODE_TO_WEATHER),40)
        self.assertEqual(provider.CODE_TO_WEATHER[1000],('晴れ',0))
        self.assertEqual(provider.CODE_TO_WEATHER[1195],('大雨',65))
        for code,(label,wmo) in provider.CODE_TO_WEATHER.items():
            self.assertIsInstance(code,int)
            self.assertTrue(label)
            self.assertIsInstance(wmo,int)

    def test_single_request_uses_coordinates_forecast_japanese_and_no_key_leak(self):
        captured=[]
        def opener(req,timeout=0):
            captured.append((req,timeout))
            return FakeResponse(json.dumps(response(code=1195)).encode('utf-8'))
        result=app.fetch_weather(self.conf,opener)
        self.assertEqual(result.provider,'weatherapi')
        self.assertEqual(result.condition_text,'大雨')
        self.assertAlmostEqual(result.wind,5)
        self.assertEqual(result.high,17.4)
        self.assertEqual(result.low,8.6)
        self.assertEqual(result.humidity,94)
        self.assertEqual(result.precip,100)
        self.assertEqual(len(captured),1)
        url=captured[0][0].full_url
        self.assertTrue(url.startswith(provider.ENDPOINT))
        self.assertIn('36.514400%2C136.565600',url)
        self.assertIn('days=1',url)
        self.assertIn('lang=ja',url)
        self.assertIn('alerts=no',url)
        self.assertEqual(captured[0][1],12)

    def test_missing_key_is_clear_and_does_not_contact_network(self):
        def bad_opener(*args,**kwargs):
            self.fail('Missing key must not request network')
        conf={**self.conf,'weatherapi_key':''}
        with self.assertRaisesRegex(provider.WeatherAPIError,'APIキーが未設定'):
            app.fetch_weather(conf,bad_opener)

    def test_invalid_key_uses_safe_error_without_leaking_key(self):
        conf={**self.conf,'weatherapi_key':'private-key-do-not-print'}
        def fake_error(req,timeout=0):
            return FakeResponse(json.dumps({'error':{'code':2006,'message':'Invalid key'}}).encode())
        with self.assertRaises(provider.WeatherAPIError) as exc:
            app.fetch_weather(conf,fake_error)
        self.assertNotIn('private-key-do-not-print',str(exc.exception))
        self.assertIn('APIキーが無効',str(exc.exception))

    def test_switch_to_openmeteo_preserves_original_adapter(self):
        sample={'current':{'temperature_2m':12,'relative_humidity_2m':70,
                           'weather_code':3,'wind_speed_10m':4},
                'daily':{'time':[app.jp_now().date().isoformat()],
                         'temperature_2m_max':[17],
                         'temperature_2m_min':[8],
                         'precipitation_probability_max':[95]}}
        urls=[]
        def opener(req,timeout=0):
            urls.append(req.full_url)
            return FakeResponse(json.dumps(sample).encode())
        r=app.fetch_weather({**self.conf,'weather_provider':'openmeteo'},opener)
        self.assertEqual(r.provider,'openmeteo')
        self.assertEqual(r.code,3)
        self.assertEqual(r.precip,95)
        self.assertEqual(r.temperature,12)
        self.assertIn('open-meteo.com',urls[0])

    def test_invalid_source_rejected(self):
        with self.assertRaisesRegex(ValueError,'天気の取得元'):
            app.fetch_weather({**self.conf,'weather_provider':'other'},lambda *a:None)

    def test_render_uses_weatherapi_text_not_wmo_description_or_rain_threshold(self):
        w=app.Weather(**provider.parse_forecast(response(code=1195,precip_mm=0),
                                                  '白山市',fetched=self.at))
        trace=[]
        original=app.style_label
        def record(draw,conf,key,text,*args,**kwargs):
            trace.append((key,str(text)))
            return original(draw,conf,key,text,*args,**kwargs)
        with patch.object(app,'style_label',side_effect=record):
            im=app.render_original(app.jp_now(),w,app.TrainState(),self.conf)
        self.assertEqual(im.size,(480,320))
        self.assertIn(('weather_description','大雨'),trace)
        self.assertIn(('weather_city','白山市'),trace)

    def test_old_settings_migrate_without_discarding_other_config(self):
        old={'weather_city':'津幡町','weather_latitude':36.6693,'weather_longitude':136.7288,
             'train_count':2,'port':'COM7','show_seconds':True,'layout_revision':390}
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'settings.json'
            p.write_text(json.dumps(old),encoding='utf-8')
            with patch.object(app,'SETTINGS',p):
                conf=app.load_settings()
                self.assertEqual(conf['weather_provider'],'weatherapi')
                self.assertEqual(conf['weatherapi_key'],'')
                self.assertEqual(conf['weather_city'],'津幡町')
                self.assertEqual(conf['port'],'COM7')
                self.assertEqual(conf['train_count'],2)
                conf['weatherapi_key']='TEST_KEY_LOCAL_ONLY'
                app.save_settings(conf)
                saved=app.load_settings()
                self.assertEqual(saved['weather_provider'],'weatherapi')
                self.assertEqual(saved['weatherapi_key'],'TEST_KEY_LOCAL_ONLY')
                self.assertEqual(saved['train_count'],2)


if __name__=='__main__':
    unittest.main()
