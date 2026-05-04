from __future__ import annotations

import argparse
import sys

from desktop_backend import QT_BACKEND, backend_fallback_message, resolve_desktop_backend


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Launch okra assistant desktop shell.")
    parser.add_argument("--backend", choices=["qt"], help="Qt is the only supported desktop backend.")
    args, passthrough_argv = parser.parse_known_args(argv)

    backend, reason = resolve_desktop_backend(args.backend)
    message = backend_fallback_message(backend, reason)
    if message:
        print(message, file=sys.stderr)
    if backend != QT_BACKEND:
        raise RuntimeError(f"Unsupported desktop backend: {backend}")
    from desktop_shell_qt import main as qt_main

    qt_main(passthrough_argv)


if __name__ == "__main__":
    main()
