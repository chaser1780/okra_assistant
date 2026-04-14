from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    try:
        from desktop_shell_qt import main as qt_main
    except ModuleNotFoundError as exc:
        if exc.name != "PySide6":
            raise
        print("PySide6 unavailable, falling back to legacy Tk shell.", file=sys.stderr)
        from desktop_shell import main as tk_main

        tk_main()
        return
    qt_main()


if __name__ == "__main__":
    main()
