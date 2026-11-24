"""Piccole utilità per la finestra della console di Windows."""
from __future__ import annotations

import ctypes
import os


def _kernel32():
    if os.name != "nt":
        return None
    try:
        return ctypes.windll.kernel32  # type: ignore[attr-defined]
    except AttributeError:
        return None


def set_title(title: str) -> None:
    kernel32 = _kernel32()
    if kernel32 is not None:
        try:
            kernel32.SetConsoleTitleW(title)
        except OSError:
            pass


def launched_by_double_click() -> bool:
    """True se la console è stata creata apposta per questo programma (doppio clic).

    In un terminale già aperto la console è condivisa con la shell, quindi i
    processi collegati sono di più. Quando parte da "Avvia TempCleaner.cmd"
    (variabile TEMPCLEANER_LAUNCHER=1) c'è anche cmd.exe, per questo la soglia sale a 2.
    """
    kernel32 = _kernel32()
    if kernel32 is None:
        return False
    try:
        processes = (ctypes.c_uint32 * 8)()
        count = kernel32.GetConsoleProcessList(processes, 8)
    except OSError:
        return False
    own = 2 if os.environ.get("TEMPCLEANER_LAUNCHER") == "1" else 1
    return 0 < count <= own


def pause_if_needed() -> None:
    """Tiene aperta la finestra alla fine, così si può leggere il report."""
    if not launched_by_double_click():
        return
    try:
        input("\nPremi Invio per chiudere...")
    except (EOFError, KeyboardInterrupt):
        pass
