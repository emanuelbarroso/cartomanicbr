"""Estatísticas gerais: how a project's classification breaks down by
category, at three levels (Brasil, região, estado), in município count,
official area and population.

Pure pandas, no GUI and no I/O: callers hand in a *universe* frame (one
row per município, built by `build_universe` from geometry attributes +
IBGE numbers) and the project's classification/scheme, and get back plain
DataFrames ready to display.

Rows per group, in order:
  - one per visible category (which ones depends on the map's view mode),
  - "Subtotal (≥ X)" in "≥ Hierarquia" mode,
  - "Outras categorias" -- classified, but in a category the current view
    mode leaves out (or in one that no longer exists in the scheme),
  - "Sem classificação",
  - "Total".
Percentages are always relative to the group's Total row, so the
category rows (+ outras + sem) add up to 100%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

from .project import Tier

KIND_TIER = "categoria"
KIND_SUBTOTAL = "subtotal"
KIND_OTHER = "outras"
KIND_NONE = "sem"
KIND_TOTAL = "total"

LABEL_OTHER = "Outras categorias"
LABEL_NONE = "Sem classificação"
LABEL_TOTAL = "Total"

LEVEL_BRASIL = "brasil"
LEVEL_REGIAO = "regiao"
LEVEL_ESTADO = "estado"
LEVELS = (LEVEL_BRASIL, LEVEL_REGIAO, LEVEL_ESTADO)

RESULT_COLUMNS = [
    "grupo", "grupo_ordem", "linha", "tipo", "cor",
    "municipios", "pct_municipios", "area_km2", "pct_area",
    "populacao", "pct_populacao", "ufs",
]

_STATE_COLS = ["code_state", "abbrev_state", "name_state", "code_region", "name_region"]


# ------------------------------------------------------------------ universe
def build_universe(
    munis: pd.DataFrame,
    area: Optional[pd.DataFrame] = None,
    populacao: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """One row per município: `code_muni`, state/region columns,
    `has_geometry`, `area_km2`, `populacao`.

    `munis` is the geometry's attribute table (what the map can show and
    what can be classified). `area` / `populacao` are `code_muni` +
    `area_km2` / `populacao` frames; either may be None (column stays NaN).
    A code present in `populacao` but not in `munis` (a município created
    after the geometry's year) is still added -- with `has_geometry=False`
    and its state inferred from the code's first two digits -- so state,
    region and Brasil population totals match IBGE's.
    """
    base = munis[["code_muni"] + _STATE_COLS].copy()
    base["code_muni"] = base["code_muni"].astype("int64")
    base["code_state"] = base["code_state"].astype("int64")
    base["code_region"] = base["code_region"].astype("int64")
    base = base.drop_duplicates("code_muni")
    base["has_geometry"] = True

    if populacao is not None and not populacao.empty:
        extra_codes = sorted(set(populacao["code_muni"].astype("int64")) - set(base["code_muni"]))
        if extra_codes:
            states = base[_STATE_COLS].drop_duplicates("code_state")
            extra = pd.DataFrame({"code_muni": pd.Series(extra_codes, dtype="int64")})
            extra["code_state"] = extra["code_muni"] // 100000
            extra = extra.merge(states, on="code_state", how="inner")
            extra["has_geometry"] = False
            base = pd.concat([base, extra[base.columns]], ignore_index=True)

    for frame, col in ((area, "area_km2"), (populacao, "populacao")):
        if frame is not None and not frame.empty and col in frame.columns:
            values = frame[["code_muni", col]].copy()
            values["code_muni"] = values["code_muni"].astype("int64")
            base = base.merge(values.drop_duplicates("code_muni"), on="code_muni", how="left")
            base[col] = base[col].astype("float64")
        else:
            base[col] = float("nan")
    return base.reset_index(drop=True)


# ------------------------------------------------------------------- result
@dataclass
class StatsResult:
    tables: Dict[str, pd.DataFrame]
    notes: List[str] = field(default_factory=list)
    has_area: bool = True
    has_populacao: bool = True

    def __getitem__(self, level: str) -> pd.DataFrame:
        return self.tables[level]


def _visible_tiers(scheme: Sequence[Tier], mode: str, tier: Optional[str]) -> List[Tier]:
    ordered = sorted(scheme, key=lambda t: t.sort_order)
    by_name = {t.name: t for t in ordered}
    if tier is None or tier not in by_name or mode == "all":
        return ordered
    if mode == "exact":
        return [by_name[tier]]
    if mode == "at_least":
        floor = by_name[tier].sort_order
        return [t for t in ordered if t.sort_order >= floor]
    raise ValueError(f"unknown mode {mode!r}")


def _sum_or_nan(series: pd.Series) -> float:
    return float(series.sum()) if series.notna().any() else float("nan")


def _pct(value: float, total: float) -> float:
    if pd.isna(value) or pd.isna(total) or total == 0:
        return float("nan")
    return value / total


def _row(grupo, ordem, linha, tipo, cor, part: pd.DataFrame, total: dict) -> dict:
    with_geom = part[part["has_geometry"]]
    municipios = int(len(with_geom))
    area = _sum_or_nan(part["area_km2"])
    pop = _sum_or_nan(part["populacao"])
    return {
        "grupo": grupo, "grupo_ordem": ordem, "linha": linha, "tipo": tipo, "cor": cor,
        "municipios": municipios, "pct_municipios": _pct(municipios, total["municipios"]),
        "area_km2": area, "pct_area": _pct(area, total["area_km2"]),
        "populacao": pop, "pct_populacao": _pct(pop, total["populacao"]),
        "ufs": int(with_geom["abbrev_state"].nunique()),
    }


def _group_rows(grupo, ordem, df: pd.DataFrame, visible: List[Tier],
                mode: str, tier: Optional[str]) -> List[dict]:
    total = {
        "municipios": int(df["has_geometry"].sum()),
        "area_km2": _sum_or_nan(df["area_km2"]),
        "populacao": _sum_or_nan(df["populacao"]),
    }
    rows = [_row(grupo, ordem, t.name, KIND_TIER, t.color, df[df["bucket"] == t.name], total)
            for t in visible]
    if mode == "at_least" and tier is not None and len(visible) > 0:
        names = [t.name for t in visible]
        rows.append(_row(grupo, ordem, f"Subtotal (≥ {tier})", KIND_SUBTOTAL, None,
                         df[df["bucket"].isin(names)], total))
    other = df[df["bucket"] == LABEL_OTHER]
    if len(other) or mode in ("exact", "at_least"):
        rows.append(_row(grupo, ordem, LABEL_OTHER, KIND_OTHER, None, other, total))
    rows.append(_row(grupo, ordem, LABEL_NONE, KIND_NONE, None, df[df["bucket"] == LABEL_NONE], total))
    rows.append(_row(grupo, ordem, LABEL_TOTAL, KIND_TOTAL, None, df, total))
    return rows


def compute(
    universe: pd.DataFrame,
    classification: Mapping[int, str],
    scheme: Sequence[Tier],
    mode: str = "all",
    tier: Optional[str] = None,
    included_states: Optional[Iterable[str]] = None,
) -> StatsResult:
    """Break `universe` down by category at every level.

    `classification`: code_muni -> tier name. `mode`/`tier` follow the
    map's view mode (`ViewModeBar`): "all", "exact", "at_least".
    `included_states`: when given, only municípios of these UFs count
    (an empty iterable means nothing counts)."""
    if mode not in ("all", "exact", "at_least"):
        raise ValueError(f"unknown mode {mode!r}")
    if mode != "all" and tier is None:
        mode = "all"

    notes: List[str] = []
    df = universe.copy()
    if included_states is not None:
        included = set(included_states)
        df = df[df["abbrev_state"].isin(included)]
        if not included:
            notes.append("Nenhum estado incluído no projeto -- nada a contar.")

    visible = _visible_tiers(scheme, mode, tier)
    visible_names = {t.name for t in visible}
    tiers = df["code_muni"].map(classification)
    df["bucket"] = LABEL_NONE
    df.loc[tiers.notna(), "bucket"] = LABEL_OTHER
    df.loc[tiers.isin(visible_names), "bucket"] = tiers

    known = {t.name for t in scheme}
    orphans = sorted({t for t in classification.values() if t not in known})
    if orphans:
        notes.append(
            "Classificação em categoria(s) fora do esquema atual, contada em "
            f"\"{LABEL_OTHER}\": {', '.join(orphans)}."
        )
    no_geom = df[~df["has_geometry"]]
    if len(no_geom) and no_geom["populacao"].notna().any():
        codes = ", ".join(str(c) for c in sorted(no_geom["code_muni"]))
        notes.append(
            f"{len(no_geom)} município(s) sem geometria no mapa (criado(s) após 2022: {codes}): "
            "só a população entra nos totais, em \"Sem classificação\"."
        )

    tables: Dict[str, pd.DataFrame] = {}
    groupings = {
        LEVEL_BRASIL: [("Brasil", 0, df)],
        LEVEL_REGIAO: [
            (name, int(code), part)
            for (code, name), part in df.groupby(["code_region", "name_region"], sort=True)
        ],
        LEVEL_ESTADO: [
            (f"{abbr} - {name}", int(code), part)
            for (code, abbr, name), part in df.groupby(
                ["code_state", "abbrev_state", "name_state"], sort=True
            )
        ],
    }
    for level, groups in groupings.items():
        rows: List[dict] = []
        for grupo, ordem, part in groups:
            rows.extend(_group_rows(grupo, ordem, part, visible, mode, tier))
        tables[level] = pd.DataFrame(rows, columns=RESULT_COLUMNS)

    return StatsResult(
        tables=tables,
        notes=notes,
        has_area=bool(universe["area_km2"].notna().any()),
        has_populacao=bool(universe["populacao"].notna().any()),
    )


__all__ = [
    "build_universe", "compute", "StatsResult", "LEVELS",
    "LEVEL_BRASIL", "LEVEL_REGIAO", "LEVEL_ESTADO",
    "KIND_TIER", "KIND_SUBTOTAL", "KIND_OTHER", "KIND_NONE", "KIND_TOTAL",
    "LABEL_OTHER", "LABEL_NONE", "LABEL_TOTAL",
]
