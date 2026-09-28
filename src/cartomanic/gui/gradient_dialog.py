"""A 2-color gradient generator, opened from the scheme editor for a
hierarchical legend: pick a color for each end and a common recipe, watch a
live preview, and on OK get back one color per category already in the
scheme (in sort_order) -- no more hand-picking every step's color one at a
time when all you want is a smooth ramp from A to B.

Pure `colorsys` (stdlib) + `tk.Canvas` rectangles for the preview strip --
no imaging library, consistent with the rest of the GUI layer.
"""
from __future__ import annotations

import colorsys
import tkinter as tk
from tkinter import ttk
from tkinter.colorchooser import askcolor
from typing import Callable, List, Tuple

from ._dialog_utils import center_over

_RECIPES = ("rgb", "rgb_ease", "hsv_short", "hsv_long")
_RECIPE_LABELS = {
    "rgb": "Linear (RGB)",
    "rgb_ease": "Suave (RGB, ease-in-out)",
    "hsv_short": "HSV (caminho curto)",
    "hsv_long": "HSV (caminho longo)",
}


def _hex_to_rgb01(hex_color: str) -> Tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb01_to_hex(rgb: Tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


def _hue_lerp(h0: float, h1: float, t: float, long_path: bool) -> float:
    diff = h1 - h0
    is_short = abs(diff) <= 0.5
    if long_path == is_short:
        diff -= 1 if diff > 0 else -1
    return (h0 + diff * t) % 1.0


def generate_gradient(left_hex: str, right_hex: str, recipe: str, n: int) -> List[str]:
    """`n` colors from `left_hex` to `right_hex` (inclusive), per `recipe`
    (one of `_RECIPES`)."""
    if n <= 0:
        return []
    if n == 1:
        return [left_hex]

    left, right = _hex_to_rgb01(left_hex), _hex_to_rgb01(right_hex)
    h0, s0, v0 = colorsys.rgb_to_hsv(*left)
    h1, s1, v1 = colorsys.rgb_to_hsv(*right)

    colors = []
    for i in range(n):
        t = i / (n - 1)
        if recipe == "rgb":
            rgb = tuple(_lerp(left[c], right[c], t) for c in range(3))
        elif recipe == "rgb_ease":
            te = _smoothstep(t)
            rgb = tuple(_lerp(left[c], right[c], te) for c in range(3))
        elif recipe in ("hsv_short", "hsv_long"):
            h = _hue_lerp(h0, h1, t, long_path=(recipe == "hsv_long"))
            rgb = colorsys.hsv_to_rgb(h, _lerp(s0, s1, t), _lerp(v0, v1, t))
        else:
            raise ValueError(f"unknown gradient recipe {recipe!r}")
        colors.append(_rgb01_to_hex(rgb))
    return colors


class GradientDialog(tk.Toplevel):
    _PREVIEW_W = 360
    _PREVIEW_H = 36

    def __init__(self, master, n_steps: int, on_ok: Callable[[List[str]], None]):
        super().__init__(master)
        self.title("Criar Gradiente de Cor")
        self.resizable(False, False)
        self.transient(master)

        self.n_steps = n_steps
        self.on_ok = on_ok
        self.left_color = "#ffffff"
        self.right_color = "#333333"
        self.recipe_var = tk.StringVar(value=_RECIPES[0])

        self._build()
        self._update_preview()
        center_over(self, master)
        self.grab_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        colors_row = ttk.Frame(frm)
        colors_row.pack(fill="x")

        left_col = ttk.Frame(colors_row)
        left_col.pack(side="left", padx=(0, 24))
        ttk.Label(left_col, text="Cor esquerda").pack(anchor="w")
        swatch_row = ttk.Frame(left_col)
        swatch_row.pack(anchor="w", pady=(2, 0))
        self.left_swatch = tk.Label(swatch_row, text="        ", background=self.left_color,
                                     relief="solid", borderwidth=1)
        self.left_swatch.pack(side="left")
        ttk.Button(swatch_row, text="Escolher...", command=self._pick_left).pack(side="left", padx=(6, 0))

        right_col = ttk.Frame(colors_row)
        right_col.pack(side="left")
        ttk.Label(right_col, text="Cor direita").pack(anchor="w")
        swatch_row2 = ttk.Frame(right_col)
        swatch_row2.pack(anchor="w", pady=(2, 0))
        self.right_swatch = tk.Label(swatch_row2, text="        ", background=self.right_color,
                                      relief="solid", borderwidth=1)
        self.right_swatch.pack(side="left")
        ttk.Button(swatch_row2, text="Escolher...", command=self._pick_right).pack(side="left", padx=(6, 0))

        recipes_row = ttk.Frame(frm)
        recipes_row.pack(fill="x", pady=(14, 0))
        ttk.Label(recipes_row, text="Tipo de gradiente:").pack(anchor="w")
        for value in _RECIPES:
            ttk.Radiobutton(recipes_row, text=_RECIPE_LABELS[value], value=value,
                             variable=self.recipe_var, command=self._update_preview).pack(anchor="w")

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=12)

        self.preview = tk.Canvas(frm, width=self._PREVIEW_W, height=self._PREVIEW_H,
                                  highlightbackground="#999999", highlightthickness=1)
        self.preview.pack()

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(0, 6))

    # --------------------------------------------------------------- edits
    def _pick_left(self) -> None:
        _, hex_color = askcolor(color=self.left_color, parent=self, title="Cor esquerda")
        if hex_color:
            self.left_color = hex_color
            self.left_swatch.configure(background=hex_color)
            self._update_preview()

    def _pick_right(self) -> None:
        _, hex_color = askcolor(color=self.right_color, parent=self, title="Cor direita")
        if hex_color:
            self.right_color = hex_color
            self.right_swatch.configure(background=hex_color)
            self._update_preview()

    def _update_preview(self) -> None:
        """One block per category the gradient will actually be applied to
        -- not an idealized smooth ramp -- so this is exactly what "OK"
        produces, resolution included."""
        self.preview.delete("all")
        colors = generate_gradient(self.left_color, self.right_color, self.recipe_var.get(), self.n_steps)
        step_w = self._PREVIEW_W / len(colors)
        for i, color in enumerate(colors):
            x0 = i * step_w
            self.preview.create_rectangle(x0, 0, x0 + step_w, self._PREVIEW_H, fill=color, outline="#ffffff")

    def _on_ok(self) -> None:
        colors = generate_gradient(self.left_color, self.right_color, self.recipe_var.get(), self.n_steps)
        self.on_ok(colors)
        self.destroy()


__all__ = ["GradientDialog", "generate_gradient"]
