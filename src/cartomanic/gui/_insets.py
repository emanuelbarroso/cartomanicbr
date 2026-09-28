"""Detects polygon *parts* that sit far enough from a state's main body
that including them in the normal bounding-box fit would shrink everything
else down to a speck.

This operates on individual polygon parts, not whole municipalities,
because a distant island isn't always its own municipality: Fernando de
Noronha (PE) is, but Trindade e Martim Vaz is administratively just one of
Vitória's (ES) thirteen polygon parts -- the other twelve are the mainland
city. Splitting at the part level lets a single município contribute rings
to both the main map and the inset box.

Municipalities are dissolved into connected landmasses (`unary_union`); the
biggest one by area is "mainland". A part not touching it needs an actual
distance test to tell apart two very different things that both produce a
disconnected part: an ordinary near-shore island (Ilhabela/SP, Ilha de Sao
Vicente/Santos, the Abrolhos-adjacent islets off Caravelas/BA -- all within
a few tenths of a degree, some of that just simplification pulling the
coastline and the island apart) versus a genuinely remote territory
(Fernando de Noronha/PE at ~4 degrees, Trindade e Martim Vaz/ES at
~10.4-11.4 degrees). The threshold sits an order of magnitude above the
near-shore cases and comfortably below the remote ones, so it separates
the two without hardcoding any name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import geopandas as gpd
from shapely.ops import unary_union

_MIN_WATER_GAP_DEGREES = 1.0  # real gap required to call something an island, not simplification noise
_MAX_INSET_FRACTION = 0.15    # never treat more than this share of parts as insets


@dataclass(frozen=True)
class MuniPart:
    code_muni: int
    geometry: object  # a single shapely Polygon


def _explode(muni_gdf: gpd.GeoDataFrame) -> List[MuniPart]:
    parts: List[MuniPart] = []
    for code, geom in zip(muni_gdf["code_muni"], muni_gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        parts.extend(MuniPart(int(code), p) for p in polys)
    return parts


def split_inset_parts(
    muni_gdf: Optional[gpd.GeoDataFrame],
) -> Tuple[List[MuniPart], List[MuniPart]]:
    """Returns (mainland_parts, inset_parts) as flat lists of `MuniPart`.
    `inset_parts` is empty for the common case: a state where every
    municipality (and every part of every municipality) is part of one
    contiguous landmass."""
    if muni_gdf is None or muni_gdf.empty:
        return [], []

    all_parts = _explode(muni_gdf)
    if len(all_parts) < 2:
        return all_parts, []

    merged = unary_union([p.geometry for p in all_parts])
    blobs = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    mainland_blob = max(blobs, key=lambda g: g.area)

    mainland, candidates = [], []
    for part in all_parts:
        rep = part.geometry.representative_point()
        (mainland if mainland_blob.intersects(rep) else candidates).append(part)

    if not candidates:
        return all_parts, []

    confirmed = [p for p in candidates if p.geometry.distance(mainland_blob) > _MIN_WATER_GAP_DEGREES]
    if not confirmed or len(confirmed) > max(1, len(all_parts) * _MAX_INSET_FRACTION):
        return all_parts, []

    confirmed_ids = {id(p) for p in confirmed}
    mainland_final = [p for p in all_parts if id(p) not in confirmed_ids]
    return mainland_final, confirmed


__all__ = ["MuniPart", "split_inset_parts"]
