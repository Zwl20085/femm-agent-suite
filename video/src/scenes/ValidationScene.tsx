import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, Heading, MONO, Panel, SANS, useSpring } from "../theme";
import type { SceneConfig } from "../audioConfig";

type Row = { name: string; femm: string; ref: string; refNote: string; err: string };

// Every number is from a live run on FEMM 5 build 06oct2026 (docs/femm5-facts.md, tests -m live).
const ROWS: Row[] = [
  { name: "Solenoid self-test, centre B", femm: "6.179 mT", ref: "6.136 mT", refNote: "analytic", err: "0.7 %" },
  { name: "C-core gap flux density", femm: "0.238 T", ref: "0.2405 T", refNote: "analytic", err: "1.0 %" },
  { name: "SPM mean torque, iq 10 A", femm: "1.415 N·m", ref: "1.428 N·m", refNote: "dq formula", err: "0.9 %" },
  { name: "Cogging p-p, rotate vs AGE", femm: "0.3824 N·m", ref: "0.3835 N·m", refNote: "air-gap element", err: "0.3 %" },
  { name: "AC round wire R(f), to 10 kHz", femm: "R(f)", ref: "Bessel", refNote: "exact solution", err: "≤ 1.3 %" },
  { name: "AC power balance", femm: "½ Re(V I*)", ref: "losses", refNote: "block integral", err: "0.00 %" },
  { name: "Electrostatic, heat, current flow", femm: "3 cases", ref: "analytic", refNote: "benchmarks", err: "< 1 %" },
];

const COLS = [430, 200, 290, 170];

const Cell: React.FC<{ w: number; children: React.ReactNode; right?: boolean }> = ({ w, children, right }) => (
  <div style={{ width: w, paddingRight: right ? 24 : 0, textAlign: right ? "right" : "left", boxSizing: "border-box" }}>{children}</div>
);

const TableRow: React.FC<{ row: Row; delay: number; even: boolean }> = ({ row, delay, even }) => {
  const frame = useCurrentFrame();
  const p = useSpring(delay);
  const errP = interpolate(frame, [delay + 10, delay + 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        height: 70,
        paddingLeft: 26,
        background: even ? "rgba(255,255,255,0.025)" : "transparent",
        borderTop: `1px solid ${C.border}`,
        opacity: p,
        transform: `translateX(${(1 - p) * -40}px)`,
      }}
    >
      <Cell w={COLS[0]}>
        <span style={{ fontFamily: SANS, fontSize: 25, color: C.text }}>{row.name}</span>
      </Cell>
      <Cell w={COLS[1]}>
        <span style={{ fontFamily: MONO, fontSize: 24, color: C.text }}>{row.femm}</span>
      </Cell>
      <Cell w={COLS[2]}>
        <div style={{ fontFamily: MONO, fontSize: 24, color: C.text, lineHeight: 1.1 }}>{row.ref}</div>
        <div style={{ fontFamily: SANS, fontSize: 17, color: C.muted, marginTop: 3 }}>{row.refNote}</div>
      </Cell>
      <Cell w={COLS[3]} right>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, color: C.accent, opacity: errP }}>{row.err}</span>
      </Cell>
    </div>
  );
};

const Stat: React.FC<{ value: string; label: string; delay: number }> = ({ value, label, delay }) => {
  const p = useSpring(delay);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - p) * 16}px)` }}>
      <div style={{ fontFamily: MONO, fontSize: 34, fontWeight: 700, color: C.text }}>{value}</div>
      <div style={{ fontFamily: SANS, fontSize: 20, color: C.muted, marginTop: 2 }}>{label}</div>
    </div>
  );
};

export const ValidationScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const [l1, l2, l3] = scene.lines.map((l) => l.from);
  const head = useSpring(l1 + 10);
  const img = useSpring(l1 + 30);
  const delays = [l2, l2 + 16, l2 + 60, l2 + 110, l3, l3 + 30, l3 + 90];
  const statAt = l3 + 120;
  return (
    <AbsoluteFill>
      <Heading kicker="Validated" title="Every number checked against theory" />
      <Panel style={{ position: "absolute", left: 120, top: 240, width: 1116, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", height: 54, paddingLeft: 26, opacity: head, background: C.panel2 }}>
          {["Benchmark", "FEMM 5", "Reference", "Error"].map((h, i) => (
            <Cell key={h} w={COLS[i]} right={i === 3}>
              <span style={{ fontFamily: MONO, fontSize: 19, letterSpacing: 2, color: C.muted, textTransform: "uppercase" }}>{h}</span>
            </Cell>
          ))}
        </div>
        {ROWS.map((r, i) => (
          <TableRow key={r.name} row={r} delay={delays[i]} even={i % 2 === 0} />
        ))}
      </Panel>
      <Panel style={{ position: "absolute", left: 1270, top: 240, width: 530, padding: 16, boxSizing: "border-box", opacity: img, transform: `scale(${0.94 + 0.06 * img})` }}>
        <div style={{ background: "#ffffff", borderRadius: 8, overflow: "hidden" }}>
          <Img src={staticFile("ccore_force_vs_gap.png")} style={{ width: 498, display: "block" }} />
        </div>
        <div style={{ fontFamily: MONO, fontSize: 18, color: C.muted, marginTop: 10 }}>C-core force vs gap, FEMM 5 vs analytic</div>
      </Panel>
      <div style={{ position: "absolute", left: 1270, top: 640, width: 530, display: "grid", gridTemplateColumns: "1fr 1fr", rowGap: 26, columnGap: 20 }}>
        <Stat value="0.55 s" label="engine launch" delay={statAt} />
        <Stat value="0.13-0.25 s" label="10-15k-element solve" delay={statAt + 6} />
        <Stat value="677" label="catalogued commands" delay={statAt + 12} />
        <Stat value="771" label="materials, 4 libraries" delay={statAt + 18} />
      </div>
    </AbsoluteFill>
  );
};
