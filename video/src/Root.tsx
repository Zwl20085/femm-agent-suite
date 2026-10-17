import React from "react";
import { Composition } from "remotion";
import { Main } from "./Main";
import { FPS, TOTAL_FRAMES } from "./audioConfig";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="FemmAgentSuiteIntro"
    component={Main}
    durationInFrames={TOTAL_FRAMES}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
