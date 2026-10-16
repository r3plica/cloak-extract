import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cloak_extract


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cwd = self.root / "working"
        self.script = self.root / "tool"
        self.cwd.mkdir()
        self.script.mkdir()
        old_cwd = os.getcwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, old_cwd)
        script_patch = patch.object(cloak_extract, "__file__", str(self.script / "cloak_extract.py"))
        script_patch.start()
        self.addCleanup(script_patch.stop)

    def write_config(self, folder, values):
        path = folder / "cloak-extract.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return path

    def parse(self, *flags):
        return cloak_extract.parse_args(["https://example.com", *flags])

    def assert_config_error(self, text):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            self.parse()
        self.assertEqual(error.exception.code, 2)
        self.assertIn(text, stderr.getvalue())

    def test_missing_config_preserves_defaults(self):
        args = self.parse()
        self.assertFalse(args.site)
        self.assertFalse(args.all_pages)
        self.assertFalse(args.no_auto_params)
        self.assertIsNone(args.out_dir)
        self.assertEqual(args.workers, 8)
        self.assertEqual(args.limit, 0)
        self.assertEqual(args.host, [])
        self.assertEqual(args.exclude_host, [])

    def test_url_only_call_uses_configured_site_options(self):
        self.write_config(self.cwd, {"site": True, "all-pages": True, "out-dir": "images"})
        with patch.object(cloak_extract, "run_site", return_value=0) as run:
            self.assertEqual(cloak_extract.main(["https://example.com"]), 0)
        args = run.call_args.args[0]
        self.assertEqual(args.url, "https://example.com")
        self.assertTrue(args.all_pages)
        self.assertEqual(args.out_dir, "images")

    def test_script_fallback_and_current_folder_precedence(self):
        self.write_config(self.script, {"site": True, "workers": 3})
        self.assertTrue(self.parse().site)
        self.assertEqual(self.parse().workers, 3)
        self.write_config(self.cwd, {"workers": 5})
        args = self.parse()
        self.assertFalse(args.site)
        self.assertEqual(args.workers, 5)

    def test_cli_overrides_scalars_booleans_and_lists(self):
        self.write_config(self.cwd, {
            "site": True, "all-pages": True, "no-auto-params": True,
            "out-dir": "configured", "workers": 3, "filter": "configured",
            "host": ["configured"], "exclude-host": ["configured"],
            "out": "configured.txt", "quiet": True,
        })
        args = self.parse(
            "--no-site", "--no-all-pages", "--auto-params", "--out-dir", "cli",
            "--workers", "12", "--filter", "cli", "--host", "one", "--host", "two",
            "--exclude-host", "cli", "-o", "cli.txt", "--no-quiet",
        )
        self.assertFalse(args.site)
        self.assertFalse(args.all_pages)
        self.assertFalse(args.no_auto_params)
        self.assertFalse(args.quiet)
        self.assertEqual(args.out_dir, "cli")
        self.assertEqual(args.workers, 12)
        self.assertEqual(args.url_filter, "cli")
        self.assertEqual(args.host, ["one", "two"])
        self.assertEqual(args.exclude_host, ["cli"])
        self.assertEqual(args.out, "cli.txt")

    def test_explicit_config_and_opt_out(self):
        self.write_config(self.cwd, {"site": True})
        selected = self.write_config(self.root, {"workers": 2})
        args = self.parse("--config", str(selected))
        self.assertFalse(args.site)
        self.assertEqual(args.workers, 2)
        (self.cwd / "cloak-extract.json").write_text("invalid", encoding="utf-8")
        self.assertFalse(self.parse("--no-config").site)

    def test_missing_explicit_config_is_an_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            self.parse("--config", "missing.json")
        self.assertEqual(error.exception.code, 2)
        self.assertIn("Cannot read config", stderr.getvalue())

    def test_invalid_config_fails_before_running(self):
        cases = [
            ("{", "Cannot read config"),
            ("[]", "must contain a JSON object"),
            ("null", "must contain a JSON object"),
            ('{"all_pages": true}', "Unknown config option"),
            ('{"url": "https://other.example"}', "Unknown config option"),
            ('{"site": "true"}', "must be bool"),
            ('{"workers": true}', "must be int"),
            ('{"workers": 1.5}', "must be int"),
            ('{"out-dir": null}', "must be str"),
            ('{"host": "example.com"}', "must be array of strings"),
            ('{"exclude-host": [1]}', "must be array of strings"),
        ]
        for content, error in cases:
            with self.subTest(content=content):
                (self.cwd / "cloak-extract.json").write_text(content, encoding="utf-8")
                self.assert_config_error(error)

    def test_unreadable_config_does_not_fall_back(self):
        (self.cwd / "cloak-extract.json").mkdir()
        self.write_config(self.script, {"site": True})
        self.assert_config_error("Cannot read config")

    def test_help_and_version_do_not_depend_on_valid_config(self):
        (self.cwd / "cloak-extract.json").write_text("invalid", encoding="utf-8")
        for flag in ("--help", "--version"):
            with self.subTest(flag=flag), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    cloak_extract.parse_args([flag])
                self.assertEqual(error.exception.code, 0)

    def test_utf8_bom_is_supported(self):
        (self.cwd / "cloak-extract.json").write_text('{"site": true}', encoding="utf-8-sig")
        self.assertTrue(self.parse().site)


if __name__ == "__main__":
    unittest.main()
