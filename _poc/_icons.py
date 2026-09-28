"""Toolbar glyphs, taken from the Windows icon font.

Adapted from the harmonica project (`harmonica.gui_boxes._icons`). Windows 11
ships "Segoe Fluent Icons" and Windows 10 "Segoe MDL2 Assets"; the codepoints
used here exist in both. `icon_family` picks whichever is installed (falling
back to the default font, which renders a box -- only happens off Windows).
"""
import tkinter.font as tkfont

_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# command id -> Segoe icon-font codepoint
_CODEPOINTS = {
    "proj_new": 0xE710,     # Add
    "proj_open": 0xE8E5,    # OpenFile
    "proj_save": 0xE74E,    # Save
    "proj_save_as": 0xE792, # SaveAs
    "proj_close": 0xE8BB,   # ChromeClose
}

GLYPHS = {name: chr(cp) for name, cp in _CODEPOINTS.items()}
_FALLBACK = chr(0xE783)     # Info -- visible marker if a name is missing


def glyph(name: str) -> str:
    return GLYPHS.get(name, _FALLBACK)


def icon_family(root=None) -> str:
    available = set(tkfont.families(root))
    return next((f for f in _FAMILIES if f in available), "TkDefaultFont")


def icon_font(root=None, size: int = 13) -> tkfont.Font:
    return tkfont.Font(root=root, family=icon_family(root), size=size)
