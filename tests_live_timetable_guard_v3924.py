# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.24: 639M 09:21 vs 09:25 cannot be shown as 発車済.

All tests use synthetic offline records: no dependence on current train
positions, internet connection, or wall-clock time.
"""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from ir_live_operations import LiveTrain, LiveTrainState, inspect_live_leg, status_for_leg
from train_operations import OperationRecord, TrainOperations, public_train_status
from turzx_dashboard import TZ, Train, TrainState, live_train_diagnostics

NOW=datetime(2026,11,25,9,21,0,tzinfo=TZ)
DEPART=datetime(2026,11,25,9,25,0,tzinfo=TZ)


def sample(number='0639M', observed=NOW, at='Matto', nxt='Nonoichi', delay=0):
    live=LiveTrain(
        number,observed,observed+timedelta(seconds=30),
        delay,'odpt.RailDirection:IRIshikawa.Toyama',at,nxt,
        'Komatsu','Kanazawa')
    return LiveTrainState((live,),observed)


def status(live, now=NOW, depart=DEPART, ops=None, num='639M'):
    return public_train_status(
        num,depart,now,ops,'加賀笠間','金沢',live)[0]


class DepartureBeforeTimetableRegression(unittest.TestCase):
    def test_repro_639M_921_925_position_already_beyond_boarding(self):
        current=sample()
        self.assertEqual(status(current),'639M 未確認')
        verdict=inspect_live_leg(
            '639M','加賀笠間','金沢',DEPART,NOW,current)
        self.assertEqual(verdict['api_status'],'未確認')
        self.assertIn('時刻表と矛盾',verdict['reason'])
        self.assertEqual(verdict['from_station'],'松任')
        self.assertEqual(verdict['to_station'],'野々市')
        self.assertIn('09:21:00',verdict['observed'])
        self.assertIn('09:25:00',verdict['scheduled_depart'])

    def test_api_reports_leaving_boarding_station_before_schedule(self):
        current=sample(at='Kaga-Kasama',nxt='Nishi-Matto')
        self.assertEqual(status(current),'639M 未確認')
        verdict=inspect_live_leg(
            '639M','加賀笠間','金沢',DEPART,NOW,current)
        self.assertIn('時刻表と矛盾',verdict['reason'])

    def test_at_boarding_without_next_station_is_not_departed(self):
        current=sample(at='Kaga-Kasama',nxt='')
        self.assertEqual(status(current),'639M 正常')
        verdict=inspect_live_leg(
            '639M','加賀笠間','金沢',DEPART,NOW,current)
        self.assertIn('停車中',verdict['reason'])

    def test_approaching_boarding_station_still_normal(self):
        self.assertEqual(status(sample(at='Mikawa',nxt='Kaga-Kasama')),
                         '639M 正常')

    def test_after_departure_with_current_position_is_departed(self):
        at=datetime(2026,11,25,9,26,0,tzinfo=TZ)
        current=sample(observed=at-timedelta(seconds=20))
        self.assertEqual(status(current,now=at),'639M 発車済')

    def test_observation_before_departure_cannot_become_departed_later(self):
        at=datetime(2026,11,25,9,25,10,tzinfo=TZ)
        pre=datetime(2026,11,25,9,24,58,tzinfo=TZ)
        current=sample(observed=pre)
        self.assertEqual(status(current,now=at),'639M 未確認')

    def test_official_cancel_and_delay_override_position_conflict(self):
        current=sample()
        cancelled=TrainOperations((OperationRecord(
            '0639M','cancelled',start='*',end='*'),))
        delayed=TrainOperations((OperationRecord(
            '639M','delayed',8,start='*',end='*'),))
        self.assertEqual(status(current,ops=cancelled),'639M 取り止め')
        self.assertEqual(status(current,ops=delayed),'639M 遅延 8分')
        self.assertEqual(status(sample(delay=5)),'639M 遅延 5分')

    def test_stale_or_missing_falls_back_to_schedule(self):
        stale=sample(observed=NOW-timedelta(minutes=5))
        missing=LiveTrainState()
        self.assertEqual(status(stale),'639M 発車前')
        self.assertEqual(status(missing),'639M 発車前')
        later=datetime(2026,11,25,9,30,0,tzinfo=TZ)
        self.assertEqual(status(missing,now=later),'639M 未確認')

    def test_second_leg_uses_kanazawa_scheduled_boarding_time(self):
        current=sample(number='0433M',at='Higashi-Kanazawa',
                       nxt='Morimoto')
        depart=datetime(2026,11,25,9,50,tzinfo=TZ)
        observed=public_train_status(
            '433M',depart,NOW,None,'金沢','津幡',current)[0]
        self.assertEqual(observed,'433M 未確認')
        diagnostics=inspect_live_leg(
            '433M','金沢','津幡',depart,NOW,current)
        self.assertTrue('時刻表と矛盾' in diagnostics['reason'])

    def test_each_candidate_is_recorded_for_settings_diagnosis(self):
        t=Train(DEPART,DEPART+timedelta(minutes=35),
                line='639M / 443M',origin='加賀笠間',destination='津幡',
                transfer_arrive=DEPART+timedelta(minutes=17),
                transfer_depart=DEPART+timedelta(minutes=21),
                transfer_arrival_platform='5',transfer_departure_platform='7')
        state=TrainState([t],'時刻表(予定)','ir_schedule',NOW)
        diag=live_train_diagnostics(state,NOW,None,sample())
        self.assertEqual(len(diag),2)
        self.assertEqual(diag[0]['number'],'639M')
        self.assertEqual(diag[0]['display'],'639M 未確認')
        self.assertTrue(diag[0]['contradiction'])
        self.assertEqual(diag[0]['from_station'],'松任')
        self.assertEqual(diag[0]['to_station'],'野々市')
        self.assertEqual(diag[0]['leg'],1)
        self.assertEqual(diag[1]['boarding'],'金沢')
        self.assertEqual(diag[1]['leg'],2)
        self.assertEqual(diag[1]['display'],'443M 発車前')


if __name__=='__main__':
    unittest.main()
