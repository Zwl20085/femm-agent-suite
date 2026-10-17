"""The `femm` MCP server: builds the server, the tool context, and registers every tool group."""
from __future__ import annotations

import importlib
import logging
import sys
import traceback
from typing import Any, Callable

try:  # mcp >= 2: FastMCP was renamed MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

from .catalog import data_dir
from .sessions import SessionManager
from .tools._common import ToolContext

CORE_GROUPS = ["session", "document", "geometry", "properties", "materials", "mesh_solve", "postproc",
               "scripting", "docs"]
ENGINEERING_GROUPS = ["experiments", "health", "report"]

INSTRUCTIONS = (
    "Drive FEMM 5 (2D finite elements: magnetics, electrostatics, heat flow, current flow). "
    "Start with femm_status; femm_selftest checks the install end to end. Typical flow: "
    "femm_new_document -> femm_problem_define -> geometry (femm_draw_*) -> femm_material_load -> "
    "femm_add_block_label -> femm_add_boundary -> femm_solve -> femm_point_values / "
    "femm_block_integral / femm_circuit_results. Lengths are in the problem units, angles in "
    "degrees. Every tool returns {ok, result | error{message, hint}}; follow the hint on errors. "
    "femm_call reaches any FEMM command; femm_api_search finds them."
)

log = logging.getLogger("femm_agent")


class _Registrar:
    """Wraps the MCP server so each `@mcp.tool()` is also recorded (name -> function, group)."""

    def __init__(self, server: Any, registry: dict[str, Callable[..., Any]], group: str, groups: dict[str, list[str]]):
        self._server = server
        self._registry = registry
        self._group = group
        self._groups = groups

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        deco = self._server.tool(*args, **kwargs)

        def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = kwargs.get("name") or (args[0] if args and isinstance(args[0], str) else fn.__name__)
            self._registry[name] = fn
            self._groups.setdefault(self._group, []).append(name)
            return deco(fn)
        return wrap

    def __getattr__(self, item: str) -> Any:
        return getattr(self._server, item)


def build_server(sessions: SessionManager | None = None, include_engineering: bool = True) -> tuple[Any, ToolContext]:
    """Create the server and context and register every available tool group.
    Engineering groups are optional: a missing or broken module is logged and skipped."""
    mcp = _Server("femm", instructions=INSTRUCTIONS)
    ctx = ToolContext(sessions=sessions or SessionManager(), repo_data=data_dir())
    registry: dict[str, Callable[..., Any]] = {}
    groups: dict[str, list[str]] = {}
    skipped: dict[str, str] = {}
    ctx.extras["tools"] = registry
    ctx.extras["groups"] = groups
    ctx.extras["skipped_groups"] = skipped
    for g in CORE_GROUPS + (ENGINEERING_GROUPS if include_engineering else []):
        try:
            mod = importlib.import_module(f".tools.{g}", __package__)
        except ModuleNotFoundError as e:
            if g in CORE_GROUPS:
                raise
            skipped[g] = f"not installed: {e}"
            continue
        except Exception as e:
            if g in CORE_GROUPS:
                raise
            skipped[g] = f"import failed: {type(e).__name__}: {e}"
            log.warning("tool group %s failed to import:\n%s", g, traceback.format_exc())
            continue
        reg = getattr(mod, "register", None)
        if reg is None:
            skipped[g] = "no register(mcp, ctx)"
            continue
        try:
            reg(_Registrar(mcp, registry, g, groups), ctx)
        except Exception as e:
            if g in CORE_GROUPS:
                raise
            skipped[g] = f"register failed: {type(e).__name__}: {e}"
            log.warning("tool group %s failed to register:\n%s", g, traceback.format_exc())
    return mcp, ctx


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    mcp, ctx = build_server()
    try:
        mcp.run()
    finally:
        ctx.sessions.close_all()


if __name__ == "__main__":
    main()
