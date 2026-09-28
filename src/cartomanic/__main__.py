"""Entry point for `python -m cartomanic` / the `cartomanic` console script."""
from .gui.main_window import MainWindow


def main() -> None:
    MainWindow().mainloop()


if __name__ == "__main__":
    main()
