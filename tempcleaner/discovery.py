"""Individua automaticamente le cartelle dei file temporanei.

Una cartella viene accettata solo se si chiama ``Temp`` o ``tmp``: il programma
non lavora mai su cartelle con un altro nome.
"""
from __future__ import annotations

import ctypes
import os
import stat
import tempfile
from dataclasses import dataclass

SCOPES = {
    "user": "Temp dell'utente corrente (%TEMP%, %TMP%)",
    "users": "Temp di tutti i profili utente (richiede amministratore)",
    "system": "Temp di sistema (%SystemRoot%\\Temp, richiede amministratore)",
    "apps": "Cartelle Temp/tmp delle applicazioni in %LOCALAPPDATA% e %APPDATA%",
}
TEMP_NAMES = frozenset({"temp", "tmp"})
APPS_MAX_DEPTH = 3
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class TempRoot:
    """Una cartella Temp da ripulire."""

    path: str
    scope: str
    label: str | None = None  # nome dell'app che possiede la cartella (scope "apps")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def path_key(path: str) -> str:
    """Chiave di confronto: percorso reale, maiuscole/minuscole normalizzate."""
    return os.path.normcase(os.path.realpath(path))


def is_inside(parent_key: str, child_key: str) -> bool:
    """True se child_key sta dentro parent_key (e non coincide)."""
    return child_key.startswith(parent_key.rstrip("\\/") + os.sep)


def is_link(entry: os.DirEntry) -> bool:
    """True per collegamenti simbolici, junction e altri reparse point."""
    if entry.is_symlink():
        return True
    attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attrs & REPARSE_POINT)


def _forbidden_keys() -> set[str]:
    names = (
        "SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
        "ProgramData", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PUBLIC",
    )
    return {path_key(v) for v in (os.environ.get(n) for n in names) if v}


def is_safe_root(path: str) -> bool:
    """Regola di sicurezza: solo cartelle esistenti chiamate Temp/tmp, mai cartelle di sistema."""
    try:
        real = os.path.realpath(path)
    except (OSError, ValueError):
        return False
    if os.path.basename(real.rstrip("\\/")).lower() not in TEMP_NAMES:
        return False
    if os.path.dirname(real) == real:  # radice di un disco
        return False
    if os.path.normcase(real) in _forbidden_keys():
        return False
    return os.path.isdir(real)


def _user_candidates() -> list[TempRoot]:
    paths = [os.environ.get("TEMP"), os.environ.get("TMP"), tempfile.gettempdir()]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths.append(os.path.join(local, "Temp"))
    return [TempRoot(p, "user") for p in paths if p]


def _users_candidates(warnings: list[str]) -> list[TempRoot]:
    profile = os.environ.get("USERPROFILE")
    base = os.path.dirname(profile) if profile else os.path.join(
        os.environ.get("SystemDrive", "C:") + os.sep, "Users")
    try:
        names = sorted(os.listdir(base))
    except OSError as exc:
        warnings.append(f"Impossibile leggere {base}: {exc.strerror or exc}")
        return []
    found, denied = [], []
    for name in names:
        path = os.path.join(base, name, "AppData", "Local", "Temp")
        try:
            with os.scandir(path):
                pass
        except PermissionError:
            denied.append(name)
            continue
        except OSError:
            continue
        found.append(TempRoot(path, "users"))
    if denied:
        warnings.append("Accesso negato ai Temp di: " + ", ".join(denied)
                        + " (avvia come amministratore per includerli)")
    return found


def _system_candidates(warnings: list[str]) -> list[TempRoot]:
    sysroot = os.environ.get("SystemRoot") or os.environ.get("windir")
    if not sysroot:
        return []
    path = os.path.join(sysroot, "Temp")
    if not is_admin():
        warnings.append(f"{path} saltata: serve avviare il terminale come amministratore")
        return []
    return [TempRoot(path, "system")]


def _app_label(base: str, path: str) -> str | None:
    parts = os.path.relpath(path, base).split(os.sep)[:-1]
    if not parts:
        return None
    if parts[0].lower() == "packages" and len(parts) > 1:  # app UWP / Microsoft Store
        return parts[1].split("_")[0]
    return parts[0]


def _apps_candidates() -> list[TempRoot]:
    user_keys = {path_key(c.path) for c in _user_candidates()}
    found = []
    for var in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(var)
        if not base or not os.path.isdir(base):
            continue
        stack = [(base, 0)]
        while stack:
            folder, depth = stack.pop()
            try:
                iterator = os.scandir(folder)
            except OSError:
                continue
            with iterator:
                for entry in iterator:
                    try:
                        if is_link(entry) or not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if entry.name.lower() in TEMP_NAMES:
                        if path_key(entry.path) not in user_keys:
                            found.append(TempRoot(entry.path, "apps", _app_label(base, entry.path)))
                    elif depth + 1 < APPS_MAX_DEPTH:
                        stack.append((entry.path, depth + 1))
    return found


def discover(scopes: list[str]) -> tuple[list[TempRoot], list[str]]:
    """Restituisce (cartelle Temp trovate, avvisi) per gli scope richiesti."""
    warnings: list[str] = []
    candidates: list[TempRoot] = []
    for scope in scopes:
        if scope == "user":
            candidates += _user_candidates()
        elif scope == "users":
            candidates += _users_candidates(warnings)
        elif scope == "system":
            candidates += _system_candidates(warnings)
        elif scope == "apps":
            candidates += _apps_candidates()
        else:
            raise ValueError(f"scope sconosciuto: {scope}")

    roots: list[TempRoot] = []
    seen: set[str] = set()
    for cand in candidates:
        if not is_safe_root(cand.path):
            continue
        key = path_key(cand.path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(TempRoot(os.path.realpath(cand.path), cand.scope, cand.label))

    # Una cartella Temp dentro un'altra già in lista verrebbe contata due volte.
    keys = [path_key(r.path) for r in roots]
    roots = [r for r, k in zip(roots, keys) if not any(is_inside(o, k) for o in keys)]
    return roots, warnings
