import os
import tempfile
import time
import unittest
from unittest import mock

from tempcleaner.cleaner import clean
from tempcleaner.cli import main, parse_scopes
from tempcleaner.discovery import TempRoot, discover, is_safe_root
from tempcleaner.scanner import scan
from tempcleaner.services import OTHER, identify

OLD = time.time() - 3 * 24 * 3600


def make(path, content=b"x" * 10, old=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    if old:
        os.utime(path, (OLD, OLD))


def age_dirs(top):
    for folder, _, _ in os.walk(top):
        os.utime(folder, (OLD, OLD))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.temp = os.path.join(self.base, "Temp")
        os.makedirs(self.temp)
        self.root = TempRoot(os.path.realpath(self.temp), "user")

    def tearDown(self):
        self._tmp.cleanup()


class SafetyTests(Base):
    def test_only_temp_names_accepted(self):
        self.assertTrue(is_safe_root(self.temp))
        other = os.path.join(self.base, "Documenti")
        os.makedirs(other)
        self.assertFalse(is_safe_root(other))
        self.assertFalse(is_safe_root(os.path.join(self.base, "NonEsiste", "Temp")))
        self.assertFalse(is_safe_root(os.path.abspath(os.sep)))

    def test_discover_user_scope_uses_env(self):
        env = {"TEMP": self.temp, "TMP": self.temp, "LOCALAPPDATA": os.path.join(self.base, "Local")}
        with mock.patch.dict(os.environ, env), \
                mock.patch("tempfile.gettempdir", return_value=self.temp):
            roots, _ = discover(["user"])
        self.assertEqual([os.path.normcase(r.path) for r in roots],
                         [os.path.normcase(os.path.realpath(self.temp))])

    def test_nested_temp_counted_once(self):
        inner = os.path.join(self.temp, "app", "tmp")
        os.makedirs(inner)
        env = {"TEMP": self.temp, "TMP": inner, "LOCALAPPDATA": os.path.join(self.base, "Local")}
        with mock.patch.dict(os.environ, env), \
                mock.patch("tempfile.gettempdir", return_value=self.temp):
            roots, _ = discover(["user"])
        self.assertEqual(len(roots), 1)


class CleanTests(Base):
    def test_old_files_deleted_recent_kept_root_kept(self):
        make(os.path.join(self.temp, "vecchio.tmp"))
        make(os.path.join(self.temp, "npm-cache", "a", "b.json"))
        make(os.path.join(self.temp, "nuovo.tmp"), old=False)
        age_dirs(os.path.join(self.temp, "npm-cache"))

        preview = scan([self.root], min_age_hours=24)
        self.assertEqual(preview.total_files, 2)
        self.assertEqual(preview.recent_files, 1)

        result = clean(preview)
        self.assertEqual(result.deleted_files, 2)
        self.assertEqual(result.freed, 20)
        self.assertEqual(result.deleted_dirs, 2)
        self.assertTrue(os.path.isdir(self.temp))
        self.assertEqual(os.listdir(self.temp), ["nuovo.tmp"])
        self.assertIn("Node.js (npm/yarn)", result.by_service)

    def test_dry_scan_deletes_nothing(self):
        make(os.path.join(self.temp, "a.log"))
        scan([self.root], min_age_hours=0)
        self.assertTrue(os.path.exists(os.path.join(self.temp, "a.log")))

    def test_file_in_use_is_skipped(self):
        path = os.path.join(self.temp, "bloccato.tmp")
        make(path)
        handle = open(path, "rb")
        try:
            result = clean(scan([self.root], min_age_hours=24))
        finally:
            handle.close()
        if os.name == "nt":
            self.assertEqual(result.deleted_files, 0)
            self.assertEqual(result.skipped_total, 1)
            self.assertTrue(os.path.exists(path))

    def test_readonly_file_deleted(self):
        path = os.path.join(self.temp, "sola_lettura.tmp")
        make(path)
        os.chmod(path, 0o444)
        result = clean(scan([self.root], min_age_hours=24))
        self.assertEqual(result.deleted_files, 1)
        self.assertFalse(os.path.exists(path))

    def test_links_are_never_followed(self):
        outside = os.path.join(self.base, "Importante")
        make(os.path.join(outside, "dati.txt"))
        link = os.path.join(self.temp, "collegamento")
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(outside, link)
            else:
                os.symlink(outside, link)
        except (OSError, AttributeError, ImportError) as exc:
            self.skipTest(f"impossibile creare il collegamento: {exc}")
        preview = scan([self.root], min_age_hours=0)
        self.assertEqual(preview.total_files, 0)
        self.assertEqual(preview.skipped_links, 1)
        clean(preview)
        self.assertTrue(os.path.exists(os.path.join(outside, "dati.txt")))
        if os.name == "nt":
            os.rmdir(link)


class ServiceAndCliTests(unittest.TestCase):
    def test_identify(self):
        self.assertEqual(identify("chrome_BITS_1234", True), "Google Chrome / Chromium")
        self.assertEqual(identify("MSI1a2b3.LOG"), "Installer / Windows Installer")
        self.assertEqual(identify("random.etl"), "Tracce diagnostiche Windows (.etl)")
        self.assertEqual(identify("qwerty", True), OTHER)

    def test_parse_scopes(self):
        self.assertEqual(parse_scopes("1,4"), ["user", "apps"])
        self.assertEqual(parse_scopes("user, system,user"), ["user", "system"])
        self.assertEqual(parse_scopes("all"), ["user", "users", "system", "apps"])
        with self.assertRaises(ValueError):
            parse_scopes("documenti")

    def test_yes_requires_accept_responsibility(self):
        with mock.patch("tempcleaner.cli.discover") as disc, mock.patch("sys.stderr"):
            self.assertEqual(main(["-s", "user", "-y"]), 2)
            disc.assert_not_called()

    def test_refusing_disclaimer_deletes_nothing(self):
        with mock.patch("tempcleaner.cli.clean") as cln, \
                mock.patch("builtins.input", side_effect=["no"]), mock.patch("builtins.print"):
            self.assertEqual(main(["-s", "user", "-a", "0"]), 0)
            cln.assert_not_called()


class ConsoleTests(unittest.TestCase):
    def _fake_kernel32(self, count):
        fake = mock.Mock()
        fake.GetConsoleProcessList.return_value = count
        return mock.patch("tempcleaner.console._kernel32", return_value=fake)

    def test_double_click_detection(self):
        from tempcleaner import console
        with self._fake_kernel32(1):
            self.assertTrue(console.launched_by_double_click())
        with self._fake_kernel32(3):
            self.assertFalse(console.launched_by_double_click())
        with self._fake_kernel32(2), mock.patch.dict(os.environ, {"TEMPCLEANER_LAUNCHER": "1"}):
            self.assertTrue(console.launched_by_double_click())
        with self._fake_kernel32(2), mock.patch.dict(os.environ, {"TEMPCLEANER_LAUNCHER": ""}):
            self.assertFalse(console.launched_by_double_click())

    def test_pause_only_on_double_click(self):
        from tempcleaner import console
        with self._fake_kernel32(1), mock.patch("builtins.input") as inp:
            console.pause_if_needed()
            inp.assert_called_once()
        with self._fake_kernel32(3), mock.patch("builtins.input") as inp:
            console.pause_if_needed()
            inp.assert_not_called()

    def test_main_pauses_even_after_error(self):
        with mock.patch("tempcleaner.cli._run", side_effect=RuntimeError("boom")), \
                mock.patch("tempcleaner.cli.pause_if_needed") as pause, \
                mock.patch("sys.stderr"), mock.patch("traceback.print_exc"):
            from tempcleaner.cli import main as cli_main
            self.assertEqual(cli_main([]), 1)
            pause.assert_called_once()


def demo_scan():
    """ScanResult finto, usato per i test della GUI e per lo screenshot."""
    from tempcleaner.scanner import Item, ScanResult
    roots = [TempRoot(r"C:\Users\utente\AppData\Local\Temp", "user"),
             TempRoot(r"C:\Users\utente\AppData\Local\Programma\Temp", "apps", "Programma")]
    data = [(0, "chrome_BITS_1", "Google Chrome / Chromium", 120, 2_500_000),
            (0, "npm-cache-1", "Node.js (npm/yarn)", 760, 900_000),
            (0, "vscode-inno-updater", "Visual Studio Code", 7, 280_000_000),
            (0, "MSI1a2b.LOG", "Installer / Windows Installer", 24, 70_000),
            (1, "cache.tmp", "Programma", 12, 23_000)]
    items = []
    for root_index, name, service, count, size in data:
        root = roots[root_index]
        item = Item(root, root.path + "\\" + name, name, service, True)
        item.files = [(f"{item.path}\\f{i}", size // count) for i in range(count)]
        item.dirs = [item.path]
        items.append(item)
    items[0].recent_files, items[0].recent_size = 40, 15_000_000
    return roots, ScanResult(roots, items, 24.0)


class GuiTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter
            self.root = tkinter.Tk()
        except Exception as exc:  # noqa: BLE001 - nessun display o Tk non installato
            self.skipTest(f"Tk non disponibile: {exc}")
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_scan_results_fill_the_window(self):
        from tempcleaner.gui import App
        app = App(self.root)
        roots, result = demo_scan()
        app.show_scan(roots, ["avviso di prova"], result)
        self.assertEqual(len(app.services_tree.get_children()), 5)
        self.assertEqual(len(app.roots_tree.get_children()), 2)
        self.assertEqual(str(app.clean_btn.cget("state")), "normal")
        self.assertEqual(app.stat_vars["files"][1].get(), "923")

    def test_clean_needs_responsibility(self):
        from tempcleaner.gui import App
        app = App(self.root)
        roots, result = demo_scan()
        app.show_scan(roots, [], result)
        with mock.patch.object(App, "ask_responsibility", return_value=False), \
                mock.patch("tempcleaner.gui.clean") as cln:
            app.start_clean()
            cln.assert_not_called()


class LaunchModeTests(unittest.TestCase):
    def test_no_arguments_opens_gui(self):
        from tempcleaner import cli
        with mock.patch.object(cli, "_try_gui", return_value=0) as gui:
            self.assertEqual(cli._run([]), 0)
            gui.assert_called_once()

    def test_arguments_use_text_mode(self):
        from tempcleaner import cli
        with mock.patch.object(cli, "_try_gui") as gui, mock.patch("sys.stdout"):
            self.assertEqual(cli._run(["--disclaimer"]), 0)
            gui.assert_not_called()


class PackageTests(unittest.TestCase):
    def test_release_zip_has_launcher_first_and_no_folders(self):
        import importlib.util
        import zipfile
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("build", os.path.join(root, "packaging", "build.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as out:
            target = build.build(__import__("pathlib").Path(out))
            with zipfile.ZipFile(target) as package:
                names = package.namelist()
                self.assertFalse(any("/" in n for n in names))
                self.assertEqual(sorted(names, key=str.lower)[0], "Avvia TempCleaner.cmd")
                self.assertIn(b"\r\n", package.read("Avvia TempCleaner.cmd"))
                pyz = zipfile.ZipFile(__import__("io").BytesIO(package.read("TempCleaner-app.pyz")))
                self.assertIn("__main__.py", pyz.namelist())
                self.assertIn("tempcleaner/cli.py", pyz.namelist())


if __name__ == "__main__":
    unittest.main()
