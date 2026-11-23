"""Parsing of IBGE agregados API responses -- no network: the payloads
below mirror the real response shape (one entry per variable, series keyed
by município with a {period: value} map)."""
import pandas as pd

from cartomanic.data import ibge_source


def _var(var_id, series):
    return {
        "id": str(var_id),
        "variavel": "x",
        "unidade": "x",
        "resultados": [{
            "classificacoes": [],
            "series": [
                {"localidade": {"id": str(code), "nivel": {"id": "N6"}, "nome": "M"}, "serie": serie}
                for code, serie in series
            ],
        }],
    }


CENSO_PAYLOAD = [
    _var(93, [(2800308, {"2022": "602757"}), (1100015, {"2022": "21494"}), (9999999, {"2022": "-"})]),
    _var(6318, [(2800308, {"2022": "182.163"}), (1100015, {"2022": "7067.127"}), (9999999, {"2022": "..."})]),
]


def test_parse_agregados_flattens_to_long_format():
    long = ibge_source.parse_agregados(CENSO_PAYLOAD)
    assert list(long.columns) == ["code_muni", "variavel", "periodo", "valor"]
    assert len(long) == 6
    row = long[(long["code_muni"] == 2800308) & (long["variavel"] == 93)].iloc[0]
    assert row["periodo"] == 2022 and row["valor"] == 602757


def test_censo_is_one_row_per_municipio_with_missing_as_na():
    df = ibge_source.censo_from_long(ibge_source.parse_agregados(CENSO_PAYLOAD))
    assert list(df.columns) == ["code_muni", "populacao", "area_km2"]
    assert df["code_muni"].tolist() == [1100015, 2800308, 9999999]
    aracaju = df[df["code_muni"] == 2800308].iloc[0]
    assert aracaju["populacao"] == 602757
    assert aracaju["area_km2"] == 182.163
    missing = df[df["code_muni"] == 9999999].iloc[0]
    assert pd.isna(missing["populacao"]) and pd.isna(missing["area_km2"])
    assert str(df["populacao"].dtype) == "Int64"


def test_estimativas_long_format_one_row_per_year():
    payload = [_var(9324, [
        (2800308, {"2024": "605000", "2025": "607000"}),
        (1100015, {"2024": "22000", "2025": "X"}),
    ])]
    df = ibge_source.estimativas_from_long(ibge_source.parse_agregados(payload))
    assert list(df.columns) == ["code_muni", "ano", "populacao"]
    assert len(df) == 4
    assert df[(df["code_muni"] == 2800308) & (df["ano"] == 2025)]["populacao"].iloc[0] == 607000
    assert pd.isna(df[(df["code_muni"] == 1100015) & (df["ano"] == 2025)]["populacao"].iloc[0])
