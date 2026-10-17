# Provenance of the FEMM material libraries

Source: `docs/materials/README.md` in the femm-qt / FEMM 5 installation
(`C:\femm-qt\docs\materials\README.md`). Summarised here; the source text is authoritative.

## Libraries and licences

- Libraries: `matlib.dat` (magnetics), `statlib.dat` (electrostatics),
  `heatlib.dat` (heat flow), `condlib.dat` (current flow), shipped with femm-qt.
- Library files: released under the MIT License (copyright 2026 David Meeker and contributors),
  as stated in the source README. The same MIT terms apply to the rest of femm-qt outside `solvers/`.
- Provenance papers (PDF, in `C:\femm-qt\docs\materials\`): licensed separately under
  **CC BY 4.0**. They document sources and curve fitting for each entry.
- Scripts and data in the source-tree `provenance/` folder: MIT, per the source README.

## What the licence covers

Material property values are measured or tabulated facts and are not claimed by the libraries.
The licence covers the work on them: fitting and conditioning of curves, choice of materials and
conditions, and the organisation and naming of entries. No text, figures or tables are reproduced
from the sources, which remain under their owners' copyright.

Sources fall into three groups: standard reference works on material properties; curves fitted to
manufacturers' datasheets; and national laboratory reports. No entry rests on private communication
or permission-based reproduction.

## Papers by library

| library | provenance papers |
|---|---|
| matlib.dat | bhcurves, ironcurves, sicurves, nifecurves, cofecurves, sscurves, metglascurves, ceramiccurves, AlnicoProperties, SinteredNdFeBProperties, BondedNdFeB, SmCoProperties (all PDF) |
| statlib.dat | statlib_provenance.pdf |
| heatlib.dat | heatlib_provenance.pdf |
| condlib.dat | condlib_provenance.pdf |

## Caveats (from the source)

- Entries are typical or nominal values. Real material varies by heat, lot and processing.
  Confirm against supplier certified data or measurements where a design depends on them.
- Trade names (for example Metglas, ARMCO, Carpenter) are trademarks of their owners and are used only to
  identify the material.
- Libraries are provided as is, without warranty.
- femm-qt does not edit the shipped files in place. User edits are saved to a separate copy in the settings folder.
