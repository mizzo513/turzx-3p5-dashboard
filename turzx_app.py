# SPDX-License-Identifier: GPL-3.0-or-later
"""Single-EXE launcher: opens settings GUI or runs background USB engine."""
from __future__ import annotations
import sys


def main():
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
