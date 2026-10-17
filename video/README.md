# FEMM Agent Suite intro video

Remotion source for the introduction video (1920x1080, 30 fps, about 109 s, English narration
with burned-in captions). The rendered, compressed copy lives at
`docs/video/femm-agent-suite-intro.mp4`, with a 10 s GIF teaser at `docs/video/teaser.gif`.

## Layout

```
video/
  scripts/narration.json          narration lines per scene (spoken text and optional caption text)
  scripts/generate_audio_edge.py  Edge TTS -> public/audio/*.mp3, writes src/audioConfig.ts
  src/audioConfig.ts              generated: scene lengths and line timings (the single source of timing)
  src/Main.tsx                    scene sequencing, audio, captions, progress bar
  src/theme.tsx                   colours (dark + one amber accent), fonts, spring helpers
  src/scenes/*.tsx                one component per scene
  public/                         narration audio and the two result images from docs/images
```

Scenes: title, the problem, architecture (12 tool groups), an agent at work (SPM demo log),
validation table, the 11 skills, install, closing. Every number on screen comes from
`docs/femm5-facts.md` (live runs on FEMM 5 build 06oct2026).

## Re-render

Needs Node 18+ and ffmpeg on PATH. Fonts (Inter, JetBrains Mono) are fetched from Google Fonts at
render time.

```powershell
cd video
npm install
npm run dev                     # Remotion Studio preview
npx remotion render src/index.ts FemmAgentSuiteIntro out/femm-agent-suite-intro.mp4
```

### Changing the narration

Edit `scripts/narration.json`, then regenerate the audio and the timings (from the repo root):

```powershell
.venv\Scripts\pip install edge-tts
.venv\Scripts\python video\scripts\generate_audio_edge.py --force   # voice en-GB-RyanNeural
```

Without network access to Edge TTS, `--captions-only` writes estimated timings and the video
renders with captions and no audio. Scene animations key off the line start frames in
`audioConfig.ts`, so they stay in sync after a regeneration.

### Repo copies

```powershell
ffmpeg -i video/out/femm-agent-suite-intro.mp4 -c:v libx264 -preset slow -crf 28 -pix_fmt yuv420p `
  -tune stillimage -c:a aac -b:a 96k -movflags +faststart docs/video/femm-agent-suite-intro.mp4
ffmpeg -ss 48 -t 10 -i video/out/femm-agent-suite-intro.mp4 -vf "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" docs/video/teaser.gif
```
