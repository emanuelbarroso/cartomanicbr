"""Cartomanic's main window: menu bar, icon-only project toolbar, and a
project-tree / map-canvas split body.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

import pandas as pd

from ..data import geo_source
from ..engine import classification_io
from ..engine.project import DEFAULT_ROOT_LABEL, HIERARCHICAL, PROJECT_EXT, Project
from ._icons import glyph, icon_family, icon_font
from ._tooltip import Tooltip
from .bulk_tier_dialog import BulkTierDialog
from .map_canvas import MapCanvas
from .map_tree import MapTree, Selection
from .obtain_data_dialog import ObtainFromCsvDialog, ObtainFromInternetDialog
from .preview_dialog import PreviewDialog
from .scheme_editor_dialog import SchemeEditorDialog
from .state_picker_dialog import StatePickerDialog
from .view_mode_bar import ViewMode, ViewModeBar

APP_TITLE = "Cartomanic BR"
_PROJECT_TYPES = [("Projeto Cartomanic BR", f"*{PROJECT_EXT}"), ("Todos", "*.*")]
_EMPTY_COLORS = pd.DataFrame(columns=["code_muni", "color"])


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x680")
        self.minsize(720, 480)

        self.project: Optional[Project] = None
        self._current_view: Optional[Selection] = None
        self._view_mode: ViewMode = ("all", None)
        self._icon_font = icon_font(self, 14)
        self.status_var = tk.StringVar(value="Pronto.")
        self._resize_job: Optional[str] = None

        self._build_menu()
        self._build_toolbar()
        self.view_mode_bar = ViewModeBar(self, on_change=self._on_view_mode_change)
        self._build_body()
        self._build_statusbar()
        self._sync_title()
        self._sync_layout()
        self._sync_root_label()
        self._sync_map_tree()
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

    # ------------------------------------------------------------------ UI
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Project", command=self._project_open)
        file_menu.add_command(label="Close Project", command=self._project_close)
        file_menu.add_separator()
        file_menu.add_command(label="Save Project", command=self._project_save)
        file_menu.add_command(label="Save Project As...", command=self._project_save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_quit)
        menubar.add_cascade(label="File", menu=file_menu)

        data_menu = tk.Menu(menubar, tearoff=0)
        data_menu.add_command(label="Obtain from Internet...", command=self._open_obtain_from_internet)
        data_menu.add_command(label="Obtain from CSV...", command=self._open_obtain_from_csv)
        data_menu.add_separator()
        data_menu.add_command(label="Export JSON", command=self._export_classification_json)
        data_menu.add_command(label="Import JSON", command=self._import_classification_json)
        menubar.add_cascade(label="Data", menu=data_menu)

        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=(6, 2))

        style = ttk.Style(self)
        style.configure("Icon.Toolbutton", font=(icon_family(self), 14), width=3,
                         anchor="center", padding=4)

        proj = ttk.Frame(top)
        proj.pack(side="left")
        buttons = (
            ("proj_new", "Novo projeto", self._project_new),
            ("proj_open", "Abrir projeto...", self._project_open),
            ("proj_save", "Salvar projeto", self._project_save),
            ("proj_save_as", "Salvar projeto como...", self._project_save_as),
            ("proj_close", "Fechar projeto", self._project_close),
            ("add_state", "Adicionar Estado...", self._open_add_state_dialog),
            ("add_all_states", "Adicionar Tudo (27 estados)", self._add_all_states),
            ("remove_state", "Remover Estado...", self._open_remove_state_dialog),
            ("remove_all_states", "Remover Tudo", self._remove_all_states),
            ("scheme_edit", "Editar esquema de classificação...", self._open_scheme_editor),
            ("bulk_tier", "Adição em série de categoria...", self._open_bulk_tier_dialog),
            ("preview", "Visualizar impressão...", self._open_preview),
            ("export_json", "Exportar classificação (JSON)...", self._export_classification_json),
            ("import_json", "Importar classificação (JSON)...", self._import_classification_json),
        )
        self._toolbar_btns = {}
        for cid, tooltip, command in buttons:
            btn = ttk.Button(proj, text=glyph(cid), style="Icon.Toolbutton", command=command)
            btn.pack(side="left", padx=1)
            Tooltip(btn, tooltip)
            self._toolbar_btns[cid] = btn

    def _build_body(self) -> None:
        self._body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)

        self._no_project_pane = ttk.Frame(self)
        ttk.Label(
            self._no_project_pane,
            text="Nenhum projeto aberto.\nCrie ou abra um projeto para navegar pelo mapa.",
            foreground="#999999", justify="center", font=("Segoe UI", 12),
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.map_tree = MapTree(
            self._body, on_select=self._on_tree_select, on_rename_root=self._on_tree_root_rename
        )

        canvas_pane = ttk.Frame(self._body)
        self.map_canvas = MapCanvas(canvas_pane)
        self.map_canvas.pack(fill="both", expand=True)
        self.map_canvas.bind_municipality_click(self._on_municipality_click)
        self.map_canvas.bind_municipality_right_click(self._on_municipality_right_click)
        self.map_canvas.bind("<Configure>", self._on_canvas_resize)
        self.hover_var = tk.StringVar(value="")
        self.map_canvas.bind_hover(lambda text: self.hover_var.set(text))
        ttk.Label(canvas_pane, textvariable=self.hover_var, foreground="#555555",
                  padding=(4, 2), anchor="w").pack(fill="x")

        self._body.add(self.map_tree, weight=1)
        self._body.add(canvas_pane, weight=4)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, relief=tk.SUNKEN)
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status_var, padding=(6, 2)).pack(side="left")

    # --------------------------------------------------------------- Data
    def _open_obtain_from_internet(self) -> None:
        ObtainFromInternetDialog(self, on_downloaded=self._on_data_downloaded)

    def _open_obtain_from_csv(self) -> None:
        ObtainFromCsvDialog(self, on_downloaded=self._on_data_downloaded)

    def _on_data_downloaded(self, dataset_id: str) -> None:
        self.status_var.set(f"Dados de '{dataset_id}' atualizados.")
        self.map_canvas.invalidate_geometry_cache()
        self._sync_map_tree()
        self._redraw_current_view()

    # ------------------------------------------------------------- states
    def _included_states(self) -> "set[str]":
        return set(self.project.get_included_states()) if self.project is not None else set()

    def _all_states_rows(self) -> "list[tuple[str, str]]":
        """Every (abbrev_state, name_state) `geo_source` knows about,
        sorted by name -- `[]` if no estados data has been obtained yet."""
        estados = geo_source.load_estados()
        if estados is None or estados.empty or "abbrev_state" not in estados.columns:
            return []
        rows = estados[["abbrev_state", "name_state"]].drop_duplicates().sort_values("name_state")
        return list(rows.itertuples(index=False))

    def _sync_map_tree(self) -> None:
        self.map_tree.refresh(self._included_states())
        self._sync_state_buttons()

    def _sync_state_buttons(self) -> None:
        included = self._included_states()
        can_add = self.project is not None and len(included) < 27
        can_remove = self.project is not None and len(included) > 0
        self._toolbar_btns["add_state"].state(["!disabled" if can_add else "disabled"])
        self._toolbar_btns["add_all_states"].state(["!disabled" if can_add else "disabled"])
        self._toolbar_btns["remove_state"].state(["!disabled" if can_remove else "disabled"])
        self._toolbar_btns["remove_all_states"].state(["!disabled" if can_remove else "disabled"])

    # ---- add
    def _open_add_state_dialog(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para adicionar um estado.")
            return
        included = self._included_states()
        options = [(a, n) for a, n in self._all_states_rows() if a not in included]
        if not options:
            msg = "Todos os estados já foram adicionados a este projeto." if included else \
                "Nenhum dado de estados obtido ainda. Use Data > Obtain from Internet."
            self.status_var.set(msg)
            return
        StatePickerDialog(self, "Adicionar Estado", options, on_ok=self._add_one_state)

    def _add_one_state(self, abbr: str) -> None:
        self.project.add_state(abbr)
        self._sync_map_tree()
        self._sync_title()
        self.status_var.set(f"Estado {abbr} adicionado ao projeto.")

    def _add_all_states(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para adicionar estados.")
            return
        included = self._included_states()
        missing = sorted(a for a, _ in self._all_states_rows() if a not in included)
        if not missing:
            msg = "Todos os estados já foram adicionados a este projeto." if included else \
                "Nenhum dado de estados obtido ainda. Use Data > Obtain from Internet."
            self.status_var.set(msg)
            return
        if not messagebox.askyesno(
            "Adicionar Tudo",
            f"Isso adiciona os {len(missing)} estado(s) restante(s) ao projeto. Continuar?",
            parent=self,
        ):
            return
        self.project.add_states(missing)
        self._sync_map_tree()
        self._sync_title()
        self.status_var.set(f"{len(missing)} estado(s) adicionado(s) ao projeto.")

    # ---- remove
    def _open_remove_state_dialog(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para remover um estado.")
            return
        included = self._included_states()
        if not included:
            self.status_var.set("Este projeto ainda não tem nenhum estado adicionado.")
            return
        options = [(a, n) for a, n in self._all_states_rows() if a in included]
        StatePickerDialog(self, "Remover Estado", options, on_ok=self._remove_one_state)

    def _remove_one_state(self, abbr: str) -> None:
        self.project.remove_state(abbr)
        self._sync_map_tree()
        self._sync_title()
        self.status_var.set(f"Estado {abbr} removido do projeto.")
        self._clear_view_if_showing_state(abbr)

    def _remove_all_states(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para remover estados.")
            return
        included = self._included_states()
        if not included:
            self.status_var.set("Este projeto ainda não tem nenhum estado adicionado.")
            return
        if not messagebox.askyesno(
            "Remover Tudo",
            f"Isso remove todos os {len(included)} estado(s) deste projeto da árvore "
            "(a classificação dos municípios não é apagada -- reflete na hora se o estado "
            "for adicionado de novo). Continuar?",
            parent=self,
        ):
            return
        self.project.remove_all_states()
        self._sync_map_tree()
        self._sync_title()
        if self._current_view is not None and self._current_view[0] == "state":
            self._current_view = None
            self.map_canvas.draw_empty("Todos os estados foram removidos deste projeto.")
        self.status_var.set(f"{len(included)} estado(s) removido(s) do projeto.")

    def _clear_view_if_showing_state(self, abbr: str) -> None:
        if self._current_view == ("state", abbr):
            self._current_view = None
            self.map_canvas.draw_empty(f"{abbr} foi removido deste projeto.")

    # ------------------------------------------------------------- canvas
    def _on_tree_select(self, selection: Selection) -> None:
        self._current_view = selection
        self._redraw_current_view()

    def _redraw_current_view(self) -> None:
        if self._current_view is None:
            return
        kind, value = self._current_view
        if kind == "country":
            self.map_canvas.draw_estados()
        elif kind == "state" and value is not None:
            if self.project is not None:
                mode, tier = self._view_mode
                colors = self.project.painted_colors_df(mode=mode, tier=tier)
            else:
                colors = _EMPTY_COLORS
            self.map_canvas.draw_painted_map(value, colors)

    def _on_canvas_resize(self, _event=None) -> None:
        """`<Configure>` fires many times a second while a window/sash drag
        is in progress -- redrawing on every single one of those would
        queue up a real backlog on a state the size of MG. Debounce: only
        redraw once the size has held still for a moment."""
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(200, self._debounced_resize_redraw)

    def _debounced_resize_redraw(self) -> None:
        self._resize_job = None
        self._redraw_current_view()

    def _recolor_municipalities(self, codes: "list[int]") -> bool:
        """Fast path for when only classification changed on the state
        already on screen: updates just those municípios' fill in place
        instead of a full `draw_painted_map`. Returns False (and does
        nothing) when the current view isn't a state -- caller should fall
        back to switching/redrawing normally in that case."""
        if not codes or self._current_view is None or self._current_view[0] != "state":
            return False
        mode, tier = self._view_mode
        colors_df = self.project.painted_colors_df(mode=mode, tier=tier) if self.project is not None \
            else _EMPTY_COLORS
        color_map = dict(zip(colors_df["code_muni"], colors_df["color"]))
        self.map_canvas.recolor_municipalities({code: color_map.get(code, "white") for code in codes})
        return True

    # ---------------------------------------------------------- root label
    def _sync_root_label(self) -> None:
        label = self.project.root_label if self.project is not None else DEFAULT_ROOT_LABEL
        self.map_tree.set_root_label(label)

    def _on_tree_root_rename(self, new_text: str) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para renomear a árvore.")
            return
        self.project.set_root_label(new_text)
        self._sync_root_label()
        self._sync_title()
        self.status_var.set(f"Árvore renomeada para '{new_text}'.")

    # -------------------------------------------------------------- scheme
    def _open_scheme_editor(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para editar o esquema de classificação.")
            return
        SchemeEditorDialog(self, self.project, on_saved=self._on_scheme_saved)

    def _on_scheme_saved(self) -> None:
        self.status_var.set("Esquema de classificação salvo.")
        self._sync_title()
        self._sync_layout()
        self._redraw_current_view()

    def _open_bulk_tier_dialog(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para classificar municípios em série.")
            return
        BulkTierDialog(self, self.project, on_rendered=self._on_bulk_tier_rendered)

    def _on_bulk_tier_rendered(self, uf: str, touched_codes: "list[int]") -> None:
        self.status_var.set(f"Classificações de {uf} aplicadas.")
        self._sync_title()
        if self._current_view == ("state", uf):
            # already looking at this state: recolor just what changed,
            # instead of reloading/redrawing the whole thing from scratch
            self._recolor_municipalities(touched_codes)
        else:
            # selecting the tree node runs the existing select->redraw path,
            # so the main map ends up showing what was just rendered either way
            self.map_tree.tree.selection_set(f"state:{uf}")

    def _open_preview(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para visualizar a impressão.")
            return
        PreviewDialog(self, self.project, self._current_view, self._view_mode,
                      source_canvas=self.map_canvas)

    # -------------------------------------------------------- JSON export
    def _export_classification_json(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Exportar classificação (JSON)", defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            initialfile=f"{self.project.name}.json", parent=self,
        )
        if not path:
            return
        data = classification_io.export_to_dict(self.project)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("Exportar JSON", f"Falha ao gravar o arquivo:\n{exc}", parent=self)
            return
        self.status_var.set(f"Classificação exportada para {path}")

    def _import_classification_json(self) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para importar.")
            return
        path = filedialog.askopenfilename(
            title="Importar classificação (JSON)",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")], parent=self,
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Importar JSON", f"Não foi possível ler o arquivo:\n{exc}", parent=self)
            return

        try:
            scheme_kind, tiers, code_to_tier = classification_io.validate_and_parse(raw)
        except classification_io.ClassificationImportError as exc:
            messagebox.showerror(
                "Importar JSON",
                "Não foi possível importar -- corrija e tente de novo:\n\n" + "\n".join(exc.errors),
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Importar JSON",
            "Isso substitui o esquema de classificação e todas as categorias atuais "
            "deste projeto pelo conteúdo do arquivo. Continuar?",
            parent=self,
        ):
            return

        classification_io.apply_import(self.project, scheme_kind, tiers, code_to_tier)
        self.status_var.set(f"Classificação importada de {path}")
        self._sync_title()
        self._sync_layout()
        self._redraw_current_view()

    def _sync_layout(self) -> None:
        """Shows/hides the view-mode bar and the whole tree+canvas body as
        one pass, always re-packing both dynamic pieces in the same order
        (view-mode bar, then body-or-placeholder) rather than relying on
        `before=`/`after=` anchors that break once the referenced widget is
        itself hidden."""
        self.view_mode_bar.pack_forget()
        self._body.pack_forget()
        self._no_project_pane.pack_forget()

        show_view_mode_bar = self.project is not None and self.project.scheme_kind == HIERARCHICAL
        if show_view_mode_bar:
            tier_names = [t.name for t in self.project.get_scheme()]
            self.view_mode_bar.set_tiers(tier_names)
            self.view_mode_bar.pack(fill="x", padx=8, pady=(0, 4))
        else:
            self._view_mode = ("all", None)

        if self.project is None:
            self._no_project_pane.pack(fill="both", expand=True, padx=8, pady=4)
        else:
            self._body.pack(fill="both", expand=True, padx=8, pady=4)

    def _on_view_mode_change(self, mode: str, tier: Optional[str]) -> None:
        self._view_mode = (mode, tier)
        self._redraw_current_view()

    def _on_municipality_click(self, code_muni: int) -> None:
        if self.project is None:
            self.status_var.set("Abra um projeto para classificar municípios.")
            return
        category_names = [t.name for t in self.project.get_scheme()]
        if not category_names:
            self.status_var.set("O projeto ainda não tem um esquema de classificação (categorias).")
            return

        current = self.project.get_tier_for(code_muni)
        if current is None:
            next_category = category_names[0]
        else:
            idx = category_names.index(current) if current in category_names else -1
            next_category = category_names[idx + 1] if 0 <= idx < len(category_names) - 1 else None

        if next_category is None:
            self.project.clear_classification(code_muni)
            self.status_var.set(f"Município {code_muni}: classificação removida.")
        else:
            self.project.set_classification(code_muni, next_category)
            self.status_var.set(f"Município {code_muni}: {next_category}.")

        self._sync_title()
        if not self._recolor_municipalities([code_muni]):
            self._redraw_current_view()

    def _on_municipality_right_click(self, code_muni: int) -> None:
        """Right-click: clear the município's category outright, whatever
        it currently is -- a shortcut over left-clicking all the way
        around the cycle back to "none"."""
        if self.project is None:
            self.status_var.set("Abra um projeto para apagar categorias.")
            return
        if self.project.get_tier_for(code_muni) is None:
            self.status_var.set(f"Município {code_muni} já está sem categoria.")
            return
        self.project.clear_classification(code_muni)
        self.status_var.set(f"Município {code_muni}: categoria removida.")
        self._sync_title()
        if not self._recolor_municipalities([code_muni]):
            self._redraw_current_view()

    # ------------------------------------------------------------ project
    def _sync_title(self) -> None:
        if self.project is None:
            self.title(APP_TITLE)
            return
        name = self.project.path.name if self.project.path else f"{self.project.name} (não salvo)"
        dirty = "*" if self.project.dirty else ""
        self.title(f"{dirty}{name} - {APP_TITLE}")

    def _confirm_discard(self) -> bool:
        if self.project is None or not self.project.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Cartomanic BR", "Salvar as alterações do projeto antes de continuar?", parent=self
        )
        if answer is None:
            return False
        if answer:
            return self._project_save()
        return True

    def _project_new(self) -> None:
        if not self._confirm_discard():
            return
        name = simpledialog.askstring("Novo projeto", "Nome do projeto:", parent=self)
        if not name:
            return
        if self.project is not None:
            self.project.close()
        self.project = Project.new(name)
        self.status_var.set(f"Projeto '{name}' criado.")
        self._sync_title()
        self._sync_layout()
        self._sync_root_label()
        self._sync_map_tree()
        self._redraw_current_view()

    def _project_open(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(title="Abrir projeto", filetypes=_PROJECT_TYPES, parent=self)
        if not path:
            return
        try:
            project = Project.open(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Abrir projeto", str(exc), parent=self)
            return
        if self.project is not None:
            self.project.close()
        self.project = project
        self.status_var.set(f"Projeto '{project.name}' aberto.")
        self._sync_title()
        self._sync_layout()
        self._sync_root_label()
        self._sync_map_tree()
        self._redraw_current_view()

    def _project_save(self) -> bool:
        if self.project is None:
            return False
        if self.project.path is None:
            return self._project_save_as()
        self.project.save()
        self.status_var.set("Projeto salvo.")
        self._sync_title()
        return True

    def _project_save_as(self) -> bool:
        if self.project is None:
            return False
        path = filedialog.asksaveasfilename(
            title="Salvar projeto", defaultextension=PROJECT_EXT, filetypes=_PROJECT_TYPES,
            initialfile=self.project.name, parent=self,
        )
        if not path:
            return False
        self.project.save_as(path)
        self.status_var.set(f"Projeto salvo em {path}")
        self._sync_title()
        return True

    def _project_close(self) -> None:
        if not self._confirm_discard():
            return
        if self.project is not None:
            self.project.close()
        self.project = None
        self.status_var.set("Projeto fechado.")
        self._sync_title()
        self._sync_layout()
        self._sync_root_label()
        self._sync_map_tree()
        self._redraw_current_view()

    def _on_quit(self) -> None:
        if self._confirm_discard():
            if self.project is not None:
                self.project.close()
            self.destroy()


__all__ = ["MainWindow"]
