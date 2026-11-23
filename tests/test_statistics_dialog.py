"""End-to-end smoke test of the Estatísticas gerais window wired into the
real MainWindow, with the bundled geometry + IBGE data. Skipped where Tk
or the bundled data are unavailable."""
import tkinter as tk

import pytest

from cartomanic.data import geo_source, ibge_source
from cartomanic.engine.project import HIERARCHICAL, Project, Tier
from cartomanic.gui.statistics_dialog import CENSO_LABEL, StatisticsDialog

ARACAJU = 2800308
ARACAJU_POP_2022 = 602757


@pytest.fixture
def app():
    try:
        from cartomanic.gui.main_window import MainWindow
        win = MainWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk indisponível: {exc}")
    if geo_source.load_municipios() is None or ibge_source.load_censo_2022() is None:
        win.destroy()
        pytest.skip("dados empacotados indisponíveis")
    win.withdraw()
    win.project = Project.new("teste")
    win.project.set_scheme([Tier("A", "#ff0000", 0), Tier("B", "#0000ff", 1)])
    win.project.add_states(["SE", "AL"])
    win._sync_layout()
    yield win
    if win._stats_dialog_open():
        win._stats_dialog.destroy()
    if win.project is not None:
        win.project.close()
        win.project = None
    win.destroy()


def _open(app) -> StatisticsDialog:
    app._open_statistics()
    dlg = app._stats_dialog
    assert isinstance(dlg, StatisticsDialog)
    return dlg


def _brasil_row(dlg, label):
    tree = dlg._trees["brasil"]
    for iid in tree.get_children():
        if tree.item(iid, "text") == label:
            return tree.item(iid, "values")
    raise AssertionError(f"linha {label!r} não encontrada")


def _settle(dlg):
    """Run the debounced refresh now instead of waiting for `after`."""
    if dlg._refresh_job is not None:
        dlg.after_cancel(dlg._refresh_job)
    dlg.refresh()


def test_opens_with_census_totals(app):
    dlg = _open(app)
    assert dlg.pop_source_var.get() == CENSO_LABEL
    assert any(o.startswith("Estimativa ") for o in dlg.pop_combo["values"])
    total = _brasil_row(dlg, "Total")
    assert total[0] == "5.570"
    assert total[4] == "203.080.756"
    assert total[6] == "27"
    assert len(dlg._trees["regiao"].get_children()) == 5
    assert len(dlg._trees["estado"].get_children()) == 27


def test_click_classification_updates_window(app):
    dlg = _open(app)
    app._on_municipality_click(ARACAJU)          # -> A, same path as a map click
    _settle(dlg)
    a = _brasil_row(dlg, "A")
    assert a[0] == "1"
    assert a[4] == f"{ARACAJU_POP_2022:,}".replace(",", ".")
    assert a[6] == "1"

    app._on_municipality_right_click(ARACAJU)    # clear
    _settle(dlg)
    assert _brasil_row(dlg, "A")[0] == "0"


def test_only_included_states_and_estimate_source(app):
    dlg = _open(app)
    dlg.only_included_var.set(True)
    dlg.refresh()
    assert _brasil_row(dlg, "Total")[6] == "2"   # SE + AL
    assert len(dlg._trees["estado"].get_children()) == 2

    estimates = [o for o in dlg.pop_combo["values"] if o.startswith("Estimativa ")]
    dlg.pop_source_var.set(estimates[0])
    dlg.refresh()
    assert _brasil_row(dlg, "Total")[4] != "203.080.756"


def test_follows_hierarchical_view_mode(app):
    app.project.set_scheme_kind(HIERARCHICAL)
    app._sync_layout()
    dlg = _open(app)
    app._on_view_mode_change("at_least", "B")
    _settle(dlg)
    labels = [dlg._trees["brasil"].item(i, "text") for i in dlg._trees["brasil"].get_children()]
    assert labels == ["B", "Subtotal (≥ B)", "Outras categorias", "Sem classificação", "Total"]
    assert "≥ Hierarquia (B)" in dlg.mode_var.get()


def test_closing_project_clears_window(app):
    dlg = _open(app)
    app.project.close()
    app.project = None
    app._sync_layout()
    _settle(dlg)
    assert not dlg._trees["brasil"].get_children()
    assert "Nenhum projeto" in dlg.notes_var.get()
