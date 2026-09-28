import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from cartomanic.engine.snapshot_store import MAX_SNAPSHOTS, SnapshotStore


def _fake_municipios(n: int = 3) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"code_muni": range(n), "name_muni": [f"Muni {i}" for i in range(n)]},
        geometry=[Point(i, i) for i in range(n)],
        crs="EPSG:4674",
    )


def test_append_and_load_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path / "cache")
    info = store.append("municipios", _fake_municipios(3), params="year=2022")
    assert store.count("municipios") == 1
    loaded = store.load(info.id)
    assert isinstance(loaded, gpd.GeoDataFrame)
    assert len(loaded) == 3


def test_buffer_caps_at_five_and_append_then_fails(tmp_path):
    store = SnapshotStore(tmp_path / "cache")
    for i in range(MAX_SNAPSHOTS):
        store.append("municipios", _fake_municipios(i + 1), params=f"n={i}")
    assert store.count("municipios") == MAX_SNAPSHOTS
    assert store.can_append("municipios") is False
    with pytest.raises(ValueError):
        store.append("municipios", _fake_municipios(1))


def test_replace_keeps_buffer_size_and_updates_row(tmp_path):
    store = SnapshotStore(tmp_path / "cache")
    infos = [store.append("municipios", _fake_municipios(i + 1)) for i in range(MAX_SNAPSHOTS)]
    target = infos[0].id

    store.replace("municipios", target, _fake_municipios(99), params="replaced")

    assert store.count("municipios") == MAX_SNAPSHOTS
    reloaded = store.load(target)
    assert len(reloaded) == 99


def test_latest_is_most_recently_written(tmp_path):
    store = SnapshotStore(tmp_path / "cache")
    store.append("municipios", _fake_municipios(1))
    store.append("municipios", _fake_municipios(2))
    latest = store.latest("municipios")
    assert len(latest) == 2


def test_datasets_are_independent(tmp_path):
    store = SnapshotStore(tmp_path / "cache")
    store.append("municipios", _fake_municipios(1))
    store.append("estados", pd.DataFrame({"abbrev_state": ["SP"]}))
    assert store.count("municipios") == 1
    assert store.count("estados") == 1
    assert isinstance(store.latest("estados"), pd.DataFrame)
