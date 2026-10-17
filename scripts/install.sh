#!/usr/bin/env bash
# Install femm-agent-suite for Claude Code on macOS / Linux: venv + package, MCP registration, skills.
#   ./scripts/install.sh                      # user-wide MCP server "femm" + skills
#   FEMM_DIR=~/.local/opt/femm-qt/bin ./scripts/install.sh
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
scope="${SCOPE:-user}"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[plots]"
py="$repo/.venv/bin/python"

env_args=()
if [ -n "${FEMM_DIR:-}" ]; then env_args=(-e "FEMM_DIR=$FEMM_DIR"); fi
claude mcp remove femm --scope "$scope" >/dev/null 2>&1 || true
claude mcp add femm --scope "$scope" "${env_args[@]}" -- "$py" -m femm_agent
echo "Registered MCP server 'femm' ($scope scope) -> $py -m femm_agent"

if [ -z "${NO_SKILLS:-}" ]; then
  dest="$HOME/.claude/skills"
  mkdir -p "$dest"
  for s in .claude/skills/*/; do
    name="$(basename "$s")"
    rm -rf "$dest/$name"
    cp -R "$s" "$dest/$name"
    echo "Installed skill $name -> $dest"
  done
fi
"$py" -c "from femm_agent.config import find_femm, femm_version; i=find_femm(); print('FEMM 5 found:', (str(i.bin_dir)+'  '+str(femm_version(i))) if i else 'NOT FOUND - install FEMM 5 from https://www.femm.info or set FEMM_DIR')"
echo "Done. Restart Claude Code, then ask: 'run the FEMM self-test'."
