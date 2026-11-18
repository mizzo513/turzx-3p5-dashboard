# -*- coding: utf-8 -*-
"""Checks installed runtime packages without PowerShell -c quoting issues.
This script does not access the display, Windows settings, or network.
"""
from __future__ import annotations
import argparse
import sys

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    try:
        if not ((3, 11) <= sys.version_info[:2] <= (3, 14)):
            raise RuntimeError('Python 3.11-3.14 is required')
        if sys.maxsize <= 2**32:
            raise RuntimeError('64-bit Python is required')
        import PIL
        import serial
        import tkinter
        if not args.quiet:
            print('Dependencies OK')
            print('Python:', sys.version.split()[0])
            print('Pillow:', PIL.__version__)
            print('pyserial:', getattr(serial, '__version__', getattr(serial, 'VERSION', 'installed')))
            print('tkinter:', tkinter.TkVersion)
        return 0
    except Exception as exc:
        if not args.quiet:
            print('Dependencies NOT ready:', type(exc).__name__, str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
