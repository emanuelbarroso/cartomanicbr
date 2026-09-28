"""Toolbar > Adicionar/Remover Estado: pick one state from a given list via
a combobox, OK/Cancel. Used for both directions -- adding hands in the
states not yet in the project, removing hands in the ones that are -- the
dialog itself doesn't know or care which; it just picks one abbreviation
and hands it back. The confirmation for "do all of them at once" and the
actual writing to the project stay in `MainWindow`.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Tuple

from ._dialog_utils import center_over


class StatePickerDialog(tk.Toplevel):
    def __init__(self, master, title: str, options: List[Tuple[str, str]], on_ok: Callable[[str], None]):
        """`options`: [(abbrev_state, name_state), ...] -- whatever the
        caller wants offered (e.g. not-yet-included states to add, or
        already-included ones to remove)."""
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)

        self.on_ok = on_ok
        self._abbrevs = [abbr for abbr, _ in options]
        labels = [f"{abbr} - {name}" for abbr, name in options]

        self.choice_var = tk.StringVar(value=labels[0] if labels else "")

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Estado:").grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(
            frm, textvariable=self.choice_var, state="readonly", values=labels, width=28
        )
        self.combo.grid(row=0, column=1, padx=(6, 0))
        if labels:
            self.combo.current(0)

        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.ok_btn = ttk.Button(btns, text="OK", command=self._on_ok)
        self.ok_btn.pack(side="right")
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(0, 6))
        if not labels:
            self.ok_btn.state(["disabled"])

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._on_ok())
        center_over(self, master)
        self.grab_set()

    def _on_ok(self) -> None:
        idx = self.combo.current()
        if idx < 0:
            return
        self.on_ok(self._abbrevs[idx])
        self.destroy()


__all__ = ["StatePickerDialog"]
