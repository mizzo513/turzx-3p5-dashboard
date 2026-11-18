"""Offline regression tests: original user-provided schedule to display mapping."""
import unittest
from datetime import datetime, timedelta
import json
from pathlib import Path
import turzx_dashboard as dash
import rail_core


class IntegratedIRScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf={**dash.load_settings(),'ir_route':'kanazawa_tsubata'}
        cls.doc=rail_core.load_schedule(dash.IR_SCHEDULE_PATH)

    def at(self, year,month,day,hour,minute):
        return datetime(year,month,day,hour,minute,tzinfo=dash.TZ)

    def test_original_source_untouched_and_structure(self):
        self.assertEqual(self.doc['revision'],'2026-03-14')
        self.assertGreater(len(self.doc['first']),20)
        self.assertGreater(len(self.doc['second']),20)
        self.assertEqual(self.conf['train_source'],'ir_schedule')
        self.assertEqual(self.conf['weather_city'],'白山市')

    def test_weekday_next_three(self):
        now=self.at(2026,11,18,7,45)  # Wednesday
        state=dash.upcoming_from_ir_schedule(now,self.conf)
        self.assertEqual(len(state.trains),3)
        self.assertEqual([x.depart.strftime('%H:%M') for x in state.trains],['07:55','08:01','08:12'])
        self.assertEqual([x.platform for x in state.trains],['7','6','5'])
        self.assertEqual(state.trains[0].line,'629M')

    def test_holiday_no_weekday_only_service(self):
        now=self.at(2026,11,23,7,45)  # Labour Thanksgiving Day
        state=dash.upcoming_from_ir_schedule(now,self.conf)
        self.assertEqual(len(state.trains),3)
        self.assertNotIn('629M',[x.line for x in state.trains])
        self.assertNotIn('07:55',[x.depart.strftime('%H:%M') for x in state.trains])

    def test_midnight_arrival_carries_next_date(self):
        now=self.at(2026,11,18,23,40)
        state=dash.upcoming_from_ir_schedule(now,self.conf)
        t=state.trains[0]
        self.assertEqual(t.depart.strftime('%H:%M'),'23:48')
        self.assertEqual(t.arrive.strftime('%H:%M'),'00:01')
        self.assertEqual(t.arrive.date().isoformat(),'2026-11-19')
        self.assertEqual(round((t.arrive-t.depart).total_seconds()/60),13)

    def test_unsupported_route_not_misrepresented(self):
        conf={**self.conf,'train_from':'小松'}
        state=dash.upcoming_from_ir_schedule(self.at(2026,11,18,8,0),conf)
        self.assertEqual(state.trains,[])
        self.assertIsNotNone(state.error)

    def test_physical_rotation_matches_previous(self):
        now=self.at(2026,11,18,7,45)
        tr=dash.upcoming_from_ir_schedule(now,self.conf)
        w=dash.Weather(city='白山市')
        p=dash.render_physical(now,w,tr,self.conf)
        self.assertEqual(p.size,(480,320))
        self.assertEqual(p.getpixel((0,0)),dash.render_original(now,w,tr,self.conf).getpixel((479,319)))


if __name__=='__main__': unittest.main()
