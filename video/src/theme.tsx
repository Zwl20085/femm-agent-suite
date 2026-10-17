import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

const inter = loadInter("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "500", "700"], subsets: ["latin"] });

export const C = {
  bg: "#0a0e14",
  bg2: "#0f1520",
  panel: "#131b28",
  panel2: "#18212f",
  border: "#243044",
  text: "#e6edf3",
  muted: "#8b98a9",
  dim: "#5b6778",
  accent: "#f5a524", // the one accent colour (amber)
  accentSoft: "rgba(245,165,36,0.14)",
};

export const SANS = inter.fontFamily;
export const MONO = mono.fontFamily;

/** Spring from 0 to 1 starting at `delay` frames. */
export const useSpring = (delay = 0, damping = 200, durationInFrames?: number): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping }, durationInFrames });
};

/** Fade + rise in at `delay`. */
export const Rise: React.FC<{ delay?: number; dy?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  delay = 0,
  dy = 28,
  children,
  style,
}) => {
  const p = useSpring(delay);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - p) * dy}px)`, ...style }}>{children}</div>
  );
};

/** Characters of `text` visible at the current frame when typing at `cps` chars/second from `start`. */
export const useTyped = (text: string, start: number, cps = 40): string => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.max(0, Math.floor(((frame - start) / fps) * cps));
  return text.slice(0, Math.min(n, text.length));
};

export const Cursor: React.FC<{ color?: string }> = ({ color = C.accent }) => {
  const frame = useCurrentFrame();
  const on = Math.floor(frame / 15) % 2 === 0;
  return <span style={{ display: "inline-block", width: "0.55em", height: "1.05em", marginLeft: 2, verticalAlign: "-0.15em", background: on ? color : "transparent" }} />;
};

/** Scene heading: small accent kicker + large title, top-left. */
export const Heading: React.FC<{ kicker: string; title: string }> = ({ kicker, title }) => {
  const p = useSpring(2);
  return (
    <div style={{ position: "absolute", left: 120, top: 84, opacity: p, transform: `translateX(${(1 - p) * -30}px)` }}>
      <div style={{ fontFamily: MONO, fontSize: 24, letterSpacing: 4, color: C.accent, textTransform: "uppercase" }}>{kicker}</div>
      <div style={{ fontFamily: SANS, fontSize: 60, fontWeight: 700, color: C.text, marginTop: 6, letterSpacing: -1 }}>{title}</div>
    </div>
  );
};

export const Panel: React.FC<{ style?: React.CSSProperties; children: React.ReactNode; accent?: boolean }> = ({ style, children, accent }) => (
  <div
    style={{
      background: C.panel,
      border: `1.5px solid ${accent ? C.accent : C.border}`,
      borderRadius: 18,
      boxShadow: accent ? `0 0 40px ${C.accentSoft}` : "0 10px 40px rgba(0,0,0,0.35)",
      ...style,
    }}
  >
    {children}
  </div>
);

/** Fade the whole scene in and out at its edges. */
export const useSceneFade = (duration: number): number => {
  const frame = useCurrentFrame();
  return interpolate(frame, [0, 12, duration - 12, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

/** Terminal window chrome. */
export const Terminal: React.FC<{ title: string; style?: React.CSSProperties; children: React.ReactNode }> = ({ title, style, children }) => (
  <Panel style={{ overflow: "hidden", ...style }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 20px", background: C.panel2, borderBottom: `1px solid ${C.border}` }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ width: 13, height: 13, borderRadius: 7, background: i === 0 ? C.accent : C.border }} />
      ))}
      <div style={{ fontFamily: MONO, fontSize: 19, color: C.muted, marginLeft: 12 }}>{title}</div>
    </div>
    <div style={{ padding: "18px 24px" }}>{children}</div>
  </Panel>
);
