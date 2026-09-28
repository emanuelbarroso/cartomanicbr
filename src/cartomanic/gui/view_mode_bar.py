"""Visualization-mode strip: only meaningful for a hierarchical scheme.

"Tudo" shows every classified município in its own tier color (same as a
discrete scheme always does). "= Exato" isolates one tier. "≥ Hierarquia"
shows that tier and everything above it, each still in its own color -- the
same semantics as adventure-maps' cumulative "known" view.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

ViewMode = Tuple[str, Optional[str]]  # (mode, tier) -- mode in "all"/"exact"/"at_least"


class ViewModeBar(ttk.Frame):
    def __init__(self, parent, on_change: Callable[[str, Optional[str]], None], *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.on_change = on_change
        self.mode_var = tk.StringVar(value="all")
        self.tier_var = tk.StringVar(value="")

        ttk.Label(self, text="Visualização:").pack(side="left", padx=(4, 6))
        ttk.Radiobutton(self, text="Tudo", value="all", variable=self.mode_var, command=self._changed).pack(
            side="left"
        )
        ttk.Radiobutton(
            self, text="= Exato", value="exact", variable=self.mode_var, command=self._changed
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            self, text="≥ Hierarquia", value="at_least", variable=self.mode_var, command=self._changed
        ).pack(side="left", padx=(8, 0))

        self.tier_combo = ttk.Combobox(self, textvariable=self.tier_var, state="disabled", width=18)
        self.tier_combo.pack(side="left", padx=(10, 0))
        self.tier_combo.bind("<<ComboboxSelected>>", lambda _e: self._changed())

    def set_tiers(self, tier_names: List[str]) -> None:
        self.tier_combo.configure(values=tier_names)
        if tier_names and self.tier_var.get() not in tier_names:
            self.tier_var.set(tier_names[0])
        elif not tier_names:
            self.tier_var.set("")

    def _changed(self) -> None:
        is_filtered = self.mode_var.get() in ("exact", "at_least")
        self.tier_combo.configure(state="readonly" if is_filtered else "disabled")
        tier = self.tier_var.get() if is_filtered and self.tier_var.get() else None
        self.on_change(self.mode_var.get(), tier)


__all__ = ["ViewModeBar", "ViewMode"]
