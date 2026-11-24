"""Crea dist/TempCleaner.zip, il pacchetto da scaricare per gli utenti.

Contiene solo file (nessuna cartella), così in Esplora file il primo elemento
in ordine alfabetico è "Avvia TempCleaner.cmd". Il codice Python è impacchettato
in TempCleaner-app.pyz, un archivio zip che Python esegue direttamente.
"""
from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "Avvia TempCleaner.cmd"
APP = "TempCleaner-app.pyz"
APP_MAIN = "import sys\nfrom tempcleaner.cli import main\n\nsys.exit(main())\n"


def _crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def build_app() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pyz:
        pyz.writestr("__main__.py", APP_MAIN)
        for source in sorted((ROOT / "tempcleaner").glob("*.py")):
            pyz.write(source, f"tempcleaner/{source.name}")
    return buffer.getvalue()


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "TempCleaner.zip"
    entries = {
        LAUNCHER: _crlf((ROOT / LAUNCHER).read_bytes()),
        APP: build_app(),
        "LEGGIMI.txt": _crlf((ROOT / "packaging" / "LEGGIMI.txt").read_bytes()),
        "DISCLAIMER.txt": _crlf((ROOT / "DISCLAIMER.md").read_bytes()),
        "LICENSE.txt": _crlf((ROOT / "LICENSE").read_bytes()),
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (out_dir / "TempCleaner.zip.sha256").write_text(f"{digest}  TempCleaner.zip\n", encoding="ascii")
    return target


if __name__ == "__main__":
    out = build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist")
    print(out)
