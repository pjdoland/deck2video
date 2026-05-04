# Writing slides

## Slide structure

Both Marp and Slidev use `---` (horizontal rules) as slide delimiters. The first `---` block is always YAML frontmatter and is not treated as a slide.

```markdown
---
marp: true          ← frontmatter (not a slide)
---

# First Slide       ← slide 1

---

# Second Slide      ← slide 2
```

A file with no `---` delimiters will raise an error. You need at least one delimiter to separate frontmatter from the first slide.

## YAML frontmatter

The frontmatter block configures the presentation engine. The keys differ between Marp and Slidev.

### Marp frontmatter

```markdown
---
marp: true
theme: default
paginate: true
---
```

The `marp: true` key is the strongest signal for [auto-detection](format-detection.md). Other common Marp frontmatter keys: `theme`, `paginate`, `header`, `footer`, `class`, `size`, `math`, `style`, `headingDivider`.

### Slidev frontmatter

```markdown
---
transition: slide-left
drawings:
  persist: false
fonts:
  sans: Inter
---
```

Slidev-specific keys include: `transition`, `clicks`, `drawings`, `routerMode`, `aspectRatio`, `canvasWidth`, `themeConfig`, `fonts`, `favicon`, `titleTemplate`. Any of these in the frontmatter triggers Slidev auto-detection.

## Speaker notes

Speaker notes are written as HTML comments. deck2video extracts them and synthesizes speech from the text.

### Basic usage

```markdown
---

# Architecture

<!-- Our system has three main components. -->
```

### Multi-line notes

Comments can span multiple lines. The text is joined as-is:

```markdown
<!-- Our system has three main components.
Each one handles a different part of the pipeline.
Let me walk through them one by one. -->
```

### Multiple comments per slide

If a slide has multiple HTML comments (that aren't directives or video tags), their content is joined with newlines:

```markdown
# Overview

<!-- First, let's talk about the frontend. -->

Some bullet points here.

<!-- Now let's look at the backend. -->
```

This produces notes equivalent to:

```
First, let's talk about the frontend.
Now let's look at the backend.
```

### Empty comments

An empty or whitespace-only comment produces `notes=""` (an empty string), not `None`. This means the slide is treated as having notes (but with nothing to say), so it won't get the silent hold treatment. The TTS engine receives an empty string, which produces a very short audio file.

```markdown
<!-- -->       ← notes="" (empty string, not silent hold)
<!--  -->      ← notes="" (same)
```

If you want a silent hold, simply omit the comment entirely.

### Slides without notes

Slides with no HTML comments (or only directive/video comments) get `notes=None` and are rendered as silent holds. The default hold duration is 3 seconds, controlled by `--hold-duration`.

```markdown
---

# Questions?

← no comment here, so this slide is silent for 3 seconds
```

## Marp directive comments

In Marp decks, certain HTML comments are styling directives, not speaker notes. deck2video recognizes and filters these out:

```markdown
<!-- _class: lead -->
<!-- paginate: true -->
<!-- backgroundColor: #fff -->
<!-- header: My Talk -->
<!-- footer: Page %d -->
```

The full list of recognized directive keywords:

`class`, `paginate`, `header`, `footer`, `backgroundColor`, `backgroundImage`, `backgroundPosition`, `backgroundRepeat`, `backgroundSize`, `color`, `theme`, `math`, `marp`, `size`, `style`, `headingDivider`, `lang`, `title`, `description`, `author`, `image`, `keywords`, `url`

These are matched case-insensitively. The underscore prefix (`_class` vs `class`) is also handled. Directive comments are silently removed from the slide body and are not included in speaker notes.

## Slidev per-slide frontmatter

Slidev supports per-slide frontmatter: YAML key-value pairs at the very start of each slide block:

```markdown
---
layout: center
class: text-center
---

# Centered Title

<!-- This slide uses a centered layout. -->
```

deck2video's Slidev parser strips per-slide frontmatter from the slide body. It recognizes lines matching `key: value` at the start of each slide block. Unlike Marp, the Slidev parser does not filter directive comments. All HTML comments are treated as speaker notes (except video directives).

## Slidev Vue components

Slidev supports Vue components in the slide body:

```markdown
---

# Animations

<v-click>

This appears on click.

</v-click>

<v-clicks>

- Item one
- Item two
- Item three

</v-clicks>
```

deck2video does not process these components; they're passed through to the Slidev CLI for rendering. The presence of Vue components (`v-click`, `v-clicks`, `v-after`, `v-click-hide`, `Arrow`, `RenderWhen`, `SlidevVideo`) is used as a signal for [auto-detection](format-detection.md).

## Slidev click animations

When you use `v-click` or `v-clicks` for progressive reveal, you can sync narration to each animation step by adding `[click]` markers in your speaker notes. deck2video treats each marker as a step boundary: the text before the marker plays while the slide is in its initial state, the text after plays when the first animation fires, and so on.

### Writing click markers

Place `[click]` on its own line inside an HTML comment, at each point in the narration where the next animation should have already triggered:

```markdown
---

# Key Features

<v-clicks>

- Fast — sub-millisecond latency
- Reliable — 99.99% uptime SLA
- Scalable — handles millions of requests

</v-clicks>

<!--
Let's look at the three key features of our platform.
[click]
First, it's fast — with sub-millisecond latency at the 99th percentile.
[click]
Second, it's reliable — we maintain a 99.99% uptime SLA.
[click]
And third, it scales to handle millions of requests without configuration.
-->
```

This produces four video segments for the slide:
- **Initial state** (no bullets visible): "Let's look at the three key features of our platform."
- **After click 1** (first bullet visible): "First, it's fast..."
- **After click 2** (two bullets visible): "Second, it's reliable..."
- **After click 3** (all bullets visible): "And third, it scales..."

### Rules

- `[click]` must appear on its own line (leading/trailing whitespace is ignored).
- Matching is case-insensitive (`[CLICK]` and `[Click]` both work).
- A fragment with only whitespace between two markers produces a silent hold for that step.
- The number of `[click]` markers in your notes must match the number of `v-click` steps in the slide. If they don't match, Slidev will export a different number of images than expected and the pipeline will exit with an error.
- `[click]` markers in video-directive slides (`<!-- video: ... -->`) are stripped and the slide is never click-expanded.
- Marp slides are unaffected — click expansion only applies to Slidev.

### Click count mismatch

If you write three `[click]` markers but a slide has five `v-click` directives, the Slidev CLI exports five images but deck2video expects four. The pipeline exits with:

```
Error: expected 4 step(s) but slidev export produced 6 image(s).
  Hint: verify that the number of [click] markers in your speaker notes
  matches the v-click directives in each slide.
```

Count the `v-click` / `<v-clicks>` entries in the slide body and ensure you have the same number of `[click]` markers in the notes. Each item in a `<v-clicks>` list counts as one click.

### Slides with v-click but no [click] markers

If a slide has `v-click` directives but you haven't added `[click]` markers to the notes, deck2video treats it as a single step. The Slidev CLI will export multiple images (initial state + one per click) but deck2video will expect only one — causing the same count mismatch error above. Add `[click]` markers to your notes, or remove the `v-click` directives if you don't need step-by-step reveal in the video.

## Video directive

You can embed a screencast that replaces the rendered slide image. Use a `video:` directive inside an HTML comment:

```markdown
---

# Live Demo

<!-- video: assets/demo.mov -->

<!-- Watch as we deploy the service to production. -->
```

### How it works

- The `<!-- video: path -->` comment is extracted and not treated as speaker notes.
- The video file replaces the PNG that marp-cli would have rendered for this slide.
- The video's original audio track is stripped and replaced with TTS narration.
- If the narration is longer than the video, the last frame is frozen until the audio finishes.
- Video paths are resolved relative to the input markdown file's directory.

### Path resolution

```
project/
├── slides.md
└── assets/
    └── demo.mov
```

In `slides.md`:

```markdown
<!-- video: assets/demo.mov -->   ← resolved to project/assets/demo.mov
```

If the video file doesn't exist at the resolved path, the pipeline exits with an error.

### Combining video and notes

A slide can have both a video directive and speaker notes. Place them in separate comments:

```markdown
<!-- video: assets/demo.mov -->
<!-- Here we walk through the deployment process step by step. -->
```

Putting both in the same comment won't work because the video directive regex expects the entire comment content to be `video: path`. Use separate comments.

See [Video Assembly](video-assembly.md) for details on resolution, framerate, and encoding.

## Tips for TTS-friendly writing

Chatterbox works best with natural-sounding prose.

Write full sentences. Fragments and bullet-point-style notes sound awkward when spoken aloud.

Avoid abbreviations the engine might mispronounce. Use [pronunciation overrides](voice-and-tts.md#pronunciation-overrides) for technical terms like "kubectl", "nginx", or "PostgreSQL".

Watch out for sentence splitting. deck2video splits on `.`, `!`, or `?` followed by whitespace. Abbreviations like "e.g." or "Dr." will cause a split mid-sentence. Spell them out instead ("for example", not "e.g.").

Keep notes concise. Long notes mean long audio, which means long video segments. Write what you'd actually say while presenting.

Use punctuation for pacing. Periods create natural pauses. Commas create shorter ones. The TTS engine respects these.

Test with `--interactive`. Use [interactive mode](interactive-mode.md) to listen to each slide's audio and regenerate anything that sounds off.
