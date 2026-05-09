# Video assembly

## Pipeline overview

The assembly step (step 4 of 4) works in two phases:

1. **Per-slide segments.** Each slide gets its own MPEG-TS video segment, combining a visual (static image or screencast) with its audio file.
2. **Concatenation.** All segments are joined into a single MP4 using ffmpeg's concat demuxer with stream copying (no re-encoding).

## Static slide segments

For slides without a `<!-- video: ... -->` directive, the rendered PNG is looped for the duration of the audio:

```
ffmpeg -loop 1 -framerate {fps} -i slide.png -i audio.wav \
  -t {duration} -c:v libx264 -tune stillimage -pix_fmt yuv420p \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
  -c:a aac -b:a 192k [-af "adelay=...,apad=whole_dur=..."] -f mpegts segment.ts
```

Key details:

- The image is encoded as H.264 video with the `stillimage` tune (optimized for static content).
- Duration is rounded up to the nearest whole frame at the chosen `fps` so segment boundaries land on frame edges (prevents A/V drift compounding across many slides).
- When `--audio-padding` is set, `apad=whole_dur=…` extends the audio to exactly the segment duration so the trailing pad isn't clipped. (Older versions used `-shortest`, which silently truncated the trailing pad.)
- Output is MPEG-TS format for seamless concatenation.

Before concatenation, deck2video runs `ffprobe` on every segment and verifies that pixel format, codec, frame rate, dimensions, and audio channel count/sample rate all match. A mismatch aborts the run with a list of mismatched fields per segment — concatenating mismatched segments with `-c copy` would silently A/V-drift the output.

## Screencast segments

For slides with a `<!-- video: ... -->` directive, the screencast video replaces the static image:

- The screencast's **original audio track is stripped** and replaced with the TTS narration.
- The video and TTS audio are mapped separately: `0:v` (video from screencast) and `1:a` (audio from TTS).

### Frame freezing

If the TTS narration (with padding) is longer than the screencast, the last frame of the video is frozen until the audio finishes. This uses ffmpeg's `tpad` filter:

```
tpad=stop_mode=clone:stop_duration={freeze_seconds}
```

If the screencast is longer than the narration, the segment duration is set to the video length. No audio stretching occurs.

### Scaling behavior

Screencasts use a slightly different scaling rule than static slides. Static slides are always scaled to fit 1920x1080, maintaining aspect ratio, with letterboxing/pillarboxing as needed. Screencasts are only scaled *down* if larger than 1920x1080. Smaller videos keep their original resolution and are centered on a black 1920x1080 canvas. This prevents small screen recordings from being upscaled and looking blurry.

## Output resolution

All output is 1920x1080 (Full HD). Both static slides and screencasts are scaled and padded to this resolution:

- Aspect ratio is always preserved (no stretching).
- If the source is wider than 16:9, black bars appear on top and bottom (letterboxing).
- If the source is taller than 16:9, black bars appear on left and right (pillarboxing).

There is no option to change the output resolution. It's hardcoded at 1920x1080.

## Audio padding

The `--audio-padding` flag adds silence before and after each slide's audio:

```bash
python -m deck2video deck.md --audio-padding 300
```

The value is in **milliseconds**. `--audio-padding 300` adds 300ms of silence before the narration starts and 300ms after it ends, extending each slide's total duration by 600ms.

This is useful for:

- Adding a brief pause between slides so narration doesn't feel rushed.
- Giving viewers a moment to read the slide before narration begins.

The padding is applied as an ffmpeg audio delay filter (`adelay`), not by modifying the WAV files.

## Framerate

### Auto-detection

When screencasts are present, the output framerate is automatically set to the highest framerate found among all embedded videos. This is determined by querying each video with ffprobe.

Fractional rates from screencasts (e.g. `30000/1001` = 29.97) are preserved end-to-end as floats and passed to ffmpeg with six decimal digits of precision. Older versions truncated to int (29.97 → 29), causing cumulative A/V drift over long videos.

When no screencasts are present, the default framerate is **24 fps**.

### Manual override

```bash
python -m deck2video deck.md --fps 30
```

The `--fps` flag overrides auto-detection entirely. The specified framerate is used for all segments.

### Console output

The chosen framerate is always printed:

```
  Output framerate: 30 fps
```

## Codec details

| Property | Value |
|----------|-------|
| Video codec | H.264 (libx264) |
| Pixel format | yuv420p |
| Audio codec | AAC |
| Audio bitrate | 192 kbps |
| Segment format | MPEG-TS (.ts) |
| Final format | MP4 |
| Final mux | Stream copy (no re-encoding) |

The MPEG-TS intermediate format is used because it supports seamless concatenation without re-encoding. The final concat step copies the streams into an MP4 container.

## Intermediate files

During assembly, these files are created in the temp directory:

| File | Description |
|------|-------------|
| `segment_001.ts` | MPEG-TS segment for slide 1 |
| `segment_002.ts` | MPEG-TS segment for slide 2 |
| ... | One segment per slide |
| `concat.txt` | ffmpeg concat demuxer input file listing all segments |

These are cleaned up automatically on success unless `--keep-temp` is set. See [Troubleshooting](troubleshooting.md) for how to inspect them.
