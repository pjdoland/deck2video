---
marp: true
theme: default
paginate: true
style: |
  :root {
    --color-bg: #fdfdfd;
    --color-fg: #2d2d2d;
    --color-accent: #3b82f6;
    --color-accent-light: #eff6ff;
    --color-muted: #6b7280;
    font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
    letter-spacing: -0.01em;
  }
  section {
    background: var(--color-bg);
    color: var(--color-fg);
    padding: 60px 80px;
  }
  h1 {
    color: var(--color-accent);
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  h2 {
    color: var(--color-fg);
    border-bottom: 2px solid var(--color-accent);
    padding-bottom: 8px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  h3 {
    color: var(--color-muted);
    font-weight: 400;
  }
  a {
    color: var(--color-accent);
  }
  code {
    background: var(--color-accent-light);
    color: var(--color-accent);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
  }
  pre code {
    background: #1e293b;
    color: #e2e8f0;
    font-size: 1em;
  }
  pre {
    background: #1e293b;
    border-radius: 8px;
    padding: 24px;
  }
  blockquote {
    border-left: 4px solid var(--color-accent);
    padding-left: 20px;
    color: var(--color-muted);
    font-style: italic;
  }
  ul, ol {
    line-height: 1.8;
  }
  li {
    margin-bottom: 2px;
  }
  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
  }
  section.lead h1 {
    font-size: 2.8em;
    margin-bottom: 0;
  }
  section.lead h3 {
    font-size: 1.3em;
  }
  section.lead p {
    font-size: 1.2em;
    max-width: 70%;
  }
  em {
    color: var(--color-accent);
    font-style: normal;
    font-weight: 600;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# deck2video

### Narrated Video Presentations from Markdown

<!-- Hello, my name is PJ. Occasionally I have to make demo or training videos. Over the past year I've gotten increasingly frustrated with my process for producing these. So I decided to finally do something about it. -->

---

## The Problem

- Recording narrated videos is tedious
- You need a quiet room, a decent mic, and no background noise
- You stumble over words, re-record, and stumble again
- Eventually you get something usable

<!-- So what's the problem? If you want the presentation's audio to sound decent, you need a quiet room, a microphone, and no background noise. Then you record your script, stumble over a word, do another take, and another. Eventually you get something usable. -->

---

## The Real Problem

- A week later, you need to update that video
- The API changed, or you found a better way to explain something
- Re-record the whole thing, or splice in a patch that never quite matches
- So you just... don't update it

<!-- But here's the part that really got to me. A week later, you need to update that video. Maybe the API changed, or you found a better way to explain something. You either re-record the whole thing or splice in a new section that never quite matches. The tone is different, the room sounds different. I kept putting off updates because the re-recording took longer than the actual change. -->

---

<!-- _class: lead -->

# deck2video

Write slides in Markdown. Add speaker notes.
Run one command. Get a narrated video.

<!-- So in my free time I built this thing called deck2video. The idea is simple. You write your presentation in Markdown using Marp or Slidev, put your narration in the speaker notes as HTML comments, and run a single command. It auto-detects which format you're using. The tool spits out an MP4 with narration in your own voice. And if you need to change something, you can edit the text and just regenerate the MP4. And all of this can run locally on your laptop. -->

---

## Why Not ElevenLabs?

- Cloud TTS services charge per character — adds up when you regenerate often
- Your scripts and voice data go to third-party servers
- Chatterbox TTS is MIT-licensed and runs entirely on your machine
- No API keys, no usage limits, no data leaving your laptop

<!-- I looked at ElevenLabs and similar services first. They're good, but they charge per character, which adds up if you're regenerating often. And your scripts go to their servers, which complicates things when proprietary information is involved. So I went with Chatterbox TTS instead. It's MIT licensed and it runs entirely on your own machine. -->

---

## It's Just a Text File

- One `.md` file contains your slides, your script, and your content
- Plain text diffs cleanly in Git — speaker note changes are one-line diffs
- Branch, review, and merge presentations the same way you manage code
- The video is a build artifact, not the source of truth
- Feed the same Markdown into RAG pipelines, semantic search, or whatever else

<!-- One benefit of this approach is that everything lives in a single Markdown file. Slides, speaker notes, all of it. It diffs cleanly in Git, so you can review changes in a pull request. Someone fixes a factual error in a speaker note? That's a one-line diff. The MP4 is just a build artifact. You could regenerate videos in CI if you wanted to. And because it's plain text, you can feed it straight into a RAG pipeline. An LLM can index it, search it, answer questions about it. With a video or a PowerPoint you'd need to transcribe audio or extract text from images. Markdown is already plain text. -->

---

## Accessibility for Free

- Speaker notes *are* the transcript — they exist before the video does
- No separate captioning or transcription step
- WCAG compliance without any extra work

<!-- Web Content Accessibility Guidelines require text alternatives for multimedia, which usually means someone has to go back and caption the video after the fact. It's tedious, so it often doesn't happen. But with this approach you wrote the transcript first. The text alternative exists before the video does. -->

---

## How It Works

```
 .md file  ──▶  Detect  ──▶  Parse  ──▶  Render  ──▶  TTS  ──▶  Assemble  ──▶  .mp4
                  │            │           │            │            │
              Marp or      split slides  Marp CLI   Chatterbox    ffmpeg
              Slidev?      extract notes or Slidev   → WAV per    → segment
                                          → PNG       slide        → concat
```

<!-- Under the hood it's a four-stage pipeline with an automatic format detection step up front. The tool looks at your frontmatter and directive comments to figure out whether you're using Marp or Slidev. Then it parses the Markdown, renders slides as PNGs with the appropriate CLI, synthesizes audio with Chatterbox TTS, and stitches it all together with ffmpeg. If you give it a short sample of your voice, the TTS clones you. It's not perfect, but it's surprisingly good. Let me walk through each stage. -->

---

## Stage 1: Parsing

- Splits the Markdown on `---` delimiters
- First block is YAML front matter (theme, styles) -- skipped
- HTML comments are extracted as speaker notes
- Format-specific handling: Marp directive comments are filtered out; Slidev per-slide frontmatter is stripped
- Each slide becomes a `Slide` dataclass: index, body text, and notes

```python
@dataclass
class Slide:
    index: int
    body: str
    notes: str | None
```

<!-- Parsing is the boring part. Split on triple-dash delimiters, skip the YAML front matter, pull out HTML comments as speaker notes. There are separate parsers for Marp and Slidev because they handle metadata differently. Marp uses HTML comments for directives like underscore-class or underscore-paginate, so those get filtered out. Slidev uses per-slide frontmatter blocks, so those get stripped instead. Either way, what you're left with is a list of Slide dataclasses. -->

---

## Stage 2: Rendering

- Marp: calls `npx @marp-team/marp-cli` or a global `marp` install
- Slidev: calls `npx slidev export` or a global `slidev` install
- Both render the entire deck as PNG images for 1920x1080 output
- Output files are numbered: `slides.001`, `slides.002`, etc.
- A sanity check confirms the image count matches the parsed slide count

```bash
# Marp
npx @marp-team/marp-cli presentation.md \
    --images png --image-scale 2 --output slides
# Slidev
npx slidev export presentation.md --format png --output slides
```

<!-- Rendering is a subprocess call to the appropriate CLI. For Marp it's marp-cli, for Slidev it's the Slidev CLI's export command. Both check for a global install first, then fall back to npx. PNG output gets us nineteen twenty by ten eighty images. There's a sanity check: if the parser found 12 slides but the renderer only produced 11 images, we bail out. Better to stop here than produce a video where slide 7's audio plays over slide 8's image. -->

---

## Stage 3: TTS with Chatterbox

- Chatterbox TTS runs locally — no API calls, no data leaving your machine
- Voice cloning from a short WAV sample of your voice
- Sentences are grouped into chunks and concatenated into one WAV per slide
- Slides without notes get a silent WAV
- Pronunciation overrides via a JSON mapping file

```python
# Chunking: 12 sentences → 4 TTS calls instead of 12
sentence_groups = [" ".join(sentences[i:i+3])
                   for i in range(0, len(sentences), 3)]
```

<!-- This is the slow part. Chatterbox is a neural TTS model that runs on your local GPU or CPU. You give it a WAV sample of your voice and it clones you. Each chunk comes back as a tensor. We concatenate them with torch dot cat, one WAV per slide. Slides with no speaker notes get a silent WAV: just a RIFF header and zeroed samples. Oh, and if it mispronounces something, you can add a pronunciation override file. It's just a JSON file that maps words to phonetic spellings. -->

---

## Stage 4: Assembly with ffmpeg

- Each slide becomes an MPEG-TS segment: image looped for the audio duration
- Video uses `libx264` with the `stillimage` tune — almost no bitrate wasted
- Images are scaled and padded to exactly 1920 x 1080
- Audio is encoded as 192 kbps AAC
- Segments are concatenated with ffmpeg's concat demuxer into the final MP4

```
slide.png + audio.wav  ──▶  segment_001.ts
slide.png + audio.wav  ──▶  segment_002.ts
                            ...
all .ts files  ──▶  concat demuxer  ──▶  output.mp4
```

<!-- Last stage. Each slide becomes an MPEG transport stream segment. The PNG loops as video frames for the duration of that slide's audio. We use x264 with the stillimage tuning flag, so the encoder figures out that every frame is identical and the bitrate drops to almost nothing. Images get scaled and padded to nineteen twenty by ten eighty. Audio is encoded as 192 kilobits per second AAC. Then ffmpeg joins all the segments. That last step is a stream copy, no re-encoding. Takes a couple of seconds. -->

---

## Embedded Screencasts

- Any slide can include a screencast instead of a static image
- Add `<!-- video: path/to/file.mov -->` to embed a video
- The TTS narration from speaker notes still provides the audio
- The screencast's own audio track is stripped
- Duration is the longer of the narration or the video
- If the narration runs longer, the last frame of the video freezes
- Output framerate auto-detects from the highest screencast framerate

<!-- video: assets/screencast-test.mov -->

<!-- Not every slide is a static image. If you need to show a screen recording, a terminal session, or a product demo, you can embed a video file directly into a slide. Just add a video directive as an HTML comment with the path to the file. The tool strips the screencast's audio and replaces it with the TTS narration from your speaker notes, same as any other slide. If your narration runs longer than the video, the last frame freezes until the audio finishes. The output framerate automatically matches the highest framerate among your screencasts, so a sixty frames per second recording stays smooth. You can override this with the fps flag if you want. -->

---

## When Things Go Wrong

- All intermediate files land in a single temp directory
- If a stage fails, the temp directory is preserved for debugging
- On success, it is cleaned up (or kept with `--keep-temp`)
- Files are zero-padded: `audio_001.wav`, `segment_001.ts` — easy to correlate

<!-- Everything goes into one temp directory. PNGs, WAVs, transport stream segments, all of it. If a stage fails, that directory sticks around so you can see where things stopped. On success it gets cleaned up, unless you pass a keep temp flag. -->

---

## Getting Started

```bash
source setup.sh
python -m deck2video deck.md --voice my-voice.wav
```

- Works with Marp and Slidev — format is auto-detected, or force it with `--format`
- Provide a short voice sample for cloning, or omit `--voice` for the default
- GPU recommended — CPU works but is slower
- Tune with `--exaggeration`, `--cfg-weight`, `--temperature`
- Fix mispronunciations with `--pronunciations overrides.json`

<!-- For the reference sample for voice cloning, you can record five to ten minutes of yourself reading varied content. Different emotions, different pacing. I actually booked an hour at a recording studio to do this so I'd get the best quality sample possible. Then point it at your slide deck, pass in your voice file, and a couple of minutes later you get an MP4. There are flags to tune expressiveness and cloning fidelity. I'll be using this for demos and training videos, but with a for-loop and a folder of Markdown files you could easily use this to build a YouTube empire of ten thousand AI-narrated brainrot videos. I'm not going to do that… Probably. -->

---

<!-- _class: lead -->

This entire presentation was generated using *deck2video*.

No microphone. No recording session. Just a Markdown file.

<!-- So, full disclosure. This presentation was generated with deck2video. And you can almost certainly tell. The cadence is a little off, some words land weird. But it still sounds better than what I would have actually recorded, which would be full of ums and ahs, pops, and breath sounds. The whole thing is a single Markdown file. If I needed to fix something, I'd edit the text and regenerate. The real me is probably getting coffee right now. -->

---

<!-- _paginate: false -->

# Thanks

*Total time: about 4 hours*

- 1 hr recording my voice at a studio ($85)
- 2.5 hrs building the tool with Claude Code
- 30 min writing this deck in Vim

https://github.com/pjdoland/deck2video

*Questions?*

<!-- So here's the actual time breakdown. One hour at Cue Recording Studios in Falls Church, Virginia, getting a studio-quality recording of my voice. That cost eighty-five bucks. Two and a half hours with Claude Code building the entire pipeline, start to finish. And about thirty minutes writing this presentation, mostly just editing text files in Vim with Claude helping. Then I kicked off the generation and walked away. That's it. The repo is on GitHub if you want to try it. I'm happy to walk through the setup or answer questions. Thank you for your time. -->
