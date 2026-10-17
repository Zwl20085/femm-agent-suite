"""Offline tests for femm_agent.catalog (search, lookup, validation, graceful degradation)."""
import json

import pytest

from femm_agent import catalog
from femm_agent.catalog import Catalog, data_dir


def test_data_dir_has_catalog():
    assert (data_dir() / "commands.json").is_file()


def test_get_and_aliases():
    c = catalog.get("mi_probdef")
    assert c and c["physics"] == "magnetics" and c["phase"] == "pre"
    assert catalog.get("MI_PROBDEF")["name"] == "mi_probdef"
    assert catalog.get("no_such_command") is None


def test_search_ranks_name_first():
    hits = catalog.search("blockintegral", physics="magnetics")
    assert hits[0]["name"] == "mo_blockintegral"
    hits = catalog.search("air gap", physics="magnetics", phase="post")
    names = [h["name"] for h in hits]
    assert any("gap" in n for n in names[:5])
    assert all(h["physics"] in ("magnetics", "common") for h in hits)
    assert all(h["phase"] in ("post", "common") for h in hits)
    assert "signature" in hits[0] and hits[0]["signature"].startswith("mo_")


def test_validate_args():
    assert catalog.validate_args("mi_addnode", [1, 2]) == []
    w = catalog.validate_args("mi_probdef", ["mm", 0])
    assert any("at least 4" in x for x in w) and any("should be number" in x for x in w)
    w = catalog.validate_args("mi_addnode", [1, 2, 3, 4])
    assert any("at most" in x for x in w)
    w = catalog.validate_args("mo_getb", [0, 0])
    assert any("pyFEMM helper" in x for x in w)
    w = catalog.validate_args("mi_addnodes", [1])
    assert "mi_addnode" in w[0]
    w = catalog.validate_args("mo_blockintegral", [999])
    assert any("documented codes" in x for x in w)


def test_read_only_and_physics_of():
    assert catalog.is_read_only("mo_getpointvalues") is True
    assert catalog.is_read_only("mi_addnode") is False
    assert catalog.is_read_only("nope") is None
    assert catalog.physics_of("eo_getv") == ("electrostatics", "post")
    assert catalog.physics_of("newdocument") is None


def test_missing_catalog_degrades(tmp_path):
    cat = Catalog(tmp_path / "commands.json")
    with pytest.warns(UserWarning):
        assert cat.search("node") == []
    assert cat.get("mi_addnode") is None
    assert "not found" in cat.validate_args("mi_addnode", [1, 2])[0]
    # the file lands later: the catalog picks it up without a restart
    (tmp_path / "commands.json").write_text(json.dumps([{"name": "mi_addnode", "physics": "magnetics",
                                                           "phase": "pre", "args": [], "description": "x"}]))
    assert cat.get("mi_addnode") is not None and cat.warning is None


def test_corrupt_catalog(tmp_path):
    p = tmp_path / "commands.json"
    p.write_text("{not json")
    cat = Catalog(p)
    with pytest.warns(UserWarning):
        assert len(cat) == 0
    assert "could not be read" in cat.warning
