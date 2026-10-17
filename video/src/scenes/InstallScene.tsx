import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C, Cursor, Heading, MONO, Panel, SANS, Terminal, useSpring, useTyped } from "../theme";
import type { SceneConfig } from "../audioConfig";

const Cmd: React.FC<{ os: string; prompt: string; cmd: string; delay: number; top: number }> = ({ os, prompt, cmd, delay, top }) => {
  const frame = useCurrentFrame();
  const p = useSpring(delay);
  const typed = useTyped(cmd, delay + 8, 45);
  return (
    <Terminal title={os} style={{ position: "absolute", left: 120, top, width: 1000, opacity: p, transform: `translateX(${(1 - p) * -40}px)` }}>
      <div style={{ fontFamily: MONO, fontSize: 28, color: C.text, whiteSpace: "nowrap" }}>
        <span style={{ color: C.dim }}>{prompt} </span>
        {typed}
        {frame >= delay && typed.length < cmd.length ? <Cursor /> : null}
      </div>
    </Terminal>
  );
};

export const InstallScene: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const [l1, l2] = scene.lines.map((l) => l.from);
  const ask = useSpring(l2);
  const answer = useSpring(l2 + 55);
  const askText = useTyped("run the FEMM self-test", l2 + 6, 30);
  return (
    <AbsoluteFill>
      <Heading kicker="Install" title="One script, or one plugin command" />
      <Cmd os="Windows · PowerShell" prompt="PS>" cmd=".\scripts\install.ps1" delay={l1} top={250} />
      <Cmd os="macOS · Linux" prompt="$" cmd="./scripts/install.sh" delay={l1 + 15} top={450} />
      <Cmd os="Claude Code" prompt=">" cmd="/plugin marketplace add Zwl20085/femm-agent-suite" delay={l1 + 30} top={650} />
      <div style={{ position: "absolute", left: 1180, top: 250, width: 620 }}>
        <div style={{ fontFamily: MONO, fontSize: 22, letterSpacing: 3, color: C.accent, opacity: ask }}>THEN JUST ASK</div>
        <Panel style={{ marginTop: 18, padding: "24px 28px", opacity: ask, transform: `translateY(${(1 - ask) * 20}px)` }}>
          <div style={{ fontFamily: MONO, fontSize: 20, color: C.muted }}>you</div>
          <div style={{ fontFamily: SANS, fontSize: 38, color: C.text, fontWeight: 600, marginTop: 6 }}>{askText}</div>
        </Panel>
        <Panel accent style={{ marginTop: 22, padding: "24px 28px", opacity: answer, transform: `translateY(${(1 - answer) * 20}px)` }}>
          <div style={{ fontFamily: MONO, fontSize: 20, color: C.muted }}>femm_selftest</div>
          <div style={{ fontFamily: MONO, fontSize: 25, color: C.text, marginTop: 10, lineHeight: 1.6 }}>
            <div>
              <span style={{ color: C.accent, fontWeight: 700 }}>PASS</span> FEMM 5 found, engine up
            </div>
            <div>solenoid B 6.179 mT</div>
            <div>analytic   6.136 mT <span style={{ color: C.accent }}>(0.7 %)</span></div>
          </div>
        </Panel>
      </div>
    </AbsoluteFill>
  );
};
