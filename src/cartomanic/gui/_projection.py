"""Shared helpers for turning shapely geometry into canvas coordinates.

Centralized so the state/municipality/painted-map draw paths in
`MapCanvas` don't each reimplement the same bounds-fit-and-project math
(that trio used to drift independently in the pybrmania prototype).
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

Ring = List[Tuple[float, float]]


def polygon_rings(geom) -> List[Ring]:
    """Exterior ring(s) of a shapely Polygon/MultiPolygon.

    Interior rings (holes) are not represented -- tkinter's Canvas has no
    native support for compound/holed fills, so a municipality with an
    enclave would render solid rather than punched out. Same limitation the
    old hand-rolled GeoJSON parser had, just explicit now instead of silent.
    """
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [list(geom.exterior.coords)]
    if geom.geom_type == "MultiPolygon":
        return [list(part.exterior.coords) for part in geom.geoms]
    return []


def bounds(ring_groups: Iterable[Sequence[Ring]]) -> Optional[Tuple[float, float, float, float]]:
    xs = [x for rings in ring_groups for ring in rings for x, _ in ring]
    ys = [y for rings in ring_groups for ring in rings for _, y in ring]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def fit(cw: float, ch: float, minx: float, miny: float, maxx: float, maxy: float,
        margin: float = 0.05) -> Optional[Tuple[float, float, float]]:
    """Scale + offsets so a bounding box fills (cw, ch) with a margin."""
    width = maxx - minx
    height = maxy - miny
    if width <= 0 or height <= 0:
        return None
    s = min(cw / width, ch / height) * (1 - margin)
    xoff = (cw - width * s) / 2
    yoff = (ch - height * s) / 2
    return s, xoff, yoff


def to_canvas(x: float, y: float, minx: float, miny: float, s: float,
              xoff: float, yoff: float, ch: float) -> Tuple[float, float]:
    sx = (x - minx) * s + xoff
    sy = ch - (y - miny) * s - yoff
    return sx, sy


def ring_to_canvas_coords(ring: Ring, minx: float, miny: float, s: float,
                           xoff: float, yoff: float, ch: float) -> List[float]:
    coords: List[float] = []
    for x, y in ring:
        sx, sy = to_canvas(x, y, minx, miny, s, xoff, yoff, ch)
        coords.extend([sx, sy])
    return coords


def ring_to_box_coords(ring: Ring, minx: float, miny: float, s: float, xoff: float,
                        yoff: float, box_h: float, box_x: float, box_y: float) -> List[float]:
    """Like `ring_to_canvas_coords`, but for a sub-rectangle placed at
    `(box_x, box_y)` on the canvas -- used to fit an inset (e.g. a distant
    island) into its own small framed box, independently scaled from the
    main map. `s`/`xoff`/`yoff` come from `fit(box_w, box_h, ...)`."""
    coords: List[float] = []
    for x, y in ring:
        lx, ly = to_canvas(x, y, minx, miny, s, xoff, yoff, box_h)
        coords.extend([lx + box_x, ly + box_y])
    return coords


__all__ = [
    "polygon_rings", "bounds", "fit", "to_canvas",
    "ring_to_canvas_coords", "ring_to_box_coords",
]
