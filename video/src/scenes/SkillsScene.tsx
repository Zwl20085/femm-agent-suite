import React from "react";
import { AbsoluteFill } from "remotion";
import { C, Heading, MONO, Panel, SANS, useSpring } from "../theme";
import type { SceneConfig } from "../audioConfig";

const SKILLS: [string, string][] = [
  ["femm", "router: picks the right skill and tools"],
  ["femm-magnetics", "magnetostatic and time-harmonic problems"],
  ["femm-electrostatics-thermal-currentflow", "the other three physics"],
  ["femm-geometry", "nodes, arcs, shapes, groups, DXF"],
  ["femm-materials", "771 materials, FEMM 5 renames, B-H"],
  ["femm-experiments", "cogging, back-EMF, L, AC sweeps"],
  ["femm-health-check", "physics sanity rules before trusting"],
  ["femm-postprocess", "fields, integrals, plots, reports"],
  ["femm-scripting", "677 commands, journals, pyFEMM export"],
  ["femm-machine-design", "motors from sizing to torque proof"],
  ["femm-troubleshooting", "errors, meshing and solver fixes"],
];

const SkillCard: React.FC<{ name: string; desc: string; delay: number; router: boolean }> = ({ name, desc, delay, router }) => {
  const p = useSpring(delay, 13);
  return (
    <Panel
      accent={router}
      style={{
        height: 132,
        padding: "22px 26px",
        boxSizing: "border-box",
        opacity: Math.min(1, p * 1.4),
        transform: `translateY(${(1 - p) * 26}px) scale(${0.94 + 0.06 * p})`,
      }}
    >
      <div style={{ fontFamily: MONO, fontSize: name.length > 30 ? 20 : 26, fontWeight: 700, color: router ? C.accent : C.text, whiteSpace: "nowrap" }}>
        {name}
      </div>
      <div style={{ fontFamily: SANS, fontSize: 23, color: C.muted, marginTop: 12 }}>{desc}</div>
    </Panel>
  );
};

export const SkillsScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const l1 = scene.lines[0].from;
  const note = useSpring(l1 + 11 * 8 + 10);
  return (
    <AbsoluteFill>
      <Heading kicker="11 Claude skills" title="The operating manual for the tools" />
      <div style={{ position: "absolute", left: 120, right: 120, top: 250, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
        {SKILLS.map(([n, d], i) => (
          <SkillCard key={n} name={n} desc={d} delay={l1 + i * 8} router={i === 0} />
        ))}
        <div style={{ display: "flex", alignItems: "center", padding: "0 26px", opacity: note }}>
          <div style={{ fontFamily: SANS, fontSize: 25, color: C.muted, lineHeight: 1.35 }}>
            Loaded on demand by Claude Code. They say <span style={{ color: C.text }}>which tool, in which order</span>, and what a sane answer looks like.
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
