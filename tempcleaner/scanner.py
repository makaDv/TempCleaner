"""Scansione delle cartelle Temp: cosa c'è e cosa si può eliminare."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .discovery import TempRoot, is_link
from .services import identify


@dataclass
class Item:
    """Un elemento di primo livello dentro una cartella Temp (file o cartella)."""

    root: TempRoot
    path: str
    name: str
    service: str
    is_dir: bool
    files: list[tuple[str, int]] = field(default_factory=list)  # (percorso, byte) eliminabili
    dirs: list[str] = field(default_factory=list)  # cartelle da rimuovere se vuote, prima le più profonde
    recent_files: int = 0
    recent_size: int = 0
    skipped_links: int = 0
    errors: int = 0

    @property
    def size(self) -> int:
        return sum(s for _, s in self.files)


@dataclass
class ScanResult:
    roots: list[TempRoot]
    items: list[Item]
    min_age_hours: float
    root_errors: list[tuple[TempRoot, str]] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return sum(len(i.files) for i in self.items)

    @property
    def total_size(self) -> int:
        return sum(i.size for i in self.items)

    @property
    def total_dirs(self) -> int:
        return sum(len(i.dirs) for i in self.items)

    @property
    def recent_files(self) -> int:
        return sum(i.recent_files for i in self.items)

    @property
    def recent_size(self) -> int:
        return sum(i.recent_size for i in self.items)

    @property
    def skipped_links(self) -> int:
        return sum(i.skipped_links for i in self.items)

    @property
    def errors(self) -> int:
        return sum(i.errors for i in self.items)

    def by_root(self) -> dict[str, list[int]]:
        """percorso cartella -> [file, cartelle, byte]."""
        out = {r.path: [0, 0, 0] for r in self.roots}
        for i in self.items:
            row = out[i.root.path]
            row[0] += len(i.files)
            row[1] += len(i.dirs)
            row[2] += i.size
        return out

    def by_service(self) -> dict[str, list[int]]:
        """servizio -> [file, byte] (solo file eliminabili)."""
        out: dict[str, list[int]] = {}
        for i in self.items:
            if not i.files:
                continue
            row = out.setdefault(i.service, [0, 0])
            row[0] += len(i.files)
            row[1] += i.size
        return out


def _add_file(entry: os.DirEntry, item: Item, cutoff: float) -> None:
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        item.errors += 1
        return
    if st.st_mtime <= cutoff:
        item.files.append((entry.path, st.st_size))
    else:
        item.recent_files += 1
        item.recent_size += st.st_size


def _walk(top: str, item: Item, cutoff: float, top_mtime: float) -> None:
    dirs: list[str] = []
    stack = [top]
    while stack:
        folder = stack.pop()
        try:
            iterator = os.scandir(folder)
        except OSError:
            item.errors += 1
            continue
        with iterator:
            for entry in iterator:
                try:
                    if is_link(entry):
                        item.skipped_links += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        if entry.stat(follow_symlinks=False).st_mtime <= cutoff:
                            dirs.append(entry.path)
                        continue
                except OSError:
                    item.errors += 1
                    continue
                _add_file(entry, item, cutoff)
    dirs.sort(key=lambda p: p.count(os.sep), reverse=True)
    if top_mtime <= cutoff:
        dirs.append(top)
    item.dirs = dirs


def _scan_entry(root: TempRoot, entry: os.DirEntry, cutoff: float) -> Item:
    try:
        link = is_link(entry)
        is_dir = not link and entry.is_dir(follow_symlinks=False)
    except OSError:
        link, is_dir = False, False
    item = Item(root, entry.path, entry.name, root.label or identify(entry.name, is_dir), is_dir)
    if link:
        item.skipped_links += 1
    elif is_dir:
        try:
            mtime = entry.stat(follow_symlinks=False).st_mtime
        except OSError:
            mtime = float("inf")
        _walk(entry.path, item, cutoff, mtime)
    else:
        _add_file(entry, item, cutoff)
    return item


def scan(roots: list[TempRoot], min_age_hours: float = 24.0, now: float | None = None) -> ScanResult:
    """Elenca il contenuto delle cartelle Temp.

    Sono eliminabili solo i file non modificati nelle ultime ``min_age_hours`` ore.
    Collegamenti simbolici e junction non vengono mai seguiti.
    """
    cutoff = (time.time() if now is None else now) - min_age_hours * 3600
    result = ScanResult(roots, [], min_age_hours)
    for root in roots:
        try:
            iterator = os.scandir(root.path)
        except OSError as exc:
            result.root_errors.append((root, exc.strerror or str(exc)))
            continue
        with iterator:
            for entry in iterator:
                result.items.append(_scan_entry(root, entry, cutoff))
    return result
