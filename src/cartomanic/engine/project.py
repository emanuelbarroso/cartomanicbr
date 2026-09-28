"""The project container.

A `Project` never holds geometry -- only metadata and the small tabular data
that describes *how* municipalities are classified. The map is always
re-rendered from bundled/downloaded geometry (see `cartomanic.data`) plus
whatever this project's tables say. The project itself is a single DuckDB
file on disk (or an unsaved temp file until the user picks a location).

Classification is intentionally minimal here: one row per municipality
(current state, no history) -- the interactive scheme-design work is a
later step. `code_muni` is the IBGE code, matching the geometry data.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

PROJECT_EXT = ".cmbr"
DEFAULT_ROOT_LABEL = "Mapa Político"

DISCRETE = "discrete"
HIERARCHICAL = "hierarchical"
_SCHEME_KINDS = (DISCRETE, HIERARCHICAL)


@dataclass(frozen=True)
class Tier:
    name: str
    color: str
    sort_order: int


class Project:
    def __init__(self, name: str, description: str = "", scheme_kind: str = DISCRETE,
                 root_label: str = DEFAULT_ROOT_LABEL, *, _db_path: Optional[Path] = None):
        self.name = name
        self.description = description
        self.scheme_kind = scheme_kind
        self.root_label = root_label
        self.path: Optional[Path] = None
        self.dirty = False

        self._tmp_dir: Optional[tempfile.TemporaryDirectory] = None
        if _db_path is None:
            self._tmp_dir = tempfile.TemporaryDirectory(prefix="cartomanic_")
            _db_path = Path(self._tmp_dir.name) / f"unsaved{PROJECT_EXT}"
        self._db_path = _db_path
        self._con = duckdb.connect(str(self._db_path))
        self._init_schema()

    # --------------------------------------------------------- lifecycle
    @classmethod
    def new(cls, name: str, description: str = "", scheme_kind: str = DISCRETE) -> "Project":
        project = cls(name, description, scheme_kind)
        project._write_metadata()
        project.dirty = True
        return project

    @classmethod
    def open(cls, path: Path) -> "Project":
        path = Path(path)
        con = duckdb.connect(str(path))
        row = con.execute(
            "SELECT name, description, scheme_kind, root_label FROM project LIMIT 1"
        ).fetchone()
        con.close()
        if row is None:
            raise ValueError(f"{path} has no project metadata")
        name, description, scheme_kind, root_label = row
        project = cls(name, description, scheme_kind, root_label, _db_path=path)
        project.path = path
        return project

    def save(self) -> None:
        if self.path is None:
            raise ValueError("project has no path yet -- use save_as()")
        self._write_metadata()
        self._con.execute("CHECKPOINT")
        self.dirty = False

    def save_as(self, path: Path) -> None:
        path = Path(path)
        self._write_metadata()
        self._con.execute("CHECKPOINT")
        self._con.close()
        shutil.copyfile(self._db_path, path)
        self._db_path = path
        self._con = duckdb.connect(str(self._db_path))
        self.path = path
        self.dirty = False

    def close(self) -> None:
        self._con.close()
        if self._tmp_dir is not None:
            self._tmp_dir.cleanup()

    # ------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS project (
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                scheme_kind TEXT NOT NULL,
                root_label TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS scheme (
                tier TEXT PRIMARY KEY,
                color TEXT NOT NULL,
                sort_order INTEGER NOT NULL
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS classification (
                code_muni BIGINT PRIMARY KEY,
                tier TEXT NOT NULL,
                note TEXT,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS included_states (
                abbrev_state TEXT PRIMARY KEY
            )
            """
        )

    def _write_metadata(self) -> None:
        self._con.execute("DELETE FROM project")
        self._con.execute(
            "INSERT INTO project (name, description, scheme_kind, root_label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [self.name, self.description, self.scheme_kind, self.root_label, datetime.now(timezone.utc)],
        )

    def set_root_label(self, label: str) -> None:
        self.root_label = label.strip() or DEFAULT_ROOT_LABEL
        self.dirty = True

    # -------------------------------------------------------- states list
    def get_included_states(self) -> "list[str]":
        rows = self._con.execute(
            "SELECT abbrev_state FROM included_states ORDER BY abbrev_state"
        ).fetchall()
        return [row[0] for row in rows]

    def add_state(self, abbrev_state: str) -> None:
        self._con.execute(
            "INSERT INTO included_states (abbrev_state) VALUES (?) "
            "ON CONFLICT (abbrev_state) DO NOTHING",
            [abbrev_state],
        )
        self.dirty = True

    def add_states(self, abbrevs: "list[str]") -> None:
        if not abbrevs:
            return
        self._con.executemany(
            "INSERT INTO included_states (abbrev_state) VALUES (?) "
            "ON CONFLICT (abbrev_state) DO NOTHING",
            [(a,) for a in abbrevs],
        )
        self.dirty = True

    def remove_state(self, abbrev_state: str) -> None:
        """Only affects the navigation list -- a município already
        classified in this state keeps its classification (re-adding the
        state brings it right back), matching how `add_state` never touches
        classification either."""
        self._con.execute("DELETE FROM included_states WHERE abbrev_state = ?", [abbrev_state])
        self.dirty = True

    def remove_all_states(self) -> None:
        self._con.execute("DELETE FROM included_states")
        self.dirty = True

    # ------------------------------------------------------------ scheme
    def set_scheme(self, tiers: list[Tier]) -> None:
        self._con.execute("DELETE FROM scheme")
        self._con.executemany(
            "INSERT INTO scheme (tier, color, sort_order) VALUES (?, ?, ?)",
            [(t.name, t.color, t.sort_order) for t in tiers],
        )
        self.dirty = True

    def get_scheme(self) -> list[Tier]:
        rows = self._con.execute(
            "SELECT tier, color, sort_order FROM scheme ORDER BY sort_order"
        ).fetchall()
        return [Tier(*row) for row in rows]

    def set_scheme_kind(self, kind: str) -> None:
        if kind not in _SCHEME_KINDS:
            raise ValueError(f"unknown scheme kind {kind!r}; expected one of {_SCHEME_KINDS}")
        self.scheme_kind = kind
        self.dirty = True

    # ------------------------------------------------------ classification
    def set_classification(self, code_muni: int, tier: str, note: str = "") -> None:
        self._con.execute(
            """
            INSERT INTO classification (code_muni, tier, note, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (code_muni) DO UPDATE SET
                tier = excluded.tier, note = excluded.note, updated_at = excluded.updated_at
            """,
            [code_muni, tier, note, datetime.now(timezone.utc)],
        )
        self.dirty = True

    def clear_classification(self, code_muni: int) -> None:
        self._con.execute("DELETE FROM classification WHERE code_muni = ?", [code_muni])
        self.dirty = True

    def get_tier_for(self, code_muni: int) -> Optional[str]:
        row = self._con.execute(
            "SELECT tier FROM classification WHERE code_muni = ?", [code_muni]
        ).fetchone()
        return row[0] if row else None

    def get_classification_df(self) -> pd.DataFrame:
        return self._con.execute(
            "SELECT code_muni, tier, note, updated_at FROM classification"
        ).fetchdf()

    def import_scheme_and_classification(
        self, scheme_kind: str, tiers: "list[Tier]", code_to_tier: "dict[int, str]"
    ) -> None:
        """Wholesale replace: used by JSON import, where the file is meant
        to be a complete snapshot, not a merge on top of whatever the
        project already had classified."""
        self.set_scheme_kind(scheme_kind)
        self.set_scheme(tiers)
        self._con.execute("DELETE FROM classification")
        if code_to_tier:
            now = datetime.now(timezone.utc)
            self._con.executemany(
                "INSERT INTO classification (code_muni, tier, note, updated_at) VALUES (?, ?, '', ?)",
                [(code, tier, now) for code, tier in code_to_tier.items()],
            )
        self.dirty = True

    def painted_colors_df(self, mode: str = "all", tier: Optional[str] = None) -> pd.DataFrame:
        """`code_muni` + `color`, ready for `MapCanvas.draw_painted_map`.

        `mode`:
        - "all" (default): every classified município, each in its own
          tier's color. The only mode that makes sense for a discrete
          scheme.
        - "exact": only municípios classified exactly as `tier` ("=" view).
        - "at_least": municípios classified at `tier` or higher by
          `sort_order` ("≥" view) -- each still kept in its own tier's
          color, not merged into one. Meant for a hierarchical scheme.
        """
        where, params = "", []
        if mode == "exact" and tier is not None:
            where, params = "WHERE c.tier = ?", [tier]
        elif mode == "at_least" and tier is not None:
            where = "WHERE s.sort_order >= (SELECT sort_order FROM scheme WHERE tier = ?)"
            params = [tier]
        elif mode not in ("all", "exact", "at_least"):
            raise ValueError(f"unknown mode {mode!r}")

        return self._con.execute(
            f"""
            SELECT c.code_muni AS code_muni, s.color AS color
            FROM classification c
            JOIN scheme s ON s.tier = c.tier
            {where}
            """,
            params,
        ).fetchdf()


__all__ = ["Project", "Tier", "PROJECT_EXT", "DISCRETE", "HIERARCHICAL", "DEFAULT_ROOT_LABEL"]
