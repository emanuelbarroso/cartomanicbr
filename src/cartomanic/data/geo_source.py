"""Fetching and loading municipality/state geometry.

Downloads go through `geobr` and land in a `SnapshotStore` (Cartomanic's
standard pattern for anything fetched from the internet -- see
`cartomanic.engine.snapshot_store`). Rendering code never talks to geobr
directly; it asks this module for "whatever the latest snapshot says".
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import geopandas as gpd

from ..engine.snapshot_store import SnapshotStore

MUNICIPIOS_DATASET = "municipios"
ESTADOS_DATASET = "estados"

_DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent / "geo_cache"


def default_store() -> SnapshotStore:
    return SnapshotStore(_DEFAULT_CACHE_ROOT)


def fetch_municipios(year: int = 2022, *, simplified: bool = True) -> gpd.GeoDataFrame:
    """All ~5570 Brazilian municipalities in one GeoDataFrame, straight from
    geobr/IBGE. This is a network call -- the GUI runs it off the main
    thread (see `ObtainDataDialog`)."""
    import geobr

    return geobr.read_municipality(code_muni="all", year=year, simplified=simplified)


def fetch_estados(year: int = 2022, *, simplified: bool = True) -> gpd.GeoDataFrame:
    import geobr

    return geobr.read_state(year=year, simplified=simplified)


def load_municipios(store: Optional[SnapshotStore] = None) -> Optional[gpd.GeoDataFrame]:
    """The latest saved municipios snapshot, or None if nothing was ever
    obtained yet."""
    store = store or default_store()
    return store.latest(MUNICIPIOS_DATASET)


def load_estados(store: Optional[SnapshotStore] = None) -> Optional[gpd.GeoDataFrame]:
    store = store or default_store()
    return store.latest(ESTADOS_DATASET)


def load_municipios_for_state(state_abbr: str, store: Optional[SnapshotStore] = None) -> Optional[gpd.GeoDataFrame]:
    gdf = load_municipios(store)
    if gdf is None or "abbrev_state" not in gdf.columns:
        return None
    return gdf[gdf["abbrev_state"] == state_abbr]


__all__ = [
    "MUNICIPIOS_DATASET",
    "ESTADOS_DATASET",
    "default_store",
    "fetch_municipios",
    "fetch_estados",
    "load_municipios",
    "load_estados",
    "load_municipios_for_state",
]
