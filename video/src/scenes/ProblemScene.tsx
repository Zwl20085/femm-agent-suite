import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, Heading, MONO, Panel, SANS, useSpring, useTyped } from "../theme";
import type { SceneConfig } from "../audioConfig";

const Column: React.FC<{ delay: number; step: string; title: string; accent?: boolean; children: React.ReactNode }> = ({
  delay,
  step,
  title,
  accent,
  children,
}) => {
  const p = useSpring(delay);
  return (
    <Panel
      accent={accent}
      style={{ width: 530, height: 580, padding: 36, opacity: p, transform: `translateY(${(1 - p) * 40}px)`, display: "flex", flexDirection: "column" }}
    >
      <div style={{ fontFamily: MONO, fontSize: 22, color: accent ? C.accent : C.muted, letterSpacing: 3 }}>{step}</div>
      <div style={{ fontFamily: SANS, fontSize: 38, fontWeight: 700, color: C.text, marginTop: 10, lineHeight: 1.15 }}>{title}</div>
      <div style={{ marginTop: 30, flex: 1 }}>{children}</div>
    </Panel>
  );
};

/** A schematic GUI window with a mouse pointer clicking toolbar buttons. */
const ClickyGui: React.FC<{ start: number }> = ({ start }) => {
  const frame = useCurrentFrame();
  const t = Math.max(0, frame - start);
  const target = Math.floor(t / 22) % 4;
  const x = 18 + target * 94;
  const press = t % 22 < 6;
  return (
    <div style={{ position: "relative", height: 340, borderRadius: 12, border: `1px solid ${C.border}`, background: C.bg2, overflow: "hidden" }}>
      <div style={{ display: "flex", gap: 14, padding: 18, borderBottom: `1px solid ${C.border}` }}>
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            style={{ width: 80, height: 40, borderRadius: 8, background: i === target && press ? C.border : C.panel2, border: `1px solid ${C.border}` }}
          />
        ))}
      </div>
      <svg width={456} height={250} style={{ position: "absolute", left: 0, top: 80 }}>
        <rect x={78} y={40} width={300} height={160} fill="none" stroke={C.dim} strokeWidth={2} strokeDasharray="8 8" />
        <circle cx={228} cy={120} r={48} fill="none" stroke={C.dim} strokeWidth={2} />
        <text x={228} y={232} fill={C.dim} fontFamily={MONO} fontSize={18} textAnchor="middle">
          click, drag, click, repeat
        </text>
      </svg>
      <svg width={40} height={50} style={{ position: "absolute", left: x + 44, top: 36 + (press ? 3 : 0) }}>
        <path d="M2 2 L2 38 L12 28 L19 44 L26 41 L19 26 L33 26 Z" fill={C.text} stroke={C.bg} strokeWidth={2} />
      </svg>
    </div>
  );
};

const Check: React.FC<{ delay: number; text: string }> = ({ delay, text }) => {
  const p = useSpring(delay);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 28, opacity: p, transform: `translateX(${(1 - p) * 20}px)` }}>
      <svg width={34} height={34} style={{ flexShrink: 0 }}>
        <rect x={1} y={1} width={32} height={32} rx={8} fill={C.accentSoft} stroke={C.accent} strokeWidth={2} />
        <path
          d="M9 17 L15 23 L25 11"
          fill="none"
          stroke={C.accent}
          strokeWidth={3.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={30}
          strokeDashoffset={30 * (1 - p)}
        />
      </svg>
      <div style={{ fontFamily: SANS, fontSize: 30, color: C.text }}>{text}</div>
    </div>
  );
};

export const ProblemScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const [l1, l2, l3] = scene.lines.map((l) => l.from);
  const code = useTyped("mi_addnode(0, 0)\nmi_analyze()\nmo_getb(10, 0)", l2 + 30, 26);
  const reply = interpolate(frame, [l2 + 110, l2 + 125], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Heading kicker="The problem" title="Simulation tools were built for clicks" />
      <div style={{ position: "absolute", top: 268, left: 120, right: 120, display: "flex", justifyContent: "space-between" }}>
        <Column delay={l1} step="BEFORE" title="FEA lives behind a GUI">
          <ClickyGui start={l1} />
        </Column>
        <Column delay={l2} step="FEMM 5 · OCT 2026" title="Headless, scriptable over TCP">
          <div style={{ fontFamily: MONO, fontSize: 22, color: C.muted, marginBottom: 14 }}>Windows · macOS · Linux</div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 25,
              lineHeight: 1.6,
              background: C.bg2,
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              padding: "18px 22px",
              height: 290,
              whiteSpace: "pre",
              color: C.text,
              boxSizing: "border-box",
            }}
          >
            <div style={{ color: C.dim }}>{"# TCP 127.0.0.1:48015"}</div>
            {code}
            <div style={{ color: C.accent, opacity: reply }}>{"-> 0.862\t0.003"}</div>
          </div>
        </Column>
        <Column delay={l3} step="WHAT AGENTS NEED" title="A validated layer on top" accent>
          <Check delay={l3 + 25} text="Catch mistakes, return hints" />
          <Check delay={l3 + 45} text="Check the physics" />
          <Check delay={l3 + 65} text="Compare with theory" />
          <Check delay={l3 + 85} text="Keep a replayable journal" />
        </Column>
      </div>
    </AbsoluteFill>
  );
};
