# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.23: real observed IR positions drive per-leg status.

The payload shapes are based on the actual 2026-11-25 08:56 JST
ishi-train /api/v1/trains capture. Tests never access the network.
"""
import io
import json
import unittest
from dataclasses import replace
from datetime import datetime,timedelta
from unittest.mock import patch

from ir_live_operations import (
    ENDPOINT, LiveTrain, LiveTrainState, parse_live_feed, fetch_live_trains,
    normalize_train_number, status_for_leg, station_code,
)
from train_operations import (
    OperationRecord, TrainOperations, public_train_status, matching_record,
)
from turzx_dashboard import DEFAULTS, TZ, Weather, Train, TrainState, render_original


NOW=datetime(2026,11,25,8,56,40,tzinfo=TZ)
FRESH='2026-11-25T08:56:18+09:00'
VALID='2026-11-25T08:56:48+09:00'
PREFIX='odpt.Station:IRIshikawa.IRIshikawa.'
def train(no,where,to='null',direction='Toyama',delay='0'):
    return {
        '@type':'odpt:Train','odpt:trainNumber':no,
        '@dc:date':FRESH,'@dct:valid':VALID,
        'odpt:fromStation':PREFIX+where,
        'odpt:toStation':PREFIX+to if to!='null' else 'null',
        'odpt:railDirection':'odpt.RailDirection:IRIshikawa.'+direction,
        'odpt:delay':delay,
        'odpt:startingStation':PREFIX+'Komatsu',
        'odpt:terminalStation':PREFIX+'Kanazawa',
    }
REALISTIC=[
    train('1641M','Iburihashi'),
    train('0639M','Komatsu'),
    train('0227M','Mikawa'),
    train('1328M','Mikawa',direction='Fukui'),
    train('0637M','Matto'),
    train('3001M','Kanazawa'),
    train('0638M','Kanazawa',direction='Fukui'),
    train('0433M','Higashi-Kanazawa','Morimoto'),
    train('0530M','Kurikara','Tsubata',direction='Fukui'),
]


class OfficialIRLiveFeedTests(unittest.TestCase):
    def setUp(self):
        self.live=parse_live_feed(REALISTIC,NOW)

    def status(self,no,orig,dest,day=NOW,dep=None,ops=None,live=None):
        dep=dep or NOW+timedelta(minutes=10)
        return public_train_status(no,dep,day,ops,orig,dest,
                                   self.live if live is None else live)[0]

    def test_snapshot_is_actual_shape_and_normalizes_leading_zeroes(self):
        self.assertEqual(len(self.live.trains),9)
        self.assertEqual(normalize_train_number('0639M'),'639M')
        self.assertEqual(normalize_train_number('0000433M'),'433M')
        self.assertIsNotNone(self.live.current_matches('639M',NOW))
        self.assertIsNotNone(self.live.current_matches('0433M',NOW))
        self.assertEqual(self.live.fresh_count(NOW),9)
        self.assertEqual(station_code(PREFIX+'Kaga-Kasama'),'Kaga-Kasama')

    def test_approaching_first_boarding_station_is_normal(self):
        self.assertEqual(self.status('1641M','加賀笠間','金沢'),'1641M 正常')
        self.assertEqual(self.status('227M','加賀笠間','金沢'),'227M 正常')
        self.assertEqual(self.status('639M','加賀笠間','金沢'),'639M 正常')

    def test_current_station_is_not_passed_until_actual_movement(self):
        self.assertEqual(self.status('3001M','金沢','津幡'),'3001M 正常')
        moved=list(self.live.trains)
        idx=next(i for i,x in enumerate(moved) if x.number=='3001M')
        moved[idx]=replace(moved[idx],to_station='Higashi-Kanazawa')
        updated=LiveTrainState(tuple(moved),NOW)
        # The observed departure conflicts with a still-future timetable.
        self.assertEqual(self.status('3001M','金沢','津幡',live=updated),
                         '3001M 未確認')
        self.assertEqual(self.status(
            '3001M','金沢','津幡',live=updated,
            dep=NOW-timedelta(minutes=2)), '3001M 発車済')

    def test_passed_actual_boarding_station_is_departed(self):
        earlier=NOW-timedelta(minutes=3)
        self.assertEqual(
            self.status('637M','加賀笠間','金沢',dep=earlier),
            '637M 発車済')
        self.assertEqual(
            self.status('433M','金沢','津幡',dep=earlier),
            '433M 発車済')
        self.assertEqual(self.status('530M','金沢','津幡'),'530M 発車前')
        # 530M is opposite-direction, and can never be confirmed
        # as running for a Kanazawa->Tsubata transfer.

    def test_verified_delay_overrides_normal_and_departed(self):
        delayed=[replace(row,delay=7) if row.number=='433M' else row
                 for row in self.live.trains]
        live=LiveTrainState(tuple(delayed),NOW)
        self.assertEqual(
            self.status('0433M','金沢','津幡',live=live),'0433M 遅延 7分')
        future=TrainOperations((
            OperationRecord('1641M','delayed',9,'*','*'),))
        self.assertEqual(
            self.status('1641M','加賀笠間','金沢',ops=future),
            '1641M 遅延 9分')

    def test_official_cancellation_is_highest_priority_even_if_live(self):
        ops=TrainOperations((
            OperationRecord('1641M','cancelled',start='*',end='*'),))
        self.assertEqual(self.status('1641M','加賀笠間','金沢',ops=ops),
                         '1641M 取り止め')
        self.assertEqual(
            matching_record(TrainOperations((
                OperationRecord('0639M','cancelled',start='*',end='*'),)),
                '639M','加賀笠間','金沢').kind,'cancelled')

    def test_no_live_evidence_only_scheduled_future_or_unverified(self):
        self.assertEqual(self.status('999M','金沢','津幡'),'999M 発車前')
        past=NOW-timedelta(minutes=15)
        self.assertEqual(self.status('999M','金沢','津幡',dep=past),
                         '999M 未確認')
        self.assertEqual(self.status('1641M','加賀笠間','金沢',
                                     live=LiveTrainState(error='timeout')),
                         '1641M 発車前')

    def test_stale_future_dated_or_duplicate_data_never_proves_normal(self):
        stale=NOW+timedelta(minutes=2)
        self.assertIsNone(self.live.current_matches('1641M',stale))
        self.assertEqual(
            self.status('1641M','加賀笠間','金沢',day=stale),
            '1641M 発車前')
        tomorrow=NOW+timedelta(days=1)
        self.assertIsNone(self.live.current_matches('1641M',tomorrow))
        dup=LiveTrainState((self.live.trains[0],self.live.trains[0]),NOW)
        self.assertEqual(
            self.status('1641M','加賀笠間','金沢',live=dup),
            '1641M 発車前')

    def test_wrong_direction_unknown_station_missing_delay_no_false_normal(self):
        wrong=LiveTrainState((replace(self.live.trains[0],
                                       direction='odpt.RailDirection:IRIshikawa.Fukui'),),NOW)
        self.assertEqual(self.status('1641M','加賀笠間','金沢',live=wrong),
                         '1641M 発車前')
        missing=LiveTrainState((replace(self.live.trains[0],delay=None),),NOW)
        self.assertEqual(self.status('1641M','加賀笠間','金沢',live=missing),
                         '1641M 発車前')
        unknown=LiveTrainState((replace(self.live.trains[0],
                                         at_station='Nonexistent'),),NOW)
        self.assertEqual(self.status('1641M','加賀笠間','金沢',live=unknown),
                         '1641M 発車前')

    def test_json_timeout_errors_and_invalid_payload(self):
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        seen=[]
        def opener(req,timeout):
            seen.append((req.full_url,timeout))
            return Response(json.dumps(REALISTIC).encode('utf-8'))
        state=fetch_live_trains(opener)
        self.assertEqual(len(state.trains),9)
        self.assertEqual(seen[0][0],ENDPOINT)
        self.assertEqual(state.error,'')
        self.assertTrue(fetch_live_trains(
            lambda req,timeout: (_ for _ in ()).throw(OSError('offline'))).error)
        with self.assertRaises(ValueError):
            parse_live_feed({'wrong':'shape'})
        with self.assertRaises(ValueError):
            parse_live_feed([{}]*401)


class VisualStatusIntegrationTests(unittest.TestCase):
    def test_render_both_legs_with_first_arriving_second_departed(self):
        now=NOW
        t=Train(
            now+timedelta(minutes=8),now+timedelta(minutes=49),
            line='1641M / 433M',origin='加賀笠間',destination='津幡',
            transfer_arrive=now+timedelta(minutes=25),
            transfer_depart=now+timedelta(minutes=37),
            transfer_arrival_platform='3',transfer_departure_platform='6')
        state=TrainState([t],'時刻表(予定)','ir_schedule',now)
        recorded={}
        from turzx_dashboard import style_label
        def spy(draw,conf,key,value,*args,**kw):
            recorded[key]=str(value)
            return style_label(draw,conf,key,value,*args,**kw)
        with patch('turzx_dashboard.style_label',side_effect=spy):
            frame=render_original(now,Weather(),state,DEFAULTS,
                                  train_live=parse_live_feed(REALISTIC,now))
        self.assertEqual(frame.size,(480,320))
        self.assertEqual(recorded['train_service_first_1'],'1641M 正常')
        self.assertEqual(recorded['train_service_second_1'],'433M 未確認')
        self.assertEqual(recorded['train_transfer_platform_1'],'3→6　12分')
        for key in ['train_time_1','train_kan_arr_1','train_kan_dep_1','train_arrive_1']:
            self.assertIn(key,recorded)


if __name__=='__main__':
    unittest.main()
