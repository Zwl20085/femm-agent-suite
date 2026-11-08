"""`python -m femm_agent [--doctor [--json] | --version]`; no flag runs the MCP server (stdio).

--doctor and --version work even when the server module cannot be imported (missing or broken
`mcp`), because doctor.py imports nothing beyond the standard library and the suite's pure modules.
"""
import sys


def main() -> None:
    argv = sys.argv[1:]
    if "--version" in argv:
        from . import __version__
        print(f"femm-agent-suite {__version__}")
        sys.exit(0)
    if "--doctor" in argv:
        from . import doctor
        sys.exit(doctor.cli(as_json="--json" in argv))
    from .server import main as server_main
    server_main()


if __name__ == "__main__":
    main()
