"""Left-hand map navigation tree: Brasil + whichever states the caller says
to list. Geometry always comes from `geo_source` (never touched here beyond
reading it) -- which states are *shown* is the caller's call, so a brand
new project can start with none and grow one "Adicionar Estado" at a time.
Selecting a node reports what was picked; `MainWindow` decides how to paint
it and which states to pass in.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable, Iterable, Optional, Tuple

from ..data import geo_source
from ..engine.project import DEFAULT_ROOT_LABEL
from ._tooltip import Tooltip

Selection = Tuple[str, Optional[str]]  # ("country", None) | ("state", abbr)

_COUNTRY_IID = "country"


class MapTree(ttk.Frame):
    def __init__(self, parent, on_select: Optional[Callable[[Selection], None]] = None,
                 on_rename_root: Optional[Callable[[str], None]] = None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.on_select = on_select
        self.on_rename_root = on_rename_root

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew")
        self._toggle_btn = ttk.Button(toolbar, text="−", width=3, command=self._toggle_all)
        self._toggle_btn.pack(side="left", padx=2, pady=2)
        Tooltip(self._toggle_btn, "Expandir/recolher a lista de estados")

        self.tree = ttk.Treeview(self, selectmode="browse")
        self.tree.heading("#0", text=DEFAULT_ROOT_LABEL, anchor="w")
        self.tree.column("#0", width=240)
        self.tree.grid(row=1, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns")

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.refresh()

    # --------------------------------------------------------- root label
    def set_root_label(self, text: str) -> None:
        self.tree.heading("#0", text=text)

    def _on_double_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "heading":
            return
        if self.on_rename_root is None:
            return
        current = self.tree.heading("#0", "text")
        new_text = simpledialog.askstring(
            "Renomear árvore", "Nome (reflete o que este projeto está classificando):",
            initialvalue=current, parent=self,
        )
        if new_text and new_text.strip():
            self.on_rename_root(new_text.strip())

    # ------------------------------------------------------------- content
    def refresh(self, included: Optional[Iterable[str]] = None) -> None:
        """Reload: "Brasil" plus one child per abbreviation in `included`
        (any order) -- call after Data > Obtain from ... changes what's
        available, or after a state is added to/removed from the project.
        `included=None` shows every state `geo_source` knows about (used
        when there's no per-project filter to apply)."""
        self.tree.delete(*self.tree.get_children())
        estados = geo_source.load_estados()
        if estados is None or estados.empty or "abbrev_state" not in estados.columns:
            self.tree.insert("", "end", text="(Nenhum dado obtido -- use Data > Obtain from Internet)")
            return

        self.tree.insert("", "end", iid=_COUNTRY_IID, text="Brasil", open=True)
        rows = estados[["abbrev_state", "name_state"]].drop_duplicates().sort_values("name_state")
        if included is not None:
            included_set = set(included)
            rows = rows[rows["abbrev_state"].isin(included_set)]
        for abbr, name in rows.itertuples(index=False):
            self.tree.insert(_COUNTRY_IID, "end", iid=f"state:{abbr}", text=f"{abbr} - {name}")

    def _toggle_all(self) -> None:
        """Collapses/expands "Brasil" -- the states are its children now, so
        this actually does something (it didn't, back when every state sat
        as a sibling of "Brasil" with nothing nested under anything)."""
        children = self.tree.get_children("")
        if not children:
            return
        now_open = not self.tree.item(children[0], "open")
        for item in children:
            self.tree.item(item, open=now_open)
        self._toggle_btn.configure(text="−" if now_open else "+")

    # ------------------------------------------------------------ events
    def _on_tree_select(self, _event=None) -> None:
        if self.on_select is None:
            return
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid == _COUNTRY_IID:
            self.on_select(("country", None))
        elif iid.startswith("state:"):
            self.on_select(("state", iid.split(":", 1)[1]))


__all__ = ["MapTree"]
