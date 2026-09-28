import pytest

from cartomanic.engine import classification_io
from cartomanic.engine.project import DISCRETE, HIERARCHICAL, Project, Tier

# real IBGE codes from the bundled data (used throughout the session):
# 2211001 = Teresina, PI ; 2200103 = Agricolândia, PI ; 3550308 = São Paulo, SP
TERESINA, AGRICOLANDIA, SAO_PAULO = 2211001, 2200103, 3550308


def _project_with_data():
    p = Project.new("Trilhas")
    p.set_scheme([Tier("visitado", "#e8702a", 0), Tier("capital", "#555555", 1)])
    p.set_classification(TERESINA, "capital")
    p.set_classification(AGRICOLANDIA, "visitado")
    return p


def test_export_groups_by_state_and_category_id():
    p = _project_with_data()
    try:
        data = classification_io.export_to_dict(p)
        assert data["scheme_kind"] == DISCRETE
        assert data["categories"] == {
            "0": {"name": "visitado", "color": "#e8702a", "sort_order": 0},
            "1": {"name": "capital", "color": "#555555", "sort_order": 1},
        }
        assert data["classification"]["PI"]["1"] == [TERESINA]
        assert data["classification"]["PI"]["0"] == [AGRICOLANDIA]
    finally:
        p.close()


def test_export_then_validate_then_apply_roundtrips():
    p = _project_with_data()
    try:
        data = classification_io.export_to_dict(p)
    finally:
        p.close()

    scheme_kind, tiers, code_to_tier = classification_io.validate_and_parse(data)
    assert scheme_kind == DISCRETE
    assert {t.name for t in tiers} == {"visitado", "capital"}
    assert code_to_tier == {TERESINA: "capital", AGRICOLANDIA: "visitado"}

    fresh = Project.new("Outro projeto")
    try:
        classification_io.apply_import(fresh, scheme_kind, tiers, code_to_tier)
        assert fresh.scheme_kind == DISCRETE
        assert fresh.get_tier_for(TERESINA) == "capital"
        assert fresh.get_tier_for(AGRICOLANDIA) == "visitado"
    finally:
        fresh.close()


def test_import_replaces_rather_than_merges():
    fresh = Project.new("P")
    try:
        fresh.set_scheme([Tier("antigo", "#000000", 0)])
        fresh.set_classification(SAO_PAULO, "antigo")

        data = {
            "scheme_kind": DISCRETE,
            "categories": {"0": {"name": "novo", "color": "#fff", "sort_order": 0}},
            "classification": {"PI": {"0": [TERESINA]}},
        }
        scheme_kind, tiers, code_to_tier = classification_io.validate_and_parse(data)
        classification_io.apply_import(fresh, scheme_kind, tiers, code_to_tier)

        assert fresh.get_tier_for(SAO_PAULO) is None  # wiped, not merged
        assert fresh.get_tier_for(TERESINA) == "novo"
        assert [t.name for t in fresh.get_scheme()] == ["novo"]
    finally:
        fresh.close()


@pytest.mark.parametrize(
    "data, expected_snippet",
    [
        ({"categories": {}, "classification": {}}, "scheme_kind"),
        ({"scheme_kind": DISCRETE, "classification": {}}, "categories"),
        (
            {"scheme_kind": DISCRETE, "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
             "classification": "not-a-dict"},
            "classification",
        ),
        (
            {"scheme_kind": DISCRETE, "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
             "classification": {"XX": {"0": [1]}}},
            "XX",
        ),
        (
            {"scheme_kind": DISCRETE, "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
             "classification": {"PI": {"9": [TERESINA]}}},
            "9",
        ),
        (
            {"scheme_kind": DISCRETE, "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
             "classification": {"PI": {"0": [99999999]}}},
            "99999999",
        ),
        (
            {"scheme_kind": DISCRETE, "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
             # Teresina is PI, not SP -- state/município mismatch
             "classification": {"SP": {"0": [TERESINA]}}},
            str(TERESINA),
        ),
    ],
)
def test_validate_rejects_malformed_input_with_a_readable_reason(data, expected_snippet):
    with pytest.raises(classification_io.ClassificationImportError) as exc_info:
        classification_io.validate_and_parse(data)
    assert any(expected_snippet in msg for msg in exc_info.value.errors)


def test_validate_rejects_duplicate_municipio_across_categories():
    data = {
        "scheme_kind": DISCRETE,
        "categories": {
            "0": {"name": "a", "color": "#fff", "sort_order": 0},
            "1": {"name": "b", "color": "#000", "sort_order": 1},
        },
        "classification": {"PI": {"0": [TERESINA], "1": [TERESINA]}},
    }
    with pytest.raises(classification_io.ClassificationImportError) as exc_info:
        classification_io.validate_and_parse(data)
    assert any("mais de uma vez" in msg for msg in exc_info.value.errors)


def test_validate_accepts_hierarchical_kind():
    data = {
        "scheme_kind": HIERARCHICAL,
        "categories": {"0": {"name": "a", "color": "#fff", "sort_order": 0}},
        "classification": {},
    }
    scheme_kind, tiers, code_to_tier = classification_io.validate_and_parse(data)
    assert scheme_kind == HIERARCHICAL
    assert code_to_tier == {}
