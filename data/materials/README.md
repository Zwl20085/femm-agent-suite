# Material libraries (parsed)

JSON exports of the four FEMM 5 material libraries shipped in `C:\femm-qt\bin`.
Provenance and licences: see `PROVENANCE.md` in this folder.

## Counts

| library | physics | materials | folders | JSON |
|---|---|---|---|---|
| matlib.dat | magnetics | 282 | 25 | magnetics.json |
| statlib.dat | electrostatics | 95 | 12 | electrostatics.json |
| heatlib.dat | heat flow | 136 | 20 | heatflow.json |
| condlib.dat | current flow | 258 | 24 | currentflow.json |

Counts match the expected totals (282 / 95 / 136 / 258). The `folders` count is the number of
`<BeginFolder>` entries, including nested ones.

Other files here: `name_index.json` (magnetic names, families, FEMM 4.2 favourite mapping).

## File format

Each library is text with CRLF line endings and blocks of the form:

    <BeginFolder> / <FolderName> = "..." / ... / <EndFolder>     (folders can nest)
    <BeginBlock> / <BlockName> = "..." / <key> = value / ... / <EndBlock>

Point tables follow a `<BHPoints>` (matlib) or `<TKPoints>` (heatlib) line as unlabelled
`x y` rows, indented in some cases. `matlib.dat` is UTF-8, the others are ASCII.

## Parsing rules

1. Read as UTF-8 (BOM stripped). Strip leading and trailing whitespace from each line; skip blank lines.
2. `<BeginFolder>` pushes the next `<FolderName>`; `<EndFolder>` pops. Each material's `folder` is the
   slash-joined stack, for example `Hard Magnetic Materials / Alnico Magnets`. Materials outside any folder
   (for example `Air` in matlib) have `folder: null`.
3. `<BeginBlock>` starts a material; `<EndBlock>` ends it.
4. `<BlockName>` gives `name`. Other `<key> = value` lines are stored under their original key
   (no renaming). Values in double quotes are stripped of quotes. Values that are integers or floats
   are converted to numbers. Anything else stays a string.
5. Unlabelled rows of two numbers after a `<BHPoints>` or `<TKPoints>` line go into `BH_curve` (matlib)
   or `TK_curve` (heatlib) as `[x, y]` pairs. The declared point count is checked against the rows read.
6. `<FolderURL>` (matlib), `<FolderVendor>` (heatlib) and similar lines outside a block are ignored.
7. Output JSON keeps every key present in the block; no key is dropped and none is invented.

## Key names (magnetics)

The actual keys differ from some informal names:

| informal | key in matlib.dat |
|---|---|
| relative permeability | `Mu_x`, `Mu_y` |
| coercivity | `H_c`, direction `H_cAngle` |
| current density | `J_re`, `J_im` |
| conductivity | `Sigma` (MS/m) |
| lamination thickness | `d_lam` (not `Lam_d`) |
| lamination fill | `LamFill`, type `LamType` |
| max hysteresis angle | `Phi_h` (not `Phi_hmax`), with `Phi_hx`, `Phi_hy` |
| BH point count | `BHPoints` |

Electrostatics keys: `ex`, `ey`, `qv`. Heat flow: `Kx`, `Ky`, `Kt`, `qv`, `TKPoints`.
Current flow: `ox`, `oy`, `ex`, `ey`, `ltx`, `lty`.

## Known ambiguities

- `Ammonia` appears twice in heatlib.dat, in different folders (`Saturated Liquids (stagnant only)` and
  `Gases at 1 atm (stagnant only)`) with different `Kx`. Both are kept. Name lookup must use folder too.
- Name case and spelling are kept as in the file, including `°` (U+00B0) in names such as `1010 Steel (1400°F)`.
- `folder` is the full path. Names alone are not unique keys (see Ammonia); use folder plus name.
