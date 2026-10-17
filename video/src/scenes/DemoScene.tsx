import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, Cursor, Heading, MONO, Panel, SANS, Terminal, useSpring, useTyped } from "../theme";
import type { SceneConfig } from "../audioConfig";

const PROMPT = "Build a 12-slot 4-pole SPM, run cogging and back-EMF, prove the torque.";

// Tool calls and the numbers they returned on FEMM 5 build 06oct2026 (docs/femm5-facts.md).
const LOG: [string, string][] = [
  ['femm_session_open(physics="magnetics")', "engine up in 0.55 s"],
  ['femm_build_benchmark(kind="spm")', "12 slots, 4 poles, A/B/C"],
  ['femm_material_search("NdFeB 42")', "N42, Br 1.312 T"],
  ["femm_solve()", "9.7k elements, 0.15 s"],
  ['femm_experiment_cogging(method="rotate")', "0.3824 N·m p-p"],
  ['femm_experiment_cogging(method="age")', "0.3835 N·m p-p (0.3 %)"],
  ["femm_experiment_backemf(pole_pairs=2)", "E1 9.973 V @ 1000 rpm"],
  ['femm_experiment_inductance(dq={...})', "Ld 0.427 mH, Lq 0.421 mH"],
  ["femm_experiment_torque_vs_angle(...)", "mean 1.415 N·m @ iq 10 A"],
  ["femm_health_check()", "PASS  dq formula 1.428 N·m"],
  ["femm_report()", "report.md written"],
];

const START = 95;
const STEP = 38;

const LogLine: React.FC<{ call: string; result: string; at: number; last: boolean }> = ({ call, result, at, last }) => {
  const frame = useCurrentFrame();
  const typed = useTyped(call, at, 70);
  if (frame < at) return null;
  const done = frame >= at + 16;
  const spin = "|/-\\"[Math.floor(frame / 3) % 4];
  const resP = interpolate(frame, [at + 16, at + 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const highlight = result.startsWith("PASS") || result.startsWith("mean");
  return (
    <div style={{ display: "flex", fontFamily: MONO, fontSize: 21, lineHeight: "36px", whiteSpace: "nowrap" }}>
      <span style={{ color: C.dim, width: 26 }}>{">"}</span>
      <span style={{ color: C.text, width: 560, overflow: "hidden" }}>
        {typed}
        {!done && last ? <Cursor /> : null}
      </span>
      <span style={{ color: done ? (highlight ? C.accent : C.muted) : C.dim, opacity: done ? resP : 1, fontWeight: highlight ? 700 : 400 }}>
        {done ? `ok  ${result}` : typed.length === call.length ? spin : ""}
      </span>
    </div>
  );
};

export const DemoScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const prompt = useTyped(PROMPT, 14, 48);
  const bubble = useSpring(8);
  const term = useSpring(START - 12);
  const img = useSpring(START + 3 * STEP + 10);
  const verdictAt = START + 9 * STEP + 20;
  const verdict = useSpring(verdictAt, 14);
  const active = Math.floor((frame - START) / STEP);
  return (
    <AbsoluteFill>
      <Heading kicker="An agent at work" title="From one prompt to a proven result" />
      <div style={{ position: "absolute", left: 120, right: 120, top: 222, opacity: bubble, transform: `translateY(${(1 - bubble) * 20}px)` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ fontFamily: MONO, fontSize: 22, color: C.bg, background: C.text, borderRadius: 8, padding: "6px 14px", fontWeight: 700 }}>you</div>
          <div style={{ fontFamily: SANS, fontSize: 36, color: C.text, fontWeight: 500 }}>
            {prompt}
            {prompt.length < PROMPT.length ? <Cursor /> : null}
          </div>
        </div>
      </div>
      <Terminal title="claude · femm MCP tools" style={{ position: "absolute", left: 120, top: 320, width: 1060, height: 500, opacity: term, boxSizing: "border-box" }}>
        {LOG.map(([call, result], i) => (
          <LogLine key={i} call={call} result={result} at={START + i * STEP} last={i === Math.min(active, LOG.length - 1)} />
        ))}
      </Terminal>
      <Panel style={{ position: "absolute", left: 1210, top: 320, width: 590, padding: 18, boxSizing: "border-box", opacity: img, transform: `scale(${0.94 + 0.06 * img})` }}>
        <Img src={staticFile("spm_field_B.png")} style={{ width: 554, borderRadius: 10, display: "block" }} />
        <div style={{ fontFamily: MONO, fontSize: 19, color: C.muted, marginTop: 10 }}>|B|, 12-slot / 4-pole SPM, FEMM 5</div>
      </Panel>
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 846,
          width: 1060,
          height: 78,
          borderRadius: 14,
          background: C.accentSoft,
          border: `1.5px solid ${C.accent}`,
          display: "flex",
          alignItems: "center",
          padding: "0 30px",
          boxSizing: "border-box",
          gap: 24,
          opacity: verdict,
          transform: `translateY(${(1 - verdict) * 20}px)`,
        }}
      >
        <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, color: C.bg, background: C.accent, borderRadius: 6, padding: "4px 12px" }}>PROVEN</div>
        <div style={{ fontFamily: SANS, fontSize: 28, whiteSpace: "nowrap", color: C.text }}>
          Torque <b>1.415 N·m</b> simulated, <b>1.428 N·m</b> by the dq formula
        </div>
      </div>
    </AbsoluteFill>
  );
};
