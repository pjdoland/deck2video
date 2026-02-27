# Troubleshooting

## "marp-cli not found" / "Neither `npx` nor `marp` found"

The Marp renderer needs either `marp` (globally installed marp-cli) or `npx` (Node.js package runner) on your PATH.

**Fix:**

```bash
# Install marp-cli globally
npm install -g @marp-team/marp-cli

# Or just ensure Node.js/npm is installed (npx comes with npm)
brew install node        # macOS
sudo apt install nodejs npm   # Ubuntu/Debian
```

## "slidev not found" / "Neither `slidev` nor `npx` found"

Same as above, but for Slidev presentations.

**Fix:**

```bash
npm install -g @slidev/cli
npm install -g playwright-chromium   # npm package Slidev imports at runtime
npx playwright install chromium      # Downloads the Chromium browser binary
```

Both `playwright-chromium` steps are required. `npm install -g playwright-chromium` installs the Node package that Slidev imports; `npx playwright install chromium` downloads the actual browser binary used to render slides. Missing either one causes export to fail.

## "The exporting for Slidev is powered by Playwright, please install it via `npm i -D playwright-chromium`"

Slidev can't find the `playwright-chromium` npm package. Because Slidev is installed globally, the package must also be installed globally (not locally with `-D`).

**Fix:**

```bash
npm install -g playwright-chromium
npx playwright install chromium
```

After installing, re-run `setup.sh` and it will verify the installation is complete.

## "ffmpeg not found" / "ffprobe not found"

The assembler needs both `ffmpeg` and `ffprobe` on your PATH. They're usually installed together.

**Fix:**

```bash
brew install ffmpeg       # macOS
sudo apt install ffmpeg   # Ubuntu/Debian
```

On Windows, download from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin/` directory to your PATH.

## Slide count mismatch

```
Error: parsed 5 slides but marp-cli produced 3 images.
```

This means the parser found a different number of slides than the renderer produced. Common causes:

1. **Slidev per-slide frontmatter.** In Slidev, a slide with layout options uses a two-`---` block: `---\nlayout: section\n---`. The parser treats this as one separator. If you see a count mismatch where the parser finds more slides than Slidev exports, check for per-slide frontmatter blocks that aren't being collapsed correctly.

2. **Extra `---` delimiters.** A `---` inside a code block or at an unexpected position can create phantom slides during parsing. Check your markdown for stray horizontal rules.

3. **Frontmatter issues.** If the frontmatter block isn't properly closed with `---`, the parser may miscount.

4. **Renderer behavior differences.** Marp-cli and Slidev may handle edge cases (empty slides, trailing delimiters) differently from the parser.

**Fix:** Inspect your markdown for stray `---` lines. Use `--keep-temp` to see the rendered images and compare with your expected slide count.

## TTS quality issues

### Speech sounds robotic or unnatural

- Increase `--exaggeration` (try 0.6-0.7).
- Increase `--temperature` (try 0.9-1.0).
- Provide a better voice reference WAV (clearer audio, longer sample).

### Speech is inconsistent between sentences

- Lower `--temperature` (try 0.5-0.6).
- Lower `--exaggeration` (try 0.3-0.4).

### Technical terms are mispronounced

- Use `--pronunciations` with a JSON mapping file.
- See [Voice and TTS: pronunciation overrides](voice-and-tts.md#pronunciation-overrides).

### Abbreviations cause sentence splitting errors

"e.g.", "i.e.", "Dr.", "vs." and similar abbreviations with periods cause the sentence splitter to break mid-phrase.

- Spell out abbreviations: "for example" instead of "e.g."
- See [Voice and TTS: known edge cases](voice-and-tts.md#known-edge-cases).

### A specific slide consistently sounds bad

- Use `--interactive` mode to regenerate individual slides during the initial run.
- Use `--redo-slides` to regenerate specific slides after a completed run (e.g., `--redo-slides 3,6 --temp-dir ./build`). See [Examples](examples.md#redo-bad-slides-without-re-running-the-full-pipeline).
- Rewrite the speaker notes to be simpler and more conversational.
- Break long notes into shorter sentences.

## GPU out-of-memory errors

```
Moved model to CPU due to GPU memory pressure
```

This is informational. deck2video automatically falls back to CPU, so processing continues but slower. If you're running other GPU-intensive tasks, close them first. You can also use `--device cpu` to skip the GPU entirely.

If the CPU retry also fails, the slide gets a silent WAV and the pipeline continues:

```
Slide 4: TTS failed on CPU (error details), substituting silence
```

## Debugging with `--keep-temp`

The `--keep-temp` flag preserves all intermediate files after a successful run:

```bash
python -m deck2video deck.md --keep-temp
```

On failure, intermediate files are always preserved (even without `--keep-temp`). The temp directory path is printed:

```
Error encountered. Temp files preserved at: /tmp/deck2video_abc123
```

## Temp directory contents

| File | Description |
|------|-------------|
| `deck2video.log` | Detailed debug log of the entire pipeline run |
| `slides.001` | Rendered PNG for slide 1 (Marp, no extension) |
| `slides/1.png` | Rendered PNG for slide 1 (Slidev — exported to a subdirectory) |
| `audio_001.wav` | TTS audio for slide 1 |
| `audio_002.wav` | TTS audio for slide 2 (or silence) |
| `segment_001.ts` | Encoded MPEG-TS video segment for slide 1 |
| `segment_002.ts` | Encoded MPEG-TS video segment for slide 2 |
| `concat.txt` | ffmpeg concat demuxer input listing all segments |

### File naming conventions

- All indices are zero-padded to 3 digits: `001`, `002`, ..., `999`.
- Slide numbering starts at 1 (matching the slide index in output messages).
- Audio files: `audio_{index}.wav`
- Image files: `slides.{index}` (Marp) or `slides/{index}.png` (Slidev — in a subdirectory, not zero-padded)
- Segments: `segment_{index}.ts`

### Inspecting the log file

The log file (`deck2video.log`) contains DEBUG-level output for the entire run:

```bash
cat /tmp/deck2video_abc123/deck2video.log
```

It includes:

- CLI arguments
- Parse results (slide count, notes length, video paths)
- Exact ffmpeg/marp-cli/slidev commands and their output
- Timing for each pipeline step
- TTS details (sentence counts, chunk counts, device info)
- Any errors with full tracebacks

### Playing individual audio files

You can listen to individual slide audio files to identify problems:

```bash
# macOS
afplay /tmp/deck2video_abc123/audio_003.wav

# Linux
aplay /tmp/deck2video_abc123/audio_003.wav
```

## Custom temp directory

Use `--temp-dir` to control where intermediate files are written:

```bash
python -m deck2video deck.md --temp-dir ./build
```

When using a custom temp directory:

- The directory is created if it doesn't exist.
- Files are **never** automatically cleaned up (even without `--keep-temp`), since you've explicitly chosen the location.
- Multiple runs to the same directory will overwrite existing files.

## setup.sh Errors

### "This script must be sourced, not executed"

```bash
# Wrong:
./setup.sh
bash setup.sh

# Correct:
source setup.sh
```

The script must be sourced because it activates a virtual environment in your current shell.

### "python3.11 not found"

The setup script specifically requires Python 3.11. Install it:

```bash
brew install python@3.11   # macOS
sudo apt install python3.11 python3.11-venv   # Ubuntu/Debian
```

### Broken venv

If the virtual environment gets corrupted, setup.sh detects and recreates it:

```
  Existing venv is broken — removing...
  ✓ Created .venv
```

If this keeps happening, manually delete `.venv/` and run `source setup.sh` again.
