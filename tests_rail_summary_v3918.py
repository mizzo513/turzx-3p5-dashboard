# SPDX-License-Identifier: GPL-3.0-or-later
"""V3.9.18: opt-in conservative summary for official rail-status notices."""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops

from rail_official_status import (
    RailNotice, LineInfo, parse_ir, parse_nanao, combine, display_notice_text,
)
from turzx_dashboard import (
    Weather, TrainState, DEFAULTS, TZ, load_settings,
    read_live_settings, render_original, notice_region,
)


IR_STORM=('ＩＲいしかわ鉄道線及びＪＲ七尾線では、強風が見込まれるため、'
          '本日（１１月１９日）、始発から終日にかけて、'
          '列車に遅れや運転見合わせがでる場合がございます。')
JR_STORM=(
    '<html><main><div>Nanao Line Possibility of Train Suspension Tomorrow '
    'Section Between Tsubata and Wakuraonsen Cause Strong Wind more</div>'
    '</main></html>')


class SummaryTextTests(unittest.TestCase):
    def test_off_keeps_exact_existing_text(self):
        text='IR：遅延・見合わせの可能性（本日・強風）　｜　七尾線：明日 運休の可能性（津幡～和倉温泉）'
        notice=RailNotice(text=text)
        self.assertEqual(display_notice_text(notice),text)
        self.assertEqual(display_notice_text(notice,False),text)
        self.assertEqual(display_notice_text(text,False),text)

    def test_on_shortens_both_real_parser_outputs_without_losing_qualifiers(self):
        ir=parse_ir({'train_state':{'title':IR_STORM}})
        jr=parse_nanao(JR_STORM)
        self.assertEqual((ir.state,jr.state),('impacted','impacted'))
        notice=combine(ir,jr)
        compact=display_notice_text(notice,True)
        self.assertLess(len(compact),len(notice.text))
        for required in ('IR','七尾線','本日','明日','強風','津幡～和倉温泉'):
            self.assertIn(required,compact)
        self.assertIn('遅延/見合わせの恐れ',compact)
        self.assertIn('運休の恐れ',compact)
        self.assertNotIn('運行情報：正常',compact)
        self.assertEqual(notice.text,combine(ir,jr).text)

    def test_certainty_line_and_scope_must_be_preserved(self):
        cases=(
            ('IR：運転見合わせ（本日・強風）','IR：見合わせ（本日・強風）'),
            ('IR：運転見合わせの可能性','IR：見合わせの恐れ'),
            ('七尾線：明日 運休の可能性（津幡～和倉温泉）',
             '七尾線：明日 運休の恐れ（津幡～和倉温泉）'),
            ('七尾線：運休（津幡～和倉温泉）',
             '七尾線：運休（津幡～和倉温泉）'),
            ('IR：影響区間未確認','IR：影響区間未確認'),
            ('IR：未確認　/　七尾線：平常','IR：未確認｜七尾線：平常'),
            ('運行情報：取得中','運行情報：取得中'),
            ('運行情報：表示OFF','運行情報：表示OFF'),
            ('七尾線：明日 運転再開（津幡～七尾）',
             '七尾線：明日 運転再開（津幡～七尾）'),
        )
        for before,expected in cases:
            with self.subTest(before=before):
                self.assertEqual(display_notice_text(before,True),expected)
        text='七尾線：15:00まで運転見合わせ（津幡～和倉温泉）'
        self.assertIn('15:00',display_notice_text(text,True))
        self.assertIn('津幡～和倉温泉',display_notice_text(text,True))

    def test_renderer_on_off_changes_only_rail_notice_pixels(self):
        now=datetime(2026,11,20,9,31,25,tzinfo=TZ)
        text='IR：遅延・見合わせの可能性（本日・強風）　｜　七尾線：明日 運休の可能性（津幡～和倉温泉）'
        notice=RailNotice(text=text)
        conf=copy.deepcopy(DEFAULTS)
        conf['rail_status_summarize']=False
        original=render_original(now,Weather(),TrainState(),conf,rail_notice=notice)
        conf['rail_status_summarize']=True
        abbreviated=render_original(now,Weather(),TrainState(),conf,rail_notice=notice)
        diff=ImageChops.difference(original,abbreviated)
        self.assertIsNotNone(diff.getbbox())
        bounds=notice_region(conf)
        outside=diff.copy()
        outside.paste((0,0,0),box=bounds)
        self.assertIsNone(outside.getbbox())
        self.assertEqual(notice.text,text)

    def test_old_settings_remain_opted_out_and_live_settings_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            saved=Path(directory)/'settings.json'
            saved.write_text(json.dumps({'layout_revision':397}),encoding='utf-8')
            with patch('turzx_dashboard.SETTINGS',saved):
                self.assertFalse(load_settings()['rail_status_summarize'])
                self.assertFalse(read_live_settings()['rail_status_summarize'])
                conf=copy.deepcopy(DEFAULTS)
                conf['rail_status_summarize']=True
                saved.write_text(json.dumps(conf),encoding='utf-8')
                self.assertTrue(read_live_settings()['rail_status_summarize'])


if __name__=='__main__':
    unittest.main()
