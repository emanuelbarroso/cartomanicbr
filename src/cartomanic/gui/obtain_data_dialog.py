"""Data > Obtain from Internet / Obtain from CSV.

Both dialogs are thin: the actual buffer bookkeeping (append vs. replace,
disabling append once the 5-slot buffer is full, picking which snapshot to
overwrite) lives once in `_SnapshotBufferDialog` and is shared. What differs
between sources is only *how the DataFrame is obtained* -- a threaded geobr
fetch for the internet case, a synchronous local read for CSV.
"""
from __future__ import annotations

import os
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, NamedTuple, Optional

import pandas as pd

from ..data import geo_source, ibge_source
from ..engine.snapshot_store import MAX_SNAPSHOTS, SnapshotStore
from ._dialog_utils import center_over


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "dataset"


class _SnapshotBufferDialog(tk.Toplevel):
    """Common chrome: buffer count, append/replace radios, replace target,
    status line, and the final "write snapshot" step. Subclasses supply the
    top of the form (how to pick/obtain the DataFrame) via `_build_source`
    and `_start` and call `_finish(dataset_id, df, params)` when a frame is
    ready to be written.
    """

    def __init__(self, master, title: str, store: Optional[SnapshotStore] = None,
                 on_downloaded: Optional[Callable[[str], None]] = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)

        self.store = store or geo_source.default_store()
        self.on_downloaded = on_downloaded
        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        self.mode_var = tk.StringVar(value="append")
        self.replace_target_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self._replace_ids: list[str] = []

        self._frm = ttk.Frame(self, padding=14)
        self._frm.pack(fill="both", expand=True)
        self._next_row = 0

        self._build_source(self._frm)
        self._build_buffer_controls(self._frm)

        self.bind("<Escape>", lambda _e: self.destroy())
        center_over(self, master)
        self.grab_set()
        self.refresh_buffer_state()

    # ---------------------------------------------------- layout helpers
    def _grid_row(self) -> int:
        row = self._next_row
        self._next_row += 1
        return row

    def _build_buffer_controls(self, frm: ttk.Frame) -> None:
        self.buffer_label = ttk.Label(frm, foreground="#666666")
        self.buffer_label.grid(row=self._grid_row(), column=0, columnspan=2, sticky="w", pady=(4, 10))

        modes = ttk.Frame(frm)
        modes.grid(row=self._grid_row(), column=0, columnspan=2, sticky="w")
        self.append_radio = ttk.Radiobutton(
            modes, text="Adicionar novo snapshot", value="append",
            variable=self.mode_var, command=self._on_mode_change,
        )
        self.append_radio.pack(anchor="w")
        self.replace_radio = ttk.Radiobutton(
            modes, text="Substituir snapshot existente:", value="replace",
            variable=self.mode_var, command=self._on_mode_change,
        )
        self.replace_radio.pack(anchor="w", pady=(4, 0))

        self.replace_combo = ttk.Combobox(
            frm, textvariable=self.replace_target_var, state="disabled", width=34,
        )
        self.replace_combo.grid(row=self._grid_row(), column=0, columnspan=2, sticky="w", padx=(20, 0))

        ttk.Label(frm, textvariable=self.status_var, foreground="#666666").grid(
            row=self._grid_row(), column=0, columnspan=2, sticky="w", pady=(12, 0)
        )

        btns = ttk.Frame(frm)
        btns.grid(row=self._grid_row(), column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.action_btn = ttk.Button(btns, text=self._action_label(), command=self._start)
        self.action_btn.pack(side="right")
        ttk.Button(btns, text="Fechar", command=self.destroy).pack(side="right", padx=(0, 6))

    # -------------------------------------------------- subclass contract
    def _build_source(self, frm: ttk.Frame) -> None:
        raise NotImplementedError

    def _action_label(self) -> str:
        raise NotImplementedError

    def _current_dataset_id(self) -> Optional[str]:
        raise NotImplementedError

    def _start(self) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------ buffer
    def refresh_buffer_state(self) -> None:
        dataset_id = self._current_dataset_id()
        if dataset_id is None:
            self.buffer_label.configure(text="")
            self.append_radio.state(["disabled"])
            self.replace_combo.configure(values=[], state="disabled")
            return

        snapshots = self.store.list(dataset_id)
        n = len(snapshots)
        self.buffer_label.configure(text=f"Snapshots salvos: {n}/{MAX_SNAPSHOTS}")

        can_append = n < MAX_SNAPSHOTS
        self.append_radio.state(["!disabled"] if can_append else ["disabled"])
        if not can_append and self.mode_var.get() == "append":
            self.mode_var.set("replace")

        labels = [f"{s.fetched_at:%Y-%m-%d %H:%M} ({s.row_count} linhas)" for s in snapshots]
        self._replace_ids = [s.id for s in snapshots]
        self.replace_combo.configure(values=labels)
        if labels:
            self.replace_combo.current(0)  # default: replace the oldest
        self._on_mode_change()

    def _on_mode_change(self) -> None:
        is_replace = self.mode_var.get() == "replace"
        self.replace_combo.configure(state="readonly" if is_replace else "disabled")

    def _pick_replace_target(self) -> Optional[str]:
        if self.mode_var.get() != "replace":
            return None
        idx = self.replace_combo.current()
        if idx < 0:
            messagebox.showwarning(self.title(), "Escolha qual snapshot substituir.", parent=self)
            return None
        return self._replace_ids[idx]

    def _finish(self, dataset_id: str, df, params: str) -> None:
        mode = self.mode_var.get()
        replace_id = self._pick_replace_target() if mode == "replace" else None
        if mode == "replace" and replace_id is None:
            self.action_btn.configure(state="normal")
            return
        try:
            if mode == "append":
                info = self.store.append(dataset_id, df, params=params)
            else:
                info = self.store.replace(dataset_id, replace_id, df, params=params)
        except Exception as exc:  # noqa: BLE001
            self.action_btn.configure(state="normal")
            messagebox.showerror(self.title(), f"Falha ao salvar snapshot: {exc}", parent=self)
            return

        self.status_var.set(f"Concluído: {info.row_count} linha(s) em {info.fetched_at:%Y-%m-%d %H:%M}.")
        self.action_btn.configure(state="normal")
        self.refresh_buffer_state()
        if self.on_downloaded is not None:
            self.on_downloaded(dataset_id)


# ---------------------------------------------------------------- internet
class _Dataset(NamedTuple):
    id: str
    label: str
    fetch: Callable[[], object]  # () -> DataFrame/GeoDataFrame


_INTERNET_DATASETS = [
    _Dataset(geo_source.MUNICIPIOS_DATASET, "Municípios", geo_source.fetch_municipios),
    _Dataset(ibge_source.CENSO_2022_DATASET, "População e área (Censo 2022)",
             ibge_source.fetch_censo_2022),
    _Dataset(ibge_source.ESTIMATIVAS_DATASET, "População estimada (IBGE)",
             ibge_source.fetch_estimativas),
]


class ObtainFromInternetDialog(_SnapshotBufferDialog):
    POLL_MS = 120

    def __init__(self, master, store: Optional[SnapshotStore] = None,
                 on_downloaded: Optional[Callable[[str], None]] = None):
        self.dataset_var = tk.StringVar(value=_INTERNET_DATASETS[0].label)
        super().__init__(master, "Obtain from Internet", store=store, on_downloaded=on_downloaded)

    def _build_source(self, frm: ttk.Frame) -> None:
        ttk.Label(frm, text="Tipo de dado:").grid(row=self._grid_row(), column=0, sticky="w")
        combo = ttk.Combobox(
            frm, textvariable=self.dataset_var, state="readonly", width=32,
            values=[d.label for d in _INTERNET_DATASETS],
        )
        combo.grid(row=self._next_row - 1, column=1, sticky="w", padx=(6, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_buffer_state())

    def _action_label(self) -> str:
        return "Baixar"

    def _current_dataset(self) -> _Dataset:
        label = self.dataset_var.get()
        return next(d for d in _INTERNET_DATASETS if d.label == label)

    def _current_dataset_id(self) -> Optional[str]:
        return self._current_dataset().id

    def _start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        dataset = self._current_dataset()
        if self.mode_var.get() == "replace" and self._pick_replace_target() is None:
            return

        self.action_btn.configure(state="disabled")
        self.status_var.set("Baixando (pode levar um tempo)...")

        def job() -> None:
            try:
                df = dataset.fetch()
                self._queue.put(("fetched", df))
            except Exception as exc:  # noqa: BLE001 - reported to the user
                self._queue.put(("error", exc))

        self._worker = threading.Thread(target=job, daemon=True)
        self._worker.start()
        self.after(self.POLL_MS, self._drain)

    def _drain(self) -> None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(self.POLL_MS, self._drain)
            return

        if kind == "error":
            self.status_var.set("")
            self.action_btn.configure(state="normal")
            messagebox.showerror(self.title(), f"Falha ao baixar: {payload}", parent=self)
            return

        dataset = self._current_dataset()
        self._finish(dataset.id, payload, params=f"fetched via {dataset.id}")


# --------------------------------------------------------------------- csv
class ObtainFromCsvDialog(_SnapshotBufferDialog):
    def __init__(self, master, store: Optional[SnapshotStore] = None,
                 on_downloaded: Optional[Callable[[str], None]] = None):
        self.path_var = tk.StringVar(value="")
        self.name_var = tk.StringVar(value="")
        super().__init__(master, "Obtain from CSV", store=store, on_downloaded=on_downloaded)

    def _build_source(self, frm: ttk.Frame) -> None:
        row = self._grid_row()
        ttk.Label(frm, text="Arquivo CSV:").grid(row=row, column=0, sticky="w")
        path_row = ttk.Frame(frm)
        path_row.grid(row=row, column=1, sticky="w", padx=(6, 0))
        ttk.Entry(path_row, textvariable=self.path_var, width=30, state="readonly").pack(side="left")
        ttk.Button(path_row, text="Escolher...", command=self._choose_file).pack(side="left", padx=(4, 0))

        ttk.Label(frm, text="Nome do dataset:").grid(row=self._grid_row(), column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frm, textvariable=self.name_var, width=32).grid(
            row=self._next_row - 1, column=1, sticky="w", padx=(6, 0), pady=(6, 0)
        )
        self.name_var.trace_add("write", lambda *_a: self.refresh_buffer_state())

    def _action_label(self) -> str:
        return "Importar"

    def _current_dataset_id(self) -> Optional[str]:
        name = self.name_var.get().strip()
        return _slugify(name) if name else None

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar CSV", filetypes=[("CSV", "*.csv"), ("Todos", "*.*")], parent=self,
        )
        if not path:
            return
        self.path_var.set(path)
        if not self.name_var.get().strip():
            self.name_var.set(os.path.splitext(os.path.basename(path))[0])

    def _start(self) -> None:
        path = self.path_var.get()
        if not path:
            messagebox.showwarning(self.title(), "Escolha um arquivo CSV primeiro.", parent=self)
            return
        dataset_id = self._current_dataset_id()
        if not dataset_id:
            messagebox.showwarning(self.title(), "Dê um nome ao dataset.", parent=self)
            return
        if self.mode_var.get() == "replace" and self._pick_replace_target() is None:
            return

        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.title(), f"Falha ao ler o CSV: {exc}", parent=self)
            return

        self._finish(dataset_id, df, params=f"imported from {os.path.basename(path)}")


# kept for backwards compatibility with earlier POC wiring
ObtainDataDialog = ObtainFromInternetDialog

__all__ = ["ObtainFromInternetDialog", "ObtainFromCsvDialog", "ObtainDataDialog"]
