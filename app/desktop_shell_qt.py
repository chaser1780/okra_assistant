from __future__ import annotations

import sys
from pathlib import Path


try:
    from qtui.shell import QtDesktopShell, main, run_app
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from qtui.shell import QtDesktopShell, main, run_app


__all__ = ["QtDesktopShell", "run_app", "main"]


if __name__ == "__main__":
    main()
