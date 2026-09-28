"""Data/toolbar > Preview: a mockup of the current map printed on a chosen
ISO paper size (A0-A5), portrait or landscape, with an optional legend.

Reuses `MapCanvas` itself for the actual rendering (same inset boxes, same
projection) instead of duplicating that logic -- the only new work here is
laying out a scaled-down "sheet of paper" around it. `current_view` /
`view_mode` are a snapshot taken when the dialog opens; reopen it to pick
up further changes made in the main window.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

import pandas as pd

from ..engine.project import Project
from ._dialog_utils import center_over
from .map_canvas import MapCanvas

# ISO 216 series, portrait, (width_mm, height_mm)
_PAPER_SIZES_MM = {
    "A0": (841, 1189),
    "A1": (594, 841),
    "A2": (420, 594),
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
}
_PREVIEW_MAX_W = 460
_PREVIEW_MAX_H = 600
_MARGIN_FRACTION = 0.04
_LEGEND_FRACTION = 0.14
_LEGEND_MIN_PX = 44
_EMPTY_COLORS = pd.DataFrame(columns=["code_muni", "color"])


class PreviewDialog(tk.Toplevel):
    def __init__(self, master, project: Optional[Project], current_view: Optional[Tuple[str, Optional[str]]],
                 view_mode: Tuple[str, Optional[str]], source_canvas: Optional[MapCanvas] = None):
        super().__init__(master)
        self.title("Visualizar Impressão")
        self.resizable(False, False)
        self.transient(master)

        self.project = project
        self.current_view = current_view
        self.view_mode = view_mode
        # seed the preview's own inset cache from the already-drawn main
        # canvas -- avoids paying the (cached-away) mainland/inset dissolve
        # cost again just because this is a fresh MapCanvas instance
        self._seed_cache = dict(source_canvas._inset_cache) if source_canvas is not None else {}

        self.paper_var = tk.StringVar(value="A4")
        self.orientation_var = tk.StringVar(value="portrait")
        self.legend_var = tk.BooleanVar(value=True)

        self._page_frame: Optional[tk.Frame] = None
        self._preview_canvas: Optional[MapCanvas] = None

        self._build()
        self._rebuild_preview()
        center_over(self, master)
        self.grab_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        controls = ttk.Frame(frm)
        controls.pack(fill="x")
        ttk.Label(controls, text="Tamanho:").pack(side="left")
        paper_combo = ttk.Combobox(
            controls, textvariable=self.paper_var, state="readonly", width=6,
            values=list(_PAPER_SIZES_MM.keys()),
        )
        paper_combo.pack(side="left", padx=(6, 20))
        paper_combo.bind("<<ComboboxSelected>>", lambda _e: self._rebuild_preview())

        ttk.Radiobutton(controls, text="Retrato", value="portrait", variable=self.orientation_var,
                         command=self._rebuild_preview).pack(side="left")
        ttk.Radiobutton(controls, text="Paisagem", value="landscape", variable=self.orientation_var,
                         command=self._rebuild_preview).pack(side="left", padx=(8, 20))

        ttk.Checkbutton(controls, text="Mostrar legenda", variable=self.legend_var,
                         command=self._rebuild_preview).pack(side="left")

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=12)

        self._stage = ttk.Frame(frm)
        self._stage.pack(fill="both", expand=True)

        ttk.Button(frm, text="Fechar", command=self.destroy).pack(anchor="e", pady=(12, 0))

    # ------------------------------------------------------------- layout
    def _page_pixel_size(self) -> Tuple[int, int]:
        w_mm, h_mm = _PAPER_SIZES_MM[self.paper_var.get()]
        if self.orientation_var.get() == "landscape":
            w_mm, h_mm = h_mm, w_mm
        scale = min(_PREVIEW_MAX_W / w_mm, _PREVIEW_MAX_H / h_mm)
        return max(60, round(w_mm * scale)), max(60, round(h_mm * scale))

    def _rebuild_preview(self) -> None:
        if self._page_frame is not None:
            self._page_frame.destroy()

        page_w, page_h = self._page_pixel_size()
        show_legend = bool(self.legend_var.get() and self.project is not None and self.project.get_scheme())
        legend_h = max(_LEGEND_MIN_PX, round(page_h * _LEGEND_FRACTION)) if show_legend else 0
        margin = max(4, round(min(page_w, page_h) * _MARGIN_FRACTION))

        self._page_frame = tk.Frame(self._stage, width=page_w, height=page_h, background="white",
                                     highlightbackground="#999999", highlightthickness=1)
        self._page_frame.pack_propagate(False)
        self._page_frame.pack(anchor="center", pady=4)

        map_w = max(10, page_w - 2 * margin)
        map_h = max(10, page_h - legend_h - 2 * margin)
        self._preview_canvas = MapCanvas(self._page_frame, width=map_w, height=map_h)
        self._preview_canvas._inset_cache.update(self._seed_cache)
        self._preview_canvas.place(x=margin, y=margin)

        if show_legend:
            legend = tk.Frame(self._page_frame, background="white")
            legend.place(x=margin, y=page_h - legend_h - margin // 2,
                         width=page_w - 2 * margin, height=legend_h)
            self._draw_legend(legend)

        self._preview_canvas.update_idletasks()
        self._draw_map()

    def _draw_map(self) -> None:
        canvas = self._preview_canvas
        kind, value = self.current_view if self.current_view else (None, None)
        if kind == "country":
            canvas.draw_estados()
        elif kind == "state" and value:
            if self.project is not None:
                mode, tier = self.view_mode
                colors = self.project.painted_colors_df(mode=mode, tier=tier)
            else:
                colors = _EMPTY_COLORS
            canvas.draw_painted_map(value, colors)
        else:
            canvas.draw_empty("Nada selecionado\npara visualizar.")

    def _draw_legend(self, parent: tk.Frame) -> None:
        tiers = self.project.get_scheme() if self.project is not None else []
        row = ttk.Frame(parent)
        row.pack(fill="both", expand=True, padx=4, pady=4)
        for tier in tiers:
            item = tk.Frame(row, background="white")
            item.pack(side="left", padx=6)
            tk.Frame(item, width=12, height=12, background=tier.color,
                     highlightbackground="#999999", highlightthickness=1).pack(side="left")
            tk.Label(item, text=tier.name, background="white", font=("Segoe UI", 8)).pack(
                side="left", padx=(4, 0)
            )


__all__ = ["PreviewDialog"]
