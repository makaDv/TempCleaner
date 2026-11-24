"""Interfaccia a riga di comando."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .cleaner import clean
from .disclaimer import ACCEPT_WORDS, DISCLAIMER
from .discovery import SCOPES, discover
from .report import Style, enable_color, print_preview, print_result, print_roots, to_json
from .scanner import scan

SCOPE_LIST = list(SCOPES)


def parse_scopes(text: str) -> list[str]:
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    if "all" in parts:
        return SCOPE_LIST[:]
    chosen = []
    for p in parts:
        if p.isdigit() and 1 <= int(p) <= len(SCOPE_LIST):
            p = SCOPE_LIST[int(p) - 1]
        if p not in SCOPES:
            raise ValueError(p)
        if p not in chosen:
            chosen.append(p)
    if not chosen:
        raise ValueError(text)
    return chosen


def _scope_arg(text: str) -> list[str]:
    try:
        return parse_scopes(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"scope non valido: {exc}. Valori ammessi: {', '.join(SCOPE_LIST)}, all") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tempcleaner",
        description="Trova automaticamente le cartelle Temp di Windows e ne elimina il contenuto "
                    "in sicurezza. Elimina SOLO file dentro cartelle chiamate Temp/tmp.",
    )
    p.add_argument("-s", "--scope", type=_scope_arg,
                   help="cartelle da pulire, separate da virgola: " + ", ".join(SCOPE_LIST)
                        + ", all (senza questa opzione viene mostrato un menu)")
    p.add_argument("-a", "--min-age", type=float, default=24.0, metavar="ORE",
                   help="elimina solo file non modificati da almeno ORE ore (default: 24)")
    p.add_argument("-n", "--dry-run", action="store_true", help="mostra solo l'anteprima, non elimina nulla")
    p.add_argument("-y", "--yes", action="store_true", help="non chiedere conferma prima di eliminare")
    p.add_argument("-t", "--top", type=int, default=10, metavar="N", help="righe nelle classifiche (default: 10)")
    p.add_argument("-v", "--verbose", action="store_true", help="elenca ogni file eliminato")
    p.add_argument("--json", action="store_true", help="output in formato JSON (senza domande)")
    p.add_argument("--accept-responsibility", action="store_true",
                   help="dichiari di assumerti la responsabilità dell'uso (obbligatorio con --yes)")
    p.add_argument("--disclaimer", action="store_true", help="mostra l'esclusione di responsabilità ed esce")
    p.add_argument("--no-color", action="store_true", help="disattiva i colori")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def ask_scopes(style: Style) -> list[str]:
    print(style.bold("Quali cartelle Temp vuoi pulire?"))
    for n, (name, desc) in enumerate(SCOPES.items(), 1):
        print(f"  {n}) {name.ljust(7)} {desc}")
    print("  Puoi sceglierne più di una, separate da virgola (es. 1,4), oppure 'all'.")
    while True:
        answer = input("Scelta [1]: ").strip() or "1"
        try:
            return parse_scopes(answer)
        except ValueError:
            print(style.yellow("  Scelta non valida, riprova."))


def accept_disclaimer(style: Style) -> bool:
    print(style.yellow("\n" + DISCLAIMER))
    answer = input(style.bold("\nScrivi ACCETTO per assumerti la responsabilità e continuare: "))
    return answer.strip().lower() in ACCEPT_WORDS


def confirm(question: str) -> bool:
    return input(question).strip().lower() in {"s", "si", "sì", "y", "yes"}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:  # output rediretto su file o pipe: UTF-8 per non perdere le lettere accentate
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure") and not sys.stderr.isatty():
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.min_age < 0:
        print("--min-age non può essere negativo", file=sys.stderr)
        return 2
    style = Style(enable_color(args.no_color or args.json))
    if args.disclaimer:
        print(DISCLAIMER)
        return 0
    if args.yes and not args.dry_run and not args.accept_responsibility:
        print("--yes elimina senza domande: aggiungi --accept-responsibility per dichiarare che ti "
              "assumi la responsabilità dell'uso (vedi --disclaimer).", file=sys.stderr)
        return 2

    try:
        if args.scope:
            scopes = args.scope
        elif not args.json and sys.stdin.isatty():
            scopes = ask_scopes(style)
        else:
            scopes = ["user"]

        roots, warnings = discover(scopes)
        result = None
        if args.json:
            preview = scan(roots, args.min_age)
            if args.yes and not args.dry_run:
                result = clean(preview)
            print(json.dumps(to_json(roots, warnings, preview, result), indent=2, ensure_ascii=False))
            return 0

        print_roots(roots, warnings, style)
        if not roots:
            print(style.yellow("\nNessuna cartella Temp accessibile."))
            return 0
        print(style.dim("\nScansione in corso..."))
        preview = scan(roots, args.min_age)
        print_preview(preview, args.top, style)

        if not preview.total_files and not preview.total_dirs:
            print(style.green("\nNiente da eliminare: le cartelle Temp sono già pulite."))
            return 0
        if args.dry_run:
            print(style.dim("\nModalità anteprima (--dry-run): nessun file è stato eliminato."))
            return 0
        if args.yes:
            print(style.dim("\nResponsabilità accettata con --accept-responsibility."))
        else:
            if not accept_disclaimer(style):
                print("Responsabilità non accettata, nessun file eliminato.")
                return 0
            if not confirm(style.bold("\nEliminare definitivamente questi file? [s/N]: ")):
                print("Operazione annullata, nessun file eliminato.")
                return 0

        print(style.dim("Eliminazione in corso..."))
        result = clean(preview, keep_paths=args.verbose)
        print_result(result, args.top, args.verbose, style)
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\nInterrotto.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
