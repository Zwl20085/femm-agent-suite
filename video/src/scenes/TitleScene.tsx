import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SANS, useSpring } from "../theme";
import type { SceneConfig } from "../audioConfig";

/** Dipole-like field lines drawn with SVG; they "draw on" and then flow. */
const FieldLines: React.FC = () => {
  const frame = useCurrentFrame();
  const cx = 960;
  const cy = 470;
  const loops = [90, 150, 220, 300, 390, 490];
  return (
    <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
      {loops.map((r, i) => {
        const draw = interpolate(frame, [i * 4, i * 4 + 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const len = 2 * Math.PI * Math.sqrt((r * r + (r * 0.5) ** 2) / 2);
        const flow = -frame * 1.2;
        return (
          <g key={r} opacity={0.12 + 0.05 * (loops.length - i)}>
            {[-1, 1].map((side) => (
              <ellipse
                key={side}
                cx={cx + side * r}
                cy={cy}
                rx={r}
                ry={r * 0.5}
                fill="none"
                stroke={i === 1 ? C.accent : C.muted}
                strokeWidth={i === 1 ? 2.2 : 1.4}
                strokeDasharray={draw >= 1 ? "14 10" : `${len * draw} ${len}`}
                strokeDashoffset={draw >= 1 ? flow * side : 0}
              />
            ))}
          </g>
        );
      })}
    </svg>
  );
};

const Chip: React.FC<{ label: string; delay: number; accent?: boolean }> = ({ label, delay, accent }) => {
  const p = useSpring(delay);
  return (
    <div
      style={{
        fontFamily: MONO,
        fontSize: 26,
        padding: "10px 22px",
        borderRadius: 999,
        border: `1.5px solid ${accent ? C.accent : C.border}`,
        color: accent ? C.accent : C.text,
        background: C.panel,
        opacity: p,
        transform: `translateY(${(1 - p) * 20}px)`,
      }}
    >
      {label}
    </div>
  );
};

export const TitleScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const t = useSpring(6, 14);
  const l2 = scene.lines[1]?.from ?? 60;
  const tag = useSpring(l2);
  const chips = ["MCP server", "88 tools", "11 skills", "4 physics", "FEMM 5"];
  return (
    <AbsoluteFill>
      <FieldLines />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingBottom: 120 }}>
        <div style={{ fontFamily: MONO, fontSize: 26, letterSpacing: 6, color: C.accent, opacity: t }}>
          FINITE ELEMENT MAGNETICS, FOR AGENTS
        </div>
        <div
          style={{
            fontFamily: SANS,
            fontWeight: 800,
            fontSize: 150,
            letterSpacing: -4,
            color: C.text,
            marginTop: 18,
            transform: `scale(${0.85 + 0.15 * t})`,
            opacity: Math.min(1, t * 1.5),
            textShadow: "0 8px 60px rgba(0,0,0,0.8)",
          }}
        >
          FEMM Agent Suite
        </div>
        <div style={{ fontFamily: SANS, fontSize: 44, color: C.muted, marginTop: 18, opacity: tag, transform: `translateY(${(1 - tag) * 20}px)` }}>
          AI agents that drive FEMM 5, <span style={{ color: C.text }}>and prove the answers are right.</span>
        </div>
        <div style={{ display: "flex", gap: 18, marginTop: 50 }}>
          {chips.map((c, i) => (
            <Chip key={c} label={c} delay={l2 + 20 + i * 5} accent={i === 4} />
          ))}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
