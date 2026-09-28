"""JSON export/import for a project's classification scheme + assignments.

Two dictionaries, matching what someone would actually want to hand-edit or
diff:

- "categories": every category, keyed by a stable string id (its
  `sort_order`), holding name/color/sort_order. `scheme_kind` (discrete or
  hierarchical) sits alongside it, not per-category -- it describes the
  whole legend.
- "classification": one dict per state (UF), each keyed by a category id,
  holding the list of `code_muni` assigned to it.

Import is all-or-nothing: every row is validated against the current
project + bundled geometry (JSON shape, valid UF, unknown category id,
unknown/mismatched município, duplicate município) and every problem is
collected into one `ClassificationImportError` before a single município is
touched -- never a partial apply. Geometry itself is never part of this
file; only the two dictionaries above, referencing what the running
Cartomanic already has.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..data import geo_source
from .project import DISCRETE, HIERARCHICAL, Project, Tier

FORMAT_VERSION = 1
_VALID_KINDS = (DISCRETE, HIERARCHICAL)


class ClassificationImportError(Exception):
    """`errors` holds every problem found in the file, not just the first."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _code_to_uf_map() -> Dict[int, str]:
    muni_gdf = geo_source.load_municipios()
    if muni_gdf is None or "abbrev_state" not in muni_gdf.columns:
        return {}
    return dict(zip(muni_gdf["code_muni"].astype(int), muni_gdf["abbrev_state"]))


def _known_ufs() -> "set[str]":
    estados = geo_source.load_estados()
    if estados is None or estados.empty or "abbrev_state" not in estados.columns:
        return set()
    return set(estados["abbrev_state"])


# ------------------------------------------------------------------ export
def export_to_dict(project: Project) -> Dict[str, Any]:
    scheme = project.get_scheme()
    categories = {
        str(t.sort_order): {"name": t.name, "color": t.color, "sort_order": t.sort_order}
        for t in scheme
    }
    name_to_id = {t.name: str(t.sort_order) for t in scheme}

    classification: Dict[str, Dict[str, List[int]]] = {}
    df = project.get_classification_df()
    if not df.empty:
        code_to_uf = _code_to_uf_map()
        for row in df.itertuples(index=False):
            code = int(row.code_muni)
            cat_id = name_to_id.get(row.tier)
            uf = code_to_uf.get(code)
            if cat_id is None or uf is None:
                continue  # stale/unmatchable row (e.g. geometry changed since); skip rather than fail export
            classification.setdefault(uf, {}).setdefault(cat_id, []).append(code)

    return {
        "cartomanic_export_version": FORMAT_VERSION,
        "scheme_kind": project.scheme_kind,
        "categories": categories,
        "classification": classification,
    }


# ------------------------------------------------------------------ import
def validate_and_parse(data: Any) -> Tuple[str, List[Tier], Dict[int, str]]:
    """Returns (scheme_kind, tiers, code_muni -> category name). Raises
    `ClassificationImportError` (every problem found, not just the first)
    if `data` doesn't match the export schema."""
    errors: List[str] = []

    if not isinstance(data, dict):
        raise ClassificationImportError(["O arquivo não contém um objeto JSON no nível principal."])

    scheme_kind = data.get("scheme_kind")
    if scheme_kind not in _VALID_KINDS:
        errors.append(
            f"'scheme_kind' ausente ou inválido (esperado 'discrete' ou 'hierarchical'): {scheme_kind!r}"
        )

    categories = data.get("categories")
    tiers: List[Tier] = []
    id_to_name: Dict[str, str] = {}
    if not isinstance(categories, dict) or not categories:
        errors.append("'categories' ausente, vazio, ou não é um objeto.")
    else:
        for cat_id, entry in categories.items():
            if not isinstance(entry, dict):
                errors.append(f"Categoria '{cat_id}': deveria ser um objeto com name/color/sort_order.")
                continue
            name, color, sort_order = entry.get("name"), entry.get("color"), entry.get("sort_order")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"Categoria '{cat_id}': 'name' ausente ou vazio.")
                continue
            if not isinstance(color, str) or not color.strip():
                errors.append(f"Categoria '{cat_id}': 'color' ausente ou vazio.")
                continue
            if not isinstance(sort_order, int):
                errors.append(f"Categoria '{cat_id}': 'sort_order' ausente ou não é inteiro.")
                continue
            id_to_name[cat_id] = name
            tiers.append(Tier(name, color, sort_order))

    classification = data.get("classification")
    code_to_tier: Dict[int, str] = {}

    if not isinstance(classification, dict):
        errors.append("'classification' ausente ou não é um objeto.")
    else:
        known_ufs = _known_ufs()
        code_to_real_uf = _code_to_uf_map()
        seen_codes: Dict[int, str] = {}

        for uf, per_category in classification.items():
            if known_ufs and uf not in known_ufs:
                errors.append(f"Estado '{uf}' não é uma UF brasileira reconhecida.")
                continue
            if not isinstance(per_category, dict):
                errors.append(f"Estado '{uf}': deveria mapear id de categoria para lista de municípios.")
                continue
            for cat_id, codes in per_category.items():
                if cat_id not in id_to_name:
                    errors.append(f"Estado '{uf}': categoria '{cat_id}' não existe em 'categories'.")
                    continue
                if not isinstance(codes, list):
                    errors.append(f"Estado '{uf}', categoria '{cat_id}': deveria ser uma lista de códigos.")
                    continue
                for code in codes:
                    if not isinstance(code, int):
                        errors.append(
                            f"Estado '{uf}', categoria '{cat_id}': código de município inválido: {code!r}."
                        )
                        continue
                    if code in seen_codes:
                        errors.append(f"Município {code} aparece mais de uma vez (também em {seen_codes[code]}).")
                        continue
                    real_uf = code_to_real_uf.get(code)
                    if real_uf is None:
                        errors.append(f"Município {code} não encontrado nos dados geográficos atuais.")
                        continue
                    if real_uf != uf:
                        errors.append(f"Município {code} está listado em '{uf}', mas pertence a '{real_uf}'.")
                        continue
                    seen_codes[code] = f"{uf}/{cat_id}"
                    code_to_tier[code] = id_to_name[cat_id]

    if errors:
        raise ClassificationImportError(errors)

    tiers.sort(key=lambda t: t.sort_order)
    return scheme_kind, tiers, code_to_tier


def apply_import(project: Project, scheme_kind: str, tiers: List[Tier], code_to_tier: Dict[int, str]) -> None:
    project.import_scheme_and_classification(scheme_kind, tiers, code_to_tier)


__all__ = [
    "FORMAT_VERSION", "ClassificationImportError",
    "export_to_dict", "validate_and_parse", "apply_import",
]
