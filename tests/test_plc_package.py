"""Keep the PLC package independent of the integration and HA test stubs."""

import shutil
import subprocess
import sys
from pathlib import Path


def test_plc_package_imports_without_home_assistant_or_parent_modules(tmp_path):
    """Import only the copied package in a fresh interpreter with HA blocked."""
    source = Path(__file__).resolve().parents[1] / "custom_components" / "s7plc" / "plc"
    shutil.copytree(
        source, tmp_path / "plc", ignore=shutil.ignore_patterns("__pycache__")
    )
    check = """
import importlib
import importlib.abc
import pkgutil
import sys

class BlockHomeAssistant(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "homeassistant" or fullname.startswith("homeassistant."):
            raise AssertionError(f"PLC package must not import {fullname}")

sys.meta_path.insert(0, BlockHomeAssistant())
sys.path.insert(0, sys.argv[1])
import plc

for module in pkgutil.walk_packages(plc.__path__, plc.__name__ + "."):
    importlib.import_module(module.name)

assert not any(name == "homeassistant" or name.startswith("homeassistant.")
               for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", check, str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
