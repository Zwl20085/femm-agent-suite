import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, SANS, useSceneFade } from "./theme";
import { HAS_AUDIO, SCENES, TOTAL_FRAMES, getSceneStart, type SceneConfig } from "./audioConfig";
import { TitleScene } from "./scenes/TitleScene";
import { ProblemScene } from "./scenes/ProblemScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { DemoScene } from "./scenes/DemoScene";
import { ValidationScene } from "./scenes/ValidationScene";
import { SkillsScene } from "./scenes/SkillsScene";
import { InstallScene } from "./scenes/InstallScene";
import { ClosingScene } from "./scenes/ClosingScene";

const COMPONENTS: Record<string, React.FC<{ scene: SceneConfig }>> = {
  title: TitleScene,
  problem: ProblemScene,
  architecture: ArchitectureScene,
  demo: DemoScene,
  validation: ValidationScene,
  skills: SkillsScene,
  install: InstallScene,
  closing: ClosingScene,
};

/** Faint grid that drifts slowly; the only background decoration. */
const Backdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const shift = (frame * 0.25) % 80;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 70% 20%, #121a28 0%, ${C.bg} 60%)`,
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.border}33 1px, transparent 1px), linear-gradient(90deg, ${C.border}33 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
          backgroundPosition: `${shift}px ${shift}px`,
        }}
      />
    </AbsoluteFill>
  );
};

/** Caption band synced to each narration line. */
const Captions: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const line = scene.lines.find((l) => frame >= l.from && frame < l.from + l.frames + 8);
  if (!line) return null;
  const o = interpolate(frame, [line.from, line.from + 6, line.from + line.frames + 2, line.from + line.frames + 8], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 34, display: "flex", justifyContent: "center", opacity: o }}>
      <div
        style={{
          maxWidth: 1500,
          padding: "10px 26px",
          borderRadius: 12,
          background: "rgba(5,8,12,0.82)",
          border: `1px solid ${C.border}`,
          color: C.text,
          fontFamily: SANS,
          fontSize: 31,
          lineHeight: 1.3,
          textAlign: "center",
        }}
      >
        {line.text}
      </div>
    </div>
  );
};

const SceneFrame: React.FC<{ scene: SceneConfig }> = ({ scene }) => {
  const Comp = COMPONENTS[scene.id];
  const fade = useSceneFade(scene.durationInFrames);
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <Comp scene={scene} />
      <Captions scene={scene} />
    </AbsoluteFill>
  );
};

const Progress: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 0, bottom: 0, height: 5, width: `${(frame / TOTAL_FRAMES) * 100}%`, background: C.accent, opacity: 0.85 }} />
  );
};

export const Main: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg }}>
    <Backdrop />
    {SCENES.map((scene, i) => (
      <Sequence key={scene.id} from={getSceneStart(i)} durationInFrames={scene.durationInFrames} name={scene.title}>
        <SceneFrame scene={scene} />
        {HAS_AUDIO &&
          scene.lines.map((l) => (
            <Sequence key={l.file} from={l.from} durationInFrames={l.frames} name={l.file}>
              <Audio src={staticFile(`audio/${l.file}`)} />
            </Sequence>
          ))}
      </Sequence>
    ))}
    <Progress />
  </AbsoluteFill>
);
