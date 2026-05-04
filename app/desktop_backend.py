from __future__ import annotations

import importlib.util
import os


BACKEND_ENV = "OKRA_DESKTOP_BACKEND"
AUTO_BACKEND = "auto"
QT_BACKEND = "qt"
_VALID_BACKENDS = {AUTO_BACKEND, QT_BACKEND}


def normalize_backend(value: str | None) -> str:
    text = str(value or AUTO_BACKEND).strip().lower()
    if text not in _VALID_BACKENDS:
        return QT_BACKEND
    if text == AUTO_BACKEND:
        return QT_BACKEND
    return text


def pyside6_available() -> bool:
    return importlib.util.find_spec("PySide6") is not None


def resolve_desktop_backend(preferred: str | None = None) -> tuple[str, str]:
    requested = normalize_backend(preferred or os.getenv(BACKEND_ENV))
    if requested != QT_BACKEND:
        raise RuntimeError(f"Unsupported desktop backend: {requested}")
    if not pyside6_available():
        raise ModuleNotFoundError("PySide6")
    return QT_BACKEND, "qt_only"


def backend_fallback_message(backend: str, reason: str) -> str:
    if backend == QT_BACKEND and reason == "qt_only":
        return "Launching Qt desktop shell."
    return "Qt desktop shell requires PySide6."
