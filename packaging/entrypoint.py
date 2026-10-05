"""PyInstaller's analysis walks from a plain script, not a package's
`__main__.py` run via `-m` -- this is that script. Kept outside `src/` so it
is obviously build tooling, not part of the installable package.
"""
from cartomanic.__main__ import main

if __name__ == "__main__":
    main()
