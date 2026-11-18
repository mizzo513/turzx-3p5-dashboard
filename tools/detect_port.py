# -*- coding: utf-8 -*-
"""Device selection for one-click setup. Never accesses the serial port or sends data."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from pathlib import Path
from serial.tools import list_ports

VID, PID = 0x1A86, 0x5722
SERIAL_IDS = {'USB35INCHIPSV2', 'USB35INCHIPS'}


def find_display_ports(ports):
    return sorted([p for p in ports
        if getattr(p, 'vid', None) == VID
        and getattr(p, 'pid', None) == PID
        and str(getattr(p, 'serial_number', '')).upper() in SERIAL_IDS],
        key=lambda p: p.device.upper())


def target_port(ports, old_port):
    matches = find_display_ports(ports)
    if len(matches) <= 1:
        return 'AUTO', len(matches)
    # Multiple identical devices: preserve known port if still present.
    for p in matches:
        if p.device.upper() == str(old_port).upper():
            return p.device, len(matches)
    return '', len(matches)


def update_settings(path: Path, ports):
    config=json.loads(path.read_text(encoding='utf-8-sig'))
    selected, count = target_port(ports, config.get('port', 'COM11'))
    if not selected:
        print('Multiple matching TURZX devices; please select a COM port in the GUI settings.')
        return config.get('port', 'COM11'), count
    if selected != config.get('port'):
        config['port']=selected
        temp=path.with_suffix('.json.tmp')
        with temp.open('w', encoding='utf-8') as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        os.replace(temp, path)
    if count == 1:
        print('Device found: ' + find_display_ports(ports)[0].device + ' -> AUTO mode')
    elif count == 0:
        print('No device connected; AUTO mode will retry when a compatible display is attached.')
    else:
        print('Multiple matching devices found. Current port: ' + selected)
    return selected, count


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--settings', required=True)
    args=parser.parse_args()
    path=Path(args.settings)
    if not path.is_file(): raise FileNotFoundError(path)
    selected, count=update_settings(path, list(list_ports.comports()))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
