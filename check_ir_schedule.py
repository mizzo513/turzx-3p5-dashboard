"""Inspect timetable departures without using network or USB."""
from datetime import datetime, timedelta
import turzx_dashboard as app
import rail_core


def main():
    cfg=app.load_settings()
    src=rail_core.load_schedule(app.IR_SCHEDULE_PATH)
    now=app.jp_now()
    state=app.upcoming_from_ir_schedule(now,cfg)
    print('IR timetable source revision: ',src.get('revision','unknown'))
    print('Source first leg (Kaga-Kasama -> Kanazawa):',len(src['first']),'entries')
    print('Source second leg (Kanazawa -> Tsubata):',len(src['second']),'entries')
    print('Date/time JST:',now.isoformat(timespec='seconds'))
    print('Schedule-based planned departures only, no live delay/cancellation information.')
    print('Status:',state.status)
    for n,train in enumerate(state.trains,1):
        tag='(next day) ' if train.depart.date()>now.date() else ''
        print(f'{n}: {tag}{train.depart:%Y-%m-%d %H:%M} -> {train.arrive:%Y-%m-%d %H:%M}  train={train.line}  platform={train.platform or "?"}')
    if not state.trains:print('No matching trains in schedule for the next 2 days.')


if __name__=='__main__':main()
