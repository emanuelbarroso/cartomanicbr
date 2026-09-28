"""Data > (toolbar) Adição em Série: assign a tier to many municípios of one
state at once, by moving them between two lists, then apply everything to
the project in one shot.

Nothing touches `Project` until "Renderizar" -- every >>/<< move is staged
in `self._pending` (`code_muni -> tier name, or None to clear`) so the user
can freely move municípios back and forth, switch tier/state combos to
stage changes across several tiers, and only commit once. Re-visiting a
combo already touched this session reflects the staged state, not just
what's saved in the project.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from ..data import geo_source
from ..engine.project import Project
from ._dialog_utils import center_over


class BulkTierDialog(tk.Toplevel):
    _LIST_BG = "white"
    _SEARCH_HIGHLIGHT = "#fff3b0"

    def __init__(self, master, project: Project,
                 on_rendered: Optional[Callable[[str, List[int]], None]] = None):
        super().__init__(master)
        self.title("Adição em Série")
        self.resizable(True, True)
        self.transient(master)

        self.project = project
        self.on_rendered = on_rendered
        self._pending: Dict[int, Optional[str]] = {}
        self._base_tiers: Dict[int, str] = {}
        self._left_codes: List[int] = []
        self._right_codes: List[int] = []
        self._muni_cache: Dict[str, List[Tuple[int, str]]] = {}

        self.tier_var = tk.StringVar(value="")
        self.uf_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self._refresh_base_tiers()
        self._build()
        self.geometry("640x420")
        center_over(self, master)
        self.grab_set()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="Categoria:").grid(row=0, column=0, sticky="w")
        tier_names = [""] + [t.name for t in self.project.get_scheme()]
        self.tier_combo = ttk.Combobox(
            top, textvariable=self.tier_var, state="readonly", values=tier_names, width=20
        )
        self.tier_combo.grid(row=0, column=1, padx=(6, 24))
        self.tier_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_combo_change())

        ttk.Label(top, text="Estado:").grid(row=0, column=2, sticky="w")
        self.uf_combo = ttk.Combobox(
            top, textvariable=self.uf_var, state="readonly", values=self._uf_options(), width=26
        )
        self.uf_combo.grid(row=0, column=3, padx=(6, 0))
        self.uf_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_combo_change())

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=12)

        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(3, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(body, text="Fora da categoria").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Na categoria").grid(row=0, column=3, sticky="w")

        self.left_search_var = tk.StringVar(value="")
        self.right_search_var = tk.StringVar(value="")
        left_search = ttk.Entry(body, textvariable=self.left_search_var)
        left_search.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        right_search = ttk.Entry(body, textvariable=self.right_search_var)
        right_search.grid(row=1, column=3, sticky="ew", pady=(2, 4))
        self.left_search_var.trace_add("write", lambda *_a: self._apply_search("left"))
        self.right_search_var.trace_add("write", lambda *_a: self._apply_search("right"))

        self.left_list = tk.Listbox(body, selectmode="extended", exportselection=False,
                                     state="disabled", background=self._LIST_BG)
        self.left_list.grid(row=2, column=0, sticky="nsew")
        left_sb = ttk.Scrollbar(body, orient="vertical", command=self.left_list.yview)
        left_sb.grid(row=2, column=1, sticky="ns")
        self.left_list.configure(yscrollcommand=left_sb.set)

        btns_col = ttk.Frame(body)
        btns_col.grid(row=2, column=2, padx=10)
        self.right_btn = ttk.Button(btns_col, text=">>", width=4, command=self._move_right)
        self.right_btn.pack(pady=4)
        self.left_btn = ttk.Button(btns_col, text="<<", width=4, command=self._move_left)
        self.left_btn.pack(pady=4)
        self.right_btn.state(["disabled"])
        self.left_btn.state(["disabled"])

        self.right_list = tk.Listbox(body, selectmode="extended", exportselection=False,
                                      state="disabled", background=self._LIST_BG)
        self.right_list.grid(row=2, column=3, sticky="nsew")
        right_sb = ttk.Scrollbar(body, orient="vertical", command=self.right_list.yview)
        right_sb.grid(row=2, column=4, sticky="ns")
        self.right_list.configure(yscrollcommand=right_sb.set)

        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Label(bottom, textvariable=self.status_var, foreground="#666666").pack(side="left")
        self.render_btn = ttk.Button(bottom, text="Renderizar", command=self._render)
        self.render_btn.pack(side="right")
        self.render_btn.state(["disabled"])
        ttk.Button(bottom, text="Fechar", command=self.destroy).pack(side="right", padx=(0, 6))

    def _uf_options(self) -> List[str]:
        estados = geo_source.load_estados()
        if estados is None or estados.empty or "abbrev_state" not in estados.columns:
            return [""]
        rows = estados[["abbrev_state", "name_state"]].drop_duplicates().sort_values("name_state")
        return [""] + [f"{abbr} - {name}" for abbr, name in rows.itertuples(index=False)]

    # --------------------------------------------------------------- data
    def _refresh_base_tiers(self) -> None:
        df = self.project.get_classification_df()
        self._base_tiers = {} if df.empty else dict(zip(df["code_muni"], df["tier"]))

    def _munis_for(self, uf: str) -> List[Tuple[int, str]]:
        if uf not in self._muni_cache:
            gdf = geo_source.load_municipios_for_state(uf)
            if gdf is None or gdf.empty:
                self._muni_cache[uf] = []
            else:
                rows = sorted(
                    zip(gdf["code_muni"].astype(int), gdf["name_muni"]), key=lambda r: r[1]
                )
                self._muni_cache[uf] = rows
        return self._muni_cache[uf]

    def _selected_uf(self) -> str:
        value = self.uf_var.get()
        return value.split(" - ", 1)[0] if value else ""

    def _effective_tier(self, code: int) -> Optional[str]:
        if code in self._pending:
            return self._pending[code]
        return self._base_tiers.get(code)

    # ------------------------------------------------------------ events
    def _on_combo_change(self) -> None:
        tier = self.tier_var.get()
        uf = self._selected_uf()
        active = bool(tier) and bool(uf)
        list_state = "normal" if active else "disabled"
        self.left_list.configure(state=list_state)
        self.right_list.configure(state=list_state)
        self.right_btn.state(["!disabled"] if active else ["disabled"])
        self.left_btn.state(["!disabled"] if active else ["disabled"])
        if active:
            self._load_lists(uf, tier)
        else:
            self.left_list.delete(0, "end")
            self.right_list.delete(0, "end")
            self._left_codes, self._right_codes = [], []

    def _load_lists(self, uf: str, tier: str) -> None:
        self._left_codes, self._right_codes = [], []
        self.left_list.delete(0, "end")
        self.right_list.delete(0, "end")
        for code, name in self._munis_for(uf):
            if self._effective_tier(code) == tier:
                self._right_codes.append(code)
                self.right_list.insert("end", name)
            else:
                self._left_codes.append(code)
                self.left_list.insert("end", name)
        self._apply_search("left")
        self._apply_search("right")

    # ------------------------------------------------------------ search
    def _apply_search(self, side: str) -> None:
        """As the entry above a list is typed into: jump to (select, scroll
        to) the first matching município, and give every match a light
        highlight -- this never removes/filters items, just marks them."""
        listbox = self.left_list if side == "left" else self.right_list
        query = (self.left_search_var if side == "left" else self.right_search_var).get().strip().lower()

        first_match: Optional[int] = None
        for i in range(listbox.size()):
            matches = bool(query) and listbox.get(i).lower().startswith(query)
            listbox.itemconfigure(i, background=self._SEARCH_HIGHLIGHT if matches else self._LIST_BG)
            if matches and first_match is None:
                first_match = i

        if first_match is not None:
            listbox.selection_clear(0, "end")
            listbox.selection_set(first_match)
            listbox.activate(first_match)
            listbox.see(first_match)

    def _reload_current_lists(self) -> None:
        uf, tier = self._selected_uf(), self.tier_var.get()
        if uf and tier:
            self._load_lists(uf, tier)

    def _move_right(self) -> None:
        tier = self.tier_var.get()
        sel = list(self.left_list.curselection())
        if not sel or not tier:
            return
        for i in sel:
            self._pending[self._left_codes[i]] = tier
        self._reload_current_lists()
        self._sync_render_state()

    def _move_left(self) -> None:
        sel = list(self.right_list.curselection())
        if not sel:
            return
        for i in sel:
            self._pending[self._right_codes[i]] = None
        self._reload_current_lists()
        self._sync_render_state()

    def _sync_render_state(self) -> None:
        n = len(self._pending)
        self.status_var.set(f"{n} alteração(ões) pendente(s)." if n else "")
        self.render_btn.state(["!disabled"] if n else ["disabled"])

    def _render(self) -> None:
        uf = self._selected_uf()
        touched_codes = list(self._pending.keys())
        for code, tier in self._pending.items():
            if tier is None:
                self.project.clear_classification(code)
            else:
                self.project.set_classification(code, tier)
        self._pending.clear()
        self._refresh_base_tiers()
        self._reload_current_lists()
        self.status_var.set("Aplicado.")
        self.render_btn.state(["disabled"])
        if self.on_rendered is not None and uf:
            self.on_rendered(uf, touched_codes)


__all__ = ["BulkTierDialog"]
