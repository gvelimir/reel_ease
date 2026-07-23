# reel_ease

Build a vertical (9:16) highlight reel from a set of source videos, with
on-screen captions and a music track pulled from a YouTube URL.

## Pipeline

1. **Scene detection** — [PySceneDetect] finds candidate segments in each input
   video (falls back to fixed chunks for single-shot clips).
2. **Highlight selection** — one frame per scene is sent to an OpenAI vision
   model, which ranks scenes and writes a short highlight summary. Without a
   key (or with `--no-ai`) it falls back to a deterministic longest-first pick.
3. **Compose** — chosen scenes are cropped to 9:16 and concatenated.
4. **Captions** — the exact lines from your text file are overlaid, one per
   equal time slice, bottom-centered. Two backends (see below).
5. **Music** — the YouTube track is downloaded (yt-dlp), trimmed/looped to
   length, faded out, and laid under the reel.

## Caption backends

`--caption-backend` picks how captions are drawn:

- **`ffmpeg`** (default, fast) — text is rasterized once and burned in with a
  native ffmpeg pass. Uses the `drawtext` filter when the ffmpeg build has it,
  otherwise renders each caption to a PNG (Pillow) and composites it with the
  always-available `overlay` filter. The bundled imageio-ffmpeg binary lacks
  `drawtext`, so the PNG/overlay path is used there — and it renders Unicode
  (e.g. Cyrillic) correctly via the DejaVu font.
- **`moviepy`** — per-frame `TextClip` compositing. No second encode, but much
  slower on long reels.

## Requirements

- Python 3.9+
- **ffmpeg** on your `PATH` (used by moviepy and yt-dlp) — not bundled.
  - Debian/Ubuntu: `sudo apt-get install ffmpeg`
- Python deps: `pip install -r requirements.txt`
- `OPENAI_API_KEY` in your environment for AI ranking.

## Usage

```bash
export OPENAI_API_KEY=sk-...

python make_reel.py \
  --videos clip1.mp4 clip2.mp4 clip3.mov \
  --captions captions.txt \
  --music-url "https://www.youtube.com/watch?v=..." \
  --duration 30 \
  --output my_reel.mp4
```

`captions.txt` is one caption line per row, e.g.:

```
Summer 2026
Best moments
See you next time
```

### Useful flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--duration` | `30` | Target reel length (seconds). |
| `--max-clip` | `4` | Max seconds kept per scene. |
| `--scene-threshold` | `27` | Lower = more scene cuts detected. |
| `--no-ai` | off | Skip OpenAI; use the heuristic selector. |
| `--openai-model` | `gpt-4o` | Vision model (or set `OPENAI_VISION_MODEL`). |
| `--keep-original-audio` | off | Mix source audio under the music. |
| `--font` | auto | Path to a `.ttf` for captions. |
| `--caption-backend` | `ffmpeg` | `ffmpeg` (fast burn-in) or `moviepy`. |
| `--music-file` | — | Local audio soundtrack (skips YouTube download). |
| `--music-start` | URL `t=` | Seconds into the track to start. |
| `--cookies` | — | `cookies.txt` for YouTube auth. |
| `--cookies-from-browser` | — | Read YouTube cookies from `firefox`/`chrome`. |
| `--scene-frame-skip` | `2` | Sample every (skip+1)th frame in detection. |
| `--scene-downscale` | auto | Downscale factor before detection. |
| `--scene-workers` | auto | Parallel detection processes (one per video). |
| `--preset` | `veryfast` | x264 encode preset (speed vs file size). |

## Performance

The pipeline has three timed stages, all tunable:

- **Scene detection** runs one process per input video and samples frames via
  `--scene-frame-skip` (higher = faster, slightly looser scene boundaries).
- **Assembly** and **caption burn-in** are ffmpeg x264 encodes; `--preset`
  trades encode speed for file size (`ultrafast`…`veryslow`).
- Adding music (`--music-file`/`--music-url`) muxes with `-c:v copy`, so it adds
  no video re-encode.

## Music sources

- `--music-url` downloads the track with yt-dlp. The start offset is taken from
  the URL's `t=` parameter automatically (or override with `--music-start`).
- `--music-file path.mp3` uses a local audio file instead — the reliable option
  when YouTube blocks the download.

**If the YouTube download fails** with *"Sign in to confirm you're not a bot"*
or `HTTP 403 Forbidden`: YouTube throttles anonymous/server downloads and now
often requires a PO token. Pass browser cookies (`--cookies-from-browser
chrome`) — and if media fragments still 403 (IP flagged), download the track
once through your browser and use `--music-file` with `--music-start`.

## Note on YouTube

Downloading audio from YouTube is subject to YouTube's Terms of Service. Only
use tracks you have the right to use.

[PySceneDetect]: https://www.scenedetect.com/
