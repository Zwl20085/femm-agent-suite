<#
.SYNOPSIS
  Install femm-agent-suite for Claude Code on Windows: venv + package, MCP registration, skills.
.EXAMPLE
  .\scripts\install.ps1                          # user-wide MCP server "femm" + skills
  .\scripts\install.ps1 -FemmDir "D:\femm-qt\bin"
#>
param(
  [string]$FemmDir = "",
  [ValidateSet("user", "project", "local")][string]$Scope = "user",
  [switch]$NoSkills
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
  if (-not (Test-Path ".venv")) { python -m venv .venv }
  & .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  & .\.venv\Scripts\python.exe -m pip install --quiet -e ".[plots]"
  $py = (Resolve-Path ".venv\Scripts\python.exe").Path

  $envArgs = @()
  if ($FemmDir) { $envArgs = @("-e", "FEMM_DIR=$FemmDir") }
  claude mcp remove femm --scope $Scope 2>$null | Out-Null
  claude mcp add femm --scope $Scope @envArgs -- $py -m femm_agent
  Write-Host "Registered MCP server 'femm' ($Scope scope) -> $py -m femm_agent"

  if (-not $NoSkills) {
    $dest = Join-Path $env:USERPROFILE ".claude\skills"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($s in Get-ChildItem ".claude\skills" -Directory) {
      $target = Join-Path $dest $s.Name
      if (Test-Path $target) { Remove-Item -Recurse -Force $target }
      Copy-Item $s.FullName $target -Recurse -Force
      Write-Host "Installed skill $($s.Name) -> $dest"
    }
  }
  if ($FemmDir) { $env:FEMM_DIR = $FemmDir }
  & $py -c "from femm_agent.config import find_femm, femm_version; i=find_femm(); print('FEMM 5 found:', (str(i.bin_dir)+'  '+str(femm_version(i))) if i else 'NOT FOUND - install FEMM 5 from https://www.femm.info or pass -FemmDir')"
  Write-Host "Done. Restart Claude Code, then ask: 'run the FEMM self-test'."
} finally { Pop-Location }
