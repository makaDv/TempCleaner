"""Riconosce quale programma ha creato un file o una cartella temporanea."""
from __future__ import annotations

import os
import re

# (espressione regolare sul nome, servizio). La prima che corrisponde vince.
_PATTERNS: list[tuple[str, str]] = [
    (r"^(chrome|google|crashpad|scoped_dir|chromedriver)", "Google Chrome / Chromium"),
    (r"^(msedge|edge_|microsoftedge)", "Microsoft Edge"),
    (r"^(mozilla|firefox|moz)", "Mozilla Firefox"),
    (r"^opera", "Opera"),
    (r"^brave", "Brave"),
    (r"discord", "Discord"),
    (r"^(teams|msteams)", "Microsoft Teams"),
    (r"^(zoom)", "Zoom"),
    (r"^(slack)", "Slack"),
    (r"^(whatsapp)", "WhatsApp"),
    (r"^(telegram)", "Telegram"),
    (r"^(spotify)", "Spotify"),
    (r"^steam", "Steam"),
    (r"^(epic|unreal)", "Epic Games"),
    (r"^(battle\.net|blizzard)", "Battle.net"),
    (r"^(nvidia|nv_|nvcache|gfe)", "NVIDIA"),
    (r"^(amd|radeon|ati)", "AMD"),
    (r"^(intel)", "Intel"),
    (r"^(npm-|_npx|npm_|node-|yarn|pnpm)", "Node.js (npm/yarn)"),
    (r"^(pip-|pip_|python|_mei|pyinstaller|uv-|poetry)", "Python (pip/PyInstaller)"),
    (r"^(vscode|code-|vs_|vsix)", "Visual Studio Code"),
    (r"^(visualstudio|vs[0-9]|msbuild|vsixinstaller)", "Visual Studio"),
    (r"^(dotnet|nuget|\.net)", ".NET / NuGet"),
    (r"^(go-build|gopls|go-)", "Go"),
    (r"^(cargo|rust)", "Rust"),
    (r"^(hsperfdata|jna|java|gradle|maven|jetbrains|idea)", "Java / JetBrains"),
    (r"^(git|github)", "Git / GitHub"),
    (r"^(docker)", "Docker"),
    (r"^(claude|anthropic)", "Claude"),
    (r"^(adobe|acro|photoshop|lightroom)", "Adobe"),
    (r"^(onedrive)", "OneDrive"),
    (r"^(outlook|word|excel|powerpoint|office|msoffice|onenote|mso)", "Microsoft Office"),
    (r"^(winget)", "WinGet"),
    (r"^(msi|setup|install|unins|is-)", "Installer / Windows Installer"),
    (r"^(wer|diagnostic|crash)", "Segnalazione errori Windows"),
    (r"^(windowsupdate|wu|mpcmdrun|defender|msmpeng|mpsigstub)", "Windows Update / Defender"),
    (r"^(dism|cbs|tracing)", "Manutenzione Windows"),
    (r"^\{[0-9a-f-]{36}\}$", "Installer (cartella GUID)"),
    (r"^[0-9a-f-]{36}$", "Cartelle con ID univoco"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), s) for p, s in _PATTERNS]

_EXTENSIONS = {
    ".tmp": "File .tmp generici",
    ".log": "File di log",
    ".etl": "Tracce diagnostiche Windows (.etl)",
    ".dmp": "Dump di crash",
    ".msi": "Installer / Windows Installer",
    ".msp": "Installer / Windows Installer",
    ".exe": "Eseguibili temporanei",
    ".dll": "Librerie temporanee",
    ".zip": "Archivi temporanei",
    ".cab": "Archivi temporanei",
    ".7z": "Archivi temporanei",
    ".txt": "File di testo",
    ".json": "File di dati",
    ".xml": "File di dati",
    ".png": "Immagini",
    ".jpg": "Immagini",
    ".jpeg": "Immagini",
    ".gif": "Immagini",
    ".webp": "Immagini",
    ".ps1": "Script temporanei",
    ".bat": "Script temporanei",
    ".cmd": "Script temporanei",
    ".vbs": "Script temporanei",
}

OTHER = "Altro / sconosciuto"


def identify(name: str, is_dir: bool = False) -> str:
    """Restituisce il nome del servizio probabile per un elemento in una cartella Temp."""
    for regex, service in _COMPILED:
        if regex.search(name):
            return service
    if not is_dir:
        ext = os.path.splitext(name)[1].lower()
        if ext in _EXTENSIONS:
            return _EXTENSIONS[ext]
        if re.match(r"^~?(tmp|\$)", name, re.IGNORECASE):
            return "File .tmp generici"
    return OTHER
