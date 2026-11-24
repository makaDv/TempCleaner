import os
import tempfile
import time
import unittest
from unittest import mock

from tempcleaner.cleaner import clean
from tempcleaner.cli import parse_scopes
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


if __name__ == "__main__":
    unittest.main()
