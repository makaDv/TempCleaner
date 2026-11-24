"""Interfaccia grafica (Tkinter) di TempCleaner.

Usa la stessa logica della versione testuale: discovery -> scan -> clean.
Scansione ed eliminazione girano in un thread separato, così la finestra resta reattiva.
"""
from __future__ import annotations

import ctypes
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__
from .cleaner import CleanResult, clean
from .disclaimer import DISCLAIMER
from .discovery import SCOPES, TempRoot, discover, is_admin
from .report import display_path, human
from .scanner import ScanResult, scan

REPO_URL = "https://github.com/makaDv/TempCleaner"
BG = "#f4f6fb"
CARD = "#ffffff"
TEXT = "#111827"
MUTED = "#6b7280"
ACCENT = "#2563eb"
DANGER = "#dc2626"
SUCCESS = "#16a34a"
FONT = "Segoe UI"
FULL_BLOCK, LIGHT_SHADE, DASH = chr(0x2588), chr(0x2591), chr(0x2014)

SCOPE_NOTES = {
    "user": "%TEMP% e %TMP% dell'utente corrente",
    "users": "C:\\Users\\*\\AppData\\Local\\Temp (serve amministratore)",
    "system": "%SystemRoot%\\Temp (serve amministratore)",
    "apps": "Cartelle Temp/tmp dei programmi in AppData",
}

SCOPE_TITLES = {
    "user": "Temp del mio utente",
    "users": "Temp di tutti gli utenti",
    "system": "Temp di Windows",
    "apps": "Temp delle applicazioni",
}


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _bar(fraction: float, width: int = 12) -> str:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return FULL_BLOCK * filled + LIGHT_SHADE * (width - filled)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.scan_result: ScanResult | None = None
        self.roots: list[TempRoot] = []
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)

        root.title(f"TempCleaner {__version__}")
        root.configure(bg=BG)
        root.geometry(f"{int(1000 * self.scale)}x{int(700 * self.scale)}")
        root.minsize(int(860 * self.scale), int(600 * self.scale))

        self._styles()
        self._build()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ stile
    def _styles(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD, relief="flat")
        s.configure("Title.TLabel", font=(FONT, 20, "bold"), background=BG)
        s.configure("Sub.TLabel", foreground=MUTED, background=BG)
        s.configure("Section.TLabel", font=(FONT, 11, "bold"), background=CARD)
        s.configure("CardText.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        s.configure("Warn.TLabel", background=CARD, foreground="#b45309", font=(FONT, 9))
        s.configure("StatTitle.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        s.configure("StatValue.TLabel", background=CARD, font=(FONT, 18, "bold"))
        s.configure("Card.TCheckbutton", background=CARD, font=(FONT, 10, "bold"))
        s.map("Card.TCheckbutton", background=[("active", CARD)])
        s.configure("Status.TLabel", background=BG, foreground=MUTED)
        s.configure("Footer.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        s.configure("Link.TLabel", background=BG, foreground=ACCENT, font=(FONT, 9, "underline"))
        for name, color, active, disabled in (
            ("Accent", ACCENT, "#1d4ed8", "#a5bdf3"),
            ("Danger", DANGER, "#b91c1c", "#f3b0b0"),
        ):
            s.configure(f"{name}.TButton", background=color, foreground="white", borderwidth=0,
                        focusthickness=0, padding=(20, 9), font=(FONT, 10, "bold"))
            s.map(f"{name}.TButton", background=[("disabled", disabled), ("active", active)],
                  foreground=[("disabled", "white")])
        s.configure("Treeview", rowheight=int(26 * self.scale), background=CARD,
                    fieldbackground=CARD, borderwidth=0)
        s.configure("Treeview.Heading", font=(FONT, 9, "bold"), background="#eef1f7", relief="flat")
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 7), font=(FONT, 10))
        s.map("TNotebook.Tab", background=[("selected", CARD)])
        s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e5e7eb", borderwidth=0)

    # ----------------------------------------------------------------- layout
    def _card(self, parent: tk.Widget, **grid) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
        frame.grid(**grid)
        return frame

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=(24, 18, 24, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="TempCleaner", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Trova e svuota in sicurezza le cartelle Temp di Windows. "
                               "Elimina solo file dentro cartelle chiamate Temp o tmp.",
                  style="Sub.TLabel").pack(anchor="w")

        # Opzioni
        options = self._card(main, row=1, column=0, sticky="ew", pady=(14, 10))
        options.columnconfigure((0, 1), weight=1)
        ttk.Label(options, text="Cartelle da analizzare", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        admin = is_admin()
        self.scope_vars: dict[str, tk.BooleanVar] = {}
        for index, scope in enumerate(SCOPES):
            var = tk.BooleanVar(value=scope == "user")
            self.scope_vars[scope] = var
            cell = ttk.Frame(options, style="Card.TFrame")
            cell.grid(row=1 + index // 2, column=index % 2, sticky="w", padx=(0, 20), pady=4)
            ttk.Checkbutton(cell, text=SCOPE_TITLES[scope], variable=var, style="Card.TCheckbutton").pack(anchor="w")
            needs_admin = scope in ("users", "system") and not admin
            ttk.Label(cell, text=SCOPE_NOTES[scope], style="Warn.TLabel" if needs_admin else "CardText.TLabel"
                      ).pack(anchor="w", padx=(24, 0))

        age = ttk.Frame(options, style="Card.TFrame")
        age.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(age, text="Elimina solo file non modificati da almeno", style="CardText.TLabel").pack(side="left")
        self.age_var = tk.StringVar(value="24")
        ttk.Spinbox(age, from_=0, to=720, width=5, textvariable=self.age_var).pack(side="left", padx=6)
        ttk.Label(age, text="ore (i file recenti potrebbero essere in uso)", style="CardText.TLabel").pack(side="left")

        # Azioni
        actions = ttk.Frame(main)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        actions.columnconfigure(3, weight=1)
        self.scan_btn = ttk.Button(actions, text="Analizza", style="Accent.TButton", command=self.start_scan)
        self.scan_btn.grid(row=0, column=0)
        self.clean_btn = ttk.Button(actions, text="Pulisci", style="Danger.TButton",
                                    command=self.start_clean, state="disabled")
        self.clean_btn.grid(row=0, column=1, padx=10)
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=int(140 * self.scale))
        self.progress.grid(row=0, column=2, padx=(6, 12))
        self.progress.grid_remove()  # visibile solo durante analisi ed eliminazione
        self.status = tk.StringVar(value="Scegli le cartelle e premi Analizza.")
        ttk.Label(actions, textvariable=self.status, style="Status.TLabel").grid(row=0, column=3, sticky="w")

        # Riquadri riepilogo
        stats = ttk.Frame(main)
        stats.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.stat_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        for col, (key, title) in enumerate((("space", "Spazio da liberare"), ("files", "File eliminabili"),
                                            ("dirs", "Cartelle"), ("recent", "File recenti esclusi"))):
            stats.columnconfigure(col, weight=1, uniform="stat")
            card = self._card(stats, row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
            title_var, value_var = tk.StringVar(value=title), tk.StringVar(value=DASH)
            ttk.Label(card, textvariable=title_var, style="StatTitle.TLabel").pack(anchor="w")
            label = ttk.Label(card, textvariable=value_var, style="StatValue.TLabel")
            label.pack(anchor="w")
            if key == "space":
                self.space_label = label
            self.stat_vars[key] = (title_var, value_var)

        # Schede con i dettagli
        self.tabs = ttk.Notebook(main)
        self.tabs.grid(row=4, column=0, sticky="nsew")
        self.services_tree = self._tree(
            "Servizi", [("rank", "#", 40, "e"), ("service", "Servizio", 260, "w"), ("files", "File", 90, "e"),
                        ("size", "Spazio", 100, "e"), ("bar", "Quota dello spazio", 200, "w")])
        self.roots_tree = self._tree(
            "Cartelle Temp", [("path", "Cartella", 430, "w"), ("scope", "Tipo", 110, "w"),
                              ("files", "File", 90, "e"), ("dirs", "Cartelle", 90, "e"), ("size", "Spazio", 100, "e")])
        self.cleaned_tree = self._tree(
            "Ripulito", [("item", "Elemento", 330, "w"), ("service", "Servizio", 230, "w"),
                         ("files", "File", 90, "e"), ("size", "Spazio", 100, "e")])
        notes_frame = ttk.Frame(self.tabs, style="Card.TFrame", padding=10)
        self.notes = tk.Text(notes_frame, height=6, relief="flat", wrap="word", bg=CARD, fg=TEXT,
                             font=(FONT, 10), state="disabled")
        self.notes.pack(fill="both", expand=True)
        self.tabs.add(notes_frame, text="Avvisi")

        footer = ttk.Frame(main)
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(footer, text="TempCleaner è solo uno strumento: chi lo usa si assume la piena "
                               "responsabilità di ciò che fa. I file eliminati non passano dal Cestino.",
                  style="Footer.TLabel").pack(side="left")
        link = ttk.Label(footer, text="Codice sorgente", style="Link.TLabel", cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda _e: webbrowser.open(REPO_URL))

    def _tree(self, title: str, columns: list[tuple[str, str, int, str]]) -> ttk.Treeview:
        frame = ttk.Frame(self.tabs, style="Card.TFrame", padding=6)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, heading, width, anchor in columns:
            tree.heading(key, text=heading, anchor=anchor)
            tree.column(key, width=int(width * self.scale), anchor=anchor,
                        stretch=key in ("service", "path", "item", "bar"))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.tag_configure("odd", background="#f9fafb")
        self.tabs.add(frame, text=title)
        return tree

    # ---------------------------------------------------------------- utilità
    def _fill(self, tree: ttk.Treeview, rows: list[tuple]) -> None:
        tree.delete(*tree.get_children())
        for index, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=("odd",) if index % 2 else ())

    def _set_notes(self, lines: list[str]) -> None:
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", "\n".join(lines) if lines else "Nessun avviso.")
        self.notes.configure(state="disabled")
        self.tabs.tab(3, text=f"Avvisi ({len(lines)})" if lines else "Avvisi")

    def _busy(self, busy: bool, message: str = "") -> None:
        self.scan_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.clean_btn.configure(state="disabled")
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        if message:
            self.status.set(message)

    def _background(self, kind: str, work) -> None:
        def runner() -> None:
            try:
                self.events.put((kind, work(), None))
            except Exception as exc:  # noqa: BLE001 - mostrato all'utente
                self.events.put((kind, None, exc))
        threading.Thread(target=runner, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, result, error = self.events.get_nowait()
                self._busy(False)
                if error is not None:
                    self.status.set("Si è verificato un errore.")
                    messagebox.showerror("TempCleaner", f"Errore imprevisto:\n{error}", parent=self.root)
                elif kind == "scan":
                    self.show_scan(*result)
                else:
                    self.show_clean(result)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ---------------------------------------------------------------- analisi
    def start_scan(self) -> None:
        scopes = [s for s, v in self.scope_vars.items() if v.get()]
        if not scopes:
            messagebox.showwarning("TempCleaner", "Seleziona almeno una cartella da analizzare.", parent=self.root)
            return
        try:
            hours = float(self.age_var.get().replace(",", "."))
            if hours < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("TempCleaner", "Inserisci un numero di ore valido (0 o più).", parent=self.root)
            return
        self._busy(True, "Analisi in corso...")

        def work():
            roots, warnings = discover(scopes)
            return roots, warnings, scan(roots, hours)
        self._background("scan", work)

    def show_scan(self, roots: list[TempRoot], warnings: list[str], result: ScanResult) -> None:
        self.roots, self.scan_result = roots, result
        self.stat_vars["space"][0].set("Spazio da liberare")
        self.stat_vars["space"][1].set(human(result.total_size))
        self.stat_vars["files"][0].set("File eliminabili")
        self.stat_vars["files"][1].set(_n(result.total_files))
        self.stat_vars["dirs"][1].set(_n(result.total_dirs))
        self.stat_vars["recent"][1].set(_n(result.recent_files))
        self.space_label.configure(foreground=TEXT)

        services = sorted(result.by_service().items(), key=lambda kv: kv[1][0], reverse=True)
        total = result.total_size or 1
        self._fill(self.services_tree, [
            (i, name, _n(v[0]), human(v[1]), f"{_bar(v[1] / total)}  {v[1] * 100 / total:.1f}%")
            for i, (name, v) in enumerate(services, 1)])
        by_root = result.by_root()
        self._fill(self.roots_tree, [
            (display_path(r.path) + (f"  ({r.label})" if r.label else ""), SCOPE_TITLES.get(r.scope, r.scope),
             _n(by_root[r.path][0]), _n(by_root[r.path][1]), human(by_root[r.path][2]))
            for r in roots])
        self._fill(self.cleaned_tree, [])

        notes = list(warnings)
        if result.recent_files:
            notes.append(f"{_n(result.recent_files)} file recenti ({human(result.recent_size)}) esclusi: "
                         "potrebbero essere in uso.")
        if result.skipped_links:
            notes.append(f"{_n(result.skipped_links)} collegamenti simbolici/junction ignorati.")
        if result.errors:
            notes.append(f"{_n(result.errors)} elementi non leggibili.")
        notes += [f"{display_path(r.path)} non leggibile: {err}" for r, err in result.root_errors]
        self._set_notes(notes)
        self.tabs.select(0)

        if not roots:
            self.status.set("Nessuna cartella Temp accessibile.")
        elif result.total_files or result.total_dirs:
            self.clean_btn.configure(state="normal")
            self.status.set(f"Trovate {len(roots)} cartelle Temp. Premi Pulisci per eliminare.")
        else:
            self.status.set("Niente da eliminare: le cartelle Temp sono già pulite.")

    # ----------------------------------------------------------------- pulizia
    def ask_responsibility(self) -> bool:
        """Finestra con l'esclusione di responsabilità: si procede solo spuntando la casella."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Esclusione di responsabilità")
        dialog.configure(bg=CARD)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        accepted = tk.BooleanVar(value=False)
        result = {"ok": False}

        body = ttk.Frame(dialog, style="Card.TFrame", padding=20)
        body.pack(fill="both", expand=True)
        text = tk.Text(body, width=82, height=16, wrap="word", relief="flat", bg="#fff7ed", fg=TEXT,
                       font=(FONT, 10), padx=12, pady=10)
        text.insert("1.0", DISCLAIMER)
        text.configure(state="disabled")
        text.pack(fill="both")
        ttk.Checkbutton(body, text="Ho letto e mi assumo la piena responsabilità dell'uso di questo strumento",
                        variable=accepted, style="Card.TCheckbutton").pack(anchor="w", pady=(12, 12))
        buttons = ttk.Frame(body, style="Card.TFrame")
        buttons.pack(fill="x")
        confirm = ttk.Button(buttons, text="Accetto e continuo", style="Danger.TButton", state="disabled")
        confirm.pack(side="right")
        ttk.Button(buttons, text="Annulla", command=dialog.destroy).pack(side="right", padx=10)
        accepted.trace_add("write", lambda *_: confirm.configure(state="normal" if accepted.get() else "disabled"))

        def ok() -> None:
            result["ok"] = accepted.get()
            dialog.destroy()
        confirm.configure(command=ok)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.grab_set()
        dialog.focus_set()
        self.root.wait_window(dialog)
        return result["ok"]

    def start_clean(self) -> None:
        result = self.scan_result
        if result is None:
            return
        if not self.ask_responsibility():
            self.status.set("Responsabilità non accettata: nessun file eliminato.")
            return
        question = (f"Eliminare definitivamente {_n(result.total_files)} file ({human(result.total_size)})?\n\n"
                    "I file non passano dal Cestino e l'operazione non si può annullare.")
        if not messagebox.askyesno("Conferma eliminazione", question, icon="warning",
                                   default="no", parent=self.root):
            self.status.set("Operazione annullata: nessun file eliminato.")
            return
        self._busy(True, "Eliminazione in corso...")
        self._background("clean", lambda: clean(result))

    def show_clean(self, result: CleanResult) -> None:
        self.scan_result = None
        self.clean_btn.configure(state="disabled")
        self.stat_vars["space"][0].set("Spazio liberato")
        self.stat_vars["space"][1].set(human(result.freed))
        self.space_label.configure(foreground=SUCCESS)
        self.stat_vars["files"][0].set("File eliminati")
        self.stat_vars["files"][1].set(_n(result.deleted_files))
        self.stat_vars["dirs"][1].set(_n(result.deleted_dirs))

        items = sorted(result.cleaned_items, key=lambda t: t[2], reverse=True)
        self._fill(self.cleaned_tree, [
            (item.name + ("\\" if item.is_dir else ""), item.service, _n(files), human(size))
            for item, files, size in items])
        services = sorted(result.by_service.items(), key=lambda kv: kv[1][0], reverse=True)
        total = result.freed or 1
        self._fill(self.services_tree, [
            (i, name, _n(v[0]), human(v[1]), f"{_bar(v[1] / total)}  {v[1] * 100 / total:.1f}%")
            for i, (name, v) in enumerate(services, 1)])
        self.tabs.select(2)

        summary = (f"Spazio liberato: {human(result.freed)}\n"
                   f"File eliminati: {_n(result.deleted_files)}\n"
                   f"Cartelle eliminate: {_n(result.deleted_dirs)}")
        if result.skipped_total:
            detail = ", ".join(f"{reason}: {_n(n)}" for reason, n in result.skipped.most_common())
            summary += f"\nFile saltati: {_n(result.skipped_total)} ({detail})"
            self._set_notes([f"File saltati - {detail}"])
        self.status.set("Pulizia completata. Premi Analizza per una nuova scansione.")
        messagebox.showinfo("Pulizia completata", summary, parent=self.root)


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


def run_gui() -> int:
    """Apre la finestra. Solleva tk.TclError se non c'è un display disponibile."""
    _enable_dpi_awareness()
    root = tk.Tk()

    def report(exc_type, exc, _tb) -> None:
        messagebox.showerror("TempCleaner", f"Errore imprevisto:\n{exc_type.__name__}: {exc}", parent=root)
    root.report_callback_exception = report
    App(root)
    root.mainloop()
    return 0
