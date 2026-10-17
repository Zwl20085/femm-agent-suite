import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, Heading, MONO, Panel, SANS, useSpring } from "../theme";
import type { SceneConfig } from "../audioConfig";

const GROUPS: [string, number, string][] = [
  ["session", 5, "launch, list, close engines"],
  ["document", 7, "new, open, save, problem"],
  ["geometry", 18, "nodes, arcs, shapes, DXF"],
  ["properties", 10, "blocks, boundaries, circuits"],
  ["materials", 6, "771 entries, fuzzy search"],
  ["mesh / solve", 4, "mesh, solve, load"],
  ["postproc", 10, "points, integrals, plots"],
  ["scripting", 6, "677 commands, journal"],
  ["docs", 5, "manual, facts, examples"],
  ["experiments", 9, "cogging, EMF, L, AC"],
  ["health", 3, "physics sanity rules"],
  ["report", 5, "compare, plot, report"],
];

const Box: React.FC<{ x: number; w: number; delay: number; title: string; sub: string; accent?: boolean }> = ({ x, w, delay, title, sub, accent }) => {
  const p = useSpring(delay);
  return (
    <Panel
      accent={accent}
      style={{ position: "absolute", left: x, top: 0, width: w, height: 150, padding: "26px 30px", boxSizing: "border-box", opacity: p, transform: `scale(${0.9 + 0.1 * p})` }}
    >
      <div style={{ fontFamily: MONO, fontSize: 32, fontWeight: 700, color: accent ? C.accent : C.text }}>{title}</div>
      <div style={{ fontFamily: SANS, fontSize: 24, color: C.muted, marginTop: 10 }}>{sub}</div>
    </Panel>
  );
};

const Arrow: React.FC<{ x1: number; x2: number; delay: number; label: string }> = ({ x1, x2, delay, label }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [delay, delay + 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const w = x2 - x1;
  return (
    <div style={{ position: "absolute", left: x1, top: 40, width: w, height: 70, opacity: p }}>
      <div style={{ fontFamily: MONO, fontSize: 21, color: C.accent, textAlign: "center", whiteSpace: "nowrap" }}>{label}</div>
      <svg width={w} height={30} style={{ position: "absolute", top: 34 }}>
        <line x1={8} y1={15} x2={8 + (w - 26) * p} y2={15} stroke={C.accent} strokeWidth={3} strokeDasharray="10 7" strokeDashoffset={-frame * 1.5} />
        <path d={`M${w - 20} 6 L${w - 6} 15 L${w - 20} 24`} fill="none" stroke={C.accent} strokeWidth={3} opacity={p >= 1 ? 1 : 0} />
      </svg>
    </div>
  );
};

const GroupCard: React.FC<{ name: string; n: number; desc: string; delay: number }> = ({ name, n, desc, delay }) => {
  const frame = useCurrentFrame();
  const p = useSpring(delay, 12);
  const count = Math.round(interpolate(frame, [delay, delay + 18], [0, n], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <Panel style={{ padding: "18px 22px", boxSizing: "border-box", height: 140, opacity: Math.min(1, p * 1.4), transform: `translateY(${(1 - p) * 30}px) scale(${0.92 + 0.08 * p})` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontFamily: MONO, fontSize: 25, color: C.text, fontWeight: 500 }}>{name}</div>
        <div style={{ fontFamily: MONO, fontSize: 40, color: C.accent, fontWeight: 700 }}>{count}</div>
      </div>
      <div style={{ fontFamily: SANS, fontSize: 21, color: C.muted, marginTop: 8 }}>{desc}</div>
    </Panel>
  );
};

export const ArchitectureScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const [l1, l2, l3] = scene.lines.map((l) => l.from);
  const total = Math.round(interpolate(frame, [l3, l3 + 12 * 7 + 18], [0, 88], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill>
      <Heading kicker="Architecture" title="One MCP server between the agent and FEMM" />
      <div style={{ position: "absolute", left: 120, right: 120, top: 270, height: 150 }}>
        <Box x={0} w={440} delay={l1} title="MCP client" sub="Claude Code, or any agent" />
        <Arrow x1={440} x2={690} delay={l1 + 20} label="stdio · JSON" />
        <Box x={690} w={440} delay={l1 + 30} title="femm server" sub="femm_agent · validated tools" accent />
        <Arrow x1={1130} x2={1240} delay={l2 + 10} label="TCP" />
        <Box x={1240} w={440} delay={l2 + 25} title="femm_headless" sub="FEMM 5 engine, one per session" />
      </div>
      <div style={{ position: "absolute", left: 120, top: 466, fontFamily: SANS, fontSize: 30, color: C.muted, opacity: useSpring(l3) }}>
        <span style={{ fontFamily: MONO, color: C.accent, fontSize: 40, fontWeight: 700 }}>{total}</span> tools in 12 groups
      </div>
      <div style={{ position: "absolute", left: 120, right: 120, top: 530, display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 20 }}>
        {GROUPS.map(([name, n, desc], i) => (
          <GroupCard key={name} name={name} n={n} desc={desc} delay={l3 + i * 7} />
        ))}
      </div>
    </AbsoluteFill>
  );
};
