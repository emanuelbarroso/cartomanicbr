from cartomanic.engine.project import DEFAULT_ROOT_LABEL, DISCRETE, HIERARCHICAL, Project, Tier


def test_new_project_has_no_path_and_is_dirty():
    p = Project.new("Trilhas 2024")
    try:
        assert p.path is None
        assert p.dirty is True
    finally:
        p.close()


def test_save_as_then_reopen_roundtrips_metadata_and_classification(tmp_path):
    path = tmp_path / "trilhas.cmbr"
    p = Project.new("Trilhas 2024", "Municípios visitados")
    p.set_scheme([Tier("visitado", "#e8702a", 1), Tier("capital", "#555555", 0)])
    p.set_classification(3550308, "visitado")
    p.save_as(path)
    p.close()

    reopened = Project.open(path)
    try:
        assert reopened.name == "Trilhas 2024"
        assert reopened.description == "Municípios visitados"
        assert reopened.dirty is False

        colors = reopened.painted_colors_df()
        row = colors[colors["code_muni"] == 3550308].iloc[0]
        assert row["color"] == "#e8702a"
    finally:
        reopened.close()


def test_new_project_defaults_root_label_and_it_roundtrips(tmp_path):
    path = tmp_path / "rotulo.cmbr"
    p = Project.new("Trilhas 2024")
    try:
        assert p.root_label == DEFAULT_ROOT_LABEL
        p.set_root_label("Municípios visitados")
        p.save_as(path)
    finally:
        p.close()

    reopened = Project.open(path)
    try:
        assert reopened.root_label == "Municípios visitados"
    finally:
        reopened.close()


def test_new_project_defaults_to_discrete_scheme():
    p = Project.new("Sem tipo definido")
    try:
        assert p.scheme_kind == DISCRETE
    finally:
        p.close()


def test_scheme_kind_roundtrips_through_save_as_and_open(tmp_path):
    path = tmp_path / "hier.cmbr"
    p = Project.new("Hierárquico")
    p.set_scheme_kind(HIERARCHICAL)
    p.save_as(path)
    p.close()

    reopened = Project.open(path)
    try:
        assert reopened.scheme_kind == HIERARCHICAL
    finally:
        reopened.close()


def test_at_least_mode_keeps_each_municipality_in_its_own_tier_color():
    p = Project.new("Trilhas hierárquicas", scheme_kind=HIERARCHICAL)
    try:
        p.set_scheme([
            Tier("passagem", "#f7c59f", 0),
            Tier("visitado", "#e8702a", 1),
            Tier("morei", "#7a2e0e", 2),
        ])
        p.set_classification(1, "passagem")
        p.set_classification(2, "visitado")
        p.set_classification(3, "morei")

        at_least_visitado = p.painted_colors_df(mode="at_least", tier="visitado")
        codes = set(at_least_visitado["code_muni"])
        assert codes == {2, 3}
        colors = dict(zip(at_least_visitado["code_muni"], at_least_visitado["color"]))
        assert colors[2] == "#e8702a"
        assert colors[3] == "#7a2e0e"  # kept in ITS OWN color, not merged

        exact_visitado = p.painted_colors_df(mode="exact", tier="visitado")
        assert set(exact_visitado["code_muni"]) == {2}
    finally:
        p.close()


def test_save_without_path_raises():
    p = Project.new("Sem local")
    try:
        try:
            p.save()
            assert False, "expected ValueError"
        except ValueError:
            pass
    finally:
        p.close()
