"""engine/statistics.py on a tiny synthetic Brazil: 2 regions, 3 states,
6 municípios with geometry + 1 created later (population only)."""
import math

import pandas as pd
import pytest

from cartomanic.engine import statistics as st
from cartomanic.engine.project import Tier

MUNIS = pd.DataFrame([
    # code_muni, code_state, abbrev, name_state, code_region, name_region
    (1100001, 11, "RO", "Rondônia", 1, "Norte"),
    (1100002, 11, "RO", "Rondônia", 1, "Norte"),
    (2800001, 28, "SE", "Sergipe", 2, "Nordeste"),
    (2800002, 28, "SE", "Sergipe", 2, "Nordeste"),
    (2900001, 29, "BA", "Bahia", 2, "Nordeste"),
    (2900002, 29, "BA", "Bahia", 2, "Nordeste"),
], columns=["code_muni", "code_state", "abbrev_state", "name_state", "code_region", "name_region"])

AREA = pd.DataFrame({
    "code_muni": [1100001, 1100002, 2800001, 2800002, 2900001, 2900002],
    "area_km2": [100.0, 300.0, 50.0, 50.0, 200.0, 300.0],
})
POP = pd.DataFrame({
    "code_muni": [1100001, 1100002, 2800001, 2800002, 2900001, 2900002, 2900003],
    "populacao": [10, 30, 100, 100, 200, 500, 60],  # 2900003: no geometry
})

SCHEME = [Tier("A", "#ff0000", 0), Tier("B", "#00ff00", 1), Tier("C", "#0000ff", 2)]
CLASSIF = {1100001: "A", 2800001: "B", 2800002: "C", 2900001: "C"}


@pytest.fixture
def universe():
    return st.build_universe(MUNIS, area=AREA, populacao=POP)


def _row(table, grupo, linha):
    hit = table[(table["grupo"] == grupo) & (table["linha"] == linha)]
    assert len(hit) == 1, f"{grupo}/{linha}: {len(hit)} rows"
    return hit.iloc[0]


def test_universe_adds_municipio_without_geometry_to_its_state(universe):
    assert len(universe) == 7
    extra = universe[universe["code_muni"] == 2900003].iloc[0]
    assert not extra["has_geometry"]
    assert extra["abbrev_state"] == "BA" and extra["name_region"] == "Nordeste"
    assert extra["populacao"] == 60 and math.isnan(extra["area_km2"])


def test_brasil_all_mode_counts_and_percentages(universe):
    r = st.compute(universe, CLASSIF, SCHEME)
    br = r[st.LEVEL_BRASIL]
    assert br["linha"].tolist() == ["A", "B", "C", "Sem classificação", "Total"]

    total = _row(br, "Brasil", "Total")
    assert total["municipios"] == 6                # extra has no geometry
    assert total["populacao"] == 1000              # ...but its population counts
    assert total["area_km2"] == 1000
    assert total["ufs"] == 3

    c = _row(br, "Brasil", "C")
    assert c["municipios"] == 2 and c["pct_municipios"] == pytest.approx(2 / 6)
    assert c["area_km2"] == 250 and c["pct_area"] == pytest.approx(0.25)
    assert c["populacao"] == 300 and c["pct_populacao"] == pytest.approx(0.3)
    assert c["ufs"] == 2                           # SE and BA

    sem = _row(br, "Brasil", "Sem classificação")
    assert sem["municipios"] == 2                  # 1100002, 2900002
    assert sem["populacao"] == 30 + 500 + 60       # includes the extra

    parts = br[br["tipo"] != st.KIND_TOTAL]
    assert parts["pct_municipios"].sum() == pytest.approx(1.0)
    assert parts["pct_populacao"].sum() == pytest.approx(1.0)
    assert any("sem geometria" in n for n in r.notes)


def test_region_and_state_levels(universe):
    r = st.compute(universe, CLASSIF, SCHEME)
    regioes = r[st.LEVEL_REGIAO]
    assert regioes.drop_duplicates("grupo")["grupo"].tolist() == ["Norte", "Nordeste"]
    assert _row(regioes, "Nordeste", "C")["ufs"] == 2
    assert _row(regioes, "Norte", "Total")["populacao"] == 40

    estados = r[st.LEVEL_ESTADO]
    assert estados.drop_duplicates("grupo")["grupo"].tolist() == ["RO - Rondônia", "SE - Sergipe", "BA - Bahia"]
    assert _row(estados, "BA - Bahia", "Total")["populacao"] == 760
    assert _row(estados, "SE - Sergipe", "B")["pct_municipios"] == pytest.approx(0.5)


def test_exact_mode_lumps_other_categories(universe):
    r = st.compute(universe, CLASSIF, SCHEME, mode="exact", tier="C")
    br = r[st.LEVEL_BRASIL]
    assert br["linha"].tolist() == ["C", "Outras categorias", "Sem classificação", "Total"]
    assert _row(br, "Brasil", "C")["municipios"] == 2
    assert _row(br, "Brasil", "Outras categorias")["municipios"] == 2   # A and B


def test_at_least_mode_lists_each_tier_and_subtotal(universe):
    r = st.compute(universe, CLASSIF, SCHEME, mode="at_least", tier="B")
    br = r[st.LEVEL_BRASIL]
    assert br["linha"].tolist() == ["B", "C", "Subtotal (≥ B)", "Outras categorias",
                                    "Sem classificação", "Total"]
    assert _row(br, "Brasil", "Subtotal (≥ B)")["municipios"] == 3
    assert _row(br, "Brasil", "Outras categorias")["municipios"] == 1   # A


def test_included_states_filter(universe):
    r = st.compute(universe, CLASSIF, SCHEME, included_states=["SE"])
    total = _row(r[st.LEVEL_BRASIL], "Brasil", "Total")
    assert total["municipios"] == 2 and total["ufs"] == 1 and total["populacao"] == 200
    assert r[st.LEVEL_REGIAO]["grupo"].unique().tolist() == ["Nordeste"]

    empty = st.compute(universe, CLASSIF, SCHEME, included_states=[])
    assert _row(empty[st.LEVEL_BRASIL], "Brasil", "Total")["municipios"] == 0
    assert any("Nenhum estado" in n for n in empty.notes)


def test_orphan_tier_goes_to_other_with_note(universe):
    r = st.compute(universe, {**CLASSIF, 2900002: "Z"}, SCHEME)
    assert _row(r[st.LEVEL_BRASIL], "Brasil", "Outras categorias")["municipios"] == 1
    assert any("Z" in n for n in r.notes)


def test_missing_population_and_area_are_nan(universe):
    bare = st.build_universe(MUNIS)
    r = st.compute(bare, CLASSIF, SCHEME)
    total = _row(r[st.LEVEL_BRASIL], "Brasil", "Total")
    assert total["municipios"] == 6
    assert math.isnan(total["populacao"]) and math.isnan(total["pct_area"])
    assert not r.has_area and not r.has_populacao
