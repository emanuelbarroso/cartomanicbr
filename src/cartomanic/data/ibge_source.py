"""Municipal reference numbers from IBGE's public "agregados" API (the same
tables SIDRA serves, via servicodados.ibge.gov.br -- SIDRA itself sits
behind a bot challenge that blocks plain HTTP clients).

Two datasets, both stored through the standard `SnapshotStore` pattern
(see `cartomanic.engine.snapshot_store`), just like geometry:

- `ibge_censo_2022` -- table 4714: resident population (var. 93) and
  *official* territorial area in km² (var. 6318), one row per município.
- `ibge_estimativas` -- table 6579: estimated resident population (var.
  9324), long format, one row per (município, year).

Rows are keyed by `code_muni` (7-digit IBGE code), matching the geometry.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Iterable, List, Optional

import pandas as pd

from ..engine.snapshot_store import SnapshotStore
from . import geo_source

CENSO_2022_DATASET = "ibge_censo_2022"
ESTIMATIVAS_DATASET = "ibge_estimativas"

_API = "https://servicodados.ibge.gov.br/api/v3/agregados"
_CENSO_TABLE, _VAR_POP, _VAR_AREA = 4714, 93, 6318
_ESTIM_TABLE, _VAR_POP_ESTIM = 6579, 9324
_TIMEOUT_S = 120


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "cartomanic", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        return json.load(resp)


def _to_number(value) -> Optional[float]:
    """IBGE uses placeholders ("-", "...", "X") for missing/suppressed."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_agregados(payload: list) -> pd.DataFrame:
    """Flatten an agregados `/periodos/.../variaveis/...` response into long
    format: `code_muni`, `variavel` (id, int), `periodo` (int), `valor`."""
    rows = []
    for var in payload:
        var_id = int(var["id"])
        for result in var.get("resultados", []):
            for serie in result.get("series", []):
                code = int(serie["localidade"]["id"])
                for periodo, valor in serie.get("serie", {}).items():
                    rows.append((code, var_id, int(periodo), _to_number(valor)))
    return pd.DataFrame(rows, columns=["code_muni", "variavel", "periodo", "valor"])


def fetch_censo_2022() -> pd.DataFrame:
    """`code_muni`, `populacao`, `area_km2` for every município (Censo 2022)."""
    url = f"{_API}/{_CENSO_TABLE}/periodos/2022/variaveis/{_VAR_POP}|{_VAR_AREA}?localidades=N6[all]"
    return censo_from_long(parse_agregados(_get_json(url)))


def censo_from_long(long: pd.DataFrame) -> pd.DataFrame:
    by_var = {
        var: grp.set_index("code_muni")["valor"] for var, grp in long.groupby("variavel")
    }
    codes = sorted(long["code_muni"].unique())
    empty = pd.Series(dtype="float64")
    return pd.DataFrame({
        "code_muni": pd.Series(codes, dtype="int64"),
        "populacao": by_var.get(_VAR_POP, empty).reindex(codes).round().astype("Int64").array,
        "area_km2": by_var.get(_VAR_AREA, empty).reindex(codes).astype("float64").array,
    })


def estimativa_years_available() -> List[int]:
    """Years table 6579 has *after* the 2022 census (older estimates were
    rebased by the census and aren't comparable with it)."""
    periods = _get_json(f"{_API}/{_ESTIM_TABLE}/periodos")
    return sorted(int(p["id"]) for p in periods if int(p["id"]) > 2022)


def fetch_estimativas(years: Optional[Iterable[int]] = None) -> pd.DataFrame:
    """`code_muni`, `ano`, `populacao` -- one row per (município, year).
    Defaults to every post-census year IBGE has published."""
    years = sorted(years) if years is not None else estimativa_years_available()
    if not years:
        return pd.DataFrame({"code_muni": pd.Series(dtype="int64"),
                             "ano": pd.Series(dtype="int64"),
                             "populacao": pd.Series(dtype="Int64")})
    periodos = "|".join(str(y) for y in years)
    url = f"{_API}/{_ESTIM_TABLE}/periodos/{periodos}/variaveis/{_VAR_POP_ESTIM}?localidades=N6[all]"
    return estimativas_from_long(parse_agregados(_get_json(url)))


def estimativas_from_long(long: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "code_muni": long["code_muni"].astype("int64"),
        "ano": long["periodo"].astype("int64"),
        "populacao": long["valor"].round().astype("Int64"),
    })
    return out.sort_values(["ano", "code_muni"]).reset_index(drop=True)


def load_censo_2022(store: Optional[SnapshotStore] = None) -> Optional[pd.DataFrame]:
    store = store or geo_source.default_store()
    return store.latest(CENSO_2022_DATASET)


def load_estimativas(store: Optional[SnapshotStore] = None) -> Optional[pd.DataFrame]:
    store = store or geo_source.default_store()
    return store.latest(ESTIMATIVAS_DATASET)


__all__ = [
    "CENSO_2022_DATASET",
    "ESTIMATIVAS_DATASET",
    "parse_agregados",
    "fetch_censo_2022",
    "fetch_estimativas",
    "estimativa_years_available",
    "load_censo_2022",
    "load_estimativas",
]
