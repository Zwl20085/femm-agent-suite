"""Offline sanity tests for data/commands.json (the FEMM 5 scripting command catalog)."""
import json
import re
from pathlib import Path

import pytest

CATALOG = Path(__file__).resolve().parents[1] / "data" / "commands.json"

PHYSICS = {"magnetics", "electrostatics", "heatflow", "currentflow", "common"}
PHASES = {"pre", "post", "common"}
CATEGORIES = {
    "document", "problem", "geometry", "selection", "properties", "materials", "boundaries",
    "circuits", "conductors", "mesh", "solve", "view", "point_values", "integrals",
    "bulk_getters", "plotting", "export", "misc",
}
ARG_TYPES = {"number", "string", "int", "bool", "complex", "list"}
REQUIRED_FIELDS = {
    "name", "physics", "phase", "category", "args", "returns", "read_only", "description",
    "in_pyfemm", "pyfemm_only", "source_page_hint",
}
# prefix -> (physics, phase)
PREFIX = {
    "mi": ("magnetics", "pre"), "mo": ("magnetics", "post"),
    "ei": ("electrostatics", "pre"), "eo": ("electrostatics", "post"),
    "hi": ("heatflow", "pre"), "ho": ("heatflow", "post"),
    "ci": ("currentflow", "pre"), "co": ("currentflow", "post"),
}


@pytest.fixture(scope="module")
def catalog():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    return data


@pytest.fixture(scope="module")
def by_name(catalog):
    return {c["name"]: c for c in catalog}


def test_required_fields_and_vocab(catalog):
    for c in catalog:
        assert REQUIRED_FIELDS <= set(c), c["name"]
        assert c["physics"] in PHYSICS, c["name"]
        assert c["phase"] in PHASES, c["name"]
        assert c["category"] in CATEGORIES, c["name"]
        assert isinstance(c["read_only"], bool), c["name"]
        assert isinstance(c["in_pyfemm"], bool), c["name"]
        assert isinstance(c["pyfemm_only"], bool), c["name"]
        assert c["description"].strip(), c["name"]


def test_names_unique(catalog):
    names = [c["name"] for c in catalog]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, dupes


def test_prefix_matches_physics_and_phase(catalog):
    for c in catalog:
        m = re.match(r"^(mi|mo|ei|eo|hi|ho|ci|co)_\w+$", c["name"])
        if m:
            physics, phase = PREFIX[m.group(1)]
            assert (c["physics"], c["phase"]) == (physics, phase), c["name"]
        else:
            assert (c["physics"], c["phase"]) == ("common", "common"), c["name"]


def test_every_arg_has_type_and_description(catalog):
    for c in catalog:
        seen = set()
        for a in c["args"]:
            assert a["name"] and re.match(r"^[A-Za-z_]\w*$", a["name"]), (c["name"], a)
            assert a["name"] not in seen, (c["name"], a["name"])
            seen.add(a["name"])
            assert a["type"] in ARG_TYPES, (c["name"], a)
            assert isinstance(a["optional"], bool), (c["name"], a)
            assert a["description"].strip(), (c["name"], a)


def test_required_args_precede_optional(catalog):
    for c in catalog:
        flags = [a["optional"] for a in c["args"]]
        assert flags == sorted(flags), f"{c['name']}: required arg after optional arg"


def test_enums_refer_to_real_args(catalog):
    for c in catalog:
        for key in c.get("enums", {}):
            assert key in {a["name"] for a in c["args"]}, (c["name"], key)


def test_read_only_flags_are_consistent(by_name):
    for n in ("mo_getpointvalues", "mo_blockintegral", "mo_lineintegral", "mo_getallnodes",
              "eo_getpointvalues", "ho_getpointvalues", "co_getpointvalues", "mi_getboundingbox"):
        assert by_name[n]["read_only"] is True, n
    for n in ("mi_addnode", "mi_analyze", "mi_probdef", "newdocument", "mo_addcontour"):
        assert by_name[n]["read_only"] is False, n


@pytest.mark.parametrize(
    "name,total",
    [
        ("mi_probdef", 7),         # frequency, units, type, precision, depth, minangle, acsolver
        ("ei_probdef", 5),         # units, type, precision, depth, minangle (no frequency)
        ("hi_probdef", 7),         # ... + prevsoln, timestep
        ("ci_probdef", 6),         # units, type, frequency, precision, depth, minangle
        ("mi_addboundprop", 12),   # name + A0 A1 A2 Phi Mu Sig c0 c1 BdryFormat ia oa
        ("ei_addboundprop", 6),
        ("ci_addboundprop", 6),
        ("hi_addboundprop", 8),    # name, BdryFormat, Tset, qs, Tinf, h, beta, TinfRad
        ("mi_setblockprop", 7),
        ("ei_setblockprop", 4),
        ("mi_addmaterial", 14),    # name + 13 properties
        ("ei_addmaterial", 4),
        ("hi_addmaterial", 5),
        ("ci_addmaterial", 7),
        ("mi_addcircprop", 3),
        ("mi_setsegmentprop", 5),
        ("mi_setarcsegmentprop", 4),
        ("mi_addarc", 6),
        ("mo_getpointvalues", 2),
    ],
)
def test_known_signature_arity(by_name, name, total):
    assert len(by_name[name]["args"]) == total


def test_probdef_argument_order(by_name):
    assert by_name["mi_probdef"]["args"][0]["name"] == "frequency"
    assert [a["name"] for a in by_name["ci_probdef"]["args"]][:3] == ["units", "ptype", "frequency"]
    assert by_name["hi_addboundprop"]["args"][1]["name"] == "BdryFormat"
    assert [a["name"] for a in by_name["mi_setblockprop"]["args"]][:4] == [
        "blockname", "automesh", "meshsize", "incircuit"]


def test_integral_code_tables(by_name):
    assert len(by_name["mo_blockintegral"]["enums"]["type"]) == 31      # codes 0..30
    assert len(by_name["mo_lineintegral"]["enums"]["type"]) == 6        # codes 0..5
    assert len(by_name["co_blockintegral"]["enums"]["type"]) == 12      # codes 0..11
    assert by_name["mo_blockintegral"]["enums"]["type"]["10"].lower().startswith("block volume")


def test_pyfemm_only_set(catalog):
    only = [c["name"] for c in catalog if c["pyfemm_only"]]
    assert len(only) == 62
    assert all(c["in_pyfemm"] for c in catalog if c["pyfemm_only"])
    assert "mo_getb" in only and "mi_setcurrent" in only and "mo_snapgridon" in only


def test_expected_commands_present(by_name):
    for n in ("newdocument", "open", "quit", "setcurrentdirectory", "mi_addnode", "mi_analyze",
              "mi_loadsolution", "mo_getpointvalues", "ei_addconductorprop", "hi_addtkpoint",
              "ci_addconductorprop", "mo_getallnodes", "mo_getallelements", "eo_getalld",
              "ho_getallt", "co_getallj", "mo_getallgapharmonics", "mo_gapintegral"):
        assert n in by_name, n
    assert len(by_name) >= 650
