import React from "react";
import { AbsoluteFill } from "remotion";
import { C, MONO, SANS, useSpring } from "../theme";
import type { SceneConfig } from "../audioConfig";

export const ClosingScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const l2 = scene.lines[1]?.from ?? 90;
  const t = useSpring(4, 14);
  const url = useSpring(18);
  const credit = useSpring(l2);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingBottom: 100 }}>
      <div style={{ fontFamily: SANS, fontSize: 110, fontWeight: 800, letterSpacing: -3, color: C.text, opacity: t, transform: `scale(${0.9 + 0.1 * t})` }}>
        FEMM Agent Suite
      </div>
      <div
        style={{
          marginTop: 34,
          fontFamily: MONO,
          fontSize: 44,
          color: C.accent,
          padding: "16px 34px",
          borderRadius: 14,
          border: `1.5px solid ${C.accent}`,
          background: C.accentSoft,
          opacity: url,
          transform: `translateY(${(1 - url) * 20}px)`,
        }}
      >
        github.com/Zwl20085/femm-agent-suite
      </div>
      <div style={{ marginTop: 30, fontFamily: SANS, fontSize: 28, color: C.muted, opacity: url }}>MIT licensed · MCP server + Claude skills</div>
      <div style={{ marginTop: 70, fontFamily: SANS, fontSize: 34, color: C.text, opacity: credit, transform: `translateY(${(1 - credit) * 16}px)` }}>
        FEMM 5 by David Meeker · <span style={{ fontFamily: MONO, color: C.accent }}>femm.info</span>
      </div>
    </AbsoluteFill>
  );
};
