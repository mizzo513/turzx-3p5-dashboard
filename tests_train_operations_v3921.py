# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.21: official train-level cancellation, status rows and compact transfer.

No live web requests; test realistic official public text with a fake opener.
"""
import io
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from PIL import ImageChops

from train_operations import (
    OperationRecord, TrainOperations, official_news_candidates,
    parse_cancelled_article, matching_record, public_train_status,
    fetch_official_train_operations,
)
from turzx_dashboard import (
    DEFAULTS,TZ,Weather,Train,TrainState,render_original,
)
from text_layout import ELEMENTS


ANNOUNCEMENT_URL='https://www.ishikawa-railway.jp/news/1304'
ANNOUNCEMENT_HTML="""<html><body>
<h3>IRいしかわ鉄道線強風に伴う運転取り止めについて</h3>
<p>11月20日(金) IRいしかわ鉄道線では、強風のため次の列車が運転取り止めとなります。</p>
<p>【下り】<br>
・643M 小松駅 9:45発 普通 金沢行 (小松駅松任駅間)<br>
・233M 敦賀駅 8:36発 普通 金沢行 (芦原温泉駅金沢駅間)<br>
・1647M 小松駅 11:45発 普通 金沢行 (全区間)<br>
・1649M 小松駅 12:45発 普通 金沢行 (全区間)<br>
・333M 福井駅 11:20発 普通 金沢行 (芦原温泉駅金沢駅間)
</p>
<p>【上り】<br>
・1646M 金沢駅 13:00発 普通 小松行 (全区間)
</p></body></html>"""
NEWS_HTML="""<html><body>
<a href="/news/1304">2026.11.20 お知らせ IRいしかわ鉄道線強風に伴う運転取り止めについて</a>
<a href="/news/1299">2026.11.20 お知らせ ファンクラブ更新について</a>
<a href="https://attacker.example/news/1000">運休</a>
</body></html>"""


class TestPublicTrainOperations(unittest.TestCase):
    def test_only_same_host_matching_announcement_links(self):
        self.assertEqual(official_news_candidates(NEWS_HTML),[ANNOUNCEMENT_URL])

    def test_exact_cancelled_numbers_and_explicit_ranges(self):
        records=parse_cancelled_article(ANNOUNCEMENT_HTML,date(2026,11,20),
                                        ANNOUNCEMENT_URL)
        codes={r.train_no for r in records}
        self.assertEqual(codes,{'643M','233M','1647M','1649M','333M','1646M'})
        operations=TrainOperations(records)
        # Explicit section 芦原温泉→金沢 covers 加賀笠間→金沢.
        self.assertIsNotNone(matching_record(
            operations,'333M','加賀笠間','金沢'))
        # It does not cancel the onward 金沢→津幡 leg.
        self.assertIsNone(matching_record(
            operations,'333M','金沢','津幡'))
        self.assertIsNotNone(matching_record(
            operations,'1649M','加賀笠間','金沢'))
        self.assertIsNotNone(matching_record(
            operations,'643M','加賀笠間','金沢'))
        self.assertIsNone(matching_record(
            operations,'1646M','金沢','津幡'))

    def test_stale_articles_and_unqualified_text_never_cancel(self):
        old=parse_cancelled_article(ANNOUNCEMENT_HTML,date(2026,11,21),
                                    ANNOUNCEMENT_URL)
        self.assertEqual(old,())
        no_range=ANNOUNCEMENT_HTML.replace(
            ' (全区間)','').replace(
            ' (芦原温泉駅金沢駅間)','').replace(
            ' (小松駅松任駅間)','')
        self.assertEqual(parse_cancelled_article(
            no_range,date(2026,11,20),ANNOUNCEMENT_URL),())

    def test_official_article_fetch_and_partial_failure(self):
        class Res(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self,*args):
                self.close()
        def opener(req,timeout):
            if req.full_url.endswith('/news/'):
                return Res(NEWS_HTML.encode('utf-8'))
            if req.full_url==ANNOUNCEMENT_URL:
                return Res(ANNOUNCEMENT_HTML.encode('utf-8'))
            raise OSError('unexpected URL '+req.full_url)
        out=fetch_official_train_operations(date(2026,11,20),opener)
        self.assertEqual(len(out.items),6)
        self.assertEqual(out.error,'')
        self.assertIsNotNone(out.fetched)
        self.assertEqual(
            fetch_official_train_operations(date(2026,11,21),opener).items,())

    def test_status_is_never_inferred_as_normal_from_schedule_only(self):
        now=datetime(2026,11,20,13,0,tzinfo=TZ)
        future=now+timedelta(minutes=25)
        past=now-timedelta(minutes=2)
        self.assertEqual(
            public_train_status('1649M',future,now)[0],'1649M 発車前')
        self.assertEqual(
            public_train_status('333M',past,now)[0],'333M 未確認')
        records=TrainOperations((
            OperationRecord('1649M','cancelled',start='*',end='*'),
            OperationRecord('443M','delayed',minutes=8,start='*',end='*'),
            OperationRecord('447M','normal',start='*',end='*')))
        self.assertEqual(
            public_train_status('1649M',future,now,records)[0],'1649M 取り止め')
        self.assertEqual(
            public_train_status('443M',past,now,records)[0],'443M 遅延 8分')
        self.assertEqual(
            public_train_status('447M',past,now,records)[0],'447M 正常')


class TestTransferCardRendering(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,20,13,5,tzinfo=TZ)
        t=self.now
        self.trains=[
            Train(
                t+timedelta(minutes=20),t+timedelta(minutes=52),
                '1649M / 445M',platform='5',origin='加賀笠間',
                destination='津幡',
                transfer_arrive=t+timedelta(minutes=37),
                transfer_depart=t+timedelta(minutes=40),
                transfer_arrival_platform='5',
                transfer_departure_platform='7'),
            Train(
                t+timedelta(minutes=40),t+timedelta(minutes=70),
                '333M / 847M',origin='加賀笠間',destination='津幡',
                transfer_arrive=t+timedelta(minutes=55),
                transfer_depart=t+timedelta(minutes=67),
                transfer_arrival_platform='3',
                transfer_departure_platform='6'),
            Train(
                t+timedelta(minutes=70),t+timedelta(minutes=104),
                '345M / 467M',origin='加賀笠間',destination='津幡',
                transfer_arrive=t+timedelta(minutes=88),
                transfer_depart=t+timedelta(minutes=88),
                transfer_arrival_platform='7',
                transfer_departure_platform='7',direct=True),
        ]
        self.weather=Weather()
        self.conf=dict(DEFAULTS)
        self.state=TrainState(self.trains,'時刻表(予定)','ir_schedule',self.now)

    def record(self,ops):
        from turzx_dashboard import style_label
        shown={}
        def spy(draw,conf,key,value,*args,**kwargs):
            shown[key]=(str(value),kwargs.get('color_override'))
            return style_label(draw,conf,key,value,*args,**kwargs)
        with patch('turzx_dashboard.style_label',side_effect=spy):
            picture=render_original(self.now,self.weather,self.state,self.conf,
                                    train_operations=ops)
        self.assertEqual(picture.size,(480,320))
        return shown,picture

    def test_status_replaces_station_labels_all_three_rows(self):
        ops=TrainOperations((
            OperationRecord('1649M','delayed',8,'*','*'),
            OperationRecord('445M','normal',start='*',end='*'),
            OperationRecord('333M','cancelled',start='*',end='*')))
        shown,picture=self.record(ops)
        for n in range(1,4):
            for name in ('station_depart','station_kan_arr',
                         'station_kan_dep','station_arrive'):
                self.assertNotIn(f'train_{name}_{n}',shown)
            self.assertIn(f'train_service_first_{n}',shown)
            self.assertIn(f'train_service_second_{n}',shown)
            for name in ('time','kan_arr','kan_dep','arrive'):
                self.assertIn(f'train_{name}_{n}',shown)
        self.assertEqual(shown['train_service_first_1'][0],'1649M 遅延 8分')
        self.assertEqual(shown['train_service_second_1'][0],'445M 正常')
        self.assertEqual(shown['train_transfer_platform_1'][0],'5→7　3分')
        self.assertEqual(shown['train_service_first_2'][0],'333M 取り止め')
        self.assertEqual(shown['train_transfer_platform_2'][0],'3→6　12分')
        self.assertEqual(shown['train_transfer_platform_3'][0],'直通')
        self.assertNotIn('番線',shown['train_transfer_platform_2'][0])
        self.assertNotIn('乗換',shown['train_transfer_platform_2'][0])

    def test_no_records_show_only_timetable_known_departure_status(self):
        shown,picture=self.record(TrainOperations())
        self.assertEqual(shown['train_service_first_1'][0],'1649M 発車前')
        self.assertEqual(shown['train_service_second_2'][0],'847M 発車前')
        self.assertIn('train_transfer_platform_3',shown)
        self.assertEqual(ELEMENTS['train_service_first_1'][1],172)
        self.assertEqual(ELEMENTS['train_service_second_1'][1],322)

    def test_official_cancel_triggers_visible_full_frame_change(self):
        baseline,original=self.record(TrainOperations())
        updated,picture=self.record(TrainOperations((
            OperationRecord('1649M','cancelled',start='*',end='*'),)))
        self.assertIsNotNone(ImageChops.difference(original,picture).getbbox())
        self.assertEqual(updated['train_service_first_1'][0],'1649M 取り止め')


if __name__=='__main__':
    unittest.main()
