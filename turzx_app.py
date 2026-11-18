# SPDX-License-Identifier: GPL-3.0-or-later
"""Single-EXE launcher: opens settings GUI or runs background USB engine."""
from __future__ import annotations
import sys


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        # Runs without a GUI window or USB hardware. Verifies that the frozen
        # bootloader can extract Python DLLs and import bundled dependencies.
        import tkinter
        from PIL import Image, ImageDraw, ImageFont
        import serial
        from datetime import datetime
        from turzx_dashboard import DEFAULTS, Weather, TrainState, render_original, TZ
        image=render_original(datetime(2026,11,18,12,0,tzinfo=TZ),
                              Weather(),TrainState(),DEFAULTS)
        if image.size!=(480,320):
            return 4
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--engine':
        # Same EXE is relaunched as background process, without an extra Python install.
        sys.argv=[sys.argv[0],*sys.argv[2:]]
        from turzx_dashboard import main as run_engine
        return run_engine()
    import tkinter as tk
    from tkinter import messagebox
    from settings_gui import SettingsWindow
    root=tk.Tk()
    try:
        SettingsWindow(root)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('TURZX起動エラー',str(exc))
        raise
    return 0


if __name__=='__main__':
    raise SystemExit(main())
