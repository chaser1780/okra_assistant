from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopStartupTests(unittest.TestCase):
    def test_launcher_defaults_to_fast_startup(self):
        script = (ROOT / "run_desktop_app.ps1").read_text(encoding="utf-8")

        self.assertIn("$script:autoRebuildWhenChanged = $false", script)
        self.assertIn("-AutoRebuildWhenChanged", script)
        self.assertIn("-Rebuild", script)

    def test_explicit_tauri_rebuild_does_not_build_frontend_twice(self):
        script = (ROOT / "run_desktop_app.ps1").read_text(encoding="utf-8")
        rebuild_block = script[script.index('"Building OKRA Workbench..."') : script.index('"Using existing OKRA Workbench executable:')]

        self.assertNotRegex(rebuild_block, re.compile(r"ArgumentList\s+@\('run',\s*'build'\)"))
        self.assertIn("'tauri', '--', 'build', '--no-bundle'", rebuild_block)

    def test_new_desktop_window_does_not_wait_for_launcher_managed_api(self):
        script = (ROOT / "run_desktop_app.ps1").read_text(encoding="utf-8")
        launch_block = script[script.index("} elseif (Test-Path $workbenchExe) {") : script.index('"Tauri executable not found:')]

        self.assertNotIn("Start-ManagedOkraApi", launch_block)
        self.assertIn("Start-Process -FilePath $workbenchExe", launch_block)

    def test_fund_registry_is_loaded_only_when_lookup_is_used(self):
        source = (ROOT / "app" / "web_api_services.py").read_text(encoding="utf-8")
        imports, lookup_method = source.split("class ExecutionController", 1)[0], source.split("def execution_fund_lookup", 1)[1]

        self.assertNotIn("from fund_registry import search_fund_candidates", imports)
        self.assertIn("from fund_registry import search_fund_candidates", lookup_method.split("def execution_fund_register", 1)[0])


if __name__ == "__main__":
    unittest.main()
