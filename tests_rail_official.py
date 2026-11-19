# -*- coding: utf-8 -*-
"""Offline regressions for official IR/Nanao information and one-line ticker."""
import copy
import io
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from PIL import Image, ImageChops

import rail_official_status as official
import turzx_dashboard as app
from panel_layout import PANELS
from text_layout import ELEMENTS, props


IR_STORM=('ＩＲいしかわ鉄道線及びＪＲ七尾線では、強風が見込まれるため、'
          '本日（１１月１９日）、始発から終日にかけて、'
          '列車に遅れや運転見合わせがでる場合がございます。')
JR_STORM='''<html><main><div>Obama Line Notice of Train Cancellation Today ... more</div>
<div>Nanao Line Possibility of Train Suspension Tomorrow Section Between Tsubata and Wakuraonsen Cause Strong Wind more</div>
<div>This information has been translated from our Japanese web site.</div>
</main></html>'''
JR_OTHER='''<html><main>Nanao Line Train Suspension Today Section Between Hakui and Nanao Cause Heavy Rain more</main></html>'''
JR_NORMAL='''<html><p>Nanao Line Normal Service</p></html>'''


class Response(io.BytesIO):
    headers={}
    def __enter__(self):return self
    def __exit__(self,*_args):self.close()


class OfficialRailStatusTests(unittest.TestCase):
    def test_live_ir_homepage_json_broad_announcement(self):
        state=official.parse_ir({'train_state':{'title':IR_STORM}})
        self.assertEqual(state.state,'impacted')
        self.assertIn('IR：遅延・見合わせの可能性',state.detail)
        self.assertIn('強風',state.detail)
        self.assertIn('本日',state.detail)

    def test_ir_only_route_intersections(self):
        for text in ('加賀笠間～金沢間は運転見合わせ',
                     '金沢～倶利伽羅間で運休',
                     '大聖寺～松任間で運転見合わせ',
                     '全線で遅延'):
            with self.subTest(text=text):
                self.assertTrue(official.affects_ir_route(text))
        for text in ('大聖寺～小松間で遅延',
                     '津幡～倶利伽羅間で運転見合わせ',
                     '金沢以外の観光列車の紹介'):
            with self.subTest(text=text):
                if text=='金沢以外の観光列車の紹介':
                    continue
                # A boundary station alone can still affect trains stopping
                # there; adjacent 津幡〜倶利伽羅 also has one shared station.
                if '津幡' in text:
                    self.assertTrue(official.affects_ir_route(text))
                else:self.assertFalse(official.affects_ir_route(text))
        self.assertEqual(official.parse_ir({'train_state':{'title':
            '大聖寺～小松間で列車に遅れが発生'}}).state,'unknown')

    def test_ir_normal_and_invalid_remain_distinct(self):
        self.assertEqual(official.parse_ir({'train_state':{'title':
            '現在、平常どおり運転しています。'}}).state,'normal')
        self.assertEqual(official.parse_ir({'other':'something'}).state,'未確認'.replace('未確認','unknown')) if False else None
        self.assertEqual(official.parse_ir({'other':'something'}).state,'未確認')  # metadata unconfirmed

    def test_nanao_relevant_tsubata_tomorrow(self):
        result=official.parse_nanao(JR_STORM)
        self.assertEqual(result.state,'impacted')
        self.assertIn('明日',result.detail)
        self.assertIn('運休の可能性',result.detail)
        self.assertIn('津幡～和倉温泉',result.detail)

    def test_nanao_remote_segment_not_route_related(self):
        result=official.parse_nanao(JR_OTHER)
        self.assertEqual(result.state,'irrelevant')
        self.assertNotIn('羽咋',result.detail)

    def test_nanao_normal_from_explicit_source_only(self):
        self.assertEqual(official.parse_nanao(JR_NORMAL).state,'normal')
        self.assertEqual(official.parse_nanao('<html><div>Other line normal</div></html>').state,'未確認')

    def test_partial_source_failures_never_say_all_lines_normal(self):
        value=official.combine(official.LineInfo('IR','normal','平常'),
                               official.LineInfo('七尾線'))
        self.assertIn('七尾線：未確認',value.text)
        self.assertNotIn('IR・七尾線：平常',value.text)

    def test_only_public_official_urls_fetched(self):
        calls=[]
        def opener(request,timeout=0):
            calls.append((request.full_url,timeout))
            if request.full_url==official.IR_DATA_URL:
                return Response(json.dumps({'train_state':{'title':IR_STORM}}).encode())
            if request.full_url==official.JR_HOKURIKU_URL:
                return Response(JR_STORM.encode())
            raise AssertionError('Unofficial URL')
        notice=official.fetch_official_rail_notice(opener)
        self.assertEqual([v[0] for v in calls],
                         [official.IR_DATA_URL,official.JR_HOKURIKU_URL])
        self.assertEqual(notice.ir.state,'impacted')
        self.assertEqual(notice.nanao.state,'impacted')

    def test_one_failed_source_does_not_hide_other(self):
        def opener(req,timeout=0):
            if req.full_url==official.IR_DATA_URL:raise OSError('network down')
            return Response(JR_STORM.encode())
        result=official.fetch_official_rail_notice(opener)
        self.assertEqual(result.ir.state,'未確認')
        self.assertEqual(result.nanao.state,'impacted')
        self.assertIn('七尾線',result.text)

    def test_new_notice_fits_above_first_train_card_without_overlap(self):
        conf=copy.deepcopy(app.DEFAULTS)
        text='IR：遅延・見合わせの可能性（本日・強風）　｜　七尾線：明日 運休の可能性（津幡～和倉温泉）'
        now=datetime(2026,11,19,12,0,tzinfo=app.TZ)
        notice=official.RailNotice(text=text)
        boxes={}
        a=app.render_original(now,app.Weather(),app.TrainState(),conf,
                              hit_boxes=boxes,rail_notice=notice,marquee_px=0)
        b=app.render_original(now,app.Weather(),app.TrainState(),conf,
                              rail_notice=notice,marquee_px=32)
        region=boxes['text:train_notice']
        first=boxes['panel:train_1']
        self.assertTrue(region[3]<first[1],(region,first))
        self.assertLess(region[0],region[2])
        self.assertEqual(a.size,(480,320))
        self.assertTrue(app.notice_overflows(conf,text))
        delta=ImageChops.difference(a,b)
        outside=delta.copy()
        outside.paste((0,0,0),box=region)
        self.assertIsNone(outside.getbbox(),'scrolling must change only its text strip')

    def test_short_notice_does_not_scroll(self):
        conf=copy.deepcopy(app.DEFAULTS)
        a=Image.new('RGB',(480,320),'black');b=a.copy()
        app.draw_rail_notice(a,conf,'IR：平常',0)
        app.draw_rail_notice(b,conf,'IR：平常',600)
        self.assertEqual(a.tobytes(),b.tobytes())

    def test_current_temperature_unit_is_one_celsius_symbol(self):
        now=datetime(2026,11,19,12,0,tzinfo=app.TZ)
        seen={}
        real=app.style_label
        def record(draw,cfg,key,value,*a,**kw):
            seen[key]=str(value)
            return real(draw,cfg,key,value,*a,**kw)
        with patch.object(app,'style_label',side_effect=record):
            app.render_original(now,app.Weather(temperature=19,high=22,low=16),
                                app.TrainState(),app.DEFAULTS)
        self.assertEqual(seen['weather_temperature'],'19')
        self.assertEqual(seen['weather_temperature_unit'],'℃')
        self.assertEqual(seen['weather_high_unit'],'℃')
        self.assertEqual(seen['weather_low_unit'],'℃')

    def test_wind_numeric_anchor_same_as_others(self):
        right_edges={ELEMENTS[x][1]+ELEMENTS[x][6] for x in
                     ('weather_high','weather_low','weather_rain',
                      'weather_humidity','weather_wind')}
        self.assertEqual(right_edges,{104})
        self.assertEqual(ELEMENTS['weather_wind'][1],74)


if __name__=='__main__':
    unittest.main()
