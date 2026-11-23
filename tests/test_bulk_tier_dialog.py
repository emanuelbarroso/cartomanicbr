"""Smoke tests for the Adição em Série dialog's "ocultar classificados"
checkbox. They build the real Tk dialog (hidden root), so they're skipped
where no display / Tcl install is available."""
import tkinter as tk

import pytest

from cartomanic.engine.project import Project, Tier
from cartomanic.gui.bulk_tier_dialog import BulkTierDialog

UF = "SE"


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk indisponível: {exc}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def setup(root):
    """Dialog on Sergipe with tiers A/B; first município in A, second in B."""
    project = Project.new("teste")
    project.set_scheme([Tier("A", "#ff0000", 0), Tier("B", "#0000ff", 1)])
    dialog = BulkTierDialog(root, project)
    munis = dialog._munis_for(UF)
    if len(munis) < 3:
        pytest.skip(f"geometria de {UF} indisponível")
    code_a, code_b = munis[0][0], munis[1][0]
    project.set_classification(code_a, "A")
    project.set_classification(code_b, "B")
    dialog._refresh_base_tiers()
    dialog.uf_var.set(next(v for v in dialog.uf_combo["values"] if v.startswith(f"{UF} ")))
    yield dialog, len(munis), code_a, code_b
    dialog.destroy()
    project.close()


def _select_tier(dialog, tier):
    dialog.tier_var.set(tier)
    dialog._on_combo_change()


def test_unchecked_keeps_other_categories_in_left_list(setup):
    dialog, total, _code_a, code_b = setup
    _select_tier(dialog, "A")
    assert dialog.left_list.size() == total - 1
    assert dialog.right_list.size() == 1
    assert code_b in dialog._left_codes
    assert dialog.left_header_var.get() == "Fora da categoria"


def test_checked_hides_municipios_classified_elsewhere(setup):
    dialog, total, _code_a, code_b = setup
    _select_tier(dialog, "A")
    dialog.hide_classified_var.set(True)
    dialog._reload_current_lists()
    assert code_b not in dialog._left_codes
    assert dialog.left_list.size() == total - 2
    assert dialog.right_list.size() == 1
    assert "1 oculto" in dialog.left_header_var.get()


def test_checked_also_hides_staged_moves(setup):
    dialog, _total, code_a, _code_b = setup
    dialog.hide_classified_var.set(True)
    _select_tier(dialog, "A")
    dialog.left_list.selection_set(0)
    staged = dialog._left_codes[0]
    dialog._move_right()

    _select_tier(dialog, "B")
    assert staged not in dialog._left_codes
    assert code_a not in dialog._left_codes
    assert "2 oculto" in dialog.left_header_var.get()


def test_unchecking_restores_full_list(setup):
    dialog, total, _code_a, _code_b = setup
    _select_tier(dialog, "A")
    dialog.hide_classified_var.set(True)
    dialog._reload_current_lists()
    dialog.hide_classified_var.set(False)
    dialog._reload_current_lists()
    assert dialog.left_list.size() == total - 1
