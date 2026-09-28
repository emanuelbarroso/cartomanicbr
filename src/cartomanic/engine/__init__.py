"""Project and data-retention engine (no Tkinter, no geometry rendering)."""

from .project import DISCRETE, HIERARCHICAL, Project, Tier
from .snapshot_store import MAX_SNAPSHOTS, SnapshotInfo, SnapshotStore

__all__ = [
    "Project", "Tier", "DISCRETE", "HIERARCHICAL",
    "SnapshotStore", "SnapshotInfo", "MAX_SNAPSHOTS",
]
