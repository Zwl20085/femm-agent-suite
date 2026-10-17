"""Offline tests for femm_agent.materials (library data in data/materials/, no FEMM needed)."""
import pytest

from femm_agent.materials import MaterialLibrary, parse_dat


@pytest.fixture(scope="module")
def lib():
    return MaterialLibrary(use_user_library=False)


def test_counts(lib):
    assert lib.counts() == {"magnetics": 282, "electrostatics": 95, "heatflow": 136, "currentflow": 258}


def test_get_exact_and_case(lib):
    m = lib.get("M-19 14 mil")
    assert m and m["folder"].endswith("Silicon Iron") and len(m["BH_curve"]) > 10
    assert lib.get("m-19 14 MIL")["name"] == "M-19 14 mil"
    assert lib.get("M-19 Steel") is None
    assert lib.get("Water, 20 C", physics="electrostatics")["ex"] > 70


def test_duplicate_names_by_folder(lib):
    liquid = lib.get("Ammonia", physics="heatflow", folder="Saturated Liquids")
    gas = lib.get("Ammonia", physics="heatflow", folder="Gases")
    assert liquid and gas and liquid["Kx"] != gas["Kx"]


@pytest.mark.parametrize("old,new", [
    ("M-19 Steel", "M-19 14 mil"), ("Pure Iron", "ARMCO Pure Iron"), ("1010 Steel", "1010 Steel (hot rolled)"),
    ("NdFeB 32 MGOe", "N33"), ("NdFeB 40 MGOe", "N40"), ("NdFeB 52 MGOe", "N52"), ("SmCo 24 MGOe", "SmCo24"),
    ("Air", "Air"), ("Copper", "Copper"),
])
def test_legacy_map(lib, old, new):
    assert lib.legacy_lookup(old) == new
    assert lib.suggest(old)["best"] == new


def test_legacy_targets_exist(lib):
    names = set(lib.names("magnetics"))
    assert lib.legacy_map and all(v in names for v in lib.legacy_map.values())


def test_search_fuzzy(lib):
    assert lib.search("M-19 Steel")[0]["name"] == "M-19 14 mil"
    assert lib.search("m19")[0]["name"].startswith("M-19")
    top = [r["name"] for r in lib.search("silicon iron", limit=6)]
    assert "M-19 14 mil" in top
    assert lib.search("18 AWG")[0]["name"] == "18 AWG"
    assert lib.search("N42")[0]["name"] == "N42"
    r = lib.search("water", physics="electrostatics")[0]
    assert r["name"].startswith("Water") and "eps_x" in r
    assert "BH_curve" not in lib.search("M-19")[0]


def test_suggest_unknown(lib):
    s = lib.suggest("Unobtainium 9000")
    assert s["requested"] == "Unobtainium 9000" and isinstance(s["nearest"], list)


def test_families(lib):
    fam = lib.families("magnetics")
    assert "NdFeB sintered" in fam and "N42" in fam["NdFeB sintered"]
    assert lib.families("heatflow")


def test_parse_dat(tmp_path):
    p = tmp_path / "matlib.dat"
    p.write_text(
        "<BeginBlock>\n<BlockName> = \"Air\"\n<Mu_x> = 1\n<BHPoints> = 0\n<EndBlock>\n"
        "<BeginFolder>\n<FolderName> = \"Soft\"\n"
        "<BeginBlock>\n<BlockName> = \"Iron\"\n<Mu_x> = 1000\n<Sigma> = 10.4\n<BHPoints> = 2\n"
        "  0 0\n  1.5 300\n<EndBlock>\n<EndFolder>\n", encoding="utf-8")
    mats = parse_dat(p, "magnetics")
    assert [m["name"] for m in mats] == ["Air", "Iron"]
    assert mats[0]["folder"] is None and mats[1]["folder"] == "Soft"
    assert mats[1]["BH_curve"] == [[0.0, 0.0], [1.5, 300.0]] and mats[1]["Sigma"] == 10.4
