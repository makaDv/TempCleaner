"""Stampa dei report in console (testo colorato o JSON)."""
from __future__ import annotations

import ctypes
import os
import sys

from .cleaner import CleanResult
from .discovery import TempRoot
from .scanner import ScanResult


def enable_color(force_off: bool = False) -> bool:
    if force_off or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except (AttributeError, OSError):
            return False
    return True


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, t: str) -> str:
        return self._wrap(t, "1")

    def dim(self, t: str) -> str:
        return self._wrap(t, "2")

    def green(self, t: str) -> str:
        return self._wrap(t, "32")

    def yellow(self, t: str) -> str:
        return self._wrap(t, "33")

    def red(self, t: str) -> str:
        return self._wrap(t, "31")

    def cyan(self, t: str) -> str:
        return self._wrap(t, "36")


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def display_path(path: str) -> str:
    """Accorcia i percorsi sostituendo la cartella utente con %USERPROFILE%."""
    profile = os.environ.get("USERPROFILE")
    if profile and os.path.normcase(path).startswith(os.path.normcase(profile.rstrip("\\/")) + os.sep):
        return "%USERPROFILE%" + path[len(profile.rstrip("\\/")):]
    return path


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else "..." + text[-(width - 3):]


def table(headers: list[str], rows: list[list[str]], right: set[int], style: Style) -> str:
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]

    def fmt(row: list[str]) -> str:
        cells = [str(c).rjust(w) if i in right else str(c).ljust(w)
                 for i, (c, w) in enumerate(zip(row, widths))]
        return "  " + "  ".join(cells)

    lines = [style.bold(fmt(headers)), "  " + "  ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows]
    return "\n".join(lines)


def print_roots(roots: list[TempRoot], warnings: list[str], style: Style) -> None:
    print(style.bold(f"\nCartelle Temp trovate: {len(roots)}"))
    for r in roots:
        tag = f"[{r.scope}]".ljust(9)
        extra = f"  ({r.label})" if r.label else ""
        print(f"  {style.cyan(tag)} {display_path(r.path)}{style.dim(extra)}")
    for w in warnings:
        print(style.yellow(f"  ! {w}"))


def _service_table(by_service: dict[str, list[int]], top: int, key: int, style: Style) -> str:
    total = sum(v[1] for v in by_service.values()) or 1
    ranked = sorted(by_service.items(), key=lambda kv: kv[1][key], reverse=True)[:top]
    rows = [[str(n), _cut(name, 40), f"{v[0]:,}".replace(",", "."), human(v[1]), f"{v[1] * 100 / total:.1f}%"]
            for n, (name, v) in enumerate(ranked, 1)]
    return table(["#", "Servizio", "File", "Spazio", "% spazio"], rows, {0, 2, 3, 4}, style)


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def print_preview(scan: ScanResult, top: int, style: Style) -> None:
    hours = f"{scan.min_age_hours:g}"
    print(style.bold(f"\nAnteprima: file non modificati da almeno {hours} ore"))
    rows = [[_cut(display_path(p), 60), _n(v[0]), _n(v[1]), human(v[2])] for p, v in scan.by_root().items()]
    rows.append([style.bold("TOTALE"), _n(scan.total_files), _n(scan.total_dirs), human(scan.total_size)])
    print(table(["Cartella", "File", "Cartelle", "Spazio"], rows, {1, 2, 3}, style))

    services = scan.by_service()
    if services:
        print(style.bold(f"\nServizi con più file temporanei (top {top})"))
        print(_service_table(services, top, 0, style))
        print(style.bold(f"\nServizi che occupano più spazio (top {top})"))
        print(_service_table(services, top, 1, style))

    notes = []
    if scan.recent_files:
        notes.append(f"{_n(scan.recent_files)} file recenti ({human(scan.recent_size)}) esclusi: potrebbero essere in uso")
    if scan.skipped_links:
        notes.append(f"{_n(scan.skipped_links)} collegamenti simbolici/junction ignorati")
    if scan.errors:
        notes.append(f"{_n(scan.errors)} elementi non leggibili")
    for root, err in scan.root_errors:
        notes.append(f"{display_path(root.path)} non leggibile: {err}")
    for note in notes:
        print(style.dim(f"  - {note}"))


def print_result(result: CleanResult, top: int, verbose: bool, style: Style) -> None:
    print(style.bold(style.green("\nPulizia completata")))
    print(f"  Spazio liberato:     {style.green(human(result.freed))}")
    print(f"  File eliminati:      {_n(result.deleted_files)}")
    print(f"  Cartelle eliminate:  {_n(result.deleted_dirs)}")
    if result.skipped_total:
        detail = ", ".join(f"{reason}: {_n(n)}" for reason, n in result.skipped.most_common())
        print(f"  File saltati:        {style.yellow(_n(result.skipped_total))} ({detail})")

    if result.by_service:
        print(style.bold(f"\nServizi ripuliti (top {top})"))
        print(_service_table(result.by_service, top, 0, style))

    if result.cleaned_items:
        print(style.bold(f"\nContenuto ripulito (elementi più grandi, top {top})"))
        ranked = sorted(result.cleaned_items, key=lambda t: t[2], reverse=True)[:top]
        rows = [[_cut(item.name + ("\\" if item.is_dir else ""), 45), _cut(item.service, 30), _n(f), human(b)]
                for item, f, b in ranked]
        print(table(["Elemento", "Servizio", "File", "Spazio"], rows, {2, 3}, style))

    if verbose and result.deleted_paths:
        print(style.bold("\nFile eliminati:"))
        for path in result.deleted_paths:
            print(style.dim(f"  {display_path(path)}"))


def to_json(roots: list[TempRoot], warnings: list[str], scan: ScanResult, result: CleanResult | None) -> dict:
    data = {
        "roots": [{"path": r.path, "scope": r.scope, "app": r.label} for r in roots],
        "warnings": warnings,
        "preview": {
            "min_age_hours": scan.min_age_hours,
            "files": scan.total_files,
            "dirs": scan.total_dirs,
            "bytes": scan.total_size,
            "recent_files_excluded": scan.recent_files,
            "links_ignored": scan.skipped_links,
            "by_root": {p: {"files": v[0], "dirs": v[1], "bytes": v[2]} for p, v in scan.by_root().items()},
            "by_service": {s: {"files": v[0], "bytes": v[1]} for s, v in scan.by_service().items()},
        },
        "result": None,
    }
    if result is not None:
        data["result"] = {
            "deleted_files": result.deleted_files,
            "deleted_dirs": result.deleted_dirs,
            "freed_bytes": result.freed,
            "skipped": dict(result.skipped),
            "by_service": {s: {"files": v[0], "bytes": v[1]} for s, v in result.by_service.items()},
        }
    return data
