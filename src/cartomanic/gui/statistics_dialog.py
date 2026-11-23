"""Estatísticas gerais: a non-modal window that breaks the project's
classification down by category -- Brasil / Regiões / Estados tabs, in
município count, official area and population.

All the math lives in `engine.statistics`; this module only loads the
reference data (geometry attributes + IBGE numbers, cached per window),
asks the main window for the current project/view mode via `get_context`,
and renders the result. `MainWindow` calls `request_refresh()` whenever
anything that feeds the numbers changes, so the window never goes stale
(unlike the print preview, which is a snapshot).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..data import geo_source, ibge_source
from ..engine import statistics as st
from ..engine.project import HIERARCHICAL, Project
from ._dialog_utils import center_over

Context = Tuple[Optional[Project], Tuple[str, Optional[str]]]  # (project, (mode, tier))

CENSO_LABEL = "Censo 2022"
_ESTIMATIVA_PREFIX = "Estimativa "
_DASH = "—"
_SWATCH = 12

# (column id, heading, width, levels where shown)
_COLUMNS = [
    ("municipios", "Municípios", 90, st.LEVELS),
    ("pct_municipios", "%", 60, st.LEVELS),
    ("area_km2", "Área (km²)", 110, st.LEVELS),
    ("pct_area", "%", 60, st.LEVELS),
    ("populacao", "População", 110, st.LEVELS),
    ("pct_populacao", "%", 60, st.LEVELS),
    ("ufs", "UFs", 50, (st.LEVEL_BRASIL, st.LEVEL_REGIAO)),
]
_TABS = [(st.LEVEL_BRASIL, "Brasil"), (st.LEVEL_REGIAO, "Regiões"), (st.LEVEL_ESTADO, "Estados")]


# ------------------------------------------------------------- formatting
def _fmt_number(value, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return _DASH
    text = f"{value:,.{decimals}f}"
    return text.translate(str.maketrans(",.", ".,"))  # pt-BR: 1.234,5


def _fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return _DASH
    return f"{value * 100:.1f}%".replace(".", ",")


def _mode_text(project: Optional[Project], mode: str, tier: Optional[str]) -> str:
    if project is None or project.scheme_kind != HIERARCHICAL or mode == "all" or tier is None:
        return "Visualização: Tudo"
    if mode == "exact":
        return f"Visualização: = Exato ({tier})"
    return f"Visualização: ≥ Hierarquia ({tier})"


class StatisticsDialog(tk.Toplevel):
    REFRESH_DELAY_MS = 150

    def __init__(self, master, get_context: Callable[[], Context]):
        super().__init__(master)
        self.title("Estatísticas gerais")
        self.transient(master)
        self.minsize(640, 360)

        self.get_context = get_context
        self._refresh_job: Optional[str] = None
        self._munis: Optional[pd.DataFrame] = None
        self._censo: Optional[pd.DataFrame] = None
        self._estimativas: Optional[pd.DataFrame] = None
        self._universe_cache: Dict[str, pd.DataFrame] = {}
        self._swatches: Dict[str, tk.PhotoImage] = {}
        self._trees: Dict[str, ttk.Treeview] = {}

        self.pop_source_var = tk.StringVar(value=CENSO_LABEL)
        self.only_included_var = tk.BooleanVar(value=False)
        self.mode_var = tk.StringVar(value="")
        self.notes_var = tk.StringVar(value="")
        self.source_var = tk.StringVar(value="")

        self._load_reference_data()
        self._build()
        self.geometry("840x500")
        center_over(self, master)
        self._fit_on_screen(840, 500)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()

    def _fit_on_screen(self, width: int, height: int) -> None:
        """`center_over` centers by *requested* size, which is smaller than
        the size set above -- on a 1366x768 screen that pushed the bottom
        (notes, Fechar) under the taskbar. Shrink/move to stay visible."""
        margin_bottom = 80  # taskbar (~40) + title bar (~32), not counted in geometry
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(width, sw - 20), min(height, sh - margin_bottom - 20)
        x = min(max(self.winfo_x(), 0), sw - w)
        y = min(max(self.winfo_y(), 0), sh - margin_bottom - h)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="População:").pack(side="left")
        self.pop_combo = ttk.Combobox(top, textvariable=self.pop_source_var, state="readonly", width=18)
        self.pop_combo.pack(side="left", padx=(6, 18))
        self.pop_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Checkbutton(
            top, text="Só estados incluídos no projeto",
            variable=self.only_included_var, command=self.refresh,
        ).pack(side="left")
        ttk.Label(top, textvariable=self.mode_var, foreground="#666666").pack(side="right")
        self._sync_pop_options()

        self.notebook = ttk.Notebook(frm)
        self.notebook.pack(fill="both", expand=True, pady=(10, 6))
        for level, title in _TABS:
            self._trees[level] = self._build_tree(self.notebook, level, title)

        ttk.Label(frm, textvariable=self.notes_var, foreground="#8a5a00",
                  wraplength=800, justify="left").pack(fill="x")
        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Label(bottom, textvariable=self.source_var, foreground="#666666").pack(side="left")
        ttk.Button(bottom, text="Fechar", command=self.destroy).pack(side="right")

    def _build_tree(self, notebook: ttk.Notebook, level: str, title: str) -> ttk.Treeview:
        page = ttk.Frame(notebook)
        notebook.add(page, text=title)
        cols = [c for c in _COLUMNS if level in c[3]]
        tree = ttk.Treeview(page, columns=[c[0] for c in cols], selectmode="browse")
        tree.heading("#0", text="Categoria" if level == st.LEVEL_BRASIL else "Grupo / categoria")
        tree.column("#0", width=230, stretch=True)
        for cid, heading, width, _levels in cols:
            tree.heading(cid, text=heading)
            tree.column(cid, width=width, anchor="e", stretch=False)
        tree.tag_configure("group", font=("Segoe UI", 9, "bold"))
        tree.tag_configure(st.KIND_TOTAL, font=("Segoe UI", 9, "bold"))
        tree.tag_configure(st.KIND_SUBTOTAL, font=("Segoe UI", 9, "italic"))
        tree.tag_configure(st.KIND_OTHER, foreground="#666666")
        tree.tag_configure(st.KIND_NONE, foreground="#666666")
        sb = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        return tree

    # ---------------------------------------------------------------- data
    def _load_reference_data(self) -> None:
        munis = geo_source.load_municipios()
        self._munis = None if munis is None else pd.DataFrame(munis.drop(columns="geometry"))
        self._censo = ibge_source.load_censo_2022()
        self._estimativas = ibge_source.load_estimativas()
        self._universe_cache.clear()

    def reload_reference_data(self) -> None:
        """After Data > Obtain from Internet: reread everything."""
        self._load_reference_data()
        self._sync_pop_options()
        self.request_refresh()

    def _pop_options(self) -> List[str]:
        options = []
        if self._censo is not None and not self._censo.empty:
            options.append(CENSO_LABEL)
        if self._estimativas is not None and not self._estimativas.empty:
            years = sorted(self._estimativas["ano"].unique(), reverse=True)
            options += [f"{_ESTIMATIVA_PREFIX}{int(y)}" for y in years]
        return options

    def _sync_pop_options(self) -> None:
        options = self._pop_options()
        self.pop_combo.configure(values=options, state="readonly" if options else "disabled")
        if self.pop_source_var.get() not in options:
            self.pop_source_var.set(options[0] if options else "")

    def _populacao_frame(self, source: str) -> Optional[pd.DataFrame]:
        if source == CENSO_LABEL and self._censo is not None:
            return self._censo[["code_muni", "populacao"]]
        if source.startswith(_ESTIMATIVA_PREFIX) and self._estimativas is not None:
            year = int(source[len(_ESTIMATIVA_PREFIX):])
            return self._estimativas.loc[self._estimativas["ano"] == year, ["code_muni", "populacao"]]
        return None

    def _universe(self, source: str) -> Optional[pd.DataFrame]:
        if self._munis is None:
            return None
        if source not in self._universe_cache:
            area = self._censo[["code_muni", "area_km2"]] if self._censo is not None else None
            self._universe_cache[source] = st.build_universe(
                self._munis, area=area, populacao=self._populacao_frame(source)
            )
        return self._universe_cache[source]

    # ------------------------------------------------------------- refresh
    def request_refresh(self) -> None:
        """Debounced: a bulk apply or a burst of clicks triggers one recompute."""
        if not self.winfo_exists():
            return
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(self.REFRESH_DELAY_MS, self.refresh)

    def refresh(self) -> None:
        self._refresh_job = None
        project, (mode, tier) = self.get_context()
        self.mode_var.set(_mode_text(project, mode, tier))
        if project is None or project.scheme_kind != HIERARCHICAL:
            mode, tier = "all", None

        source = self.pop_source_var.get()
        universe = self._universe(source)
        if project is None or universe is None:
            for tree in self._trees.values():
                tree.delete(*tree.get_children())
            self.notes_var.set("Nenhum projeto aberto." if project is None else
                               "Nenhum dado de municípios obtido ainda. Use Data > Obtain from Internet.")
            self.source_var.set("")
            return

        df = project.get_classification_df()
        classification = {} if df.empty else dict(zip(df["code_muni"].astype("int64"), df["tier"]))
        included = project.get_included_states() if self.only_included_var.get() else None
        result = st.compute(universe, classification, project.get_scheme(),
                            mode=mode, tier=tier, included_states=included)

        for level, tree in self._trees.items():
            self._fill_tree(level, tree, result[level])

        notes = list(result.notes)
        if not result.has_area:
            notes.append("Área oficial indisponível: obtenha \"População e área (Censo 2022)\" "
                         "em Data > Obtain from Internet.")
        if not result.has_populacao:
            notes.append("População indisponível: obtenha os dados do IBGE em Data > Obtain from Internet.")
        self.notes_var.set("\n".join(notes))
        pop_src = source or "indisponível"
        self.source_var.set(f"Fonte: IBGE -- área oficial do Censo 2022; população: {pop_src}.")

    # -------------------------------------------------------------- render
    def _swatch(self, color: Optional[str]) -> str:
        if color is None or pd.isna(color) or not color:  # pandas 3 str dtype: missing is NaN
            return ""
        if color not in self._swatches:
            img = tk.PhotoImage(master=self, width=_SWATCH, height=_SWATCH)
            try:
                img.put(color, to=(0, 0, _SWATCH, _SWATCH))
            except tk.TclError:
                img.put("#cccccc", to=(0, 0, _SWATCH, _SWATCH))
            self._swatches[color] = img
        return self._swatches[color]

    @staticmethod
    def _values(row, level: str, show_pct: bool = True) -> List[str]:
        """`show_pct=False` for a region/state header row: its % would always
        be 100% of itself -- blank reads cleaner than a column of 100,0%."""
        pct = _fmt_pct if show_pct else (lambda _v: "")
        out = [
            _fmt_number(row["municipios"]), pct(row["pct_municipios"]),
            _fmt_number(row["area_km2"], 1), pct(row["pct_area"]),
            _fmt_number(row["populacao"]), pct(row["pct_populacao"]),
        ]
        if level != st.LEVEL_ESTADO:
            out.append(_fmt_number(row["ufs"]))
        return out

    def _fill_tree(self, level: str, tree: ttk.Treeview, table: pd.DataFrame) -> None:
        """Rebuild the tree, keeping which groups the user had expanded
        (item ids are stable: the group's name) and the scroll position."""
        opened = {iid for iid in tree.get_children() if tree.item(iid, "open")}
        first_time = not tree.get_children()
        yview = tree.yview()[0]
        tree.delete(*tree.get_children())

        if level == st.LEVEL_BRASIL:
            for i, row in enumerate(table.itertuples(index=False)):
                r = row._asdict()
                tree.insert("", "end", iid=f"row{i}", text=r["linha"], image=self._swatch(r["cor"]),
                            values=self._values(r, level), tags=(r["tipo"],))
        else:
            for (grupo, _ordem), part in table.groupby(["grupo", "grupo_ordem"], sort=False):
                rows = [r._asdict() for r in part.itertuples(index=False)]
                total = next(r for r in rows if r["tipo"] == st.KIND_TOTAL)
                is_open = grupo in opened or (first_time and level == st.LEVEL_REGIAO)
                tree.insert("", "end", iid=grupo, text=grupo,
                            values=self._values(total, level, show_pct=False),
                            open=is_open, tags=("group",))
                for i, r in enumerate(x for x in rows if x["tipo"] != st.KIND_TOTAL):
                    tree.insert(grupo, "end", iid=f"{grupo}/{i}", text=r["linha"],
                                image=self._swatch(r["cor"]), values=self._values(r, level),
                                tags=(r["tipo"],))
        tree.yview_moveto(yview)


__all__ = ["StatisticsDialog", "CENSO_LABEL"]
