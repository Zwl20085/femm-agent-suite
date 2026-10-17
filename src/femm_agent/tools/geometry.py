"""Geometry tools: nodes, segments, arcs, shapes, selection and edit transforms (any physics)."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from ..sessions import Session
from ._common import ToolContext, ToolInputError, as_list, run_tool
from .document import resolve_path, save_document

EDIT_ACTION = {"nodes": 0, "segments": 1, "labels": 2, "blocks": 2, "arcs": 3, "group": 4, "groups": 4}


def _pt(p: Any, what: str = "point") -> tuple[float, float]:
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return float(p[0]), float(p[1])
    raise ToolInputError(f"{what} must be [x, y], got {p!r}", "Pass points as [[x1, y1], [x2, y2], ...] in problem units.")


def _seg(seg: Any) -> tuple[float, float, float, float]:
    if isinstance(seg, (list, tuple)) and len(seg) == 2:
        (x1, y1), (x2, y2) = _pt(seg[0]), _pt(seg[1])
        return x1, y1, x2, y2
    if isinstance(seg, (list, tuple)) and len(seg) == 4:
        return tuple(float(v) for v in seg)  # type: ignore[return-value]
    raise ToolInputError(f"segment must be [[x1,y1],[x2,y2]] or [x1,y1,x2,y2], got {seg!r}",
                         "Pass segments as [[[x1, y1], [x2, y2]], ...].")


def _action(kind: str | None) -> int | None:
    if kind is None or kind == "":
        return None
    k = kind.strip().lower()
    if k not in EDIT_ACTION:
        raise ToolInputError(f"unknown entity kind {kind!r}", "Use nodes, segments, labels, arcs or group.")
    return EDIT_ACTION[k]


def add_segment(s: Session, x1: float, y1: float, x2: float, y2: float) -> None:
    s.pre_call("addnode", x1, y1)
    s.pre_call("addnode", x2, y2)
    s.pre_call("addsegment", x1, y1, x2, y2)


def add_arc(s: Session, x1: float, y1: float, x2: float, y2: float, angle: float, maxseg: float) -> None:
    s.pre_call("addnode", x1, y1)
    s.pre_call("addnode", x2, y2)
    s.pre_call("addarc", x1, y1, x2, y2, angle, maxseg)


def draw_circle(s: Session, cx: float, cy: float, r: float, maxseg: float = 1.0) -> list[list[float]]:
    pts = [[cx + r, cy], [cx, cy + r], [cx - r, cy], [cx, cy - r]]
    for p in pts:
        s.pre_call("addnode", *p)
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        s.pre_call("addarc", a[0], a[1], b[0], b[1], 90, maxseg)
    return pts


def polyline(s: Session, points: list, closed: bool) -> int:
    pts = [_pt(p) for p in points]
    if len(pts) < 2:
        raise ToolInputError("need at least 2 points", "Pass [[x1,y1],[x2,y2],...].")
    if closed and len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    for p in pts:
        s.pre_call("addnode", *p)
    n = 0
    for i in range(len(pts) - 1):
        s.pre_call("addsegment", *pts[i], *pts[i + 1])
        n += 1
    if closed and len(pts) > 2:
        s.pre_call("addsegment", *pts[-1], *pts[0])
        n += 1
    return n


def summarize_file(path: str | Path) -> dict[str, Any]:
    """Counts and property names from a saved .fem/.fee/.feh/.fec (light parser, header lines only)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out: dict[str, Any] = {}
    for key, label in (("NumPoints", "nodes"), ("NumSegments", "segments"), ("NumArcSegments", "arcs"),
                       ("NumHoles", "holes"), ("NumBlockLabels", "block_labels")):
        m = re.search(r"^\s*\[" + key + r"\]\s*=\s*(\d+)", text, re.M | re.I)
        if m:
            out[label] = int(m.group(1))

    def names(begin: str, end: str, key: str) -> list[str]:
        res = []
        for blk in re.findall(r"<" + begin + r">(.*?)<" + end + r">", text, re.S | re.I):
            m = re.search(r"<" + key + r">\s*=\s*\"([^\"]*)\"", blk, re.I)
            if m:
                res.append(m.group(1))
        return res

    out["boundaries"] = names("BeginBdry", "EndBdry", "BdryName")
    out["materials"] = names("BeginBlock", "EndBlock", "BlockName")
    out["circuits"] = names("BeginCircuit", "EndCircuit", "CircuitName")
    out["conductors"] = names("BeginConductor", "EndConductor", "ConductorName")
    out["point_props"] = names("BeginPoint", "EndPoint", "PointName")
    return out


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_add_nodes(points: list[list[float]], session: str = "main") -> dict:
        """Add nodes at [[x, y], ...] (problem units; axi: x is r >= 0). Existing nodes at the same
        place are reused by FEMM. Usually you want femm_draw_polygon / femm_add_segments instead."""
        def run(s: Session):
            for p in points:
                s.pre_call("addnode", *_pt(p))
            return {"added": len(points)}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_segments(segments: list[list[Any]], session: str = "main") -> dict:
        """Add straight segments [[[x1,y1],[x2,y2]], ...] (or [x1,y1,x2,y2] each). End nodes are
        created as needed. Segments that cross are split by FEMM at the intersection."""
        def run(s: Session):
            for g in segments:
                add_segment(s, *_seg(g))
            return {"added": len(segments)}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_arcs(arcs: list[list[float]], session: str = "main") -> dict:
        """Add arcs [[x1, y1, x2, y2, angle_deg, maxseg_deg], ...]: from (x1,y1) counter-clockwise to
        (x2,y2) sweeping `angle_deg` (0 < angle <= 180); maxseg_deg is the arc discretisation
        (1 deg fine, 5-10 coarse; air gaps want <= 1). End nodes are created as needed."""
        def run(s: Session):
            for a in arcs:
                if len(a) == 5:
                    a = list(a) + [1.0]
                if len(a) != 6:
                    raise ToolInputError(f"arc must be [x1,y1,x2,y2,angle,maxseg], got {a!r}", "Six numbers per arc.")
                add_arc(s, *[float(v) for v in a])
            return {"added": len(arcs)}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_draw_rectangle(x1: float, y1: float, x2: float, y2: float, session: str = "main") -> dict:
        """Axis-aligned rectangle with opposite corners (x1,y1), (x2,y2): 4 nodes + 4 segments.
        Add a block label inside it afterwards (femm_add_block_label)."""
        def run(s: Session):
            s.pre_call("drawrectangle", x1, y1, x2, y2)
            return {"corners": [[x1, y1], [x2, y2]], "centre": [(x1 + x2) / 2, (y1 + y2) / 2]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_draw_circle(cx: float, cy: float, r: float, maxseg: float = 1.0, session: str = "main") -> dict:
        """Full circle of radius r around (cx, cy) as four 90-degree arcs (nodes at 0/90/180/270 deg).
        maxseg = arc discretisation in degrees. For a half circle in axi models, use femm_add_arcs."""
        def run(s: Session):
            if r <= 0:
                raise ToolInputError("radius must be > 0", "Pass r > 0 in problem units.")
            return {"nodes": draw_circle(s, cx, cy, r, maxseg), "label_hint": [cx, cy]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_draw_polygon(points: list[list[float]], closed: bool = True, session: str = "main") -> dict:
        """Polygon through [[x, y], ...]: nodes + segments, closed back to the first point by default.
        Returns the vertex centroid (a block-label candidate only if the polygon is convex)."""
        def run(s: Session):
            n = polyline(s, points, closed)
            pts = [_pt(p) for p in points]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            return {"segments": n, "closed": closed, "vertex_centroid": [cx, cy]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_draw_polyline(points: list[list[float]], session: str = "main") -> dict:
        """Open chain of segments through [[x, y], ...] (not closed). Same as femm_draw_polygon(closed=False)."""
        return run_tool(ctx, session, lambda s: {"segments": polyline(s, points, False)}, need="document")

    @mcp.tool()
    def femm_select(kind: str, points: list[list[float]] | None = None, rectangle: list[float] | None = None,
                    circle: list[float] | None = None, group: int | None = None, entities: str = "all",
                    clear_first: bool = True, session: str = "main") -> dict:
        """Select objects for a following edit (femm_move_selected, femm_delete_selected,
        femm_set_group ...). kind:
          nodes | segments | arcs | labels  -> nearest object to each of `points` [[x, y], ...]
          group     -> every object in `group`
          rectangle -> objects inside rectangle=[x1, y1, x2, y2]
          circle    -> objects inside circle=[cx, cy, R]
        entities (rectangle/circle only): nodes|segments|labels|arcs|all.
        Returns what FEMM reports for each pick (the coordinates of the selected object)."""
        def run(s: Session):
            if clear_first:
                s.pre_call("clearselected")
            k = kind.strip().lower()
            picks: list[Any] = []
            fn = {"nodes": "selectnode", "node": "selectnode", "segments": "selectsegment", "segment": "selectsegment",
                  "arcs": "selectarcsegment", "arc": "selectarcsegment", "labels": "selectlabel",
                  "label": "selectlabel", "blocks": "selectlabel"}.get(k)
            if fn:
                for p in as_list(points):
                    picks.append(s.pre_call(fn, *_pt(p)))
            elif k == "group":
                if group is None:
                    raise ToolInputError("kind=group needs group=<n>", "Pass group=<integer>.")
                s.pre_call("selectgroup", int(group))
            elif k in ("rectangle", "circle"):
                mode = {"nodes": 0, "segments": 1, "labels": 2, "arcs": 3, "all": 4}.get(entities, 4)
                if k == "rectangle":
                    if not rectangle or len(rectangle) != 4:
                        raise ToolInputError("rectangle must be [x1, y1, x2, y2]", "Pass rectangle=[x1, y1, x2, y2].")
                    s.pre_call("selectrectangle", *[float(v) for v in rectangle], mode)
                else:
                    if not circle or len(circle) != 3:
                        raise ToolInputError("circle must be [cx, cy, R]", "Pass circle=[cx, cy, R].")
                    s.pre_call("selectcircle", *[float(v) for v in circle], mode)
            else:
                raise ToolInputError(f"unknown selection kind {kind!r}",
                                     "Use nodes, segments, arcs, labels, group, rectangle or circle.")
            return {"kind": k, "picked": picks}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_clear_selected(session: str = "main") -> dict:
        """Deselect everything in the pre-processor."""
        return run_tool(ctx, session, lambda s: s.pre_call("clearselected"), need="document")

    @mcp.tool()
    def femm_delete_selected(kind: str = "all", session: str = "main") -> dict:
        """Delete the current selection. kind: all | nodes | segments | arcs | labels
        (deleting nodes also deletes segments/arcs attached to them)."""
        def run(s: Session):
            cmd = {"all": "deleteselected", "nodes": "deleteselectednodes", "segments": "deleteselectedsegments",
                   "arcs": "deleteselectedarcsegments", "labels": "deleteselectedlabels"}.get(kind)
            if cmd is None:
                raise ToolInputError(f"unknown kind {kind!r}", "Use all, nodes, segments, arcs or labels.")
            s.pre_call(cmd)
            return {"deleted": kind}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_move_selected(dx: float = 0.0, dy: float = 0.0, rotate_deg: float | None = None,
                           about: list[float] | None = None, entities: str | None = None, session: str = "main") -> dict:
        """Move the selection: translate by (dx, dy), or rotate by `rotate_deg` (counter-clockwise)
        about `about`=[x, y] (default origin). entities: nodes|segments|labels|arcs|group restricts
        what moves (default: FEMM's current edit mode; use 'group' after femm_select(kind='group'))."""
        def run(s: Session):
            ea = _action(entities)
            extra = [ea] if ea is not None else []
            if rotate_deg is not None:
                bx, by = _pt(about) if about else (0.0, 0.0)
                s.pre_call("moverotate", bx, by, rotate_deg, *extra)
                return {"rotated_deg": rotate_deg, "about": [bx, by]}
            s.pre_call("movetranslate", dx, dy, *extra)
            return {"translated": [dx, dy]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_copy_selected(dx: float = 0.0, dy: float = 0.0, rotate_deg: float | None = None,
                           about: list[float] | None = None, copies: int = 1, entities: str | None = None,
                           session: str = "main") -> dict:
        """Copy the selection `copies` times, each shifted by a further (dx, dy) or rotated by a
        further `rotate_deg` about `about` (default origin). Typical: one slot drawn, then
        femm_select(kind='group') + femm_copy_selected(rotate_deg=360/Q, copies=Q-1, entities='group')."""
        def run(s: Session):
            ea = _action(entities)
            extra = [ea] if ea is not None else []
            if rotate_deg is not None:
                bx, by = _pt(about) if about else (0.0, 0.0)
                s.pre_call("copyrotate", bx, by, rotate_deg, int(copies), *extra)
                return {"rotated_deg": rotate_deg, "copies": copies}
            s.pre_call("copytranslate", dx, dy, int(copies), *extra)
            return {"translated": [dx, dy], "copies": copies}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_mirror_selected(x1: float, y1: float, x2: float, y2: float, entities: str | None = None,
                             session: str = "main") -> dict:
        """Mirror-copy the selection about the line through (x1,y1)-(x2,y2) (the original stays)."""
        def run(s: Session):
            ea = _action(entities)
            s.pre_call("mirror", x1, y1, x2, y2, *([ea] if ea is not None else []))
            return {"mirror_line": [[x1, y1], [x2, y2]]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_scale_selected(factor: float, about: list[float] | None = None, entities: str | None = None,
                            session: str = "main") -> dict:
        """Scale the selection by `factor` about `about`=[x, y] (default origin)."""
        def run(s: Session):
            bx, by = _pt(about) if about else (0.0, 0.0)
            ea = _action(entities)
            s.pre_call("scale", bx, by, factor, *([ea] if ea is not None else []))
            return {"factor": factor, "about": [bx, by]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_set_group(group: int, session: str = "main") -> dict:
        """Put the selected objects into group number `group` (used for moving rotors, for
        femm_block_integral(group=...) and femm_field_stats(region='group:N'))."""
        return run_tool(ctx, session, lambda s: s.pre_call("setgroup", int(group)) or {"group": group}, need="document")

    @mcp.tool()
    def femm_import_dxf(path: str, tolerance: float | None = None, session: str = "main") -> dict:
        """Import a DXF drawing into the current model (xi_readdxf). `tolerance` merges nodes closer
        than this (problem units); leave None for FEMM's default. Check the result with
        femm_geometry_summary, then add block labels."""
        def run(s: Session):
            p = Path(path)
            if not p.is_absolute():
                p = s.work_dir / p
            if not p.is_file():
                raise ToolInputError(f"DXF not found: {p}", "Pass an existing .dxf path.")
            args: list[Any] = [p.resolve().as_posix()]
            if tolerance is not None:
                args.append(float(tolerance))
            s.pre_call("readdxf", *args)
            return {"imported": args[0]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_export_dxf(path: str, session: str = "main") -> dict:
        """Write the current geometry to a DXF file (xi_savedxf)."""
        def run(s: Session):
            p = resolve_path(s, path)
            if not p.lower().endswith(".dxf"):
                p = str(Path(p).with_suffix(".dxf").as_posix())
            s.pre_call("savedxf", p)
            return {"saved": p, "exists": Path(p).is_file()}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_geometry_summary(session: str = "main") -> dict:
        """Counts of nodes, segments, arcs, block labels and the defined materials, boundaries,
        circuits/conductors, plus the bounding box. FEMM 5 has no pre-processor count getters, so
        this saves the model (to its current path, or <work_dir>/model.<ext>) and reads the counts
        from the saved file. Use it to sanity-check a model before meshing."""
        def run(s: Session):
            path = save_document(s)
            out = summarize_file(path)
            out["file"] = path
            try:
                bb = s.pre_call("getboundingbox")
                if isinstance(bb, list) and len(bb) == 4:
                    out["bounding_box"] = {"x_min": bb[0], "x_max": bb[1], "y_min": bb[2], "y_max": bb[3]}
                    out["size"] = [bb[1] - bb[0], bb[3] - bb[2]]
                    out["diagonal"] = math.hypot(bb[1] - bb[0], bb[3] - bb[2])
            except Exception:
                pass
            return out
        return run_tool(ctx, session, run, need="document")
