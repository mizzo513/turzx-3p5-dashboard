# -*- coding: utf-8 -*-
"""Train-source diagnostic: no network calls when source=ir_schedule; no USB calls."""
import json
from turzx_dashboard import load_settings, train_diagnostics, jp_now
from version_info import APP_VERSION

def main():
    cfg=load_settings()
    print('TURZX',APP_VERSION,'/ timestamp',jp_now().isoformat())
    if cfg.get('train_source')!='ir_schedule':
        print('NOTE: current source is',cfg.get('train_source'),'. For the bundled IR timetable select ir_schedule in settings.')
    result=train_diagnostics(jp_now(),cfg)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result.get('error') or not result.get('trains'):
        print('No train candidates: check source, route, timetable, and time.')
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
