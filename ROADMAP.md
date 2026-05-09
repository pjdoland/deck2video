# deck2video Roadmap

This roadmap was produced by a multi-persona review of the codebase. Seven personas (Backend / SRE / Product / Security / DX / ML-Audio / QA) independently produced 30 suggestions each (210 raw items), which were deduplicated to 147 unique candidates. Each persona then voted yay/nay on every candidate. The items below all received either 7/7 (unanimous) or 6/7 (one dissent) approval.

## Consensus Ranking Table

Legend: **B**ackend · **S**RE · **P**M · **Sec**urity · **D**X · **M**L · **Q**A. ✓ = yay, ✗ = nay.

| ID | Item | Score | B | S | P | Sec | D | M | Q |
|----|------|:-----:|:-:|:-:|:-:|:--:|:-:|:-:|:-:|
| **E08** | Pin dependencies in requirements.txt with hashes | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E10** | Add timeouts to every subprocess call | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E13** | Validate input markdown size + --max-slides guardrail | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E27** | Validate pronunciation JSON value types & cap size | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E28** | Sanity-cap padding/hold-duration/fps numeric args | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **F14** | `doctor` preflight subcommand | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **B05** | get_video_fps crashes on no-video-stream / 0-denom | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **B28** | Ctrl-C leaves orphan child processes (no SIGINT handler) | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **B37** | Model never moved off GPU after pipeline ends | **7/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E15** | Verify concat segments share pix_fmt/timebase before concat | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **E40** | Drop -shortest in favor of explicit -t at frame boundary | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **E46** | Per-slide deterministic seed for reproducible regens | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **F01** | --dry-run mode (parse + plan, no render/TTS) | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **F04** | Content-hash TTS cache (skip unchanged slides) | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **F08** | Pluggable TTS backend abstraction | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **F09** | Resume-from-failure via checkpoint status in steps.json | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **F11** | Dockerfile + container image | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **F15** | Output integrity .sha256 + manifest.json sidecar | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **F16** | Configurable retry policy with backoff | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **F28** | Disable Slidev remote asset fetches by default | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **F34** | `lint` subcommand (click-mismatch, long notes) | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B01** | Mutating slide.notes corrupts input on retry | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B08** | int() truncates 29.97 → 29 fps causing A/V drift | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B09** | Concat file unquoted relative names | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B10** | TTS-failure-to-silence loses degraded list from summary | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B12** | No disk-space check before render | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B13** | setup.sh leaks shell options when sourced | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B16** | --redo-slides slide-vs-step indexing confusing | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B17** | No integrity check between runs (stale audio + new images) | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B18** | Pronunciation overrides match substrings (no \b boundaries) | **6/7** | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **B21** | npx --yes for marp installs whatever registry serves | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B22** | npx @slidev/cli without --yes can hang on stdin | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B24** | open() calls without encoding= | **6/7** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **B31** | --reassemble silently ignores changed --voice | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B32** | _parse_slide_list dedupes silently / rejects ranges | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B34** | Interactive regens use same seed → near-identical retries | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B36** | adelay + -shortest can clip trailing pad | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B39** | get_audio_duration via ffprobe drifts vs sample-accurate | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **B40** | Concat -c copy + screencast mix can silently drift A/V | **6/7** | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ |

---

## 🟢 First Pass — Easiest to Implement (≤1 day each, mostly local changes)

### **E10 — Add timeouts to every subprocess call** (7/7)
Every `subprocess.run` in `marp_renderer.py:54`, `slidev_renderer.py:81`, `assembler.py:62/123/182`, `utils.py:74/97`, and `tts.py` runs without a `timeout=` kwarg. A hung Chromium (Slidev export), wedged ffmpeg, or stuck npx call pins the entire pipeline indefinitely. Add a sensible per-call timeout (e.g. 600s render, 120s ffmpeg, 30s ffprobe) wired through a single helper.
- **Difficulty**: Trivial · **Impact**: High (eliminates the most common silent-hang failure mode) · **Risks**: Tuning timeouts per stage; long renders for big decks may need a configurable override.

### **E27 — Validate pronunciation JSON value types & cap size** (7/7)
`tts.py:20-30` checks the top-level dict but not values, so non-string values raise late inside `re.escape`. Combined with no size cap, a 100k-entry file can hang regex compilation. Validate `dict[str, str]` upfront and reject files above e.g. 1000 entries / 100 KB total.
- **Difficulty**: Trivial · **Impact**: Medium (stops one class of opaque crashes) · **Risks**: None.

### **E28 — Sanity-cap padding / hold-duration / fps args** (7/7)
`--audio-padding`, `--hold-duration`, `--fps`, `--with-clicks-audio-padding` all accept arbitrary values with no validation. A fat-fingered `--hold-duration 1e9` allocates a multi-GB silent WAV; a negative `--audio-padding` makes `adelay` reject the filter. Add argparse `type=` validators with explicit ranges (e.g. padding 0-60000ms, hold 0-300s, fps 1-120).
- **Difficulty**: Trivial · **Impact**: Medium · **Risks**: Picking caps that are generous enough not to surprise legitimate users.

### **B05 — get_video_fps crashes on no-video-stream / 0-denom** (7/7)
`utils.py:87-92` indexes `info["streams"][0]` without checking, and parses `r_frame_rate` as `num/den` without guarding against `0/0`. An audio-only or malformed container raises `KeyError`/`IndexError`/`ZeroDivisionError`. Guard both and raise a typed `Deck2VideoError` with the offending file path.
- **Difficulty**: Trivial · **Impact**: Medium · **Risks**: None.

### **E08 — Pin dependencies in requirements.txt with hashes** (7/7)
`requirements.txt` lists four packages with no version pins. Reproducibility across rebuilds and CI is impossible; a compromised PyPI release of `chatterbox-tts` or `torch` lands silently. Switch to `pip-compile` or `uv lock` and commit the resulting hash-locked file. Same applies to the global npm installs in `setup.sh` (separately addressed by B21/B22).
- **Difficulty**: Easy · **Impact**: High (reproducibility + supply-chain hardening) · **Risks**: Need a refresh cadence so security patches don't lag.

### **B07 / B12 / B13 — `.coverage` checked in / no disk check / setup.sh leaks shell opts** (6/7 each)
Three independent setup-hygiene fixes. Remove `.coverage` from history (`git rm --cached`); add a `shutil.disk_usage(temp_dir) < threshold` preflight before render with a configurable threshold; in `setup.sh`, save `set -euo pipefail` state into a variable and restore at end so `source setup.sh` doesn't permanently mutate the user's shell.
- **Difficulty**: Trivial each · **Impact**: Low–medium each · **Risks**: None.

### **B08 — int() truncates 29.97 → 29 fps causing A/V drift** (6/7)
`__main__.py:109` does `int(max(screencast_fps))`. A 29.97fps screencast becomes 29, producing cumulative audio/video drift over a long video. Use `Fraction` from stdlib (or float passed through to ffmpeg's `-r`) and let ffmpeg handle frame-rate matching natively.
- **Difficulty**: Easy · **Impact**: High for users mixing screencasts · **Risks**: Need to verify ffmpeg accepts the rational form across our target versions.

### **B16 — --redo-slides slide-vs-step indexing confusing** (6/7)
After the v-click PR (#3), `--redo-slides 3` regenerates *all* steps for slide 3, but the per-step labels in console output show step indices and click numbers without making the redo-slides correspondence explicit. Print a one-liner reminder: `"To redo slide 3: --redo-slides 3 (regenerates all 4 click steps)"` after each Slidev run, and ensure error messages on click-count mismatch echo the slide-redo command.
- **Difficulty**: Easy · **Impact**: Medium UX · **Risks**: None.

### **B31 — --reassemble silently ignores changed --voice / TTS-only flags** (6/7)
A user re-running `--reassemble --voice newvoice.wav` gets no warning that `--voice` is silently ignored because reassemble skips the TTS phase. Detect any TTS-only flags passed alongside `--reassemble` and print `"Note: --voice ignored in reassemble mode (TTS phase is skipped)"`.
- **Difficulty**: Easy · **Impact**: Medium · **Risks**: None.

### **B32 — _parse_slide_list dedupes silently / rejects ranges** (6/7)
`__main__.py:61-72` accepts `--redo-slides 2,5,7` but silently dedupes duplicates and rejects ranges like `2-5`. Add range parsing (`2-5,8`) and warn on duplicates / empty input rather than silently dropping. Reject `5-3` (descending) with a clear error.
- **Difficulty**: Easy · **Impact**: Medium UX · **Risks**: None.

### **E40 + B36 — Drop `-shortest`, use explicit `-t` rounded to whole frame** (6/7 + 6/7)
These are the same fix. `assembler.py:57` uses `-shortest` combined with `-t`, which is redundant and can clip the trailing audio pad. Drop `-shortest` and compute `-t` as `round(duration * fps) / fps` so segment boundaries land on whole frames. Eliminates per-slide truncation that compounds over long videos.
- **Difficulty**: Easy · **Impact**: High (removes a real audio-clip bug) · **Risks**: Need to retest both image-loop and screencast segments.

### **E15 — Verify concat segments share pix_fmt / timebase before concat** (6/7)
`assembler.py:172-179` uses MPEG-TS demuxer concat which silently produces drift on mismatched codec params. Before concatenation, run `ffprobe` on every segment and assert identical pix_fmt, video timebase, and AAC profile; raise a typed error listing the mismatched segment if not. (This is also a pre-condition for cleanly fixing **B40** later.)
- **Difficulty**: Easy · **Impact**: High · **Risks**: Adds N ffprobe calls — negligible cost vs encoding.

### **B39 — get_audio_duration via ffprobe drifts vs sample-accurate length** (6/7)
`utils.py:62` reads container `format.duration`, which for AAC rounds to AOT frame boundaries. Across many slides this drifts. Compute from sample count when source is WAV (we have it) and only fall back to ffprobe for non-WAV.
- **Difficulty**: Easy · **Impact**: Medium · **Risks**: None.

### **E46 — Per-slide deterministic seed** (6/7)
Add `torch.manual_seed(slide.index)` (or `slide.slide_index * 1000 + slide.click`) inside `_generate_slide_audio`. Today, regenerating the same slide with identical params yields different audio because temperature sampling is non-deterministic. A deterministic seed makes `--redo-slides` audits useful and is also a building block for **F04** (content-hash cache).
- **Difficulty**: Trivial · **Impact**: Medium (unlocks cacheability + reproducibility) · **Risks**: Need to pair with **B34** (vary seed on interactive regen) — they're complementary, not contradictory.

### **B01 — Mutating slide.notes in place corrupts input on retry** (6/7)
`tts.py:285` writes `slide.notes = apply_pronunciations(slide.notes, ...)`. On any retry path or re-run within the same process, pronunciations get applied twice. One-line fix: rebind to a local `text` variable; pass `text` everywhere downstream instead of mutating the dataclass.
- **Difficulty**: Trivial · **Impact**: High (active correctness bug) · **Risks**: None — pure local fix.

---

## 🟡 Second Pass — Moderate Effort (a focused PR, 2–5 days each)

### **E13 — Validate input markdown size + --max-slides guardrail** (7/7)
Today, a 10,000-slide deck silently begins a multi-hour render. Add an early-validation phase: cap markdown file size (e.g. 10 MB), cap parsed slide count via configurable `--max-slides` (default 500), exit with a clear error before any expensive work. Unlocks safer use as a service or in CI.
- **Difficulty**: Moderate · **Impact**: High · **Risks**: Default cap might surprise legitimate large decks; document the override.

### **F14 — `doctor` preflight subcommand** (7/7)
`python -m deck2video doctor` prints a checklist: ffmpeg/ffprobe versions, marp-cli/slidev availability, GPU detection (CUDA/MPS/CPU), Chatterbox model cache presence, disk space, Python version. Returns non-zero on any failure. Today, these failures surface mid-pipeline with cryptic output.
- **Difficulty**: Moderate · **Impact**: High onboarding · **Risks**: None.

### **B28 — Ctrl-C leaves orphan child processes** (7/7)
No SIGINT handler exists. Killing the parent strands marp-cli/slidev/ffmpeg subprocesses and a half-loaded GPU model. Wrap `subprocess.run` in a context manager that registers a SIGINT handler to terminate children, and use `process_group` (Linux/macOS) so signal propagates. Combine with **B37**.
- **Difficulty**: Moderate · **Impact**: High · **Risks**: Need cross-platform handling (Windows lacks process groups; use `CREATE_NEW_PROCESS_GROUP`).

### **B37 — Model never moved off GPU after pipeline ends** (7/7)
`tts.py` keeps the Chatterbox model resident; long `--interactive` sessions or library use leak GPU memory until process exit. Wrap the model in a context manager (`__enter__` loads, `__exit__` calls `model.cpu(); torch.cuda.empty_cache()`). Pair naturally with **B28** (signal-driven cleanup).
- **Difficulty**: Moderate · **Impact**: High for GPU users · **Risks**: Need to retest the OOM-fallback path so cleanup doesn't fire during retries.

### **F01 — --dry-run mode** (6/7)
Parse markdown, detect format, run `expand_slides_to_steps`, resolve video paths, print the plan and the would-be output file — but skip render/TTS/assemble. Invaluable for catching click-count mismatches and missing video files before a 20-minute run.
- **Difficulty**: Moderate · **Impact**: High (CI safety + user confidence) · **Risks**: Need to thread the flag through every mode (render/reassemble/redo).

### **F11 — Dockerfile + container image** (6/7)
Ship a reproducible image bundling pinned Python, ffmpeg, marp-cli, slidev, and Chromium. Eliminates "works on my Mac" install drift, gives Linux/Windows users a path that doesn't depend on `setup.sh`. Pairs with **E08** (pinned deps) and **F14** (doctor).
- **Difficulty**: Moderate · **Impact**: High for new users · **Risks**: GPU passthrough is platform-specific; CPU-only image as v1.

### **F15 — Output integrity .sha256 + manifest.json sidecar** (6/7)
Write `output.mp4.sha256` and `output.manifest.json` (containing input md hash, git SHA, model versions, all CLI args, timestamps) alongside the MP4. Enables reproducibility audits.
- **Difficulty**: Easy-moderate · **Impact**: Medium · **Risks**: Manifest schema needs to be designed once, then versioned.

### **F16 — Configurable retry policy with backoff** (6/7)
TTS/marp/slidev/ffmpeg failures get one shot today. Add `--retries N --retry-backoff` so transient Chromium crashes, GPU hiccups, or network blips during model download self-heal. Wrap the existing `subprocess` helper.
- **Difficulty**: Moderate · **Impact**: Medium-high · **Risks**: Don't retry deterministic errors (count mismatch, file-not-found).

### **F34 — `lint` subcommand** (6/7)
`python -m deck2video lint deck.md` flags: slides with no notes, unbalanced `[click]` markers vs `v-clicks` directives, notes longer than N words, markdown links in notes, missing voice files.
- **Difficulty**: Moderate · **Impact**: Medium-high · **Risks**: Need clear, fixable error messages — half-finished lint output is worse than none.

### **B09 — Concat file unquoted relative names (defensive escape)** (6/7)
`assembler.py:169` writes `f"file '{seg.name}'\n"`. Use ffmpeg's documented escape (`'\''`) or switch to absolute paths. Latent, but a one-line defensive fix.
- **Difficulty**: Easy · **Impact**: Low (latent) · **Risks**: None.

### **B10 — TTS-failure-to-silence loses degraded list from summary** (6/7)
Track a `degraded_slides: list[int]` returned from `generate_audio_for_slides` and surface it in both the summary line and `deck2video.log`.
- **Difficulty**: Easy-moderate · **Impact**: High for diagnosis · **Risks**: None.

### **B17 — No integrity check between runs (stale audio + new images)** (6/7)
Hash the input markdown into `steps.json` on full runs; on reassemble/redo, compare and warn (with an opt-in `--force` to suppress).
- **Difficulty**: Moderate · **Impact**: High (silent correctness bug) · **Risks**: Must not block legitimate workflows where the user *intends* to mix.

### **B18 — Pronunciation overrides match substrings (no \b boundaries)** (6/7)
Default to `\b{escaped}\b`, with an opt-in `"substring": true` override for cases like punctuation-adjacent matches.
- **Difficulty**: Easy-moderate · **Impact**: High (silent quality bug) · **Risks**: Backward-compatibility for users relying on the substring behavior.

### **B21 + B22 — Pin npx versions / always pass --yes** (6/7 each)
Pin to specific versions (`@marp-team/marp-cli@4.x`, `@slidev/cli@0.50.x`) and add `--yes` to the slidev invocation.
- **Difficulty**: Easy · **Impact**: High (supply chain + CI reliability) · **Risks**: Need a refresh cadence.

### **B24 — open() calls without encoding=** (6/7)
Mechanical fix across all I/O sites — add `encoding="utf-8"`.
- **Difficulty**: Trivial · **Impact**: Medium (Windows users specifically) · **Risks**: None.

### **B34 — Interactive regens use same seed → near-identical retries** (6/7)
Pass a fresh random seed (or bump the per-slide seed deterministically) on each regen. Pair with **E46**: deterministic seed for first generation, vary on user-requested regen.
- **Difficulty**: Easy · **Impact**: Medium · **Risks**: None.

### **F04 — Content-hash TTS cache** (6/7)
Hash `(notes, voice_path, exaggeration, cfg_weight, temperature, language, model_version)`; reuse cached `audio_NNN.wav` when unchanged. Cache lives in `~/.cache/deck2video/tts/<hash>.wav`.
- **Difficulty**: Moderate · **Impact**: Very high (transforms iteration loop) · **Risks**: Cache eviction policy; ensure `--no-cache` flag for debugging; depends on E46 for determinism.

### **F28 — Disable Slidev remote asset fetches by default** (6/7)
Add `--allow-remote-assets` opt-in flag; default to blocking egress at the Chromium-launch level (Slidev exposes this via Playwright config).
- **Difficulty**: Moderate · **Impact**: High security · **Risks**: May break decks that rely on remote fonts / images — needs a clear error.

---

## 🔴 Third Pass — Most Difficult / Architectural (significant design work, 1–3 weeks each)

### **F08 — Pluggable TTS backend abstraction** (6/7)
Define a `TTSBackend` protocol with `generate(text, voice, params) → (waveform, sample_rate)` and ship implementations for Chatterbox (current), ElevenLabs, OpenAI TTS, Piper, and Coqui. Future-proofs the project against Chatterbox API changes and lets users pick by cost/quality.
- **Difficulty**: Hard · **Impact**: Very high · **Risks**: Each hosted backend brings credential management, rate limiting, and dependency surface; ship Chatterbox + Piper first.

### **F09 — Resume-from-failure via checkpoint status in steps.json** (6/7)
Extend the `steps.json` manifest to record per-step status (`pending`/`rendered`/`tts_done`/`segment_built`). On crash, the next invocation auto-resumes from the first incomplete step. Touches every phase of the pipeline.
- **Difficulty**: Hard · **Impact**: Very high (long-deck reliability) · **Risks**: Need integrity check **B17** as a prerequisite.

### **B40 — Concat -c copy + screencast mix can silently drift A/V** (6/7)
Real fix is a normalization pass: re-encode all segments to identical `-video_track_timescale 90000`, identical pix_fmt, identical AAC profile/sample rate before concat. Touches `_make_segment` and `_make_video_segment` substantially. **E15** is its diagnostic precursor.
- **Difficulty**: Hard · **Impact**: High (eliminates a class of silent A/V bugs) · **Risks**: Re-encoding screencast segments costs CPU/quality vs current copy.

---

## Recommended Sequencing

1. **First PR** (1 day): all 🟢 easy items as a single "reliability and validation pass".
2. **Second PR** (~3 days): **E13 + F14 + B28 + B37** — the 7/7 moderate group as a "preflight and lifecycle pass".
3. **Third PR** (~1 week): **F04 + E46 + B17** as a coherent "iteration speed + correctness" bundle.
4. **Future**: **F08, F09, B40** each warrant their own design discussion before code.

## Methodology Notes

- **"Borda count"** here is approval voting (yay/nay), not strict ranked-choice Borda. The user's term was used loosely.
- Items at 5/7 (one persona shy of cut) were excluded but are logged in the original review transcript as honorable mentions.
- **Security** voted nay on ~60% of items as "no security impact" — by design; their lens is hardening only. When they vote yay on a non-security item it's usually because the bug has DoS implications.
- **ML/Audio** voted nay on items orthogonal to audio quality (Dockerfile, sidecar manifests, supply-chain pinning).
- **PM** voted nay on internal refactors as invisible to users.
