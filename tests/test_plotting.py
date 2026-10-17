"""Offline tests: figures are written as PNG files (skipped without matplotlib)."""
import math

import pytest

from femm_agent import plotting

pytestmark = pytest.mark.skipif(not plotting.available(), reason="matplotlib not installed")


def _is_png(p):
    with open(p, "rb") as fh:
        return fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_curves_and_harmonics(tmp_path):
    x = [i * 2.0 for i in range(16)]
    p = plotting.plot_curves(tmp_path / "c.png", x, {"a": [math.sin(v / 5) for v in x], "b": [math.cos(v / 5) for v in x]},
                             title="t", xlabel="x", ylabel="y", dashed=("b",))
    assert _is_png(p)
    p = plotting.plot_harmonics(tmp_path / "h.png", list(range(10)), [1.0 / (k + 1) for k in range(10)], title="h")
    assert _is_png(p)


def test_field_and_mesh(tmp_path):
    nodes = [[0, 0], [1, 0], [1, 1], [0, 1]]
    tri = [[0, 1, 2], [0, 2, 3]]
    p = plotting.plot_field(tmp_path / "f.png", nodes, tri, [0.5, 1.5], title="|B|", xlim=(0, 1), ylim=(0, 1))
    assert _is_png(p)
    p = plotting.plot_mesh(tmp_path / "m.png", nodes, tri)
    assert _is_png(p)
