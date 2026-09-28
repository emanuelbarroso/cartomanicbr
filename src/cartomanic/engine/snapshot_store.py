"""Retention-bounded storage for data fetched from external sources.

This is Cartomanic's standard pattern for anything downloaded rather than
authored locally (municipality geometry today; possibly other reference
datasets later). Every fetch becomes a *snapshot*: a parquet file on disk
plus one row in a DuckDB catalog recording when and how it was obtained.

At most ``MAX_SNAPSHOTS`` snapshots are kept per dataset. A caller either
*appends* a new snapshot (only allowed while there is room) or *replaces* an
existing one by id -- there is no implicit eviction, the UI is expected to
force a choice once the buffer is full.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import duckdb
import geopandas as gpd
import pandas as pd

MAX_SNAPSHOTS = 5

AnyFrame = Union[pd.DataFrame, gpd.GeoDataFrame]


@dataclass(frozen=True)
class SnapshotInfo:
    id: str
    dataset: str
    fetched_at: datetime
    row_count: int
    params: str  # freeform description of how it was fetched, e.g. "year=2022"


class SnapshotStore:
    """One store = one DuckDB catalog file + a sibling directory of parquet
    files. Holds shared reference data (e.g. municipality geometry) -- not a
    specific project's classification, which lives in :class:`Project`.
    """

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / "catalog.duckdb"
        self._files_dir = self.root / "files"
        self._files_dir.mkdir(exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------- schema
    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db_path))

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    fetched_at TIMESTAMP NOT NULL,
                    row_count BIGINT NOT NULL,
                    params TEXT NOT NULL,
                    is_geo BOOLEAN NOT NULL
                )
                """
            )

    # -------------------------------------------------------------- read
    def list(self, dataset: str) -> list[SnapshotInfo]:
        """Snapshots for *dataset*, oldest first."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, dataset, fetched_at, row_count, params FROM snapshots "
                "WHERE dataset = ? ORDER BY fetched_at ASC",
                [dataset],
            ).fetchall()
        return [SnapshotInfo(*row) for row in rows]

    def count(self, dataset: str) -> int:
        with self._connect() as con:
            row = con.execute(
                "SELECT count(*) FROM snapshots WHERE dataset = ?", [dataset]
            ).fetchone()
        return int(row[0]) if row else 0

    def can_append(self, dataset: str) -> bool:
        return self.count(dataset) < MAX_SNAPSHOTS

    def latest(self, dataset: str) -> Optional[AnyFrame]:
        snaps = self.list(dataset)
        if not snaps:
            return None
        return self.load(snaps[-1].id)

    def load(self, snapshot_id: str) -> AnyFrame:
        is_geo = self._is_geo(snapshot_id)
        path = self._files_dir / f"{snapshot_id}.parquet"
        if is_geo:
            return gpd.read_parquet(path)
        return pd.read_parquet(path)

    # ------------------------------------------------------------- write
    def append(self, dataset: str, df: AnyFrame, params: str = "") -> SnapshotInfo:
        if not self.can_append(dataset):
            raise ValueError(
                f"snapshot buffer for {dataset!r} is full ({MAX_SNAPSHOTS}); "
                "replace an existing snapshot instead"
            )
        return self._write(dataset, df, params, snapshot_id=str(uuid.uuid4()), replacing=False)

    def replace(self, dataset: str, snapshot_id: str, df: AnyFrame, params: str = "") -> SnapshotInfo:
        if self._get(dataset, snapshot_id) is None:
            raise KeyError(f"no snapshot {snapshot_id!r} for dataset {dataset!r}")
        return self._write(dataset, df, params, snapshot_id=snapshot_id, replacing=True)

    def delete(self, dataset: str, snapshot_id: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM snapshots WHERE dataset = ? AND id = ?", [dataset, snapshot_id])
        (self._files_dir / f"{snapshot_id}.parquet").unlink(missing_ok=True)

    # ---------------------------------------------------------- internals
    def _get(self, dataset: str, snapshot_id: str) -> Optional[SnapshotInfo]:
        return next((s for s in self.list(dataset) if s.id == snapshot_id), None)

    def _is_geo(self, snapshot_id: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT is_geo FROM snapshots WHERE id = ?", [snapshot_id]
            ).fetchone()
        if row is None:
            raise KeyError(f"no snapshot {snapshot_id!r}")
        return bool(row[0])

    def _write(self, dataset: str, df: AnyFrame, params: str, snapshot_id: str, replacing: bool) -> SnapshotInfo:
        is_geo = isinstance(df, gpd.GeoDataFrame)
        path = self._files_dir / f"{snapshot_id}.parquet"
        df.to_parquet(path)

        fetched_at = datetime.now(timezone.utc)
        row_count = len(df)
        with self._connect() as con:
            if replacing:
                con.execute(
                    "UPDATE snapshots SET fetched_at = ?, row_count = ?, params = ?, is_geo = ? "
                    "WHERE dataset = ? AND id = ?",
                    [fetched_at, row_count, params, is_geo, dataset, snapshot_id],
                )
            else:
                con.execute(
                    "INSERT INTO snapshots (id, dataset, fetched_at, row_count, params, is_geo) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [snapshot_id, dataset, fetched_at, row_count, params, is_geo],
                )
        return SnapshotInfo(snapshot_id, dataset, fetched_at, row_count, params)


__all__ = ["SnapshotStore", "SnapshotInfo", "MAX_SNAPSHOTS"]
