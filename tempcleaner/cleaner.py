"""Eliminazione sicura del contenuto delle cartelle Temp."""
from __future__ import annotations

import os
import stat
from collections import Counter
from dataclasses import dataclass, field

from .discovery import is_inside, is_safe_root, path_key
from .scanner import Item, ScanResult

ERROR_SHARING_VIOLATION = 32


@dataclass
class CleanResult:
    deleted_files: int = 0
    deleted_dirs: int = 0
    freed: int = 0
    skipped: Counter = field(default_factory=Counter)  # motivo -> numero di file
    by_service: dict[str, list[int]] = field(default_factory=dict)  # servizio -> [file, byte]
    cleaned_items: list[tuple[Item, int, int]] = field(default_factory=list)  # (elemento, file, byte)
    deleted_paths: list[str] = field(default_factory=list)

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except PermissionError as exc:
        if getattr(exc, "winerror", None) == ERROR_SHARING_VIOLATION:
            raise
        # Può essere un file di sola lettura: si toglie l'attributo e si riprova.
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        except OSError:
            raise exc from None


def _reason(exc: OSError) -> str:
    if getattr(exc, "winerror", None) == ERROR_SHARING_VIOLATION:
        return "in uso da un altro programma"
    if isinstance(exc, PermissionError):
        return "accesso negato"
    return "altro errore"


def _contained(root_key: str, path: str) -> bool:
    try:
        return is_inside(root_key, path_key(path))
    except (OSError, ValueError):
        return False


def clean(scan: ScanResult, keep_paths: bool = False) -> CleanResult:
    """Elimina i file eliminabili trovati da ``scan``. La cartella Temp stessa non viene mai rimossa."""
    result = CleanResult()
    safe_roots: dict[str, str | None] = {}
    for item in scan.items:
        root = item.root.path
        if root not in safe_roots:
            safe_roots[root] = path_key(root) if is_safe_root(root) else None
        root_key = safe_roots[root]
        if root_key is None:
            result.skipped["cartella non più valida"] += len(item.files)
            continue

        files = freed = 0
        for path, size in item.files:
            if not _contained(root_key, path):
                result.skipped["fuori dalla cartella Temp"] += 1
                continue
            try:
                _remove_file(path)
            except FileNotFoundError:
                continue  # già sparito
            except OSError as exc:
                result.skipped[_reason(exc)] += 1
                continue
            files += 1
            freed += size
            if keep_paths:
                result.deleted_paths.append(path)

        for folder in item.dirs:
            if not _contained(root_key, folder):
                continue
            try:
                os.rmdir(folder)  # riesce solo se la cartella è vuota
            except OSError:
                continue
            result.deleted_dirs += 1

        if files:
            result.deleted_files += files
            result.freed += freed
            row = result.by_service.setdefault(item.service, [0, 0])
            row[0] += files
            row[1] += freed
            result.cleaned_items.append((item, files, freed))
    return result
