# -*- coding: utf-8 -*-
"""Offline regression tests for 加賀笠間 → 金沢 → 津幡 timetable views."""
import copy
from datetime import datetime
from pathlib import Path
import unittest
import turzx_dashboard as app


class KagaKasamaRouteTests(unittest.TestCase):
    def setUp(self):
        self.conf=copy.deepcopy(app.DEFAULTS)
        self.now=datetime(2026,11,18,13,15,tzinfo=app.TZ)

    def test_default_migrates_existing_kanazawa_settings(self):
        self.assertEqual(self.conf['ir_route'],'via_kanazawa')
        self.assertEqual(self.conf['train_from'],'金沢')
        trains=app.upcoming_from_ir_schedule(self.now,self.conf).trains
        self.assertEqual(len(trains),3)
        first=trains[0]
        self.assertEqual(first.origin,'加賀笠間')
        self.assertEqual(first.destination,'津幡')
        self.assertEqual([first.depart.strftime('%H:%M'),first.transfer_arrive.strftime('%H:%M'),
                          first.transfer_depart.strftime('%H:%M'),first.arrive.strftime('%H:%M')],
                         ['13:25','13:42','13:45','13:57'])
        self.assertEqual((first.transfer_arrival_platform,first.transfer_departure_platform),('5','7'))

    def test_direct_train_still_shows_kanazawa_times(self):
        now=datetime(2026,11,18,18,15,tzinfo=app.TZ)
        direct=app.upcoming_from_ir_schedule(now,self.conf).trains[0]
        self.assertEqual(direct.depart.strftime('%H:%M'),'18:24')
        self.assertTrue(direct.direct)
        self.assertEqual(direct.transfer_arrive.strftime('%H:%M'),'18:40')
        self.assertEqual(direct.transfer_depart.strftime('%H:%M'),'18:45')
        self.assertEqual(direct.arrive.strftime('%H:%M'),'18:57')

    def test_next_day_after_last_train(self):
        now=datetime(2026,11,18,23,45,tzinfo=app.TZ)
        rows=app.upcoming_from_ir_schedule(now,self.conf).trains
        self.assertEqual(len(rows),3)
        self.assertTrue(all(t.depart.date()>now.date() for t in rows))
        self.assertEqual(rows[0].depart.strftime('%H:%M'),'05:35')

    def test_holiday_excludes_weekday_service(self):
        now=datetime(2026,11,23,7,45,tzinfo=app.TZ)
        rows=app.upcoming_from_ir_schedule(now,self.conf).trains
        self.assertNotIn('629M',[t.line.split(' / ')[0] for t in rows])

    def test_legacy_kanazawa_mode(self):
        conf={**self.conf,'ir_route':'kanazawa_tsubata'}
        row=app.upcoming_from_ir_schedule(self.now,conf).trains[0]
        self.assertEqual(row.depart.strftime('%H:%M'),'13:31')
        self.assertIsNone(row.transfer_arrive)

    def test_all_three_rows_have_editable_time_captions(self):
        rows=app.upcoming_from_ir_schedule(self.now,self.conf)
        hit={}
        image=app.render_original(self.now,app.Weather(city='白山市'),rows,self.conf,hit_boxes=hit)
        self.assertEqual(image.size,(480,320))
        for n in (1,2,3):
            for field in ('train_station_depart','train_station_kan_arr',
                          'train_station_kan_dep','train_station_arrive',
                          'train_time','train_kan_arr','train_kan_dep','train_arrive','train_detail'):
                self.assertIn(f'text:{field}_{n}',hit)
            x0,y0,x1,y1=hit[f'text:train_time_{n}']
            self.assertTrue(170<=x0<x1<245)
            panel=hit[f'panel:train_{n}']
            self.assertTrue(panel[1]<=y0<y1<=panel[3]+1,(n,(x0,y0,x1,y1),panel))

    def test_diagnostics_shows_interchange_and_platform(self):
        info=app.train_diagnostics(self.now,self.conf)
        self.assertEqual(info['train_from'],'加賀笠間')
        self.assertEqual(info['train_to'],'津幡')
        self.assertTrue(info['trains'][0]['kanazawa_arrive'])
        self.assertTrue(info['trains'][0]['kanazawa_depart'])
        self.assertEqual(info['trains'][0]['transfer_platform'],'5→7')

    def test_missing_schedule_does_not_fabricate_times(self):
        result=app.upcoming_from_ir_schedule(self.now,self.conf,path=Path('missing_schedule_v38.json'))
        self.assertFalse(result.trains)
        self.assertTrue(result.error)


if __name__=='__main__':unittest.main()
