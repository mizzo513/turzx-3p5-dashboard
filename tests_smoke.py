"""Offline smoke tests (never open a serial port or contact a live API)."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, date
from pathlib import Path
from PIL import Image
import turzx_dashboard as x


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class Smoke(unittest.TestCase):
    def setUp(self):
        self.conf=x.load_settings()

    def test_weather_mapping_and_url(self):
        sample={'current': {'temperature_2m': 13.2,'relative_humidity_2m': 64,
                    'weather_code': 3, 'wind_speed_10m': 3.1},
                'daily': {'time': [x.jp_now().date().isoformat()],
                    'temperature_2m_max':[17.5],'temperature_2m_min':[9.0],
                    'precipitation_probability_max':[42]}}
        calls=[]
        def opener(req,timeout=0):
            calls.append(req.full_url)
            return Response(json.dumps(sample).encode())
        w=x.fetch_weather({**self.conf,'weather_provider':'openmeteo'}, opener)
        self.assertEqual(w.city,'白山市')
        self.assertEqual(w.temperature,13.2)
        self.assertEqual(w.precip,42)
        self.assertEqual(w.high,17.5)
        self.assertIn('Asia%2FTokyo',calls[0])
        self.assertIn('temperature_2m',calls[0])

    def test_train_csv_next_day_and_service_days(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'train.csv'
            p.write_text('from,to,depart,arrive,line,platform,note,service\n金沢,津幡,23:48,00:01,IR,3,,daily\n金沢,津幡,24:20,24:34,IR,4,,daily\n金沢,津幡,14:20,14:35,IR,3,,weekday\n',encoding='utf-8')
            now=datetime(2026,11,18,23,45,tzinfo=x.TZ)
            t=x.upcoming_from_csv(now,self.conf,p)
            self.assertTrue(t.trains)
            self.assertEqual(t.trains[0].depart.strftime('%H:%M'),'23:48')
            self.assertEqual(t.trains[0].arrive.date().isoformat(),'2026-11-19')
            self.assertEqual(t.trains[1].depart.date().isoformat(),'2026-11-19')
            self.assertEqual(t.trains[1].depart.strftime('%H:%M'),'00:20')
            self.assertTrue(x.has_service('weekday',date(2026,11,18)))
            self.assertFalse(x.has_service('weekday',date(2026,11,21)))
            self.assertFalse(x.has_service('unsupported service',date(2026,11,18)))

    def test_json_stale_filter(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'status.json';now=x.jp_now()
            sample={'updated_at':now.isoformat(),'valid_for_seconds':120,
                'trains':[{'depart_at':(now+timedelta(minutes=6)).isoformat(),
                          'arrive_at':(now+timedelta(minutes=19)).isoformat(),
                          'line':'普通','platform':'3'}]}
            p.write_text(json.dumps(sample),encoding='utf-8')
            t=x.train_from_external_json(now,self.conf,p)
            self.assertEqual(len(t.trains),1)
            self.assertEqual(t.trains[0].platform,'3')
            expired=x.train_from_external_json(now+timedelta(minutes=3),self.conf,p)
            self.assertEqual(expired.status,'外部データ期限切れ')

    def test_routes_api_transit(self):
        now=x.jp_now()+timedelta(minutes=9)
        dep=now.astimezone(x.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        arr=(now+timedelta(minutes=13)).astimezone(x.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        data={'routes':[{'legs':[{'steps':[{}, {'transitDetails': {
            'stopDetails': {'departureStop':{'name':'金沢駅'},'arrivalStop':{'name':'津幡駅'},'departureTime':dep,'arrivalTime':arr},
            'transitLine':{'name':'IRいしかわ鉄道','vehicle':{'type':'RAIL'}}}}]}]}]}
        calls=[]
        def opener(req,timeout=0):
            calls.append(req)
            return Response(json.dumps(data).encode())
        c=dict(self.conf,google_maps_api_key='TEST_ONLY')
        t=x.fetch_google_transit(c,opener)
        self.assertEqual(len(t.trains),1)
        self.assertEqual(t.trains[0].line,'IRいしかわ鉄道')
        self.assertEqual(len(calls),3)
        self.assertEqual(calls[0].get_method(),'POST')
        self.assertIn('routes.googleapis.com', calls[0].full_url)

    def test_display_packets_and_bitmap(self):
        self.assertEqual(x.orientation_packet()[6],102)
        self.assertEqual(len(x.orientation_packet()),16)
        self.assertEqual(len(x.region_packet(0,262,479,319)),6)
        self.assertEqual(x.region_packet(0,262,479,319)[-1],197)
        im=Image.new('RGB',(480,58),(255,0,0))
        self.assertEqual(len(x.rgb565le(im)),480*58*2)
        im=Image.new('RGB',(480,320),(0,0,0))
        self.assertEqual(len(x.rgb565le(im)),480*320*2)

    def test_render_rotate_consistency(self):
        now=x.jp_now()
        w=x.Weather(city='白山市')
        tr=x.TrainState([], '時刻表未登録')
        original=x.render_original(now,w,tr,self.conf)
        physical=x.render_physical(now,w,tr,self.conf)
        self.assertEqual(physical.size,(480,320))
        self.assertEqual(original.tobytes(),physical.transpose(Image.Transpose.ROTATE_180).tobytes())
        self.assertTrue(physical.getbbox())


if __name__=='__main__':unittest.main(verbosity=2)
