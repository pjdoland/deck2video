# Getting started

## System requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11 | Runtime |
| Node.js / npm | Any recent LTS | Required for marp-cli (via npx) |
| ffmpeg + ffprobe | Any recent | Video encoding and media inspection |

For Slidev presentations (optional):

| Dependency | Purpose |
|------------|---------|
| @slidev/cli | Renders Slidev decks to PNG |
| playwright-chromium | Browser engine used by Slidev for export |

### macOS

```bash
brew install python@3.11 node ffmpeg
```

### Linux (Ubuntu/Debian)

```bash
sudo apt install python3.11 python3.11-venv nodejs npm ffmpeg
```

### Slidev support (optional)

Slidev PNG export requires two separate Playwright components — both must be installed:

```bash
# 1. Slidev CLI
npm install -g @slidev/cli

# 2. playwright-chromium npm package (Slidev imports this at runtime)
npm install -g playwright-chromium

# 3. Chromium browser binary (downloaded separately by Playwright)
npx playwright install chromium
```

`setup.sh` handles all three steps automatically when you answer yes to Slidev support.

## Running setup.sh

`setup.sh` checks for system dependencies, creates a Python 3.11 virtual environment, installs packages, and activates the venv in your current shell. It also asks whether you want to install Slidev support (the Slidev CLI and Playwright Chromium).

You must source the script, not execute it:

```bash
# Correct:
source setup.sh

# Wrong (will error):
./setup.sh
bash setup.sh
```

Why? The script activates a virtual environment as its final step. A child process can't modify the parent shell's environment, so `source` is required to run it in your current shell.

What the script does:

1. Checks that `python3.11`, `ffmpeg`, `ffprobe`, and `npx` (or `marp`) are on PATH.
2. Asks if you want Slidev support (skipped if `slidev` is already installed).
3. Creates `.venv/` if it doesn't exist (or recreates it if the existing one is broken).
4. Installs/upgrades pip and all packages from `requirements.txt`.
5. If you said yes to Slidev: installs `@slidev/cli`, the `playwright-chromium` npm package, and the Chromium browser binary.
6. Activates the virtual environment.

After setup completes, you can run deck2video directly:

```bash
python -m deck2video presentation.md --voice voice-sample.wav
```

## First run

### 1. Create a minimal slide deck

Save this as `demo.md`:

```markdown
---
marp: true
---

# Hello, World

<!-- Welcome to this demo presentation. -->

---

# Slide Two

<!-- This is the second slide with some narration. -->

---

# The End
```

The third slide has no speaker notes, so it will be held as a silent still image (3 seconds by default).

### 2. Run deck2video

Without voice cloning (uses the default Chatterbox voice):

```bash
python -m deck2video demo.md
```

With voice cloning:

```bash
python -m deck2video demo.md --voice my-voice.wav
```

You'll see output like:

```
  Format: marp
[1/4] Parsing slides...
  Found 3 slides
[2/4] Rendering slide images...
  Running: npx @marp-team/marp-cli demo.md --images png --image-scale 2 --no-stdin --output /tmp/deck2video_.../slides
[3/4] Generating audio...
  Using MPS (Apple Silicon) for TTS
  Slide 1: TTS OK (1 sentence in 1 chunk)
  Slide 2: TTS OK (1 sentence in 1 chunk)
  Slide 3: silent (3.0s)
[4/4] Assembling video...
  Encoding segment 1/3...
  Encoding segment 2/3...
  Encoding segment 3/3...
  Concatenating 3 segments...
  Output: demo.mp4 (1.2 MB)

Done! 3 slides processed (2 narrated, 1 silent).
Output: demo.mp4
```

### 3. Verify the output

Play `demo.mp4` with any video player. You should see each slide rendered at 1920x1080, slides 1 and 2 narrated with synthesized speech, and slide 3 displayed silently for 3 seconds.

## Next steps

- [Writing slides](writing-slides.md) for Marp and Slidev
- [Voice and TTS](voice-and-tts.md) for voice cloning and tuning
- [CLI reference](cli-reference.md) for every command-line flag
