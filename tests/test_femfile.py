"""Offline tests for the FEMM text-file parser (femm_agent.femfile)."""
from pathlib import Path

import pytest

from femm_agent import femfile

FIX = Path(__file__).parent / "fixtures"

# a hand-written miniature solution: 1 material, 1 boundary, 1 circuit, 4 nodes, 2 elements
MINI_ANS = """[Format]      =  4.0
[Frequency]   =  0
[Precision]   =  1e-08
[MinAngle]    =  30
[Depth]       =  10
[LengthUnits] =  millimeters
[ProblemType] =  planar
[Coordinates] =  cartesian
[Comment]     =  "mini"
[PointProps]   = 0
[BdryProps]   = 1
  <BeginBdry>
    <BdryName> = "A=0"
    <BdryType> = 0
  <EndBdry>
[BlockProps]  = 1
  <BeginBlock>
    <BlockName> = "Steel"
    <Mu_x> = 1
    <Mu_y> = 1
    <H_c> = 0
    <BHPoints> = 2
      0\t0
      1.5\t1000
  <EndBlock>
[CircuitProps]  = 1
  <BeginCircuit>
    <CircuitName> = "coil"
    <TotalAmps_re> = 2
    <TotalAmps_im> = 0
    <CircuitType> = 1
  <EndCircuit>
[NumPoints] = 4
0\t0\t0\t0
1\t0\t0\t0
1\t1\t0\t0
0\t1\t0\t1
[NumSegments] = 1
0\t1\t-1\t1\t0\t0
[NumArcSegments] = 1
2\t3\t90\t5\t0\t0\t0\t0
[NumHoles] = 0
[NumBlockLabels] = 1
0.5\t0.5\t1\t0\t1\t30\t2\t10\t0
[Solution]
4
0\t0\t0
1\t0\t0.001
1\t1\t0.002
0\t1\t0.001
2
0\t1\t2\t0\t0\t-1\t-1\t0
0\t2\t3\t0\t-1\t-1\t-1\t0
1
0\t1
0
0
"""

MINI_FEE = """[Format] = 1
[LengthUnits] = centimeters
[ProblemType] = planar
[BlockProps] = 1
  <BeginBlock>
    <BlockName> = "air"
    <ex> = 1
    <ey> = 1
    <qv> = 0
  <EndBlock>
[ConductorProps] = 1
  <BeginConductor>
    <ConductorName> = "one"
    <Vc> = 1
    <qc> = 0
    <ConductorType> = 1
  <EndConductor>
[NumPoints] = 1
0\t0\t0\t0\t0
[NumSegments] = 0
[NumArcSegments] = 0
[NumHoles] = 0
[NumBlockLabels] = 1
0.5\t0.5\t1\t0\t0\t0
"""


def test_parse_fixture_ccore():
    m = femfile.parse_file(FIX / "ccore.fem")
    s = m.summary()
    assert s["physics"] == "magnetics" and s["problem_type"] == "planar"
    assert s["problem"]["LengthUnits"] == "millimeters" and s["problem"]["Depth"] == 20
    assert set(s["materials_used"]) >= {"Air", "Copper", "Linear iron mu2000"}
    assert [c["name"] for c in s["circuits"]] == ["coil"]
    coil = s["circuits"][0]
    assert coil["type_name"] == "series" and coil["labels"] == 2 and coil["turns"] == 0  # +200 and -200 turns
    assert "1" in s["groups"] and s["groups"]["1"]["labels"] == 1
    bb = s["bounding_box"]
    assert bb["xmax"] - bb["xmin"] > 300  # the mi_makeABC shells (R = 3 x 60 mm)


def test_parse_fixture_spm_age():
    s = femfile.summarize_file(FIX / "spm_age.fem")
    names = {b["name"]: b for b in s["boundaries"]}
    assert names["AGE"]["type"] == 6 and names["AGE"]["type_name"] == "periodic air gap"
    assert names["AGE"]["segments"] == 4
    assert len(s["magnets"]) == 4 and all(m["material"] == "N42" for m in s["magnets"])
    mats = {m["name"]: m for m in s["materials"]}
    assert mats["M-19 14 mil"]["nonlinear"] is True and mats["N42"]["magnet"] is True
    assert sorted(c["name"] for c in s["circuits"]) == ["A", "B", "C"]
    assert all(c["labels"] == 4 for c in s["circuits"])
    # the <No Mesh> label in the AGE annulus is written as a hole
    assert s["counts"]["block_labels"] == 20 and s["counts"]["holes"] == 1


def test_parse_mini_solution():
    m = femfile.parse_text(MINI_ANS, path="mini.ans", ext=".ans")
    assert m.physics == "magnetics"
    mat = m.materials()[0]
    assert mat["BHPoints_data"] == [[0.0, 0.0], [1.5, 1000.0]]
    lab = m.block_labels()[0]
    assert lab["material"] == "Steel" and lab["circuit"] == "coil" and lab["magdir"] == 30
    assert lab["group"] == 2 and lab["turns"] == 10 and lab["external"] is False
    assert m.nodes().shape == (4, 3) and m.elements().shape == (2, 8)
    assert list(m.element_labels()) == [0, 0]
    assert m.element_materials() == ["Steel", "Steel"]
    assert m.element_areas().tolist() == pytest.approx([0.5, 0.5])
    # A = 0.001 * (x + y) Wb/m with x, y in mm -> Bx = dA/dy = 1 T, By = -dA/dx = -1 T
    b = m.element_b_planar()
    assert b.ravel().tolist() == pytest.approx([1.0, -1.0, 1.0, -1.0])
    s = m.summary()
    assert s["solution"]["nodes"] == 4 and s["solution"]["elements"] == 2
    assert s["boundaries"][0]["segments"] == 1
    # the arc from (1,1) to (0,1) spanning 90 deg CCW bulges above y = 1
    assert s["bounding_box"]["ymax"] > 1.1


def test_arc_geometry_helpers():
    cx, cy, r = femfile.arc_center((1, 0), (0, 1), 90)
    assert (cx, cy, r) == pytest.approx((0, 0, 1))
    pts = femfile._arc_samples((1, 0), (-1, 0), 180, 4)
    assert pts[2] == pytest.approx((0, 1))


def test_other_physics_and_paths():
    m = femfile.parse_text(MINI_FEE)
    assert m.physics == "electrostatics" and m.unit_to_m == 0.01
    s = m.summary()
    assert s["materials"][0]["eps_x"] == 1 and s["circuits"][0]["ConductorName"] == "one"
    assert m.block_labels()[0]["material"] == "air"
    assert femfile.solution_path("x/motor.fem").name == "motor.ans"
    assert femfile.solution_path("cap.fee").suffix == ".res"
    assert femfile.solution_path("h.feh").suffix == ".anh"
