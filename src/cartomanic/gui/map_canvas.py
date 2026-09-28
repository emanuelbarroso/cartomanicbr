"""`MapCanvas`: a thin `tk.Canvas` subclass that draws whatever the data
layer currently has -- never its own cached geometry. Ported from the
pybrmania prototype, updated to read GeoDataFrames (via `cartomanic.data`)
instead of hand-parsing GeoJSON, and to use `_projection` instead of
reimplementing the bounds/scale math per method.
"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Optional

import pandas as pd

from ..data import geo_source
from . import _projection as proj
from ._insets import split_inset_parts


class MapCanvas(tk.Canvas):
    _A4_WIDTH_POINTS = 595
    _A4_HEIGHT_POINTS = 842
    _A4_MARGIN_POINTS = 28.35  # 1 cm

    def __init__(self, master=None, a4_mode: Optional[str] = None,
                 rotation_angle: float = 0.0, **kwargs):
        kwargs.setdefault("background", "white")
        if a4_mode in ("portrait", "landscape"):
            width, height = self._A4_WIDTH_POINTS, self._A4_HEIGHT_POINTS
            if a4_mode == "landscape":
                width, height = height, width
            kwargs.setdefault("width", width)
            kwargs.setdefault("height", height)

        super().__init__(master, **kwargs)
        self.a4_mode = a4_mode
        self.rotation_angle = rotation_angle % 360.0
        self._muni_click_handler: Optional[Callable[[int], None]] = None
        self._muni_right_click_handler: Optional[Callable[[int], None]] = None
        self._hover_handler: Optional[Callable[[str], None]] = None
        self._muni_names: dict[int, tuple[str, str]] = {}   # code_muni -> (name_muni, abbrev_state)
        self._state_names: dict[str, str] = {}              # abbrev_state -> name_state
        # mainland/inset split per state: purely geometric (never depends on
        # classification), so it's cached across redraws and only dropped
        # when new geometry is obtained -- see `invalidate_geometry_cache`.
        # Was ~65% of a state's redraw time on a state the size of MG.
        self._inset_cache: dict[str, tuple[list, list]] = {}

        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", lambda e: self._on_mousewheel(e, delta=1))
        self.bind("<Button-5>", lambda e: self._on_mousewheel(e, delta=-1))

    # ------------------------------------------------------------- clicks
    def bind_municipality_click(self, handler: Optional[Callable[[int], None]]) -> None:
        """`handler(code_muni)` fires when a drawn municipality polygon is
        clicked. Polygons only carry a `code:<code_muni>` tag when they came
        from `draw_state`/`draw_painted_map` -- clicks elsewhere (state
        outlines, the country view) are silently ignored."""
        self._muni_click_handler = handler
        self.bind("<Button-1>", self._on_click, add="+")

    def _on_click(self, event) -> None:
        if self._muni_click_handler is None:
            return
        tag = self._topmost_tag(event.x, event.y, "code:")
        if tag is not None:
            self._muni_click_handler(int(tag.split(":", 1)[1]))

    def bind_municipality_right_click(self, handler: Optional[Callable[[int], None]]) -> None:
        """`handler(code_muni)` fires on a right-click over a drawn
        municipality polygon -- meant for "clear this município's category"
        regardless of which one it currently has, as a quicker alternative
        to left-clicking all the way around the cycle back to none."""
        self._muni_right_click_handler = handler
        self.bind("<Button-3>", self._on_right_click, add="+")

    def _on_right_click(self, event) -> None:
        if self._muni_right_click_handler is None:
            return
        tag = self._topmost_tag(event.x, event.y, "code:")
        if tag is not None:
            self._muni_right_click_handler(int(tag.split(":", 1)[1]))

    # -------------------------------------------------------------- hover
    def bind_hover(self, handler: Optional[Callable[[str], None]]) -> None:
        """`handler(text)` fires on every mouse move over the canvas --
        `text` is the município (+ UF) under the cursor in a state view, the
        state name in the country view, or `""` when nothing's underneath.
        Works the same way over an inset box (e.g. Fernando de Noronha) as
        over the mainland -- both carry the same tags."""
        self._hover_handler = handler
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", lambda _e: handler("") if handler else None, add="+")

    def _on_motion(self, event) -> None:
        if self._hover_handler is None:
            return
        tag = self._topmost_tag(event.x, event.y, "code:", "uf:")
        text = ""
        if tag is not None and tag.startswith("code:"):
            code = int(tag.split(":", 1)[1])
            info = self._muni_names.get(code)
            if info is not None:
                name, uf = info
                text = f"{name} - {uf}"
        elif tag is not None and tag.startswith("uf:"):
            abbr = tag.split(":", 1)[1]
            text = self._state_names.get(abbr, abbr)
        self._hover_handler(text)

    def _topmost_tag(self, x: int, y: int, *prefixes: str) -> Optional[str]:
        """The first tag starting with one of `prefixes`, on the topmost
        item touching widget-relative point `(x, y)`.

        Two corrections on top of a plain `find_overlapping`:
        - `event.x`/`event.y` are widget-relative pixels; canvas item
          coordinates are in *canvas* space, which drifts from widget space
          once the view has scrolled (`canvasx`/`canvasy` do that
          conversion). Skipping this is what made clicks land on the wrong
          municipality after any scroll.
        - `find_closest` alone can resolve to an unfilled overlay (e.g. the
          state outline drawn on top) even for a point squarely inside a
          municipality below it -- an empty `fill` still counts as "closed"
          for Tk's distance computation -- so this walks every item
          touching the point instead, topmost first.
        """
        cx, cy = self.canvasx(x), self.canvasy(y)
        items = self.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item in reversed(items):
            for tag in self.gettags(item):
                if tag.startswith(prefixes):
                    return tag
        return None

    # --------------------------------------------------------- fast paths
    def invalidate_geometry_cache(self) -> None:
        """Call after new geometry is obtained (Data > Obtain from ...) --
        the mainland/inset split cached per state would otherwise go stale
        against the replaced snapshot."""
        self._inset_cache.clear()

    def recolor_municipalities(self, colors: "dict[int, str]") -> None:
        """Update just the fill of already-drawn municipality polygons, by
        `code:<code_muni>` tag -- no geometry/projection recompute, no new
        canvas items. Only valid while the affected state is already the
        one on screen; callers fall back to a full redraw otherwise (e.g.
        switching to a state that wasn't showing)."""
        for code, color in colors.items():
            self.itemconfigure(f"code:{code}", fill=color)

    # ------------------------------------------------------------- layout
    def get_a4_usable_area(self) -> tuple[float, float]:
        if self.a4_mode == "portrait":
            return (self._A4_WIDTH_POINTS - 2 * self._A4_MARGIN_POINTS,
                     self._A4_HEIGHT_POINTS - 2 * self._A4_MARGIN_POINTS)
        if self.a4_mode == "landscape":
            return (self._A4_HEIGHT_POINTS - 2 * self._A4_MARGIN_POINTS,
                     self._A4_WIDTH_POINTS - 2 * self._A4_MARGIN_POINTS)
        return (self.winfo_width(), self.winfo_height())

    # -------------------------------------------------------------- draw
    def draw_empty(self, message: str = "MapCanvas\n(aguardando dados)") -> None:
        self.delete("all")
        self._muni_names = {}
        self._state_names = {}
        cw, ch = self.winfo_width(), self.winfo_height()
        self.create_text(cw / 2, ch / 2, text=message, fill="#b5b5b5",
                          font=("Segoe UI", 13), justify="center", tags="placeholder")

    def draw_estados(self, fill: str = "", outline: str = "black") -> None:
        self.delete("all")
        gdf = geo_source.load_estados()
        if gdf is None or gdf.empty:
            self.draw_empty("Nenhum dado de estados obtido ainda.\nUse Data > Obtain from Internet.")
            return
        self._muni_names = {}
        self._state_names = dict(zip(gdf["abbrev_state"], gdf["name_state"])) \
            if "abbrev_state" in gdf.columns and "name_state" in gdf.columns else {}
        self._draw_rows(gdf, fill=fill, outline=outline)
        self._apply_rotation_if_needed()

    def draw_state(self, state_abbr: str, fill: str = "", outline: str = "black") -> None:
        self.update_idletasks()
        self.delete("all")

        muni_gdf = geo_source.load_municipios_for_state(state_abbr)
        if muni_gdf is None or muni_gdf.empty:
            self.draw_empty(f"Sem dados para {state_abbr}.\nUse Data > Obtain from Internet.")
            return
        self._state_names = {}
        self._muni_names = self._names_lookup(muni_gdf)

        mbounds = self._draw_municipalities(state_abbr, muni_gdf, color_lookup=None, default_fill="white")
        if mbounds is not None:
            self._draw_state_outline(state_abbr, mbounds, fill=fill, outline=outline, width=2)

        self._apply_rotation_if_needed()

    def draw_painted_map(self, state_abbr: str, colors_df: pd.DataFrame, state_outline: str = "black") -> None:
        """Paint a state's municipalities per `colors_df` (`code_muni` +
        `color` columns, e.g. `Project.painted_colors_df()`). Municipalities
        absent from `colors_df` render white."""
        self.update_idletasks()
        self.delete("all")

        muni_gdf = geo_source.load_municipios_for_state(state_abbr)
        if muni_gdf is None or muni_gdf.empty:
            self.draw_empty(f"Sem dados para {state_abbr}.\nUse Data > Obtain from Internet.")
            return
        self._state_names = {}
        self._muni_names = self._names_lookup(muni_gdf)

        color_map = {}
        if colors_df is not None and "code_muni" in colors_df.columns and "color" in colors_df.columns:
            color_map = dict(zip(colors_df["code_muni"], colors_df["color"]))

        mbounds = self._draw_municipalities(
            state_abbr, muni_gdf, color_lookup=lambda code: color_map.get(code, "white"), default_fill="white"
        )
        if mbounds is not None:
            self._draw_state_outline(state_abbr, mbounds, fill="", outline=state_outline, width=3)

        self._apply_rotation_if_needed()

    # ----------------------------------------------------- insets/drawing
    _INSET_BOX_FRACTION = 0.26
    _INSET_MARGIN = 10

    def _draw_municipalities(self, state_abbr: str, muni_gdf, color_lookup, default_fill: str):
        """Draws every municipality; a distant part -- a whole municipality
        like Fernando de Noronha, or just one polygon part of a municipality
        like Vitória's share of Trindade e Martim Vaz -- is split into its
        own framed inset box instead of being left in the main fit, where
        it would otherwise force everything else down to a speck. Returns
        the mainland's own bounds so the caller can draw the state outline
        with the same projection."""
        cached = self._inset_cache.get(state_abbr)
        if cached is None:
            cached = split_inset_parts(muni_gdf)
            self._inset_cache[state_abbr] = cached
        mainland_parts, inset_parts = cached
        if not mainland_parts:
            return None

        ring_groups = [proj.polygon_rings(p.geometry) for p in mainland_parts]
        mbounds = proj.bounds(ring_groups)
        if mbounds is None:
            return None
        cw, ch = self._usable_size()
        fitted = proj.fit(cw, ch, *mbounds)
        if fitted is None:
            return None
        s, xoff, yoff = fitted
        minx, miny, _, _ = mbounds

        for part in mainland_parts:
            fill_color = color_lookup(part.code_muni) if color_lookup else default_fill
            tag = f"code:{part.code_muni}"
            for ring in proj.polygon_rings(part.geometry):
                coords = proj.ring_to_canvas_coords(ring, minx, miny, s, xoff, yoff, ch)
                if len(coords) > 4:
                    self.create_polygon(coords, fill=fill_color, outline="gray", tags=(tag,))

        if inset_parts:
            self._draw_inset_box(inset_parts, color_lookup, default_fill, cw, ch)

        return mbounds

    def _draw_inset_box(self, inset_parts, color_lookup, default_fill: str, cw: float, ch: float) -> None:
        bw = bh = min(cw, ch) * self._INSET_BOX_FRACTION
        bx = self._INSET_MARGIN
        by = ch - self._INSET_MARGIN - bh

        # opaque backing first: occludes whatever the mainland drew here
        self.create_rectangle(bx, by, bx + bw, by + bh, fill="white", outline="")

        ring_groups = [proj.polygon_rings(p.geometry) for p in inset_parts]
        ibounds = proj.bounds(ring_groups)
        if ibounds is not None:
            fitted = proj.fit(bw, bh, *ibounds, margin=0.12)
            if fitted is not None:
                s, xoff, yoff = fitted
                minx, miny, _, _ = ibounds
                for part in inset_parts:
                    fill_color = color_lookup(part.code_muni) if color_lookup else default_fill
                    tag = f"code:{part.code_muni}"
                    for ring in proj.polygon_rings(part.geometry):
                        coords = proj.ring_to_box_coords(ring, minx, miny, s, xoff, yoff, bh, bx, by)
                        if len(coords) > 4:
                            self.create_polygon(coords, fill=fill_color, outline="gray", tags=(tag,))

        self.create_rectangle(bx, by, bx + bw, by + bh, fill="", outline="#666666", width=1)
        self.create_text(bx + 4, by + 3, text="ilhas", anchor="nw",
                          font=("Segoe UI", 8), fill="#888888")

    def _draw_state_outline(self, state_abbr: str, mbounds, fill: str, outline: str, width: int) -> None:
        """Draws the state boundary ring(s) that overlap the mainland view
        (skips a distant island's own ring, already shown in its box)."""
        estados_gdf = geo_source.load_estados()
        if estados_gdf is None or "abbrev_state" not in estados_gdf.columns:
            return
        match = estados_gdf[estados_gdf["abbrev_state"] == state_abbr]
        if match.empty:
            return

        cw, ch = self._usable_size()
        fitted = proj.fit(cw, ch, *mbounds)
        if fitted is None:
            return
        s, xoff, yoff = fitted
        minx, miny, _, _ = mbounds
        minx_b, miny_b, maxx_b, maxy_b = mbounds
        margin_x, margin_y = (maxx_b - minx_b) * 0.5, (maxy_b - miny_b) * 0.5

        for geom in match.geometry:
            for ring in proj.polygon_rings(geom):
                rxs = [p[0] for p in ring]
                rys = [p[1] for p in ring]
                rcx, rcy = sum(rxs) / len(rxs), sum(rys) / len(rys)
                if not (minx_b - margin_x <= rcx <= maxx_b + margin_x
                        and miny_b - margin_y <= rcy <= maxy_b + margin_y):
                    continue  # far outside the mainland view -- e.g. an island's own ring
                coords = proj.ring_to_canvas_coords(ring, minx, miny, s, xoff, yoff, ch)
                if len(coords) > 4:
                    self.create_polygon(coords, fill=fill, outline=outline, width=width)

    def _usable_size(self) -> tuple[float, float]:
        cw, ch = self.winfo_width(), self.winfo_height()
        if cw <= 1 or ch <= 1:
            return self.get_a4_usable_area() if self.a4_mode else (500, 500)
        return cw, ch

    def _draw_rows(self, gdf, fill: str, outline: str) -> None:
        ring_groups = [proj.polygon_rings(g) for g in gdf.geometry]
        bounds = proj.bounds(ring_groups)
        if bounds is None:
            return
        cw, ch = self._usable_size()
        fitted = proj.fit(cw, ch, *bounds)
        if fitted is None:
            return
        s, xoff, yoff = fitted
        minx, miny, _, _ = bounds
        has_abbr = "abbrev_state" in gdf.columns
        for abbr, geom in zip(gdf["abbrev_state"] if has_abbr else [None] * len(gdf), gdf.geometry):
            tags = (f"uf:{abbr}",) if abbr else ()
            for ring in proj.polygon_rings(geom):
                coords = proj.ring_to_canvas_coords(ring, minx, miny, s, xoff, yoff, ch)
                if len(coords) > 4:
                    self.create_polygon(coords, fill=fill, outline=outline, tags=tags)

    @staticmethod
    def _names_lookup(muni_gdf) -> "dict[int, tuple[str, str]]":
        if "name_muni" not in muni_gdf.columns or "abbrev_state" not in muni_gdf.columns:
            return {}
        return {
            int(code): (name, uf)
            for code, name, uf in zip(muni_gdf["code_muni"], muni_gdf["name_muni"], muni_gdf["abbrev_state"])
        }

    # --------------------------------------------------------- view/zoom
    def zoom(self, factor: float) -> None:
        cw, ch = self.winfo_width(), self.winfo_height()
        if cw <= 0 or ch <= 0:
            return
        self.scale("all", cw / 2, ch / 2, factor, factor)
        self.configure(scrollregion=self.bbox("all"))

    def set_rotation(self, angle: float) -> None:
        self.rotation_angle = angle % 360.0

    def save_postscript(self, path: str) -> None:
        self.postscript(file=path)

    def _apply_rotation_if_needed(self) -> None:
        if self.rotation_angle % 360 == 0:
            return
        bbox = self.bbox("all")
        if not bbox:
            return
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        angle = math.radians(self.rotation_angle)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for item_id in self.find_all():
            coords = self.coords(item_id)
            if not coords:
                continue
            new_coords = []
            for i in range(0, len(coords), 2):
                if i + 1 >= len(coords):
                    break
                x, y = coords[i] - cx, coords[i + 1] - cy
                new_coords.extend([x * cos_a - y * sin_a + cx, x * sin_a + y * cos_a + cy])
            self.coords(item_id, *new_coords)

    def _on_mousewheel(self, event, delta: Optional[int] = None):
        """Ctrl+wheel zooms. Plain wheel does nothing: every draw already
        fits its content to the current canvas size, so there is nothing to
        pan to -- and nothing here attaches a scrollbar to show/control a
        scroll position. A bare `yview_scroll` used to run anyway, silently
        shifting the canvas's coordinate origin away from the widget's, which
        desynced every click/hover afterward (`event.x`/`event.y` are
        widget-relative; canvas item coordinates aren't, once scrolled)."""
        if delta is None:
            delta = getattr(event, "delta", 0)
        try:
            ctrl_pressed = (event.state & 0x4) != 0
        except Exception:
            ctrl_pressed = False
        if ctrl_pressed:
            self.zoom(1.1 if delta > 0 else 0.9)


__all__ = ["MapCanvas"]
