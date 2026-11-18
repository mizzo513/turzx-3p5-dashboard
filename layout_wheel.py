# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure numeric mouse-wheel rules for the text/panel layout editor.

Keeping the clamping independent from Tk permits headless CI tests.
The function has NO file, USB, GUI or settings side effects.
"""
from __future__ import annotations

NUMERIC_FIELDS = frozenset(('x','y','size','w','h','radius','border_width'))


def wheel_value(name: str, current: int, direction: int, *, kind: str,
                geometry: dict, shift: bool = False) -> int:
    """Return the next valid numeric value.

    Wheel up: +1; down: -1. Shift+wheel changes by 10.
    A panel always stays fully inside the 480x320 screen.
    A text anchor stays inside its screen coordinate range.
    """
    if name not in NUMERIC_FIELDS:
        raise ValueError('The selected field is not numeric')
    if kind not in ('text','panel'):
        raise ValueError('Unknown element kind')
    if kind == 'text' and name not in ('x','y','size'):
        raise ValueError('Text has no such dimension')
    if kind == 'panel' and name == 'size':
        raise ValueError('Panel has no font size')

    if kind == 'panel':
        x = int(geometry['x'])
        y = int(geometry['y'])
        w = int(geometry['w'])
        h = int(geometry['h'])
        limits = {
            'x':(0,max(0,480-w)), 'y':(0,max(0,320-h)),
            'w':(2,max(2,480-x)), 'h':(2,max(2,320-y)),
            'radius':(0,30), 'border_width':(0,12),
        }
    else:
        limits = {'x':(0,479),'y':(0,319),'size':(8,52)}
    lo,hi = limits[name]
    delta = (1 if direction > 0 else -1) * (10 if shift else 1)
    return min(hi,max(lo,int(current)+delta))
