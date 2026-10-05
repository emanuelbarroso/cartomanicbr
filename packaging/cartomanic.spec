# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Cartomanic BR.

First *working* build -- correctness over size for now. The heavy lifting
(geopandas/pyarrow/duckdb/pyproj) already has PyInstaller contrib hooks
installed via `pyinstaller-hooks-contrib`; `pyogrio` (GDAL bindings) does
not, and ships its own gdal_data/proj_data + bundled DLLs that static
import analysis alone won't find -- that's the one dependency this spec
handles explicitly via `collect_all`.

Build from the repo root:

    .venv/Scripts/pyinstaller packaging/cartomanic.spec --clean --noconfirm

Output lands in `dist/CartomanicBR/` (--onedir, not --onefile -- see the
README packaging notes for why).
"""
import os

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))
SRC = os.path.join(REPO_ROOT, "src")
GEO_CACHE = os.path.join(SRC, "cartomanic", "data", "geo_cache")

pyogrio_datas, pyogrio_binaries, pyogrio_hidden = collect_all("pyogrio")

datas = [
    (GEO_CACHE, "cartomanic/data/geo_cache"),
] + pyogrio_datas

binaries = list(pyogrio_binaries)

hiddenimports = list(pyogrio_hidden)

# Components confirmed unused by this app -- see packaging/README.md
# "Size pruning" for exactly how each of these was verified (removed from
# the dev venv, full test suite + a real GeoDataFrame parquet round-trip
# run against the remaining files; the same removal re-verified against
# this frozen build via a temporary smoke-test entrypoint). Re-validate
# this list whenever pyarrow/pyogrio are upgraded -- an internal
# dependency between components can appear in a new version without
# warning here; only an actual re-run of that check would catch it.
_UNUSED_SUBSTRINGS = [
    # pyarrow: Flight RPC, Substrait plan (de)serialization and the
    # Dataset discovery API -- never imported by this app, and not
    # pulled in transitively by geopandas' parquet I/O (which only needs
    # pyarrow's core + parquet + compute components). Plus pure dev
    # artifacts (C++ headers, static .lib files, the test suite) that are
    # never loaded at runtime under any code path, by construction.
    "pyarrow/arrow_flight.dll",
    "pyarrow/arrow_substrait.dll",
    "pyarrow/arrow_dataset.dll",
    "pyarrow/_flight.cp312-win_amd64.pyd",
    "pyarrow/_dataset.cp312-win_amd64.pyd",
    "pyarrow/arrow_flight.lib",
    "pyarrow/arrow_dataset.lib",
    "pyarrow/arrow.lib",
    "pyarrow/parquet.lib",
    "pyarrow/include/",
    "pyarrow/src/",
    "pyarrow/tests/",
    # pyogrio: has no PyInstaller contrib hook, so it's collected with
    # collect_all() above -- which grabs the bundled test fixtures too.
    # Never imported outside of pyogrio's own test suite.
    "pyogrio/tests/",
]


def _drop_unused(toc):
    """Filters a PyInstaller TOC (dest, source, typecode) by substring
    match against `_UNUSED_SUBSTRINGS`, independent of how the entry was
    collected (hook, collect_all, manual) -- works for both `a.binaries`
    and `a.datas`."""
    kept = []
    for entry in toc:
        haystack = entry[0].replace("\\", "/").lower()
        if any(pattern in haystack for pattern in _UNUSED_SUBSTRINGS):
            continue
        kept.append(entry)
    return TOC(kept)


a = Analysis(
    [os.path.join(REPO_ROOT, "packaging", "entrypoint.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest", "_pytest", "pip",
        "pyarrow.flight", "pyarrow.dataset", "pyarrow.substrait", "pyarrow.tests",
        "pyogrio.tests",
    ],
    noarchive=False,
)

a.binaries = _drop_unused(a.binaries)
a.datas = _drop_unused(a.datas)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CartomanicBR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CartomanicBR",
)
