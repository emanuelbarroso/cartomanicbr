"""Shared placement helper for `tk.Toplevel` dialogs.

Without an explicit `geometry()`, Tk falls back to window-manager placement
-- on Windows this can land a fresh Toplevel at `+0+0` and, since the
process didn't already have foreground focus, it won't raise itself either.
The dialog *exists* but looks like nothing happened. Every Cartomanic
dialog should call this once its widgets are built.
"""
from __future__ import annotations

import tkinter as tk


def center_over(win: tk.Toplevel, master: tk.Misc) -> None:
    win.update_idletasks()
    mw, mh = master.winfo_width(), master.winfo_height()
    mx, my = master.winfo_rootx(), master.winfo_rooty()
    ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
    x = max(mx + (mw - ww) // 2, 0)
    y = max(my + (mh - wh) // 2, 0)
    win.geometry(f"+{x}+{y}")

    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    win.after(50, lambda: win.attributes("-topmost", False))
    win.focus_force()


__all__ = ["center_over"]
