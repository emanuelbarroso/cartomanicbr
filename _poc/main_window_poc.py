"""POC #1 -- Cartomanic main window shell.

Pure layout/visualization prototype: menu bar, project toolbar (icon-font
buttons, same look as the harmonica project) and a two-pane body (project
tree on the left, map canvas placeholder on the right). No project/map logic
is wired yet -- every action just reports itself on the status bar.

Run with::

    python main_window_poc.py
"""
import tkinter as tk
from tkinter import ttk

from _icons import glyph, icon_family, icon_font

APP_TITLE = "Cartomanic"


class _IconTextButton(tk.Frame):
    """Flat toolbar button: an icon-font glyph + a text label, with hover
    feedback. Mirrors harmonica's `_IconTextButton`."""

    _BG, _HOVER, _FG, _FG_OFF = "#f0f0f0", "#e5e5e5", "#1f1f1f", "#a3a3a3"

    def __init__(self, parent, glyph_char, text, command, font):
        super().__init__(parent, bg=self._BG)
        self._command = command
        self._enabled = True
        self._ic = tk.Label(self, text=glyph_char, font=font, bg=self._BG, fg=self._FG)
        self._ic.pack(side="left", padx=(6, 3), pady=4)
        self._tx = tk.Label(self, text=text, font=("Segoe UI", 9), bg=self._BG, fg=self._FG)
        self._tx.pack(side="left", padx=(0, 8), pady=4)
        for w in (self, self._ic, self._tx):
            w.bind("<Button-1>", lambda _e: self._command() if self._enabled else None)
            w.bind("<Enter>", lambda _e: self._paint(self._HOVER))
            w.bind("<Leave>", lambda _e: self._paint(self._BG))

    def _paint(self, bg):
        bg = bg if self._enabled else self._BG
        for w in (self, self._ic, self._tx):
            w.configure(bg=bg)


class ProjectTree(ttk.Frame):
    """Left-hand project tree panel (POC stand-in for pybrmania's
    `ControlFrame`): a `+`/`-` toggle toolbar over a `ttk.Treeview`."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(toolbar, text="+", width=3, command=self._toggle_all).pack(
            side="left", padx=2, pady=2
        )

        self.tree = ttk.Treeview(self, selectmode="browse")
        self.tree.heading("#0", text="Projeto", anchor="w")
        self.tree.column("#0", width=240)
        self.tree.grid(row=1, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns")

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.insert("", "end", text="(Nenhum projeto aberto)")

    def _toggle_all(self):
        for item in self.tree.get_children():
            is_open = self.tree.item(item, "open")
            self.tree.item(item, open=not is_open)


class MapCanvasPlaceholder(tk.Canvas):
    """Right-hand drawing area (POC stand-in for pybrmania's `MapCanvas`)."""

    def __init__(self, parent, *args, **kwargs):
        kwargs.setdefault("background", "white")
        super().__init__(parent, *args, **kwargs)
        self.bind("<Configure>", self._redraw_placeholder)

    def _redraw_placeholder(self, _event=None):
        self.delete("placeholder")
        w = self.winfo_width()
        h = self.winfo_height()
        self.create_text(
            w / 2, h / 2,
            text="MapCanvas\n(aguardando projeto)",
            fill="#b5b5b5", font=("Segoe UI", 13), justify="center",
            tags="placeholder",
        )


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x680")
        self.minsize(720, 480)

        self._icon_font = icon_font(self, 13)
        self.status_var = tk.StringVar(value="Pronto.")

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

    # ------------------------------------------------------------ actions ---
    def _stub(self, label):
        def handler():
            self.status_var.set(f"Ação: {label} (ainda não implementada)")
        return handler

    # ------------------------------------------------------------------ UI ---
    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Project", command=self._stub("Open Project"))
        file_menu.add_command(label="Close Project", command=self._stub("Close Project"))
        file_menu.add_separator()
        file_menu.add_command(label="Save Project", command=self._stub("Save Project"))
        file_menu.add_command(label="Save Project As...", command=self._stub("Save Project As..."))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        self.config(menu=menubar)

    def _build_toolbar(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=(6, 2))

        proj = ttk.Frame(top)
        proj.pack(side="left")
        buttons = (
            ("proj_new", "New Project"),
            ("proj_open", "Open Project"),
            ("proj_save", "Save Project"),
            ("proj_save_as", "Save Project As..."),
            ("proj_close", "Close Project"),
        )
        for cid, label in buttons:
            btn = _IconTextButton(proj, glyph(cid), label, self._stub(label), self._icon_font)
            btn.pack(side="left", padx=1)

    def _build_body(self):
        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        self.project_tree = ProjectTree(body)
        self.map_canvas = MapCanvasPlaceholder(body)

        body.add(self.project_tree, weight=1)
        body.add(self.map_canvas, weight=4)

    def _build_statusbar(self):
        bar = ttk.Frame(self, relief=tk.SUNKEN)
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status_var, padding=(6, 2)).pack(side="left")
        ttk.Label(bar, text=f"fonte de ícones: {icon_family(self)}", padding=(6, 2)).pack(
            side="right"
        )


if __name__ == "__main__":
    MainWindow().mainloop()
