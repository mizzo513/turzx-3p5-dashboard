# SPDX-License-Identifier: GPL-3.0-or-later
"""Tkinter UI for opt-in GitHub Releases updates."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import webbrowser

from github_updater import RELEASES_PAGE, fetch_latest_release, is_newer, download_verified_update
from update_manager import install_update_package
from version_info import APP_VERSION


def check_for_updates(gui, silent=False):
    root=gui.root
    if getattr(gui, '_github_check_busy', False):
        if not silent:
            messagebox.showinfo('更新確認','GitHubへの問い合わせ中です。',parent=root)
        return
    gui._github_check_busy=True
    if not silent:
        gui.status.set('GitHub Releasesで最新バージョンを確認しています…')

    def finish(release=None, error=None):
        gui._github_check_busy=False
        if error is not None:
            if not silent:
                messagebox.showwarning('更新確認',f'最新版を確認できませんでした。\n{error}',parent=root)
                gui.status.set('GitHub更新確認失敗（表示アプリには影響ありません）')
            return
        if not is_newer(release):
            if not silent:
                messagebox.showinfo('更新確認',f'最新バージョンです（v{APP_VERSION}）',parent=root)
                gui.status.set('GitHub更新確認：最新です')
            return
        gui.status.set(f'新しいバージョン v{release.version} を利用できます')
        notes=(release.notes or '変更履歴はGitHub Releasesをご確認ください。')[:650]
        if not getattr(sys,'frozen',False):
            if not silent:
                messagebox.showinfo('更新可能',f'v{release.version} が公開されています。\n\n'
                                    'Pythonソース版で起動しています。GitHub ReleasesからEXEを取得してください。',parent=root)
                webbrowser.open(RELEASES_PAGE)
            return
        if messagebox.askyesno('TURZXの更新',
              f'新しいバージョン v{release.version} が公開されています。\n現在: v{APP_VERSION}\n\n'
              f'主な変更内容:\n{notes}\n\n自動取得して更新しますか？\n'
              '旧EXEはバックアップし、設定や時刻表は保持します。',parent=root):
            download_and_install(gui,release)

    def worker():
        try:
            release=fetch_latest_release()
            root.after(0,lambda:finish(release=release))
        except Exception as exc:
            msg=str(exc)
            try:root.after(0,lambda:finish(error=msg))
            except (RuntimeError,tk.TclError):pass

    threading.Thread(target=worker,daemon=True).start()


def download_and_install(gui,release):
    root=gui.root
    if not getattr(sys,'frozen',False):
        messagebox.showwarning('更新不可','自動置換はEXE版でのみ使用できます。',parent=root)
        return
    dialog=tk.Toplevel(root)
    dialog.title(f'v{release.version} を取得中')
    dialog.geometry('435x135')
    dialog.resizable(False,False)
    dialog.transient(root)
    dialog.grab_set()
    label=ttk.Label(dialog,text='GitHubから更新ファイルを安全に取得しています…',padding=(15,14))
    label.pack(fill='x')
    value=tk.IntVar(value=0)
    ttk.Progressbar(dialog,maximum=100,variable=value).pack(fill='x',padx=15)
    cancelled=threading.Event()
    def cancel():
        cancelled.set()
        try:label.configure(text='ダウンロードをキャンセルしています…')
        except tk.TclError:pass
    ttk.Button(dialog,text='キャンセル',command=cancel).pack(pady=8)
    dialog.protocol('WM_DELETE_WINDOW',cancel)
    staging_dir=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'TURZXDashboard'/'updates'
    destination=staging_dir/f'github_{uuid.uuid4().hex}.zip'

    def update_progress(received,total):
        try:root.after(0,lambda:value.set(round(received*100/total)))
        except (RuntimeError,tk.TclError):pass

    def complete(error=None):
        try:dialog.grab_release();dialog.destroy()
        except tk.TclError:pass
        if error is not None:
            if not cancelled.is_set():
                messagebox.showerror('更新ファイル取得失敗',str(error),parent=root)
            return
        if cancelled.is_set():
            destination.unlink(missing_ok=True)
            return
        try:
            install_update_package(gui,destination,already_confirmed=True,expected_version=release.version)
        finally:
            destination.unlink(missing_ok=True)

    def worker():
        try:
            download_verified_update(release,destination,progress=update_progress,cancelled=cancelled)
            root.after(0,complete)
        except Exception as exc:
            msg=str(exc)
            try:root.after(0,lambda:complete(error=msg))
            except (RuntimeError,tk.TclError):pass

    threading.Thread(target=worker,daemon=True).start()
