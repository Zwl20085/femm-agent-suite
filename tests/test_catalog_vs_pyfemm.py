"""Cross-check data/commands.json against the pyFEMM binding shipped with femm-qt.

Skipped when the standard install location is absent. Every FemmSession method named xx_yyy
must appear in the catalog or in EXCLUDED (names that are deliberately not FEMM commands).
"""
import ast
import json
import re
from pathlib import Path

import pytest

PYFEMM = Path("C:/femm-qt/pyfemm/femm.py")
CATALOG = Path(__file__).resolve().parents[1] / "data" / "commands.json"

pytestmark = pytest.mark.skipif(not PYFEMM.is_file(), reason="femm-qt pyfemm not installed")

# FemmSession methods of the form xx_yyy that are NOT scripting commands. Empty today: the
# session lifecycle methods and the showpointprops/hidepointprops stubs do not match xx_yyy;
# they are listed in NON_COMMAND_METHODS for documentation.
EXCLUDED = set()
NON_COMMAND_METHODS = {"__init__", "close", "callfemm", "callfemm_noeval",
                       "showpointprops", "hidepointprops"}


def _tree():
    return ast.parse(PYFEMM.read_text(encoding="utf-8"))


def _session_methods():
    for node in _tree().body:
        if isinstance(node, ast.ClassDef) and node.name == "FemmSession":
            return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    raise AssertionError("FemmSession class not found")


def _module_functions():
    return {n.name for n in _tree().body if isinstance(n, ast.FunctionDef)}


@pytest.fixture(scope="module")
def catalog():
    return {c["name"]: c for c in json.loads(CATALOG.read_text(encoding="utf-8"))}


def test_every_session_command_is_in_catalog(catalog):
    missing = sorted(
        m for m in _session_methods()
        if re.match(r"^[a-z]{2}_\w+$", m) and m not in catalog and m not in EXCLUDED
    )
    assert not missing, f"pyfemm methods absent from commands.json: {missing}"


def test_non_prefixed_session_commands_are_in_catalog(catalog):
    # newdocument, opendocument, smartmesh, messagebox, main_*, hide/showconsole ...
    for m in _session_methods():
        if m in NON_COMMAND_METHODS or re.match(r"^[a-z]{2}_\w+$", m):
            continue
        assert m in catalog, m


def test_in_pyfemm_flag_matches_binding(catalog):
    methods = _session_methods() | _module_functions()
    for name, c in catalog.items():
        if c["in_pyfemm"]:
            assert name in methods, f"{name} flagged in_pyfemm but not defined in femm.py"
    for m in _session_methods():
        if re.match(r"^[a-z]{2}_\w+$", m) and m in catalog:
            assert catalog[m]["in_pyfemm"], f"{m} is defined in femm.py but in_pyfemm is false"


def test_pyfemm_only_names_are_python_side_only(catalog):
    methods = _session_methods()
    for name, c in catalog.items():
        if c["pyfemm_only"]:
            assert name in methods, name
            assert not c["in_manual"], name
