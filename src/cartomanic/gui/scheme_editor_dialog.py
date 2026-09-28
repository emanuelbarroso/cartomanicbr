"""Edit a project's classification scheme: discrete vs. hierarchical, and
the ordered list of tiers (name + color) that make it up.

A discrete scheme is a plain set of categories -- order is just display
order. A hierarchical scheme treats `sort_order` as a level: the view-mode
bar (see `view_mode_bar.py`) can then filter the map to "exactly this tier"
(=) or "this tier or higher" (>=), each município keeping its own color.
Nothing is written to the project until "Salvar".
"""
from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk
from tkinter.colorchooser import askcolor
from typing import Callable, List, Optional

from ..engine.project import DISCRETE, HIERARCHICAL, Project, Tier
from ._dialog_utils import center_over
from .gradient_dialog import GradientDialog

MAX_BULK_ADD = 50


class SchemeEditorDialog(tk.Toplevel):
    def __init__(self, master, project: Project, on_saved: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.title("Editar esquema de classificação")
        self.resizable(False, False)
        self.transient(master)

        self.project = project
        self.on_saved = on_saved
        self._tiers: list[Tier] = list(project.get_scheme())
        self.kind_var = tk.StringVar(value=project.scheme_kind)
        self.name_var = tk.StringVar(value="")

        self._build()
        self._refresh_list()
        self.bind("<Escape>", lambda _e: self.destroy())
        center_over(self, master)
        self.grab_set()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        kind_row = ttk.Frame(frm)
        kind_row.pack(fill="x")
        ttk.Label(kind_row, text="Tipo de esquema:").pack(side="left")
        ttk.Radiobutton(kind_row, text="Discreto", value=DISCRETE, variable=self.kind_var,
                         command=self._sync_gradient_button).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(kind_row, text="Hierárquico", value=HIERARCHICAL, variable=self.kind_var,
                         command=self._sync_gradient_button).pack(side="left", padx=(8, 0))

        # "botões acima" -- the toolbar that drives the tier list below it
        toolbar = ttk.Frame(frm)
        toolbar.pack(fill="x", pady=(10, 4))
        ttk.Button(toolbar, text="Adicionar", command=self._add_tier).pack(side="left")
        ttk.Button(toolbar, text="Adicionar Várias...", command=self._add_many).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Remover", command=self._remove_tier).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="↑", width=3, command=lambda: self._move(-1)).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(toolbar, text="↓", width=3, command=lambda: self._move(1)).pack(
            side="left", padx=(2, 0)
        )
        ttk.Button(toolbar, text="Cor...", command=self._edit_color).pack(side="left", padx=(12, 0))
        self.gradient_btn = ttk.Button(toolbar, text="Criar gradiente de cor...", command=self._open_gradient)
        self.gradient_btn.pack(side="left", padx=(12, 0))

        self.tree = ttk.Treeview(
            frm, columns=("color",), show="tree headings", height=8, selectmode="browse"
        )
        self.tree.heading("#0", text="Categoria (ordem)")
        self.tree.heading("color", text="Cor")
        self.tree.column("#0", width=220)
        self.tree.column("color", width=90, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        name_row = ttk.Frame(frm)
        name_row.pack(fill="x", pady=(8, 0))
        ttk.Label(name_row, text="Nome:").pack(side="left")
        name_entry = ttk.Entry(name_row, textvariable=self.name_var)
        name_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        name_entry.bind("<Return>", lambda _e: self._apply_name())
        name_entry.bind("<FocusOut>", lambda _e: self._apply_name())

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(btns, text="Salvar", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(0, 6))

    # ---------------------------------------------------------- tier list
    def _refresh_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self._tiers):
            tag = f"row{i}"
            self.tree.tag_configure(tag, background=t.color)
            self.tree.insert("", "end", iid=str(i), text=f"{i + 1}. {t.name}", values=(t.color,), tags=(tag,))
        self._sync_gradient_button()

    def _sync_gradient_button(self) -> None:
        enabled = self.kind_var.get() == HIERARCHICAL and len(self._tiers) >= 2
        self.gradient_btn.state(["!disabled"] if enabled else ["disabled"])

    def _selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _renumber(self) -> None:
        self._tiers = [Tier(t.name, t.color, i) for i, t in enumerate(self._tiers)]

    def _on_select(self) -> None:
        idx = self._selected_index()
        self.name_var.set(self._tiers[idx].name if idx is not None else "")

    # -------------------------------------------------------------- edits
    def _add_tier(self) -> None:
        name = simpledialog.askstring("Nova categoria", "Nome da categoria:", parent=self)
        if not name or not name.strip():
            return
        _, hex_color = askcolor(parent=self, title="Cor da categoria")
        color = hex_color or "#cccccc"
        self._tiers.append(Tier(name.strip(), color, len(self._tiers)))
        self._refresh_list()
        self.tree.selection_set(str(len(self._tiers) - 1))

    def _add_many(self) -> None:
        """Adds N generically-named categories (`C{posição}`, 1-based, in
        the resulting list) -- for setting up a scheme with several
        categories at once and then coloring them all together with the
        gradient tool, instead of adding and naming one at a time."""
        n = simpledialog.askinteger(
            "Adicionar várias categorias", f"Quantas categorias adicionar? (1 a {MAX_BULK_ADD})",
            parent=self, minvalue=1, maxvalue=MAX_BULK_ADD,
        )
        if not n:
            return
        for _ in range(n):
            position = len(self._tiers) + 1
            self._tiers.append(Tier(f"C{position}", "#cccccc", len(self._tiers)))
        self._refresh_list()

    def _remove_tier(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self._tiers[idx]
        self._renumber()
        self._refresh_list()

    def _move(self, delta: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        j = idx + delta
        if not 0 <= j < len(self._tiers):
            return
        self._tiers[idx], self._tiers[j] = self._tiers[j], self._tiers[idx]
        self._renumber()
        self._refresh_list()
        self.tree.selection_set(str(j))

    def _edit_color(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        t = self._tiers[idx]
        _, hex_color = askcolor(color=t.color, parent=self, title="Cor da categoria")
        if hex_color is None:
            return
        self._tiers[idx] = Tier(t.name, hex_color, t.sort_order)
        self._refresh_list()
        self.tree.selection_set(str(idx))

    def _open_gradient(self) -> None:
        if self.kind_var.get() != HIERARCHICAL or len(self._tiers) < 2:
            return
        GradientDialog(self, len(self._tiers), on_ok=self._apply_gradient)

    def _apply_gradient(self, colors: List[str]) -> None:
        self._tiers = [Tier(t.name, color, t.sort_order) for t, color in zip(self._tiers, colors)]
        self._refresh_list()

    def _apply_name(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new_name = self.name_var.get().strip()
        t = self._tiers[idx]
        if new_name and new_name != t.name:
            self._tiers[idx] = Tier(new_name, t.color, t.sort_order)
            self._refresh_list()
            self.tree.selection_set(str(idx))

    # --------------------------------------------------------------- save
    def _save(self) -> None:
        self.project.set_scheme(self._tiers)
        self.project.set_scheme_kind(self.kind_var.get())
        if self.on_saved is not None:
            self.on_saved()
        self.destroy()


__all__ = ["SchemeEditorDialog"]
